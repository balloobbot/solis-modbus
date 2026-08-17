"""One failing block must not take the rest of the poll with it.

The integration reads its blocks independently and tolerates a failure: the
failing block's sensors keep their last values while everything else refreshes.
The library mirrors that at component granularity.
"""

from __future__ import annotations

import pytest
from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusTimeoutError,
)

from solis_modbus import SolisHybrid3Slot, UnknownInverterError

from .conftest import build_hybrid_3_slot, build_legacy


async def test_a_failed_component_leaves_the_rest_fresh() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    before = device.battery.battery_voltage

    unit.input[33128] = 2400  # meter voltage changes on the device -> 240.0 V
    unit.input[33133] = 530  # so does battery voltage -> 53.0 V
    unit.fail_read(
        33132, ModbusTimeoutError("slow battery block"), register_type="input"
    )
    report = await device.async_update()

    assert not report.complete
    assert set(report.failed) == {"battery"}
    assert isinstance(report.failed["battery"], ModbusTimeoutError)
    assert "inverter_meter" in report.updated
    assert device.inverter_meter.meter_voltage == 240.0
    assert device.battery.battery_voltage == before  # previous value kept


async def test_listeners_fire_at_the_end_and_only_for_fresh_components() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    seen: list[int] = []
    # energy is polled before external_meter and the schedule, so a listener
    # firing mid-poll would see fewer reads than the poll's final count.
    device.energy.add_update_listener(lambda: seen.append(len(unit.read_events)))
    device.battery.add_update_listener(lambda: seen.append(-1))

    unit.fail_read(
        33132, ModbusTimeoutError("slow battery block"), register_type="input"
    )
    unit.read_events.clear()
    await device.async_update()

    # One notification, after every component was tried; none for the failure.
    assert seen == [len(unit.read_events)]


async def test_a_settings_poll_notifies_its_own_components() -> None:
    """Polling the settings alone still fires their listeners, and only theirs."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    seen: list[str] = []
    device.schedule.add_update_listener(lambda: seen.append("schedule"))
    device.energy.add_update_listener(lambda: seen.append("energy"))

    await device.async_update_settings()

    assert seen == ["schedule"]


async def test_a_full_poll_notifies_each_component_once() -> None:
    """The two phases share one report, so neither phase may fire it twice."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    readings: list[int] = []
    settings: list[int] = []
    device.energy.add_update_listener(lambda: readings.append(len(unit.read_events)))
    device.schedule.add_update_listener(lambda: settings.append(len(unit.read_events)))

    unit.read_events.clear()
    await device.async_update()

    total = len(unit.read_events)
    assert readings == [total]
    assert settings == [total]


async def test_a_dead_link_raises_instead_of_reporting() -> None:
    unit, device = build_hybrid_3_slot()
    await device.async_update()
    unit.fail_requests(ModbusConnectionError("link down"))
    with pytest.raises(ModbusConnectionError):
        await device.async_update()


async def test_every_component_refreshes_on_a_healthy_device() -> None:
    _, device = build_hybrid_3_slot()
    report = await device.async_update()

    assert report.complete
    assert report.failed == {}
    assert {"clock", "battery", "inverter_meter", "settings", "schedule"} <= (
        report.updated
    )
    # Identity is settled at setup and commands are write-only: neither is polled.
    assert "identity" not in report.updated
    assert "commands" not in report.updated


async def test_legacy_containment_matches_the_hybrid_contract() -> None:
    unit, device = build_legacy()
    await device.async_update()

    unit.input[3015] = 95  # generation today changes -> 9.5 kWh
    unit.fail_read(3022, ModbusTimeoutError("slow PV block"), register_type="input")
    report = await device.async_update()

    assert set(report.failed) == {"pv"}
    assert device.generation.power_generation_today == 9.5
    assert device.pv.pv_voltage_1 == 320.1  # previous value kept


async def test_a_failed_setup_raises_and_the_next_update_retries() -> None:
    """Identity is the poll's foundation; without it there is nothing partial."""
    unit, device = build_hybrid_3_slot()
    unit.fail_read(33004, ModbusTimeoutError("no serial"), register_type="input")

    with pytest.raises(ModbusTimeoutError):
        await device.async_update()
    assert device.variant is None

    unit.fail_read(33004, None, register_type="input")
    assert (await device.async_update()).complete


async def test_a_timeout_with_nothing_answered_is_fatal() -> None:
    """A silent inverter must cost one timeout, not one per component."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()

    unit.fail_read(33022, ModbusTimeoutError("inverter asleep"), register_type="input")
    unit.read_events.clear()
    with pytest.raises(ModbusTimeoutError):
        await device.async_update()

    # The first component is the probe: the poll gave up instead of walking on.
    assert len(unit.read_events) == 1


async def test_a_settings_poll_on_a_silent_inverter_is_fatal_too() -> None:
    """Each method starts its own report, so "nothing answered" means this poll."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()

    unit.fail_read(
        43007, ModbusTimeoutError("inverter asleep"), register_type="holding"
    )
    unit.read_events.clear()
    with pytest.raises(ModbusTimeoutError):
        await device.async_update_settings()

    assert len(unit.read_events) == 1


async def test_a_settings_timeout_inside_a_full_poll_is_contained() -> None:
    """The readings already answered, so the same failure only reports here."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()

    unit.fail_read(43007, ModbusTimeoutError("slow settings"), register_type="holding")
    report = await device.async_update()

    assert set(report.failed) == {"settings"}
    assert "schedule" in report.updated


async def test_a_refusal_on_the_first_component_is_still_contained() -> None:
    """An exception response proves the inverter is there, so the poll goes on."""
    unit, device = build_hybrid_3_slot()
    await device.async_update()

    unit.fail_read(33022, IllegalDataAddressError(), register_type="input")
    report = await device.async_update()

    assert set(report.failed) == {"clock"}
    assert "battery" in report.updated


async def test_legacy_fatal_timeout_matches_the_hybrid_contract() -> None:
    unit, device = build_legacy()
    await device.async_update()

    unit.fail_read(3005, ModbusTimeoutError("inverter asleep"), register_type="input")
    unit.read_events.clear()
    with pytest.raises(ModbusTimeoutError):
        await device.async_update()

    assert len(unit.read_events) == 1


async def test_an_unknown_serial_is_not_swallowed_by_the_containment() -> None:
    """Setup errors are not per-component failures and must keep surfacing."""
    unit, device = build_hybrid_3_slot("9999999999999999")

    for _ in range(2):  # permanent, not a transient one-poll failure
        with pytest.raises(UnknownInverterError):
            await device.async_update()

    assert isinstance(device, SolisHybrid3Slot)
    assert unit.read_events  # the serial was actually attempted
