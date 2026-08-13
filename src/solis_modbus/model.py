"""What the device classes hand back from a poll."""

from __future__ import annotations

from dataclasses import dataclass

from modbus_connection import ModbusError


@dataclass(frozen=True)
class UpdateReport:
    """What one poll refreshed, by the device's component attribute names.

    A failed component kept its previous values and did not notify; the error
    that failed it rides along. A dead link is never in here — the update
    raises ``ModbusConnectionError`` instead of reporting partial silence.
    """

    updated: set[str]
    failed: dict[str, ModbusError]

    @property
    def complete(self) -> bool:
        """Whether every polled component refreshed."""
        return not self.failed
