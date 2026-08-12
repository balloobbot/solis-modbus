"""Three combined charge/discharge slots — the 43141..43170 holding block.

Each of the three slots carries one charge window and one discharge window,
and a single charge current and discharge current apply to all three. This is the
scheme the integration's ``plugin_solis`` speaks.
"""

from __future__ import annotations

from modbus_connection.model import Component, bit, gauge, integer, repeating_group

from .settings import SolisHolding, ranged

FIRST_SLOT_REGISTER = 43143
SLOT_STRIDE = 10
SLOT_COUNT = 3


class TimeSlot(Component):
    """One slot: a charge window and a discharge window, declared at slot 1."""

    max_span = 40

    charge_start_hours = integer(43143, signed=False, unit="h", writable=ranged(0, 23))
    charge_start_minutes = integer(
        43144, signed=False, unit="min", writable=ranged(0, 59)
    )
    charge_end_hours = integer(43145, signed=False, unit="h", writable=ranged(0, 23))
    charge_end_minutes = integer(
        43146, signed=False, unit="min", writable=ranged(0, 59)
    )
    discharge_start_hours = integer(
        43147, signed=False, unit="h", writable=ranged(0, 23)
    )
    discharge_start_minutes = integer(
        43148, signed=False, unit="min", writable=ranged(0, 59)
    )
    discharge_end_hours = integer(43149, signed=False, unit="h", writable=ranged(0, 23))
    discharge_end_minutes = integer(
        43150, signed=False, unit="min", writable=ranged(0, 59)
    )


class Schedule(SolisHolding):
    """The timed charge/discharge schedule."""

    timed_charge_current = gauge(
        43141, 0.1, signed=False, unit="A", writable=ranged(0, 6553.5)
    )
    timed_discharge_current = gauge(
        43142, 0.1, signed=False, unit="A", writable=ranged(0, 6553.5)
    )
    slots = repeating_group(SLOT_COUNT, TimeSlot, stride=SLOT_STRIDE)

    async def write_slot(
        self,
        index: int,
        *,
        charge_start: tuple[int, int],
        charge_end: tuple[int, int],
        discharge_start: tuple[int, int],
        discharge_end: tuple[int, int],
    ) -> None:
        """Write one slot's eight time registers in a single request.

        ``index`` is 0-based. Times are ``(hour, minute)``. The integration
        writes this block atomically; writing the fields one by one would leave
        the inverter with a half-updated slot between requests.
        """
        if not 0 <= index < SLOT_COUNT:
            raise ValueError(f"slot {index} outside 0..{SLOT_COUNT - 1}")
        values = [*charge_start, *charge_end, *discharge_start, *discharge_end]
        for hour, minute in (charge_start, charge_end, discharge_start, discharge_end):
            ranged(0, 23)(hour)
            ranged(0, 59)(minute)
        await self._unit.write_registers(
            FIRST_SLOT_REGISTER + index * SLOT_STRIDE, values
        )


class SpecialSettings(SolisHolding):
    """Protection and mode flags packed into holding register 43249."""

    special_settings = integer(43249, signed=False, writable=ranged(0, 4096))
    """The whole word; the flags below are its individual bits."""

    mppt_parallel_function = bit(43249, 0, writable=True)
    igfollow = bit(43249, 1, writable=True)
    relay_protection = bit(43249, 2, writable=True)
    i_leak_protection = bit(43249, 3, writable=True)
    pv_iso_protection = bit(43249, 4, writable=True)
    grid_interference_protection = bit(43249, 5, writable=True)
    dc_component_of_grid_current_protection_switch = bit(43249, 6, writable=True)
    const_voltage_mode_enable = bit(43249, 7, writable=True)
