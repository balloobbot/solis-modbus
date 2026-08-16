"""The parts of a hybrid inverter both protocol variants share.

Everything below register 43141 is identical between the two: the same 99
registers, the same scales, the same variant gating. Only the timed
charge/discharge schedule differs, so each variant supplies that itself.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, ClassVar

from modbus_connection import ModbusConnectionError, ModbusError, ModbusTimeoutError
from modbus_connection.model import Component, ComponentGroup

from .model import UpdateReport
from .settings import (
    Commands,
    Settings,
    SinglePhaseSettings,
    ThreePhaseSettings,
)
from .telemetry import (
    AcOutput,
    Battery,
    BatteryCurrentLimits,
    Clock,
    EnergyTotals,
    ExternalMeter,
    Generation,
    Identity,
    InverterMeter,
    PvStrings,
    PvStrings3,
    PvStrings4,
    SinglePhaseAcOutput,
    SinglePhaseExternalMeter,
    Status,
    ThreePhaseAcOutput,
    ThreePhaseExternalMeter,
)
from .variants import (
    HYBRID_SERIAL_PREFIXES,
    UnknownInverterError,
    Variant,
    variant_from_serial,
)

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

# What the inverter measures: the 33xxx input map, in ascending register order,
# so a poll still walks it front to back. identity is read once at setup.
_READINGS = (
    "clock",
    "generation",
    "pv",
    "ac_output",
    "status",
    "inverter_meter",
    "battery",
    "energy",
    "battery_current_limits",
    "external_meter",
)

# What the inverter has been configured to do: the readable 43xxx holding map.
# Each variant adds its own schedule attributes. Commands are write-only, so
# they are not here either.
_SETTINGS = ("settings",)


class SolisHybrid:
    """A Solis hybrid inverter on the 33xxx/43xxx register map.

    Construct with a ``ModbusUnit``; the caller owns the connection. The first
    update reads the serial number, settles which variant this inverter is, and
    builds the components that variant serves.

    What the inverter measures and what it has been configured to do refresh
    separately — ``async_update_readings()`` and ``async_update_settings()`` —
    so a caller can poll the settings rarely, or on demand after writing one.
    ``async_update()`` does both.
    """

    commands_class: ClassVar[type[Commands]] = Commands
    mode_enum: ClassVar[type[IntEnum]]
    schedule_polled: ClassVar[tuple[str, ...]]
    """The variant's schedule attributes, polled after the shared settings."""

    def __init__(self, unit: ModbusUnit, variant: Variant | None = None) -> None:
        self._unit = unit
        self._declared_variant = variant
        self.variant: Variant | None = variant

        self.identity = Identity(unit)
        self.clock = Clock(unit)
        self.generation = Generation(unit)
        self.status = Status(unit)
        self.inverter_meter = InverterMeter(unit)
        self.battery = Battery(unit)
        self.energy = EnergyTotals(unit)
        self.commands = self.commands_class(unit)

        # Settled by the first update, from the variant.
        self.pv: PvStrings | None = None
        self.ac_output: AcOutput | None = None
        self.settings: Settings | None = None
        self.external_meter: ExternalMeter | None = None
        self.battery_current_limits: BatteryCurrentLimits | None = None

        # The poll units of each update method; None until setup has run.
        self._readings: list[str] | None = None
        self._settings: list[str] | None = None

    @property
    def storage_mode(self) -> IntEnum | None:
        """The storage mode read back from the inverter, as this variant's enum."""
        raw = self.battery.energy_storage_control_switch
        if raw is None:
            return None
        try:
            return self.mode_enum(raw)
        except ValueError:
            return None

    async def async_setup(self) -> None:
        """Read the serial number and build this inverter's components.

        Run by the first :meth:`async_update` if the caller does not run it
        itself. A failure leaves the inverter unset up, so the next update
        retries.
        """
        await self.identity.async_update()
        variant = self._declared_variant or variant_from_serial(
            self.identity.serial_number, HYBRID_SERIAL_PREFIXES
        )
        if variant is None:
            raise UnknownInverterError(
                f"unrecognised Solis serial number {self.identity.serial_number!r}"
            )
        self.variant = variant

        pv_class = PvStrings
        if variant & Variant.MPPT4:
            pv_class = PvStrings4
        elif variant & Variant.MPPT3:
            pv_class = PvStrings3
        self.pv = pv_class(self._unit)

        single_phase = bool(variant & Variant.X1)
        self.ac_output = (
            SinglePhaseAcOutput(self._unit)
            if single_phase
            else ThreePhaseAcOutput(self._unit)
        )
        self.settings = (
            SinglePhaseSettings(self._unit)
            if single_phase
            else ThreePhaseSettings(self._unit)
        )
        self.external_meter = (
            SinglePhaseExternalMeter(self._unit)
            if single_phase
            else ThreePhaseExternalMeter(self._unit)
        )
        # Only X1 inverters serve the battery current limits at 33206.
        self.battery_current_limits = (
            BatteryCurrentLimits(self._unit) if single_phase else None
        )

        # _readings doubles as the setup marker: None means setup has to run.
        self._readings = [name for name in _READINGS if getattr(self, name) is not None]
        self._settings = [
            name
            for name in (*_SETTINGS, *self.schedule_polled)
            if getattr(self, name) is not None
        ]

    async def async_update_readings(self) -> UpdateReport:
        """Refresh what the inverter measures: the 33xxx input map.

        The first call sets the inverter up.
        """
        if self._readings is None:
            await self.async_setup()
        assert self._readings is not None  # async_setup() builds it
        return await self._async_poll(self._readings, UpdateReport(set(), {}))

    async def async_update_settings(self) -> UpdateReport:
        """Refresh what is configured: the readable 43xxx holding map.

        These change when something writes them, not on their own, so a caller
        that polls them at all polls them rarely — and reads them straight after
        writing one. The first call sets the inverter up.
        """
        if self._settings is None:
            await self.async_setup()
        assert self._settings is not None  # async_setup() builds it
        return await self._async_poll(self._settings, UpdateReport(set(), {}))

    async def async_update(self) -> UpdateReport:
        """Refresh readings and settings together, in one report.

        For a caller that does not want to schedule the two apart.
        """
        report = await self.async_update_readings()
        assert self._settings is not None  # the readings poll set the inverter up
        return await self._async_poll(self._settings, report)

    async def _async_poll(self, names: list[str], report: UpdateReport) -> UpdateReport:
        """Read each component on its own, adding what happened to ``report``.

        Components are read independently, the way the integration reads its
        blocks: a component whose read fails keeps its previous values while the
        rest still refresh. Listeners fire only after every component here has
        been tried, and only on the ones that refreshed. A failure of the link
        itself raises ``ModbusConnectionError`` instead of reporting, and so
        does a timeout while ``report`` is still empty: nothing has answered
        this cycle, and walking on would pay a timeout per component to learn
        the same.
        """
        for name in names:
            component: Component = getattr(self, name)
            try:
                await component.async_update(notify=False)
            except ModbusConnectionError:
                raise
            except ModbusTimeoutError as err:
                if not report.updated and not report.failed:
                    raise  # nothing answered at all: assume the rest time out too
                report.failed[name] = err
            except ModbusError as err:
                report.failed[name] = err
            else:
                report.updated.add(name)
        for name in names:
            if name in report.updated:
                fresh: Component = getattr(self, name)
                fresh.notify()
        return report

    async def async_read_raw(self) -> dict[str, dict[int, int | bool]]:
        """Every register this inverter reads, undecoded — for diagnostics.

        Covers ``identity``, which only setup reads, as well as the polled
        components, so a dump carries the serial number an issue report needs.
        Left out is ``commands``: those registers are written, never read.
        Nothing notifies: a download is not a poll. The first call sets the
        inverter up.
        """
        if self._readings is None:
            await self.async_setup()
        assert self._readings is not None and self._settings is not None
        components: list[Component] = [
            self.identity,
            *(getattr(self, name) for name in (*self._readings, *self._settings)),
        ]
        return await ComponentGroup(self._unit, components).async_read_raw(notify=False)
