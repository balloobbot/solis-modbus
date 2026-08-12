"""The parts of a hybrid inverter both protocol variants share.

Everything below register 43141 is identical between the two: the same 99
registers, the same scales, the same variant gating. Only the timed
charge/discharge schedule differs, so each variant supplies that itself.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, ClassVar

from modbus_connection.model import Component, ComponentGroup

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


class SolisHybrid:
    """A Solis hybrid inverter on the 33xxx/43xxx register map.

    Construct with a ``ModbusUnit``; the caller owns the connection. The first
    ``async_update()`` reads the serial number, settles which variant this
    inverter is, and builds the components that variant serves.
    """

    commands_class: ClassVar[type[Commands]] = Commands
    mode_enum: ClassVar[type[IntEnum]]

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

        self._group: ComponentGroup | None = None

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

    def schedule_components(self) -> list[Component]:
        """The variant's schedule components, polled with everything else."""
        raise NotImplementedError

    async def async_setup(self) -> None:
        """Read the serial number and build this inverter's components."""
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

        self._group = ComponentGroup(self._unit, self.polled_components)

    @property
    def polled_components(self) -> list[Component]:
        """Every component ``async_update()`` refreshes."""
        components: list[Component | None] = [
            self.clock,
            self.generation,
            self.pv,
            self.ac_output,
            self.status,
            self.inverter_meter,
            self.battery,
            self.battery_current_limits,
            self.energy,
            self.external_meter,
            self.settings,
            *self.schedule_components(),
        ]
        return [c for c in components if c is not None]

    async def async_update(self) -> None:
        """Refresh every polled component; the first call sets the inverter up."""
        if self._group is None:
            await self.async_setup()
        assert self._group is not None
        await self._group.async_update()
