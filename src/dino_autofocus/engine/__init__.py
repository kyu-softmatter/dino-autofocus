"""UI-independent engine: backend protocol and commands/events (guards, gates, records and
samples follow in T-002-2 and T-002-3).

Importing this package pulls in no UI toolkit, torch or pymmcore (checked by
tests/engine/test_contract.py); backends import their device libraries where they are used.
"""

from .backend import Backend, BackendInfo, Frame, PfsState, Positions, Readback
from .events import COMMAND_KINDS, EVENT_KINDS, Command, Event, EventSink, fan_out, queue_sink

__all__ = [
    "COMMAND_KINDS", "EVENT_KINDS", "Backend", "BackendInfo", "Command", "Event", "EventSink",
    "Frame", "PfsState", "Positions", "Readback", "fan_out", "queue_sink",
]
