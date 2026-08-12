"""Six charge and six discharge slots — the 43707..43791 holding block.

Newer firmware replaces the three combined slots with six charge slots and
six discharge slots, each carrying its own target SoC, current and voltage,
and gates each slot with a bit of the enable word at 43707. This is the
scheme the integration's ``plugin_solis_fb00`` speaks.
"""

from __future__ import annotations

from modbus_connection.model import Component, bit, gauge, integer, repeating_group

from .settings import SolisHolding, ranged

FIRST_CHARGE_REGISTER = 43708
FIRST_DISCHARGE_REGISTER = 43750
SLOT_STRIDE = 7
SLOT_COUNT = 6
TIME_OFFSET = 3
"""Registers into a slot before its start/end times begin."""


class ChargeSlot(Component):
    """One charge slot, declared at the first slot's addresses."""

    max_span = 40

    target_soc = integer(43708, signed=False, unit="%", writable=ranged(10, 100))
    current = gauge(43709, 0.1, signed=False, unit="A", writable=ranged(0, 6553.5))
    voltage = gauge(43710, 0.1, signed=False, unit="V", writable=ranged(49, 54))
    start_hours = integer(43711, signed=False, unit="h", writable=ranged(0, 23))
    start_minutes = integer(43712, signed=False, unit="min", writable=ranged(0, 59))
    end_hours = integer(43713, signed=False, unit="h", writable=ranged(0, 23))
    end_minutes = integer(43714, signed=False, unit="min", writable=ranged(0, 59))


class DischargeSlot(Component):
    """One discharge slot, same layout 42 registers further on."""

    max_span = 40

    target_soc = integer(43750, signed=False, unit="%", writable=ranged(10, 100))
    current = gauge(43751, 0.1, signed=False, unit="A", writable=ranged(0, 6553.5))
    voltage = gauge(43752, 0.1, signed=False, unit="V", writable=ranged(49, 54))
    start_hours = integer(43753, signed=False, unit="h", writable=ranged(0, 23))
    start_minutes = integer(43754, signed=False, unit="min", writable=ranged(0, 59))
    end_hours = integer(43755, signed=False, unit="h", writable=ranged(0, 23))
    end_minutes = integer(43756, signed=False, unit="min", writable=ranged(0, 59))


class Schedule(SolisHolding):
    """The timed charge/discharge schedule, with per-slot battery limits."""

    timed_charge_discharge_on_off = integer(
        43707, signed=False, writable=ranged(0, 4096)
    )
    """The enable word; the per-slot bits below are its individual bits."""

    timed_charge_slot_1_enable = bit(43707, 0, writable=True)
    timed_charge_slot_2_enable = bit(43707, 1, writable=True)
    timed_charge_slot_3_enable = bit(43707, 2, writable=True)
    timed_charge_slot_4_enable = bit(43707, 3, writable=True)
    timed_charge_slot_5_enable = bit(43707, 4, writable=True)
    timed_charge_slot_6_enable = bit(43707, 5, writable=True)
    timed_discharge_slot_1_enable = bit(43707, 6, writable=True)
    timed_discharge_slot_2_enable = bit(43707, 7, writable=True)
    timed_discharge_slot_3_enable = bit(43707, 8, writable=True)
    timed_discharge_slot_4_enable = bit(43707, 9, writable=True)
    timed_discharge_slot_5_enable = bit(43707, 10, writable=True)
    timed_discharge_slot_6_enable = bit(43707, 11, writable=True)

    charge_slots = repeating_group(SLOT_COUNT, ChargeSlot, stride=SLOT_STRIDE)
    discharge_slots = repeating_group(SLOT_COUNT, DischargeSlot, stride=SLOT_STRIDE)

    async def write_charge_slot(
        self, index: int, *, start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        """Write one charge slot's four time registers in a single request."""
        await self._write_times(FIRST_CHARGE_REGISTER, index, start, end)

    async def write_discharge_slot(
        self, index: int, *, start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        """Write one discharge slot's four time registers in a single request."""
        await self._write_times(FIRST_DISCHARGE_REGISTER, index, start, end)

    async def _write_times(
        self, base: int, index: int, start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        # The integration writes each slot's times atomically; writing the
        # four registers one by one leaves the inverter with a half-updated
        # slot in between.
        if not 0 <= index < SLOT_COUNT:
            raise ValueError(f"slot {index} outside 0..{SLOT_COUNT - 1}")
        for hour, minute in (start, end):
            ranged(0, 23)(hour)
            ranged(0, 59)(minute)
        address = base + index * SLOT_STRIDE + TIME_OFFSET
        await self._unit.write_registers(address, [*start, *end])
