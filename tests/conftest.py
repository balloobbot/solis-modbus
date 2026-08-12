"""Fixtures: Solis inverters over modbus-connection's in-memory mock backend.

The mock backend ships with ``modbus-connection`` as an auto-registered pytest
plugin, so there is no real server or socket here — just address-keyed stores
loaded with Solis-shaped register values. The raw values below are the ones the
decode tests assert against, so each carries its decoded meaning inline.
"""

from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusConnection, MockModbusUnit

from solis_modbus import SolisHybrid3Slot, SolisHybrid6Slot, SolisLegacy3000


def u32(value: int) -> list[int]:
    """Split a 32-bit value into its two big-endian register words."""
    return [value >> 16, value & 0xFFFF]


def ascii_words(text: str) -> list[int]:
    """Pack ASCII two characters per 16-bit register."""
    if len(text) % 2:
        text += "\0"
    return [(ord(text[i]) << 8) | ord(text[i + 1]) for i in range(0, len(text), 2)]


X1_SERIAL = "110F0123456789AB"  # prefix 110F -> Hybrid Gen5 5kW, single phase
X3_MPPT4_SERIAL = "1033050123456789"  # prefix 103305 -> Gen6 8kW HV, four strings
LEGACY_X1_SERIAL = "50310512"  # prefix 503105 -> legacy Hybrid Gen5 5kW

# The shared 33xxx input map. Values chosen so every scale is observable.
INPUT: dict[int, int | list[int]] = {
    33004: ascii_words(X1_SERIAL),
    33022: [25, 8, 12, 14, 30, 45],  # RTC -> 2025-08-12 14:30:45
    33029: [0, 12345],  # generation total -> 12345 kWh
    33031: [0, 300],  # this month
    33033: [0, 410],  # last month
    33035: 87,  # today -> 8.7 kWh
    33036: 152,  # yesterday -> 15.2 kWh
    33037: [0, 5000],  # this year
    33039: [0, 4200],  # last year
    33049: 3201,  # pv 1 voltage -> 320.1 V
    33050: 85,  # pv 1 current -> 8.5 A
    33051: 3150,  # pv 2 voltage -> 315.0 V
    33052: 71,  # pv 2 current -> 7.1 A
    33053: 2900,  # pv 3 voltage -> 290.0 V (MPPT3/MPPT4 only)
    33054: 60,  # pv 3 current -> 6.0 A
    33055: 2800,  # pv 4 voltage -> 280.0 V (MPPT4 only)
    33056: 55,  # pv 4 current -> 5.5 A
    33057: [0, 4600],  # pv total power -> 4600 W
    33073: 2312,  # phase 1 / inverter voltage -> 231.2 V
    33074: 2301,  # phase 2 voltage -> 230.1 V (X3)
    33075: 2298,  # phase 3 voltage -> 229.8 V (X3)
    33076: 143,  # phase 1 / inverter current -> 14.3 A
    33077: 138,  # phase 2 current (X3)
    33078: 141,  # phase 3 current (X3)
    33079: [0, 3300],  # active power -> 3300 W
    33081: [0xFFFF, 0xFF9C],  # reactive power -> -100 var (signed)
    33083: [0, 3400],  # apparent power -> 3400 VA
    33093: 415,  # inverter temperature -> 41.5 °C
    33094: 5001,  # inverter frequency -> 50.01 Hz
    33095: 3,  # inverter status -> GENERATING
    33126: u32(98765),  # meter total active power -> 987.65 kWh
    33128: 2305,  # meter voltage -> 230.5 V
    33129: 1234,  # meter current -> 12.34 A
    33130: [0xFFFF, 0xFC18],  # meter active power -> -1000 W (export)
    33132: 35,  # storage mode word (SELF_USE on the three-slot firmware)
    33133: 512,  # battery voltage -> 51.2 V
    33134: 0xFFCE,  # battery current -> -5.0 A (signed)
    33135: 1,  # charge direction -> discharging
    33139: 78,  # battery SoC -> 78 %
    33140: 99,  # battery SoH -> 99 %
    33141: 5123,  # BMS battery voltage -> 51.23 V
    33142: 0xFFCE,  # BMS battery current -> -5.0 A
    33143: 900,  # BMS charge limit -> 90.0 A
    33144: 950,  # BMS discharge limit -> 95.0 A
    33147: 1200,  # house load -> 1200 W
    33148: 300,  # bypass load -> 300 W
    33149: [0xFFFF, 0xFF06],  # battery power -> -250 W
    33161: [0, 3000],  # total battery charge -> 3000 kWh
    33163: 45,  # battery charge today -> 4.5 kWh
    33164: 52,  # battery charge yesterday -> 5.2 kWh
    33165: [0, 2800],  # total battery discharge
    33167: 41,  # battery discharge today -> 4.1 kWh
    33168: 48,  # battery discharge yesterday -> 4.8 kWh
    33169: [0, 1500],  # grid import total
    33171: 22,  # grid import today -> 2.2 kWh
    33172: 31,  # grid import yesterday -> 3.1 kWh
    33173: [0, 6000],  # grid export total
    33175: 88,  # grid export today -> 8.8 kWh
    33176: 91,  # grid export yesterday -> 9.1 kWh
    33177: [0, 7200],  # house load total
    33179: 130,  # house load today -> 13.0 kWh
    33180: 125,  # house load yesterday -> 12.5 kWh
    33206: 620,  # battery charge current limit -> 62.0 A (X1 only)
    33207: 640,  # battery discharge current limit -> 64.0 A (X1 only)
    33251: 2310,  # meter AC voltage / L1 -> 231.0 V
    33252: 1500,  # meter AC current / L1 -> 15.00 A
    33253: 2295,  # meter AC voltage L2 (X3)
    33254: 1490,  # meter AC current L2 (X3)
    33255: 2302,  # meter AC voltage L3 (X3)
    33256: 1495,  # meter AC current L3 (X3)
    33257: [0, 1100],  # meter active power L1 -> 1.1 kW (X3)
    33259: [0, 1050],  # meter active power L2 (X3)
    33261: [0, 1080],  # meter active power L3 (X3)
    33263: [0, 3230],  # meter active power total -> 3.23 kW
    33265: [0, 120],  # meter reactive power / L1 -> 120 var
    33267: [0, 110],  # meter reactive power L2 (X3)
    33269: [0, 115],  # meter reactive power L3 (X3)
    33271: [0, 345],  # meter reactive power total
    33273: [0, 3400],  # meter apparent power / L1
    33275: [0, 3300],  # meter apparent power L2 (X3)
    33277: [0, 3350],  # meter apparent power L3 (X3)
    33279: [0, 10050],  # meter apparent power total
    33281: 98,  # meter power factor -> 0.98
    33282: 4999,  # meter grid frequency -> 49.99 Hz
    33283: [0, 45000],  # meter grid import total -> 450.0 kWh
    33285: [0, 67000],  # meter grid export total -> 670.0 kWh
}

