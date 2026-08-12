"""Which registers an inverter serves, keyed off its serial number.

The integration gates every entity on a bitmask of inverter traits. For Solis
only three of those bits are ever used: the phase count (``X1``/``X3``) and the
MPPT count (``MPPT3``/``MPPT4``). ``EPS`` and ``DCB`` gate nothing in the Solis
plugins, and every entity is ``HYBRID``, so both collapse away here.
"""

from __future__ import annotations

from enum import IntFlag


class UnknownInverterError(Exception):
    """The serial number matches no known Solis variant.

    Pass ``variant=`` to the inverter to model it anyway.
    """


class Variant(IntFlag):
    """The traits that decide which fields an inverter serves."""

    X1 = 0x1
    """Single phase."""

    X3 = 0x2
    """Three phase."""

    MPPT3 = 0x4
    """A third PV string."""

    MPPT4 = 0x8
    """A third and fourth PV string."""

    @property
    def pv_strings(self) -> int:
        """How many PV strings this inverter reports."""
        if self & Variant.MPPT4:
            return 4
        if self & Variant.MPPT3:
            return 3
        return 2


# Serial-number prefix to variant, as the integration's determineInverterType
# derives it. The comment is the model the integration names for that prefix.
HYBRID_SERIAL_PREFIXES: dict[str, Variant] = {
    "1801": Variant.X1,  # PV Only S6-GR1P 1-3K
    "1802": Variant.X1,  # PV Only S6-GR1P 2.5-6K
    "0602": Variant.X1,  # Hybrid Gen5 3kW - 48v
    "0102": Variant.X1,  # AC? Gen5 3kW - 48v
    "010F": Variant.X1,  # Hybrid Gen5 3kW - 48v
    "110F": Variant.X1,  # Hybrid Gen5 5kW - 48v
    "114F": Variant.X1,  # Hybrid Gen5 6K - 48V
    "134F": Variant.X1,  # Hybrid Gen5 5kW - 48V
    "140C": Variant.X1,  # Hybrid Gen5 5kW - HV
    "143": Variant.X1,  # Hybrid Gen5 5kW - 48V
    "160F3": Variant.X1,  # Hybrid Gen5 5kW - 48v
    "160F4": Variant.X1,  # Hybrid Gen5 3.6kW - 48v
    "160F5": Variant.X1,  # Hybrid Gen5 3.6kW - 48v
    "103305": Variant.X3 | Variant.MPPT4,  # Hybrid Gen6 8kW - HV
    "103306": Variant.X3 | Variant.MPPT4,  # Hybrid Gen6 10kW - HV
    "103314": Variant.X3 | Variant.MPPT4,  # Hybrid Gen6 12kW - HV
    "103330": Variant.X3,  # Hybrid Gen6 10kW - 48v
    "110C": Variant.X3,  # Hybrid Gen5 0CA2 / 0C92 10kW - HV
    "114C": Variant.X3,  # Hybrid Gen5 10kW - HV
    "1805": Variant.X3,  # PV Only Gen5 5-20kW
    "2051": Variant.X1,  # Hybrid Gen6 EO1p-48v 5kW
    "6031": Variant.X1,  # Hybrid Gen5 3105 / 3122 Model 6kW - 48V
    "6041": Variant.X1,  # Hybrid Gen5 3106 3kW - 48V
    "1031": Variant.X1,  # Hybrid Gen5 3104 Model 5kW - 48V
    "1053": Variant.X3 | Variant.MPPT3,  # Hybrid Gen6 30kW - HV
}

LEGACY_SERIAL_PREFIXES: dict[str, Variant] = {
    "303105": Variant.X1,  # Hybrid Gen5 3kW
    "363105": Variant.X1,  # Hybrid Gen5 3.6kW
    "463105": Variant.X1,  # Hybrid Gen5 4.6kW
    "503105": Variant.X1,  # Hybrid Gen5 5kW
    "603105": Variant.X1,  # Hybrid Gen5 6kW
    "603122": Variant.X1,  # Hybrid Gen5 3.6kW
    "110CA22": Variant.X3,  # Hybrid Gen5 10kW 3Phase
}


def variant_from_serial(
    serial: str | None, prefixes: dict[str, Variant]
) -> Variant | None:
    """The variant a serial number identifies, or None if unrecognised."""
    if not serial:
        return None
    match = max((p for p in prefixes if serial.startswith(p)), key=len, default=None)
    return prefixes[match] if match is not None else None
