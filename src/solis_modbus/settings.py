"""Holding-register settings and commands, shared by both hybrid variants.

Two kinds of register live here. ``Settings`` is read back on every poll — the
integration exposes each of these as a sensor as well as a control. ``Commands``
is write-only: the integration never reads those registers, so neither do we,
and they are kept out of the polled group so an unreadable one cannot fail a
poll.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from modbus_connection.model import Component, enum, gauge, integer

from .enums import BackflowSwitchX1, BackflowSwitchX3, BatteryOverride, PowerSwitch
from .telemetry import MAX_READ_SPAN

RTC_SET_REGISTER = 43000
"""First of six holding registers the inverter's clock is written to."""


def ranged(low: float, high: float) -> Callable[[float], float]:
    """Reject a write outside the range the integration declares for a field."""

    def check(value: float) -> float:
        if not low <= value <= high:
            raise ValueError(f"{value} outside {low}..{high}")
        return value

    return check


class SolisHolding(Component):
    """Base for the 43xxx holding map."""

    max_span = MAX_READ_SPAN


class Settings(SolisHolding):
    """Inverter settings that are both readable and writable."""

    power_switch = enum(43007, PowerSwitch, writable=True)
    battery_minimum_soc = integer(
        43011, signed=False, unit="%", writable=ranged(10, 100)
    )
    force_charge_soc = integer(43018, signed=False, unit="%", writable=ranged(10, 100))
    backup_mode_soc = integer(43024, signed=False, unit="%", writable=ranged(10, 100))
    backflow_power = gauge(43074, 100, signed=False, unit="W", writable=ranged(0, 9900))
    """Export power limit, in 100 W steps."""

    battery_chargedischarge_current = gauge(
        43116, 0.1, signed=False, unit="A", writable=ranged(0, 6553.5)
    )
    battery_charge_current = gauge(
        43117, 0.1, signed=False, unit="A", writable=ranged(0, 6553.5)
    )
    battery_discharge_current = gauge(
        43118, 0.1, signed=False, unit="A", writable=ranged(0, 6553.5)
    )


class SinglePhaseSettings(Settings):
    """Settings of an X1 inverter: the export switch is a plain on/off."""

    backflow_power_switch = enum(43073, BackflowSwitchX1, writable=True)


class ThreePhaseSettings(Settings):
    """Settings of an X3 inverter: the export switch also picks phase balance."""

    backflow_power_switch = enum(43073, BackflowSwitchX3, writable=True)


class Commands(SolisHolding):
    """Write-only registers. Never polled — the integration never reads them.

    The storage mode register (43110) is declared by each protocol variant,
    which knows the mode codes its firmware accepts.
    """

    rtc_set_year = integer(43000, signed=False, writable=ranged(0, 99))
    """Two-digit year, as the integration's clock sync writes it."""

    rtc_set_month = integer(43001, signed=False, writable=ranged(1, 12))
    rtc_set_day = integer(43002, signed=False, writable=ranged(1, 31))
    rtc_set_hour = integer(43003, signed=False, writable=ranged(0, 23))
    rtc_set_minute = integer(43004, signed=False, writable=ranged(0, 59))
    rtc_set_second = integer(43005, signed=False, writable=ranged(0, 59))

    battery_control_override_discharge_power = gauge(
        43129, 10, signed=False, unit="W", writable=ranged(0, 9900)
    )
    battery_control_override_switch = enum(43135, BatteryOverride, writable=True)
    battery_control_override_charge_power = gauge(
        43136, 10, signed=False, unit="W", writable=ranged(0, 9900)
    )

    async def set_clock(self, moment: datetime) -> None:
        """Set the inverter clock, writing all six registers in one request."""
        await self._unit.write_registers(
            RTC_SET_REGISTER,
            [
                moment.year % 100,
                moment.month,
                moment.day,
                moment.hour,
                moment.minute,
                moment.second,
            ],
        )
