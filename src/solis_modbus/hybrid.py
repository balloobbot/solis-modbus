"""The parts of a hybrid inverter both protocol variants share.

Everything below register 43141 is identical between the two: the same 99
registers, the same scales, the same variant gating. Only the timed
charge/discharge schedule differs, so each variant supplies that itself.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, ClassVar

from modbus_connection import ModbusConnectionError, ModbusError
from modbus_connection.model import Component

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

# Every shared component attribute a poll may refresh, in read order — which is
# ascending register order, so a poll still walks the map front to back. Each
# variant adds its own schedule attributes; identity is read once at setup and
# commands are write-only, so neither is here.
_POLLED = (
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
    "settings",
)


class SolisHybrid:
    """A Solis hybrid inverter on the 33xxx/43xxx register map.

    Construct with a ``ModbusUnit``; the caller owns the connection. The first
    ``async_update()`` reads the serial number, settles which variant this
    inverter is, and builds the components that variant serves.
    """

    commands_class: ClassVar[type[Commands]] = Commands
    mode_enum: ClassVar[type[IntEnum]]
    schedule_polled: ClassVar[tuple[str, ...]]
    """The variant's schedule attributes, polled after the shared ones."""

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

        self._polled: list[str] | None = None

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

        # Doubles as the setup marker: None means setup still has to run.
        self._polled = [
            name
            for name in (*_POLLED, *self.schedule_polled)
            if getattr(self, name) is not None
        ]

    async def async_update(self) -> UpdateReport:
        """Refresh every component this variant serves, one at a time.

        Components are read independently, the way the integration reads its
        blocks: a component whose read fails keeps its previous values while the
        rest still refresh. Listeners fire only after every component has been
        tried, and only on the ones that refreshed. A failure of the link itself
        raises ``ModbusConnectionError`` instead of reporting.
        """
        if self._polled is None:
            await self.async_setup()
        assert self._polled is not None  # async_setup() builds it
        updated: set[str] = set()
        failed: dict[str, ModbusError] = {}
        for name in self._polled:
            component: Component = getattr(self, name)
            try:
                await component.async_update(notify=False)
            except ModbusConnectionError:
                raise
            except ModbusError as err:
                failed[name] = err
            else:
                updated.add(name)
        for name in updated:
            fresh: Component = getattr(self, name)
            fresh.notify()
        return UpdateReport(updated, failed)