# The shared 43xxx holding map, up to where the two variants diverge.
HOLDING_COMMON: dict[int, int | list[int]] = {
    43007: 190,  # power switch -> ON
    43011: 20,  # battery minimum SoC -> 20 %
    43018: 15,  # force charge SoC -> 15 %
    43024: 30,  # backup mode SoC -> 30 %
    43073: 16,  # backflow switch -> ON (X1) / ON & balanced (X3)
    43074: 50,  # backflow power -> 5000 W
    43116: 600,  # battery charge/discharge current -> 60.0 A
    43117: 550,  # battery charge current -> 55.0 A
    43118: 580,  # battery discharge current -> 58.0 A
}

# Three combined charge/discharge slots, at 43143 + 10 * n.
HOLDING_3_SLOT: dict[int, int | list[int]] = {
    43141: 500,  # timed charge current -> 50.0 A
    43142: 520,  # timed discharge current -> 52.0 A
    43143: [1, 30, 5, 45, 17, 0, 20, 15],  # slot 1 charge 01:30-05:45, dis 17:00-20:15
    43153: [2, 0, 4, 30, 18, 10, 19, 50],  # slot 2
    43163: [3, 15, 6, 0, 21, 5, 22, 40],  # slot 3
    43249: 0b1010_0101,  # special settings bits 0, 2, 5, 7
}

