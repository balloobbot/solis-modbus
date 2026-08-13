"""Writable registers: what reaches the inverter, and what is refused."""

from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusUnit

from solis_modbus import (
    BackflowSwitchX3,
    BatteryOverride,
    EnergyStorageMode3Slot,
    EnergyStorageMode6Slot,
    PowerSwitch,
)

from .conftest import build_hybrid_3_slot, build_hybrid_6_slot, build_legacy


async def written(unit: MockModbusUnit, address: int, count: int = 1) -> list[int]:
    """Read back what the store now holds at an address."""
    return await unit.read_holding_registers(address, count)


async def test_write_power_switch() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    assert device.settings is not None
    await device.settings.write("power_switch", PowerSwitch.OFF)
    assert await written(unit, 43007) == [222]


async def test_write_scaled_setting() -> None:
    """Battery current is stored in tenths of an amp."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    assert device.settings is not None
    await device.settings.write("battery_charge_current", 42.5)
    assert await written(unit, 43117) == [425]


async def test_write_export_limit_in_hundred_watt_steps() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    assert device.settings is not None
    await device.settings.write("backflow_power", 3300)
    assert await written(unit, 43074) == [33]


async def test_write_rejects_out_of_range_soc() -> None:
    _, device = build_hybrid_3_slot()
    await device.async_update()
    assert device.settings is not None
    with pytest.raises(ValueError):
        await device.settings.write("battery_minimum_soc", 5)  # floor is 10
    with pytest.raises(ValueError):
        await device.settings.write("battery_minimum_soc", 101)


async def test_write_three_phase_export_switch() -> None:
    unit, device = build_hybrid_3_slot("1033050123456789")
    await device.async_update()
    assert device.settings is not None
    await device.settings.write(
        "backflow_power_switch", BackflowSwitchX3.ON_UNBALANCED_OUTPUT
    )
    assert await written(unit, 43073) == [80]


async def test_write_storage_mode_uses_the_variants_codes() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    await device.commands.write(
        "energy_storage_control_switch", EnergyStorageMode3Slot.FEED_IN_PRIORITY
    )
    assert await written(unit, 43110) == [98]

    unit6, device6 = build_hybrid_6_slot()
    await device6.async_update()
    await device6.commands.write(
        "energy_storage_control_switch", EnergyStorageMode6Slot.FEED_IN_PRIORITY
    )
    assert await written(unit6, 43110) == [96]  # a different code for the same mode


async def test_write_battery_override() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    await device.commands.write(
        "battery_control_override_switch", BatteryOverride.FORCE_CHARGE
    )
    await device.commands.write("battery_control_override_charge_power", 2500)
    assert await written(unit, 43135) == [1]
    assert await written(unit, 43136) == [250]  # 10 W steps


async def test_set_clock_writes_six_registers_at_once() -> None:
    from datetime import datetime

    unit, device = build_hybrid_3_slot()
    await device.async_update()

    writes: list[tuple[int, list[int]]] = []
    unit.on_write(lambda event: writes.append((event.address, list(event.values))))
    await device.commands.set_clock(datetime(2026, 3, 9, 7, 8, 9))

    assert writes == [(43000, [26, 3, 9, 7, 8, 9])]
    assert await written(unit, 43000, 6) == [26, 3, 9, 7, 8, 9]


async def test_write_three_slot_times_atomically() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()

    writes: list[tuple[int, list[int]]] = []
    unit.on_write(lambda event: writes.append((event.address, list(event.values))))
    await device.schedule.write_slot(
        1,  # the second slot, at 43143 + 10
        charge_start=(2, 15),
        charge_end=(6, 45),
        discharge_start=(18, 30),
        discharge_end=(21, 0),
    )

    assert writes == [(43153, [2, 15, 6, 45, 18, 30, 21, 0])]


async def test_write_three_slot_times_validates() -> None:
    _, device = build_hybrid_3_slot()
    await device.async_update()
    with pytest.raises(ValueError):
        await device.schedule.write_slot(
            3,
            charge_start=(0, 0),
            charge_end=(1, 0),
            discharge_start=(2, 0),
            discharge_end=(3, 0),
        )
    with pytest.raises(ValueError):
        await device.schedule.write_slot(
            0,
            charge_start=(24, 0),  # hour out of range
            charge_end=(1, 0),
            discharge_start=(2, 0),
            discharge_end=(3, 0),
        )


async def test_write_single_slot_field() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    await device.schedule.slots[2].write("charge_start_hours", 4)
    assert await written(unit, 43163) == [4]  # 43143 + 2 * 10


async def test_write_special_settings_bit_keeps_the_others() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    assert await written(unit, 43249) == [0b1010_0101]

    await device.special_settings.write("igfollow", True)  # bit 1, was clear
    assert await written(unit, 43249) == [0b1010_0111]


async def test_write_six_slot_enable_bit() -> None:
    unit, device = build_hybrid_6_slot()
    await device.async_update()
    await device.schedule.write("timed_discharge_slot_6_enable", True)  # bit 11
    assert await written(unit, 43707) == [0b1000_0100_0001]


async def test_write_six_slot_charge_and_discharge_times() -> None:
    unit, device = build_hybrid_6_slot()
    await device.async_update()

    writes: list[tuple[int, list[int]]] = []
    unit.on_write(lambda event: writes.append((event.address, list(event.values))))
    await device.schedule.write_charge_slot(0, start=(1, 0), end=(4, 30))
    await device.schedule.write_discharge_slot(5, start=(19, 0), end=(23, 45))

    assert writes == [
        (43711, [1, 0, 4, 30]),  # 43708 + 0 * 7 + 3
        (43788, [19, 0, 23, 45]),  # 43750 + 5 * 7 + 3
    ]


async def test_write_six_slot_target_soc() -> None:
    unit, device = build_hybrid_6_slot()
    await device.async_update()
    await device.schedule.discharge_slots[1].write("target_soc", 35)
    assert await written(unit, 43757) == [35]  # 43750 + 1 * 7


async def test_write_six_slot_voltage_is_range_checked() -> None:
    _, device = build_hybrid_6_slot()
    await device.async_update()
    with pytest.raises(ValueError):
        await device.schedule.charge_slots[0].write("voltage", 60.0)  # ceiling is 54


async def test_legacy_map_has_nothing_writable() -> None:
    _, device = build_legacy()
    report = await device.async_update()
    for name in report.updated:
        component = getattr(device, name)
        assert not any(f.writable for f in component.declared_fields.values())
