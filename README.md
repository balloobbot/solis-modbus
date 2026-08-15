# solis-modbus

A standalone Python library that reads and controls **Ginlong Solis** inverters
over Modbus, exposed as a normal, object-oriented Python API.

The register maps are based on
[homeassistant-solax-modbus](https://github.com/wills106/homeassistant-solax-modbus)
(Apache-2.0) — specifically its `plugin_solis`, `plugin_solis_fb00` and
`plugin_solis_old` — and are verified in tests against an in-memory mock of the
inverter.

## Design

- It **consumes a connection abstraction**, not a backend: every device class
  takes a [`modbus_connection.ModbusUnit`](https://github.com/balloob/modbus-connection).
  You own the connection and choose the backend (tmodbus, pymodbus, …).
- **ASCII framing over TCP is not supported.** The library never opens a
  connection, so it can neither accept nor forward a framer choice; if you build
  the connection yourself, use RTU-over-TCP or plain TCP. Solis inverters and the
  usual RS485 gateways do not speak Modbus ASCII over TCP, and the integration's
  ASCII affordance is deliberately not carried over.
- **Setup once, then poll.** The first `async_update()` reads the serial number,
  settles which variant the inverter is, and builds only the components that
  variant serves. Later polls read each of those components in turn. A setup
  that fails leaves the inverter unset up, so the next poll retries it.
- Reads are capped at the width the integration uses for Solis — 40 registers
  (48 on the legacy map). No readable address ranges are declared, because the
  integration does not know any: it forms blocks purely by that width, so gap
  planning here reads a subset of what the integration reads, never more.

## The three protocol variants

Solis inverters speak one of three register maps. Pick the class that matches
yours; they are separate modules because the maps genuinely differ.

| Class | Module | Register map |
| --- | --- | --- |
| `SolisHybrid3Slot` | `hybrid_3_slot` | Hybrid map (33xxx input + 43xxx holding), **three combined charge/discharge slots** at 43143, plus a packed special-settings word at 43249. |
| `SolisHybrid6Slot` | `hybrid_6_slot` | The **same** 99 base registers, but the extended schedule at 43707: **six charge and six discharge slots**, each with its own target SoC, current and voltage, gated by an enable word. No 43249. |
| `SolisLegacy3000` | `legacy_3000` | The older map: **read-only input registers in the 3000 block**. Generation counters, four PV strings and AC output only — no battery, meter or scheduling data. Serial number at 3061 rather than 33004. |

The two hybrid variants are identical below register 43141 — same addresses,
scales, signedness and variant gating. Only the schedule differs, and with it
the set of storage-mode codes register 43110 accepts (`EnergyStorageMode3Slot`
vs `EnergyStorageMode6Slot`: the three-slot firmware has extra "no timed
charge/discharge" modes, and codes for the same mode differ — Self-Use is 35 on
one and 33 on the other).

## Inverter variants

Which registers an inverter actually serves depends on its model, which the
integration derives from the serial-number prefix. Only two traits matter for
Solis, and `Variant` models both:

- **Phase count** — `X1` (single-phase) or `X3` (three-phase). They share
  addresses but mean different things: input 33073 is `inverter_voltage` on an
  X1 and `grid_voltage_l1` on an X3, and holding 43073 takes a different option
  map on each. Only X1 inverters serve the battery current limits at 33206.
- **MPPT count** — `MPPT3` and `MPPT4` add a third and fourth PV string at
  33053-33056.

Each is modelled as its own component class, so a field that does not exist on
your inverter is not declared and never read. `variant_from_serial()` exposes
the prefix table directly; pass `variant=` to a device class to override it for
a model the table has not caught up with.

## Use

```python
import asyncio

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

from solis_modbus import EnergyStorageMode3Slot, SolisHybrid3Slot


async def main() -> None:
    # An RTU-over-TCP gateway. ASCII framing is not supported.
    connection = ModbusConnection(
        ModbusTcpParams(host="192.168.1.50", port=502, framer="rtu")
    )
    try:
        inverter = SolisHybrid3Slot(connection.for_unit(1))
        await inverter.async_update()

        print("Serial:", inverter.identity.serial_number)
        print("Variant:", inverter.variant)
        print("Status:", inverter.status.inverter_status)
        print("PV power:", inverter.pv.pv_total_power, "W")
        print("Battery SoC:", inverter.battery.battery_soc, "%")
        print("House load:", inverter.battery.house_load, "W")
        print("Storage mode:", inverter.storage_mode)
        print("Today:", inverter.generation.power_generation_today, "kWh")

        # Settings are read back and written through the same fields.
        await inverter.settings.write("battery_minimum_soc", 25)

        # Write-only registers live on `commands`, and are never polled.
        await inverter.commands.write(
            "energy_storage_control_switch", EnergyStorageMode3Slot.SELF_USE
        )

        # A time slot's registers are written in one request, as the
        # integration writes them.
        await inverter.schedule.write_slot(
            0,
            charge_start=(1, 30),
            charge_end=(5, 30),
            discharge_start=(17, 0),
            discharge_end=(20, 0),
        )
    finally:
        await connection.close()


asyncio.run(main())
```

Each sub-system is an independently updatable `Component` with its own update
listeners, so a consumer can refresh or subscribe to just the part it shows.

A poll reads each sub-system independently, the way the integration reads its
blocks: one slow or refused block does not take the rest of the poll with it.
`async_update()` returns an `UpdateReport` — a failed component keeps its
previous values, does not notify its listeners, and is listed by attribute name
with its error, while every other component refreshes and notifies once the
whole poll is done. A dead link (`ModbusConnectionError`) raises, and so does a
timeout before any component has answered — an inverter that is simply not
responding is not walked block by block, paying a timeout for each:

```python
report = await inverter.async_update()
for name, error in report.failed.items():
    print(f"{name} kept its previous values: {error}")
```

Containment is per component, so a component's own registers are still
all-or-nothing: `settings` covers three separate holding blocks, and the
six-slot `schedule` covers three reads of 43707-43791, each failing as a unit.

For an issue report, `async_read_raw()` dumps every register the inverter reads
undecoded, keyed by address space and address. It covers the serial number as
well, which only setup reads; the write-only command registers stay out. It
fires no update listeners — a download is not a poll, though the fields it
reads do refresh.

### Splitting the poll

A full poll is 15 requests on a three-slot X1, 14 on a three-slot X3, 16 on a
six-slot and 3 on the legacy map. Everything that only changes when something
writes it already sits in a component of its own, so a consumer can give those
their own, slower schedule and leave the rest where it is:

| Component | Requests | Blocks |
| --- | --- | --- |
| `settings` | 3 | 43007+18, 43073+2, 43116+3 |
| `schedule` (three-slot) | 1 | 43141+30 |
| `schedule` (six-slot) | 3 | 43707+40, 43747+40, 43787+5 |
| `special_settings` (three-slot) | 1 | 43249+1 |

That is 5 requests of 15 on a three-slot X1, 5 of 14 on a three-slot X3 and 6 of
16 on a six-slot. `clock` (33022+6) is a further one if you can live with the
inverter's time being minutes old. The legacy map is read-only telemetry with no
settings at all, so its 3 requests do not split.

Nothing else is worth moving. The only configuration register outside those
components is the storage-mode word read back at input 33132, and it rides
inside the 33132+19 block the live battery readings pay for anyway — carving it
out would add a request rather than save one, on all three hybrid variants.

## Field names

Field names are the integration's entity keys, so a mapping lifted from there
keeps working. Three deliberate departures:

- The repeated time slots are `repeating_group`s, so the index moved out of the
  name: `timed_charge_start_hours_2` is
  `schedule.slots[1].charge_start_hours` (three-slot) and
  `timed_discharge_volt_4` is `schedule.discharge_slots[3].voltage` (six-slot).
- `meter_apparent_power_L2` is spelled `meter_apparent_power_l2`.
- Sensors the integration computes in Home Assistant rather than reading — the
  per-string PV powers and the direction-split battery power — are properties
  (`pv.pv_power_1`, `battery.battery_input_energy`) rather than fields, since
  they have no register behind them.

Home-Assistant-only metadata (icons, device classes, entity categories,
translation keys, scan groups) is dropped.

## Development

```bash
uv sync
uv run pytest
uv run ruff format --check . && uv run ruff check .
uv run mypy
```

## License

Apache-2.0, inherited from
[homeassistant-solax-modbus](https://github.com/wills106/homeassistant-solax-modbus),
of which this is a derived work.
