"""Decode tests: synthetic registers in, engineering values out."""

from __future__ import annotations

from datetime import datetime

import pytest
from modbus_connection.mock import MockModbusUnit

from solis_modbus import (
    BackflowSwitchX1,
    BackflowSwitchX3,
    EnergyStorageMode3Slot,
    EnergyStorageMode6Slot,
    InverterStatus,
    PowerSwitch,
    SolisHybrid3Slot,
    SolisHybrid6Slot,
    SolisLegacy3000,
    Variant,
)

from .conftest import X1_SERIAL, X3_MPPT4_SERIAL, seed_hybrid


async def test_identity_and_variant(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    assert inverter_3_slot.identity.serial_number == X1_SERIAL
    assert inverter_3_slot.variant == Variant.X1


async def test_clock(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    assert inverter_3_slot.clock.time == datetime(2025, 8, 12, 14, 30, 45)


async def test_clock_unset_reads_none(mock_modbus_unit: MockModbusUnit) -> None:
    """A cleared clock reports month 0, which is not a date."""
    seed_hybrid(mock_modbus_unit, X1_SERIAL)
    mock_modbus_unit.input[33022] = [0, 0, 0, 0, 0, 0]
    device = SolisHybrid3Slot(mock_modbus_unit, variant=Variant.X1)
    await device.clock.async_update()
    assert device.clock.time is None


async def test_generation_counters(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    generation = inverter_3_slot.generation
    assert generation.power_generation_total == 12345
    assert generation.power_generation_today == pytest.approx(8.7)
    assert generation.power_generation_yesterday == pytest.approx(15.2)
    assert generation.power_generation_this_year == 5000


async def test_pv_two_strings_on_x1(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    pv = inverter_3_slot.pv
    assert pv is not None
    assert pv.pv_voltage_1 == pytest.approx(320.1)
    assert pv.pv_current_1 == pytest.approx(8.5)
    assert pv.pv_power_1 == pytest.approx(2720.9)
    assert pv.pv_total_power == 4600
    assert not hasattr(pv, "pv_voltage_3")


async def test_pv_four_strings_on_mppt4(inverter_3_slot_x3: SolisHybrid3Slot) -> None:
    await inverter_3_slot_x3.async_update()
    pv = inverter_3_slot_x3.pv
    assert pv is not None
    assert inverter_3_slot_x3.variant is not None
    assert inverter_3_slot_x3.variant.pv_strings == 4
    assert pv.pv_voltage_3 == pytest.approx(290.0)  # type: ignore[attr-defined]
    assert pv.pv_current_4 == pytest.approx(5.5)  # type: ignore[attr-defined]
    assert pv.pv_power_4 == pytest.approx(1540.0)  # type: ignore[attr-defined]


async def test_single_phase_ac_output(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    ac = inverter_3_slot.ac_output
    assert ac is not None
    assert ac.inverter_voltage == pytest.approx(231.2)  # type: ignore[attr-defined]
    assert ac.inverter_current == pytest.approx(14.3)  # type: ignore[attr-defined]
    assert ac.active_power == 3300
    assert ac.reactive_power == -100  # signed 32-bit
    assert ac.apparent_power == 3400


async def test_three_phase_ac_output(inverter_3_slot_x3: SolisHybrid3Slot) -> None:
    await inverter_3_slot_x3.async_update()
    ac = inverter_3_slot_x3.ac_output
    assert ac is not None
    assert ac.grid_voltage_l1 == pytest.approx(231.2)  # type: ignore[attr-defined]
    assert ac.grid_voltage_l3 == pytest.approx(229.8)  # type: ignore[attr-defined]
    assert ac.grid_current_l2 == pytest.approx(13.8)  # type: ignore[attr-defined]
    assert not hasattr(ac, "inverter_voltage")


async def test_status(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    status = inverter_3_slot.status
    assert status.inverter_temperature == pytest.approx(41.5)
    assert status.inverter_frequency == pytest.approx(50.01)
    assert status.inverter_status is InverterStatus.GENERATING


async def test_status_unknown_code_reads_none(mock_modbus_unit: MockModbusUnit) -> None:
    seed_hybrid(mock_modbus_unit, X1_SERIAL)
    mock_modbus_unit.input[33095] = 0x0BAD
    device = SolisHybrid3Slot(mock_modbus_unit, variant=Variant.X1)
    await device.status.async_update()
    assert device.status.inverter_status is None


async def test_battery(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    battery = inverter_3_slot.battery
    assert battery.battery_voltage == pytest.approx(51.2)
    assert battery.battery_current == pytest.approx(-5.0)  # signed 16-bit
    assert battery.battery_soc == 78
    assert battery.bms_battery_voltage == pytest.approx(51.23)
    assert battery.battery_power == -250
    assert battery.house_load == 1200


async def test_battery_directional_power(inverter_3_slot: SolisHybrid3Slot) -> None:
    """Discharging: output carries the magnitude, input is zero."""
    await inverter_3_slot.async_update()
    battery = inverter_3_slot.battery
    assert battery.battery_charge_direction == 1
    assert battery.battery_output_energy == pytest.approx(250.0)
    assert battery.battery_input_energy == pytest.approx(0.0)


async def test_battery_current_limits_are_x1_only(
    inverter_3_slot: SolisHybrid3Slot, inverter_3_slot_x3: SolisHybrid3Slot
) -> None:
    await inverter_3_slot.async_update()
    limits = inverter_3_slot.battery_current_limits
    assert limits is not None
    assert limits.battery_charge_current_limit == pytest.approx(62.0)

    await inverter_3_slot_x3.async_update()
    assert inverter_3_slot_x3.battery_current_limits is None


async def test_energy_totals(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    energy = inverter_3_slot.energy
    assert energy.total_battery_charge == 3000
    assert energy.battery_discharge_today == pytest.approx(4.1)
    assert energy.grid_export_total == 6000
    assert energy.house_load_yesterday == pytest.approx(12.5)


async def test_inverter_meter(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    meter = inverter_3_slot.inverter_meter
    assert meter.meter_total_activepower == pytest.approx(987.65)
    assert meter.meter_voltage == pytest.approx(230.5)
    assert meter.meter_current == pytest.approx(12.34)
    assert meter.meter_active_power == -1000


async def test_single_phase_external_meter(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    meter = inverter_3_slot.external_meter
    assert meter is not None
    assert meter.meter_ac_voltage == pytest.approx(231.0)  # type: ignore[attr-defined]
    assert meter.meter_ac_current == pytest.approx(15.0)  # type: ignore[attr-defined]
    assert meter.meter_reactive_power == 120  # type: ignore[attr-defined]
    assert meter.meter_active_power_total == pytest.approx(3.23)
    assert meter.meter_power_factor == pytest.approx(0.98)
    assert meter.meter_grid_import_total == pytest.approx(450.0)


async def test_three_phase_external_meter(inverter_3_slot_x3: SolisHybrid3Slot) -> None:
    await inverter_3_slot_x3.async_update()
    meter = inverter_3_slot_x3.external_meter
    assert meter is not None
    assert meter.meter_ac_voltage_l2 == pytest.approx(229.5)  # type: ignore[attr-defined]
    assert meter.meter_active_power_l1 == pytest.approx(1.1)  # type: ignore[attr-defined]
    assert meter.meter_apparent_power_l3 == 3350  # type: ignore[attr-defined]
    assert not hasattr(meter, "meter_ac_voltage")


async def test_settings(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    settings = inverter_3_slot.settings
    assert settings is not None
    assert settings.power_switch is PowerSwitch.ON
    assert settings.battery_minimum_soc == 20
    assert settings.backflow_power == 5000  # 100 W steps
    assert settings.battery_charge_current == pytest.approx(55.0)
    assert settings.backflow_power_switch is BackflowSwitchX1.ON  # type: ignore[attr-defined]


async def test_three_phase_backflow_switch(
    inverter_3_slot_x3: SolisHybrid3Slot,
) -> None:
    """Same register, a different option map on three-phase inverters."""
    await inverter_3_slot_x3.async_update()
    settings = inverter_3_slot_x3.settings
    assert settings is not None
    assert (
        settings.backflow_power_switch  # type: ignore[attr-defined]
        is BackflowSwitchX3.ON_BALANCED_OUTPUT
    )


async def test_storage_mode_per_variant(
    inverter_3_slot: SolisHybrid3Slot, inverter_6_slot: SolisHybrid6Slot
) -> None:
    """Code 35 is Self-Use on three-slot firmware; six-slot uses 33 instead."""
    await inverter_3_slot.async_update()
    assert inverter_3_slot.storage_mode is EnergyStorageMode3Slot.SELF_USE

    await inverter_6_slot.async_update()
    assert inverter_6_slot.storage_mode is EnergyStorageMode6Slot.SELF_USE


async def test_three_slot_schedule(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    schedule = inverter_3_slot.schedule
    assert schedule.timed_charge_current == pytest.approx(50.0)
    assert schedule.timed_discharge_current == pytest.approx(52.0)
    assert len(schedule.slots) == 3

    first = schedule.slots[0]
    assert (first.charge_start_hours, first.charge_start_minutes) == (1, 30)
    assert (first.charge_end_hours, first.charge_end_minutes) == (5, 45)
    assert (first.discharge_start_hours, first.discharge_start_minutes) == (17, 0)
    assert (first.discharge_end_hours, first.discharge_end_minutes) == (20, 15)

    third = schedule.slots[2]  # stride 10 lands it on 43163
    assert (third.charge_start_hours, third.charge_start_minutes) == (3, 15)
    assert (third.discharge_end_hours, third.discharge_end_minutes) == (22, 40)


async def test_special_settings_bits(inverter_3_slot: SolisHybrid3Slot) -> None:
    await inverter_3_slot.async_update()
    special = inverter_3_slot.special_settings
    assert special.special_settings == 0b1010_0101
    assert special.mppt_parallel_function is True  # bit 0
    assert special.igfollow is False  # bit 1
    assert special.relay_protection is True  # bit 2
    assert special.const_voltage_mode_enable is True  # bit 7


async def test_six_slot_schedule(inverter_6_slot: SolisHybrid6Slot) -> None:
    await inverter_6_slot.async_update()
    schedule = inverter_6_slot.schedule
    assert len(schedule.charge_slots) == 6
    assert len(schedule.discharge_slots) == 6

    charge = schedule.charge_slots[0]
    assert charge.target_soc == 90
    assert charge.current == pytest.approx(50.0)
    assert charge.voltage == pytest.approx(52.0)
    assert (charge.start_hours, charge.start_minutes) == (1, 30)
    assert (charge.end_hours, charge.end_minutes) == (5, 45)

    last_charge = schedule.charge_slots[5]  # stride 7 lands it on 43743
    assert last_charge.target_soc == 85
    assert (last_charge.start_hours, last_charge.end_hours) == (6, 10)

    discharge = schedule.discharge_slots[0]
    assert discharge.target_soc == 20
    assert discharge.voltage == pytest.approx(51.0)
    assert (discharge.start_hours, discharge.end_hours) == (17, 18)


async def test_six_slot_enable_bits(inverter_6_slot: SolisHybrid6Slot) -> None:
    await inverter_6_slot.async_update()
    schedule = inverter_6_slot.schedule
    assert schedule.timed_charge_discharge_on_off == 0b0000_0100_0001
    assert schedule.timed_charge_slot_1_enable is True
    assert schedule.timed_charge_slot_2_enable is False
    assert schedule.timed_discharge_slot_1_enable is True  # bit 6
    assert schedule.timed_discharge_slot_6_enable is False  # bit 11


async def test_six_slot_has_no_special_settings(
    inverter_6_slot: SolisHybrid6Slot,
) -> None:
    assert not hasattr(inverter_6_slot, "special_settings")


async def test_legacy_map(legacy_inverter: SolisLegacy3000) -> None:
    await legacy_inverter.async_update()
    assert legacy_inverter.variant == Variant.X1
    assert legacy_inverter.generation.pv_total_power == 4600
    assert legacy_inverter.generation.power_generation_today == pytest.approx(8.7)
    assert legacy_inverter.pv.pv_voltage_1 == pytest.approx(320.1)
    assert legacy_inverter.pv.pv_current_4 == pytest.approx(5.5)

    ac = legacy_inverter.ac_output
    assert ac is not None
    assert ac.inverter_voltage == pytest.approx(231.2)  # type: ignore[attr-defined]
    assert ac.inverter_temperature == pytest.approx(41.5)
    assert ac.grid_frequency == pytest.approx(50.01)


async def test_legacy_three_phase(mock_modbus_unit: MockModbusUnit) -> None:
    from .conftest import LEGACY_INPUT, ascii_words

    for address, value in LEGACY_INPUT.items():
        mock_modbus_unit.input[address] = value
    mock_modbus_unit.input[3061] = ascii_words("110CA221")
    device = SolisLegacy3000(mock_modbus_unit)
    await device.async_update()
    assert device.variant == Variant.X3
    ac = device.ac_output
    assert ac is not None
    assert ac.grid_voltage_s == pytest.approx(230.1)  # type: ignore[attr-defined]
    assert ac.grid_current_t == pytest.approx(14.1)  # type: ignore[attr-defined]


async def test_x3_mppt4_serial_detects_variant(
    inverter_3_slot_x3: SolisHybrid3Slot,
) -> None:
    await inverter_3_slot_x3.async_update()
    assert inverter_3_slot_x3.identity.serial_number == X3_MPPT4_SERIAL
    assert inverter_3_slot_x3.variant == Variant.X3 | Variant.MPPT4
