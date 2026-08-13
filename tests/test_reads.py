"""What a poll actually asks the inverter for.

Each pattern is checked for correctness first — every declared field is covered,
no block is wider than the inverter's limit, no block reaches registers this
variant does not serve — and only then pinned to a shape.
"""

from __future__ import annotations

from modbus_connection.mock import MockModbusUnit
from modbus_connection.model import Component

from solis_modbus import UpdateReport, Variant
from solis_modbus.legacy_3000 import MAX_READ_SPAN as LEGACY_MAX_SPAN
from solis_modbus.telemetry import MAX_READ_SPAN

from .conftest import build_hybrid_3_slot, build_hybrid_6_slot, build_legacy


def polled(device: object, report: UpdateReport) -> list[Component]:
    """The components the poll refreshed, by the report's attribute names."""
    return [getattr(device, name) for name in report.updated]


def field_addresses(components: list[Component]) -> set[tuple[str, int]]:
    """Every (space, address) the components' fields occupy, instances included."""
    addresses: set[tuple[str, int]] = set()

    def walk(component: Component) -> None:
        space = component.register_space
        for field in component.declared_fields.values():
            base = field.address + component._base_offset + component._instance_offset
            for offset in range(field.count):
                addresses.add((space, base + offset))
        for group in component._groups.values():
            for instance in group:
                walk(instance)

    for component in components:
        walk(component)
    return addresses


def read_addresses(unit: MockModbusUnit) -> set[tuple[str, int]]:
    """Every (space, address) the recorded reads covered."""
    return {
        (event.register_type, event.address + offset)
        for event in unit.read_events
        for offset in range(event.count)
    }


async def test_three_slot_x1_poll_is_correct() -> None:
    unit, device = build_hybrid_3_slot()
    report = await device.async_update()

    covered = read_addresses(unit)
    assert field_addresses(polled(device, report)) <= covered
    assert all(event.count <= MAX_READ_SPAN for event in unit.read_events)
    assert {event.register_type for event in unit.read_events} == {"input", "holding"}

    # An X1 inverter has two PV strings and its own battery current limits.
    assert ("input", 33206) in covered
    fields = field_addresses(polled(device, report))
    assert ("input", 33053) not in fields  # string 3 belongs to MPPT3/MPPT4
    assert ("input", 33055) not in fields  # string 4 belongs to MPPT4
    # The strings 1-2 block still spans them, as the integration's does: the
    # planner bridges the four-register hole rather than paying a second read.
    assert ("input", 33053) in covered


async def test_three_slot_x1_poll_shape() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    unit.read_events.clear()
    await device.async_update()  # a steady-state poll: setup is already done

    blocks = [(e.register_type, e.address, e.count) for e in unit.read_events]
    assert blocks == [
        ("input", 33022, 6),  # clock
        ("input", 33029, 12),  # generation counters
        ("input", 33049, 10),  # PV strings 1-2 and the total
        ("input", 33073, 12),  # AC output
        ("input", 33093, 3),  # temperature, frequency, status
        # The inverter meter and the battery are separate components, so they
        # are separate reads: pooling used to merge them into one 33126+25.
        # Same 25 registers either way, one request more, one failure domain
        # each — a refused battery block no longer blanks the meter.
        ("input", 33126, 6),  # inverter meter, exactly 33126-33131
        ("input", 33132, 19),  # battery, 33132-33150, bridging its two holes
        ("input", 33161, 20),  # energy counters
        ("input", 33206, 2),  # battery current limits (X1 only)
        ("input", 33251, 36),  # external meter
        ("holding", 43007, 18),  # settings
        ("holding", 43073, 2),  # export limit switch and power
        ("holding", 43116, 3),  # battery currents
        ("holding", 43141, 30),  # the three time slots
        ("holding", 43249, 1),  # special settings
    ]


async def test_three_slot_x3_mppt4_poll_is_correct() -> None:
    unit, device = build_hybrid_3_slot("1033050123456789")
    report = await device.async_update()
    assert device.variant == Variant.X3 | Variant.MPPT4

    covered = read_addresses(unit)
    assert field_addresses(polled(device, report)) <= covered
    assert all(event.count <= MAX_READ_SPAN for event in unit.read_events)

    # Four PV strings, three phases, and no X1-only battery current limits.
    assert ("input", 33055) in covered
    assert ("input", 33078) in covered  # phase 3 current
    assert ("input", 33206) not in covered
    assert ("input", 33207) not in covered


async def test_six_slot_poll_is_correct() -> None:
    unit, device = build_hybrid_6_slot()
    report = await device.async_update()

    covered = read_addresses(unit)
    assert field_addresses(polled(device, report)) <= covered
    assert all(event.count <= MAX_READ_SPAN for event in unit.read_events)

    # The extended schedule is read; the three-slot block is not on this firmware.
    assert ("holding", 43707) in covered
    assert ("holding", 43791) in covered
    assert ("holding", 43143) not in covered
    assert ("holding", 43249) not in covered


async def test_six_slot_schedule_splits_at_the_read_limit() -> None:
    """43707-43791 is 85 registers, so it costs three reads of at most 40."""
    unit, device = build_hybrid_6_slot()
    await device.async_update()

    schedule_blocks = [
        (e.address, e.count)
        for e in unit.read_events
        if e.register_type == "holding" and e.address >= 43707
    ]
    assert schedule_blocks == [(43707, 40), (43747, 40), (43787, 5)]


async def test_legacy_poll_is_correct() -> None:
    unit, device = build_legacy()
    report = await device.async_update()

    covered = read_addresses(unit)
    assert field_addresses(polled(device, report)) <= covered
    assert all(event.count <= LEGACY_MAX_SPAN for event in unit.read_events)
    # The legacy map is input registers only: nothing here is writable.
    assert {event.register_type for event in unit.read_events} == {"input"}


async def test_legacy_poll_shape() -> None:
    unit, device = build_legacy()
    await device.async_update()
    unit.read_events.clear()
    await device.async_update()

    blocks = [(e.address, e.count) for e in unit.read_events]
    assert blocks == [
        (3005, 16),  # power and the generation counters
        (3022, 8),  # four PV strings
        (3034, 10),  # AC output, temperature, frequency
    ]


async def test_serial_number_is_read_once() -> None:
    """Identity is settled at setup and stays out of the polled group."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    assert ("input", 33004) in read_addresses(unit)

    unit.read_events.clear()
    await device.async_update()
    assert ("input", 33004) not in read_addresses(unit)


async def test_write_only_registers_are_never_polled() -> None:
    """Commands hold registers the integration only ever writes."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()

    covered = read_addresses(unit)
    for address in (43000, 43005, 43110, 43129, 43135, 43136):
        assert ("holding", address) not in covered