# Six charge slots at 43708 + 7 * n, six discharge slots at 43750 + 7 * n.
HOLDING_6_SLOT: dict[int, int | list[int]] = {
    43707: 0b0000_0100_0001,  # charge slot 1 and discharge slot 1 enabled
    **{
        43708 + 7 * n: [90 - n, 500 + n, 520 + n, 1 + n, 30, 5 + n, 45]
        for n in range(6)
    },
    **{
        43750 + 7 * n: [20 + n, 400 + n, 510 + n, 17 + n, 0, 18 + n, 30]
        for n in range(6)
    },
}

LEGACY_INPUT: dict[int, int | list[int]] = {
    3005: [0, 3300],  # active power
    3007: [0, 4600],  # PV total power -> 4600 W
    3009: [0, 12345],  # generation total
    3011: [0, 300],
    3013: [0, 410],
    3015: 87,  # today -> 8.7 kWh
    3016: 152,
    3017: [0, 5000],
    3019: [0, 4200],
    3022: 3201,  # pv 1 voltage -> 320.1 V
    3023: 85,
    3024: 3150,
    3025: 71,
    3026: 2900,
    3027: 60,
    3028: 2800,
    3029: 55,
    3034: 2312,  # inverter / R voltage -> 231.2 V
    3035: 2301,
    3036: 2298,
    3037: 143,  # inverter / R current -> 14.3 A
    3038: 138,
    3039: 141,
    3042: 415,  # inverter temperature -> 41.5 °C
    3043: 5001,  # grid frequency -> 50.01 Hz
    3061: ascii_words(LEGACY_X1_SERIAL),
}


def seed_hybrid(
    unit: MockModbusUnit, serial: str, *holding: dict[int, int | list[int]]
) -> None:
    """Load the shared input map plus the given holding blocks."""
    for address, value in INPUT.items():
        unit.input[address] = value
    unit.input[33004] = ascii_words(serial)
    for store in (HOLDING_COMMON, *holding):
        for address, value in store.items():
            unit.holding[address] = value


def build_hybrid_3_slot(
    serial: str = X1_SERIAL,
) -> tuple[MockModbusUnit, SolisHybrid3Slot]:
    """A three-slot inverter on a unit of its own, seeded and ready to poll."""
    unit = MockModbusConnection().for_unit(1)
    seed_hybrid(unit, serial, HOLDING_3_SLOT)
    return unit, SolisHybrid3Slot(unit)


def build_hybrid_6_slot(
    serial: str = X1_SERIAL,
) -> tuple[MockModbusUnit, SolisHybrid6Slot]:
    """A six-slot inverter on a unit of its own."""
    unit = MockModbusConnection().for_unit(1)
    seed_hybrid(unit, serial, HOLDING_6_SLOT)
    unit.input[33132] = 33  # SELF_USE on the six-slot firmware
    return unit, SolisHybrid6Slot(unit)


def build_legacy() -> tuple[MockModbusUnit, SolisLegacy3000]:
    """A legacy inverter on the 3000-block input map."""
    unit = MockModbusConnection().for_unit(1)
    for address, value in LEGACY_INPUT.items():
        unit.input[address] = value
    return unit, SolisLegacy3000(unit)


@pytest.fixture
def inverter_3_slot() -> SolisHybrid3Slot:
    """An X1 inverter on the three-slot protocol."""
    return build_hybrid_3_slot()[1]


@pytest.fixture
def inverter_3_slot_x3() -> SolisHybrid3Slot:
    """An X3 inverter with four PV strings, on the three-slot protocol."""
    return build_hybrid_3_slot(X3_MPPT4_SERIAL)[1]


@pytest.fixture
def inverter_6_slot() -> SolisHybrid6Slot:
    """An X1 inverter on the six-slot protocol."""
    return build_hybrid_6_slot()[1]


@pytest.fixture
def legacy_inverter() -> SolisLegacy3000:
    """A legacy X1 inverter on the 3000-block input map."""
    return build_legacy()[1]


__all__ = [
    "INPUT",
    "HOLDING_COMMON",
    "HOLDING_3_SLOT",
    "HOLDING_6_SLOT",
    "LEGACY_INPUT",
    "LEGACY_X1_SERIAL",
    "X1_SERIAL",
    "X3_MPPT4_SERIAL",
    "ascii_words",
    "build_hybrid_3_slot",
    "build_hybrid_6_slot",
    "build_legacy",
    "u32",
    "seed_hybrid",
]
