"""Deriving an inverter's variant from its serial number."""

from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusConnection

from solis_modbus import (
    HYBRID_SERIAL_PREFIXES,
    LEGACY_SERIAL_PREFIXES,
    SolisHybrid3Slot,
    SolisLegacy3000,
    UnknownInverterError,
    Variant,
    variant_from_serial,
)

from .conftest import ascii_words, seed_hybrid


@pytest.mark.parametrize(
    ("serial", "expected"),
    [
        ("110F0000", Variant.X1),
        ("1031abcd", Variant.X1),
        ("1053abcd", Variant.X3 | Variant.MPPT3),
        ("103305xx", Variant.X3 | Variant.MPPT4),
        ("103330xx", Variant.X3),
        ("160F4000", Variant.X1),
        ("nonsense", None),
    ],
)
def test_hybrid_serial_prefixes(serial: str, expected: Variant | None) -> None:
    assert variant_from_serial(serial, HYBRID_SERIAL_PREFIXES) == expected


def test_longest_prefix_wins() -> None:
    """160F is not a prefix on its own; 160F3/4/5 are, and must not collide."""
    assert variant_from_serial("160F5abc", HYBRID_SERIAL_PREFIXES) == Variant.X1
    assert variant_from_serial("160F9abc", HYBRID_SERIAL_PREFIXES) is None


def test_legacy_serial_prefixes() -> None:
    assert variant_from_serial("50310512", LEGACY_SERIAL_PREFIXES) == Variant.X1
    assert variant_from_serial("110CA221", LEGACY_SERIAL_PREFIXES) == Variant.X3
    # A hybrid serial is not a legacy one: the two maps are keyed differently.
    assert variant_from_serial("110F0000", LEGACY_SERIAL_PREFIXES) is None


def test_no_serial_is_no_variant() -> None:
    assert variant_from_serial(None, HYBRID_SERIAL_PREFIXES) is None
    assert variant_from_serial("", HYBRID_SERIAL_PREFIXES) is None


def test_pv_string_count() -> None:
    assert Variant.X1.pv_strings == 2
    assert (Variant.X3 | Variant.MPPT3).pv_strings == 3
    assert (Variant.X3 | Variant.MPPT4).pv_strings == 4


async def test_unknown_serial_raises() -> None:
    unit = MockModbusConnection().for_unit(1)
    seed_hybrid(unit, "ZZZZ000000000000")
    with pytest.raises(UnknownInverterError, match="ZZZZ"):
        await SolisHybrid3Slot(unit).async_update()


async def test_declared_variant_overrides_an_unknown_serial() -> None:
    """A model the prefix table has not caught up with is still usable."""
    unit = MockModbusConnection().for_unit(1)
    seed_hybrid(unit, "ZZZZ000000000000")
    device = SolisHybrid3Slot(unit, variant=Variant.X3 | Variant.MPPT4)
    await device.async_update()
    assert device.variant == Variant.X3 | Variant.MPPT4
    assert device.pv is not None
    assert device.pv.pv_voltage_4 is not None  # type: ignore[attr-defined]


async def test_unknown_legacy_serial_raises() -> None:
    unit = MockModbusConnection().for_unit(1)
    unit.input[3061] = ascii_words("99999999")
    with pytest.raises(UnknownInverterError):
        await SolisLegacy3000(unit).async_update()
