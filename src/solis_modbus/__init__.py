"""Read and control Ginlong Solis inverters over Modbus.

Three protocol variants, one per register map the inverters speak:

- ``SolisHybrid3Slot`` — the 33xxx/43xxx hybrid map with three combined
  charge/discharge slots at 43143.
- ``SolisHybrid6Slot`` — the same map with six charge and six discharge slots
  at 43707.
- ``SolisLegacy3000`` — the older read-only input map in the 3000 block.

Each takes a ``modbus_connection.ModbusUnit``; the caller owns the connection.
ASCII framing over TCP is not supported.
"""

from __future__ import annotations

from .enums import (
    BackflowSwitchX1,
    BackflowSwitchX3,
    BatteryOverride,
    EnergyStorageMode3Slot,
    EnergyStorageMode6Slot,
    InverterStatus,
    PowerSwitch,
)
from .hybrid import SolisHybrid
from .hybrid_3_slot import SolisHybrid3Slot
from .hybrid_6_slot import SolisHybrid6Slot
from .legacy_3000 import SolisLegacy3000
from .variants import (
    HYBRID_SERIAL_PREFIXES,
    LEGACY_SERIAL_PREFIXES,
    UnknownInverterError,
    Variant,
    variant_from_serial,
)

__all__ = [
    "HYBRID_SERIAL_PREFIXES",
    "LEGACY_SERIAL_PREFIXES",
    "BackflowSwitchX1",
    "BackflowSwitchX3",
    "BatteryOverride",
    "EnergyStorageMode3Slot",
    "EnergyStorageMode6Slot",
    "InverterStatus",
    "PowerSwitch",
    "SolisHybrid",
    "SolisHybrid3Slot",
    "SolisHybrid6Slot",
    "SolisLegacy3000",
    "UnknownInverterError",
    "Variant",
    "variant_from_serial",
]
