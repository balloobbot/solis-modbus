"""Input-register telemetry, shared by both hybrid protocol variants.

Every component here reads the 33xxx input space (FC04). Field names are the
integration's entity keys, so a map lifted from there keeps working.
"""

from __future__ import annotations

from datetime import datetime

from modbus_connection.model import (
    Component,
    enum,
    gauge,
    int32,
    integer,
    string,
    uint32,
)

from .enums import InverterStatus

MAX_READ_SPAN = 40
"""Registers per read. The integration caps a Solis block at 40."""


class SolisInput(Component):
    """Base for the read-only 33xxx input map."""

    register_space = "input"
    max_span = MAX_READ_SPAN


class Identity(SolisInput):
    """The inverter's serial number. Read once; it never changes."""

    serial_number = string(33004, 8)


class Clock(SolisInput):
    """The inverter's real-time clock."""

    year = integer(33022, signed=False)
    """Two-digit year."""

    month = integer(33023, signed=False)
    day = integer(33024, signed=False)
    hour = integer(33025, signed=False)
    minute = integer(33026, signed=False)
    second = integer(33027, signed=False)

    @property
    def time(self) -> datetime | None:
        """The clock as a datetime, or None if it has not been read."""
        parts = (self.year, self.month, self.day, self.hour, self.minute, self.second)
        if any(p is None for p in parts):
            return None
        year, month, day, hour, minute, second = parts
        assert year is not None
        try:
            return datetime(
                2000 + year % 100,
                month,  # type: ignore[arg-type]
                day,  # type: ignore[arg-type]
                hour,  # type: ignore[arg-type]
                minute,  # type: ignore[arg-type]
                second,  # type: ignore[arg-type]
            )
        except ValueError:  # an unset clock reports month/day 0
            return None


class Generation(SolisInput):
    """Lifetime and periodic PV generation counters."""

    power_generation_total = uint32(33029, unit="kWh")
    power_generation_this_month = uint32(33031, unit="kWh")
    power_generation_last_month = uint32(33033, unit="kWh")
    power_generation_today = gauge(33035, 0.1, signed=False, unit="kWh")
    power_generation_yesterday = gauge(33036, 0.1, signed=False, unit="kWh")
    power_generation_this_year = uint32(33037, unit="kWh")
    power_generation_last_year = uint32(33039, unit="kWh")


class PvStrings(SolisInput):
    """The PV inputs. Two strings; see the MPPT3/MPPT4 subclasses for more."""

    pv_voltage_1 = gauge(33049, 0.1, signed=False, unit="V")
    pv_current_1 = gauge(33050, 0.1, signed=False, unit="A")
    pv_voltage_2 = gauge(33051, 0.1, signed=False, unit="V")
    pv_current_2 = gauge(33052, 0.1, signed=False, unit="A")
    pv_total_power = uint32(33057, unit="W")

    @property
    def pv_power_1(self) -> float | None:
        """String 1 power, the product the integration computes in HA."""
        return _product(self.pv_voltage_1, self.pv_current_1)

    @property
    def pv_power_2(self) -> float | None:
        """String 2 power."""
        return _product(self.pv_voltage_2, self.pv_current_2)


class PvStrings3(PvStrings):
    """Three PV strings — inverters flagged MPPT3 or MPPT4."""

    pv_voltage_3 = gauge(33053, 0.1, signed=False, unit="V")
    pv_current_3 = gauge(33054, 0.1, signed=False, unit="A")

    @property
    def pv_power_3(self) -> float | None:
        """String 3 power."""
        return _product(self.pv_voltage_3, self.pv_current_3)


class PvStrings4(PvStrings3):
    """Four PV strings — inverters flagged MPPT4."""

    pv_voltage_4 = gauge(33055, 0.1, signed=False, unit="V")
    pv_current_4 = gauge(33056, 0.1, signed=False, unit="A")

    @property
    def pv_power_4(self) -> float | None:
        """String 4 power."""
        return _product(self.pv_voltage_4, self.pv_current_4)


class AcOutput(SolisInput):
    """Inverter AC output power. Phase voltages/currents are per variant."""

    active_power = int32(33079, unit="W")
    reactive_power = int32(33081, unit="var")
    apparent_power = int32(33083, unit="VA")


class SinglePhaseAcOutput(AcOutput):
    """AC output of an X1 (single-phase) inverter."""

    inverter_voltage = gauge(33073, 0.1, signed=False, unit="V")
    inverter_current = gauge(33076, 0.1, signed=False, unit="A")


class ThreePhaseAcOutput(AcOutput):
    """AC output of an X3 (three-phase) inverter."""

    grid_voltage_l1 = gauge(33073, 0.1, signed=False, unit="V")
    grid_voltage_l2 = gauge(33074, 0.1, signed=False, unit="V")
    grid_voltage_l3 = gauge(33075, 0.1, signed=False, unit="V")
    grid_current_l1 = gauge(33076, 0.1, signed=False, unit="A")
    grid_current_l2 = gauge(33077, 0.1, signed=False, unit="A")
    grid_current_l3 = gauge(33078, 0.1, signed=False, unit="A")


class Status(SolisInput):
    """Inverter temperature, grid frequency and working status."""

    inverter_temperature = gauge(33093, 0.1, signed=False, unit="°C")
    inverter_frequency = gauge(33094, 0.01, signed=False, unit="Hz")
    inverter_status = enum(33095, InverterStatus)


class InverterMeter(SolisInput):
    """The grid meter as the inverter reports it in its own block."""

    meter_total_activepower = uint32(33126, scale=0.01, unit="kWh")
    meter_voltage = gauge(33128, 0.1, signed=False, unit="V")
    meter_current = gauge(33129, 0.01, signed=False, unit="A")
    meter_active_power = int32(33130, unit="W")


