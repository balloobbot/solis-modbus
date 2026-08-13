"""A hybrid inverter with three combined charge/discharge slots.

The map the integration's ``plugin_solis`` speaks: the shared 33xxx/43xxx
registers, three timed slots at 43143, and the special-settings word at 43249.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from modbus_connection.model import enum

from .enums import EnergyStorageMode3Slot
from .hybrid import SolisHybrid
from .schedule_3_slot import Schedule, SpecialSettings
from .settings import Commands

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

    from .variants import Variant


class Commands3Slot(Commands):
    """Write-only commands, with the storage modes this firmware accepts."""

    energy_storage_control_switch = enum(43110, EnergyStorageMode3Slot, writable=True)


class SolisHybrid3Slot(SolisHybrid):
    """A Solis hybrid inverter with three combined charge/discharge slots."""

    commands_class: ClassVar[type[Commands]] = Commands3Slot
    mode_enum = EnergyStorageMode3Slot
    schedule_polled: ClassVar[tuple[str, ...]] = ("schedule", "special_settings")

    def __init__(self, unit: ModbusUnit, variant: Variant | None = None) -> None:
        super().__init__(unit, variant)
        self.schedule = Schedule(unit)
        self.special_settings = SpecialSettings(unit)
