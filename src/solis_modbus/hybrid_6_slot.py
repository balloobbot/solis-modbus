"""A hybrid inverter with six charge and six discharge slots.

The map the integration's ``plugin_solis_fb00`` speaks: the shared 33xxx/43xxx
registers, and the extended schedule at 43707. This firmware has no
special-settings word at 43249.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from modbus_connection.model import Component, enum

from .enums import EnergyStorageMode6Slot
from .hybrid import SolisHybrid
from .schedule_6_slot import Schedule
from .settings import Commands

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

    from .variants import Variant


class Commands6Slot(Commands):
    """Write-only commands, with the storage modes this firmware accepts."""

    energy_storage_control_switch = enum(43110, EnergyStorageMode6Slot, writable=True)


class SolisHybrid6Slot(SolisHybrid):
    """A Solis hybrid inverter with six charge and six discharge slots."""

    commands_class: ClassVar[type[Commands]] = Commands6Slot
    mode_enum = EnergyStorageMode6Slot

    def __init__(self, unit: ModbusUnit, variant: Variant | None = None) -> None:
        super().__init__(unit, variant)
        self.schedule = Schedule(unit)

    def schedule_components(self) -> list[Component]:
        return [self.schedule]