class Battery(SolisInput):
    """Battery state, and the storage mode word read back from the inverter."""

    energy_storage_control_switch = integer(33132, signed=False)
    """Raw storage mode word; decode with the variant's EnergyStorageMode."""

    battery_voltage = gauge(33133, 0.1, signed=False, unit="V")
    battery_current = gauge(33134, 0.1, unit="A")
    battery_charge_direction = integer(33135, signed=False)
    """0 while charging, 1 while discharging."""

    battery_soc = integer(33139, signed=False, unit="%")
    battery_soh = integer(33140, signed=False, unit="%")
    bms_battery_voltage = gauge(33141, 0.01, signed=False, unit="V")
    bms_battery_current = gauge(33142, 0.1, unit="A")
    bms_battery_charge_limit = gauge(33143, 0.1, signed=False, unit="A")
    bms_battery_discharge_limit = gauge(33144, 0.1, signed=False, unit="A")
    house_load = integer(33147, signed=False, unit="W")
    bypass_load = integer(33148, signed=False, unit="W")
    battery_power = int32(33149, unit="W")

    @property
    def battery_input_energy(self) -> float | None:
        """Charge power (W): battery_power while the direction reads charging."""
        if self.battery_charge_direction is None or self.battery_power is None:
            return None
        return float(self.battery_power) if self.battery_charge_direction == 0 else 0.0

    @property
    def battery_output_energy(self) -> float | None:
        """Discharge power (W), as a positive number."""
        if self.battery_charge_direction is None or self.battery_power is None:
            return None
        return (
            abs(float(self.battery_power))
            if self.battery_charge_direction == 1
            else 0.0
        )


class BatteryCurrentLimits(SolisInput):
    """Battery current limits. Only X1 inverters serve this block."""

    battery_charge_current_limit = gauge(33206, 0.1, signed=False, unit="A")
    battery_discharge_current_limit = gauge(33207, 0.1, signed=False, unit="A")


class EnergyTotals(SolisInput):
    """Battery, grid and house energy counters."""

    total_battery_charge = uint32(33161, unit="kWh")
    battery_charge_today = gauge(33163, 0.1, signed=False, unit="kWh")
    battery_charge_yesterday = gauge(33164, 0.1, signed=False, unit="kWh")
    total_battery_discharge = uint32(33165, unit="kWh")
    battery_discharge_today = gauge(33167, 0.1, signed=False, unit="kWh")
    battery_discharge_yesterday = gauge(33168, 0.1, signed=False, unit="kWh")
    grid_import_total = uint32(33169, unit="kWh")
    grid_import_today = gauge(33171, 0.1, signed=False, unit="kWh")
    grid_import_yesterday = gauge(33172, 0.1, signed=False, unit="kWh")
    grid_export_total = uint32(33173, unit="kWh")
    grid_export_today = gauge(33175, 0.1, signed=False, unit="kWh")
    grid_export_yesterday = gauge(33176, 0.1, signed=False, unit="kWh")
    house_load_total = uint32(33177, unit="kWh")
    house_load_today = gauge(33179, 0.1, signed=False, unit="kWh")
    house_load_yesterday = gauge(33180, 0.1, signed=False, unit="kWh")


class ExternalMeter(SolisInput):
    """The external energy meter block. Per-phase fields are per variant."""

    meter_active_power_total = int32(33263, scale=0.001, unit="kW")
    meter_reactive_power_total = int32(33271, unit="var")
    meter_apparent_power_total = int32(33279, unit="VA")
    meter_power_factor = gauge(33281, 0.01)
    meter_grid_frequency = gauge(33282, 0.01, signed=False, unit="Hz")
    meter_grid_import_total = uint32(33283, scale=0.01, unit="kWh")
    meter_grid_export_total = uint32(33285, scale=0.01, unit="kWh")


class SinglePhaseExternalMeter(ExternalMeter):
    """External meter of an X1 (single-phase) inverter."""

    meter_ac_voltage = gauge(33251, 0.1, signed=False, unit="V")
    meter_ac_current = gauge(33252, 0.01, signed=False, unit="A")
    meter_reactive_power = int32(33265, unit="var")
    meter_apparent_power = int32(33273, unit="VA")


class ThreePhaseExternalMeter(ExternalMeter):
    """External meter of an X3 (three-phase) inverter."""

    meter_ac_voltage_l1 = gauge(33251, 0.1, signed=False, unit="V")
    meter_ac_current_l1 = gauge(33252, 0.01, signed=False, unit="A")
    meter_ac_voltage_l2 = gauge(33253, 0.1, signed=False, unit="V")
    meter_ac_current_l2 = gauge(33254, 0.01, signed=False, unit="A")
    meter_ac_voltage_l3 = gauge(33255, 0.1, signed=False, unit="V")
    meter_ac_current_l3 = gauge(33256, 0.01, signed=False, unit="A")
    meter_active_power_l1 = int32(33257, scale=0.001, unit="kW")
    meter_active_power_l2 = int32(33259, scale=0.001, unit="kW")
    meter_active_power_l3 = int32(33261, scale=0.001, unit="kW")
    meter_reactive_power_l1 = int32(33265, unit="var")
    meter_reactive_power_l2 = int32(33267, unit="var")
    meter_reactive_power_l3 = int32(33269, unit="var")
    meter_apparent_power_l1 = int32(33273, unit="VA")
    meter_apparent_power_l2 = int32(33275, unit="VA")
    meter_apparent_power_l3 = int32(33277, unit="VA")


def _product(voltage: float | None, current: float | None) -> float | None:
    if voltage is None or current is None:
        return None
    return round(voltage * current, 1)
