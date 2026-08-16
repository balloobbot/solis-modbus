#!/usr/bin/env python3

"""Query a Solis inverter and print every value.

Reads one inverter once and dumps it to the terminal — the quickest way to
check a real device with no application around it.

One script covers all three register maps: connecting, counting and printing
are identical and only the class differs, and whoever is holding the inverter
usually has to try a map to find out which one its firmware speaks.

::

    uv run script/query.py 192.168.1.50 --unit 1 --framer rtu
    uv run script/query.py /dev/ttyUSB0 --transport serial --map legacy
"""

from __future__ import annotations

import argparse
import asyncio

from modbus_connection import ModbusError
from modbus_connection.cli_helper import (
    CountingUnit,
    add_connection_args,
    connect_from_args,
    print_component,
)

from solis_modbus import (
    SolisHybrid,
    SolisHybrid3Slot,
    SolisHybrid6Slot,
    SolisLegacy3000,
    UnknownInverterError,
    Variant,
)

# The inverter is RS-485 RTU; over TCP it is reached through a gateway, which
# presents it either transparently (rtu) or as native Modbus TCP (socket).
CONNECTIONS = (("serial", "rtu"), ("tcp", "rtu"), ("tcp", "socket"))

MAPS: dict[str, type[SolisHybrid] | type[SolisLegacy3000]] = {
    "3slot": SolisHybrid3Slot,
    "6slot": SolisHybrid6Slot,
    "legacy": SolisLegacy3000,
}

# The components each map polls, in read order. A hybrid's schedule attributes
# differ per variant, so they come from the class's own ``schedule_polled``.
HYBRID_COMPONENTS = (
    "clock",
    "generation",
    "pv",
    "ac_output",
    "status",
    "inverter_meter",
    "battery",
    "energy",
    "battery_current_limits",
    "external_meter",
    "settings",
)
LEGACY_COMPONENTS = ("generation", "pv", "ac_output")


def parse_variant(text: str) -> Variant:
    """Turn ``X1,MPPT4`` into the variant flags it names."""
    variant = Variant(0)
    for part in text.split(","):
        name = part.strip().upper()
        try:
            variant |= Variant[name]
        except KeyError:
            raise argparse.ArgumentTypeError(f"unknown variant flag {name!r}") from None
    return variant


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_connection_args(parser, connections=CONNECTIONS)
    parser.add_argument("--unit", type=int, default=1, help="Modbus unit id")
    parser.add_argument(
        "--map",
        choices=tuple(MAPS),
        default="3slot",
        help="which register map the inverter speaks (default: 3slot)",
    )
    parser.add_argument(
        "--variant",
        type=parse_variant,
        help="variant flags, e.g. X1,MPPT4; read from the serial number if omitted",
    )
    args = parser.parse_args()

    try:
        connection = await connect_from_args(args)
    except ModbusError as err:
        print(f"Could not connect: {err}")
        return 1

    counting = CountingUnit(connection.for_unit(args.unit))
    inverter = MAPS[args.map](counting, args.variant)
    try:
        await inverter.async_update()  # the first call sets the inverter up
    except UnknownInverterError as err:
        print(f"{err}; pass --variant to read it anyway")
        return 1
    except ModbusError as err:
        print(f"Could not read the inverter: {err}")
        return 1
    finally:
        await connection.close()

    variant = inverter.variant
    print(f"Variant: {variant.name if variant else 'unknown'}")
    names = (
        (*HYBRID_COMPONENTS, *inverter.schedule_polled)
        if isinstance(inverter, SolisHybrid)
        else LEGACY_COMPONENTS
    )
    print()
    print_component(inverter.identity, title="identity")
    for name in names:
        component = getattr(inverter, name)
        if component is None:  # not served by this variant
            continue
        print()
        print_component(component, title=name)
    print(f"\n{counting.reads} Modbus reads")
    return 0


raise SystemExit(asyncio.run(main()))
