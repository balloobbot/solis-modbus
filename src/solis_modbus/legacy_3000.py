"""The older Solis map: read-only input registers in the 3000 block.

The integration's ``plugin_solis_old``. Nothing here is writable and there is
no battery, meter or scheduling data — it is generation and AC monitoring only.
The serial number lives at 3061 (four registers) instead of 33004.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from modbus_connection import ModbusConnectionError, ModbusError
from modbus_connection.model import (
    Component,
    ComponentGroup,
    gauge,
    string,
    uint32,
)

from .model import UpdateReport
from .variants import (
    LEGACY_SERIAL_PREFIXES,
    UnknownInverterError,
    Variant,
    variant_from_serial,
)

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

MAX_READ_SPAN = 48
"""Registers per read. The integration caps a legacy Solis block at 48."""

# Every component attribute a poll refreshes, in read order. identity is read
# once at setup and stays out.
_POLLED = ("generation", "pv", "ac_output")


class LegacyInput(Component):
    """Base for the read-only 3000 input map."""

    register_space = "input"
    max_span = MAX_READ_SPAN


class LegacyIdentity(LegacyInput):
    """The inverter's serial number, four registers of ASCII."""

    serial_number = string(3061, 4)


class LegacyGeneration(LegacyInput):
    """Output power and the generation counters."""

    activepower = uint32(3005, unit="kW")
    """As the integration labels it; the neighbouring PV total is in W."""

    pv_total_power = uint32(3007, unit="W")
    power_generation_total = uint32(3009, unit="kWh")
    power_generation_this_month = uint32(3011, unit="kWh")
    power_generation_last_month = uint32(3013, unit="kWh")
    power_generation_today = gauge(3015, 0.1, signed=False, unit="kWh")
    power_generation_yesterday = gauge(3016, 0.1, signed=False, unit="kWh")
    power_generation_this_year = uint32(3017, unit="kWh")
    power_generation_last_year = uint32(3019, unit="kWh")


class LegacyPvStrings(LegacyInput):
    """Four PV strings. The integration declares all four for every model."""

    pv_voltage_1 = gauge(3022, 0.1, signed=False, unit="V")
    pv_current_1 = gauge(3023, 0.1, signed=False, unit="A")
    pv_voltage_2 = gauge(3024, 0.1, signed=False, unit="V")
    pv_current_2 = gauge(3025, 0.1, signed=False, unit="A")
    pv_voltage_3 = gauge(3026, 0.1, signed=False, unit="V")
    pv_current_3 = gauge(3027, 0.1, signed=False, unit="A")
    pv_voltage_4 = gauge(3028, 0.1, signed=False, unit="V")
    pv_current_4 = gauge(3029, 0.1, signed=False, unit="A")


class LegacyAcOutput(LegacyInput):
    """Inverter temperature and grid frequency; phases are per variant."""

    inverter_temperature = gauge(3042, 0.1, signed=False, unit="°C")
    grid_frequency = gauge(3043, 0.01, signed=False, unit="Hz")


class LegacySinglePhaseAcOutput(LegacyAcOutput):
    """AC output of an X1 (single-phase) legacy inverter."""

    inverter_voltage = gauge(3034, 0.1, signed=False, unit="V")
    inverter_current = gauge(3037, 0.1, signed=False, unit="A")


class LegacyThreePhaseAcOutput(LegacyAcOutput):
    """AC output of an X3 (three-phase) legacy inverter."""

    grid_voltage_r = gauge(3034, 0.1, signed=False, unit="V")
    grid_voltage_s = gauge(3035, 0.1, signed=False, unit="V")
    grid_voltage_t = gauge(3036, 0.1, signed=False, unit="V")
    grid_current_r = gauge(3037, 0.1, signed=False, unit="A")
    grid_current_s = gauge(3038, 0.1, signed=False, unit="A")
    grid_current_t = gauge(3039, 0.1, signed=False, unit="A")


class SolisLegacy3000:
    """A Solis inverter that only serves the older 3000-block input map."""

    def __init__(self, unit: ModbusUnit, variant: Variant | None = None) -> None:
        self._unit = unit
        self._declared_variant = variant
        self.variant: Variant | None = variant

        self.identity = LegacyIdentity(unit)
        self.generation = LegacyGeneration(unit)
        self.pv = LegacyPvStrings(unit)

        self.ac_output: LegacyAcOutput | None = None
        self._polled: list[str] | None = None

    async def async_setup(self) -> None:
        """Read the serial number and settle whether this is X1 or X3.

        Run by the first :meth:`async_update` if the caller does not run it
        itself. A failure leaves the inverter unset up, so the next update
        retries.
        """
        await self.identity.async_update()
        variant = self._declared_variant or variant_from_serial(
            self.identity.serial_number, LEGACY_SERIAL_PREFIXES
        )
        if variant is None:
            raise UnknownInverterError(
                f"unrecognised Solis serial number {self.identity.serial_number!r}"
            )
        self.variant = variant
        self.ac_output = (
            LegacySinglePhaseAcOutput(self._unit)
            if variant & Variant.X1
            else LegacyThreePhaseAcOutput(self._unit)
        )
        # Doubles as the setup marker: None means setup still has to run.
        self._polled = [name for name in _POLLED if getattr(self, name) is not None]

    async def async_update(self) -> UpdateReport:
        """Refresh every polled component, one at a time.

        Same contract as :meth:`solis_modbus.SolisHybrid.async_update`: a failed
        component keeps its previous values and is reported, listeners fire after
        the whole poll and only for refreshed components, and a dead link raises
        ``ModbusConnectionError``.
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

    async def async_read_raw(self) -> dict[str, dict[int, int | bool]]:
        """Every register this inverter reads, undecoded — for diagnostics.

        Covers ``identity``, which only setup reads, as well as the polled
        components. The first call sets the inverter up.
        """
        if self._polled is None:
            await self.async_setup()
        assert self._polled is not None  # async_setup() builds it
        components: list[Component] = [
            self.identity,
            *(getattr(self, name) for name in self._polled),
        ]
        return await ComponentGroup(self._unit, components).async_read_raw()
