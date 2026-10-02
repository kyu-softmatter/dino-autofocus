"""What the server assumes about the engine: command/event shapes and the runner interface.

Commands, events and their kind lists come from the engine (T-002, `engine/events.py`).
`EngineAPI` and `FrameSource` are the server's own copy until the runner (T-011,
`engine/runner.py`) defines them; then this module re-exports those instead.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from ...engine.events import COMMAND_KINDS, EVENT_KINDS, ORIGINS, Command, Event

__all__ = [
    "COMMAND_KINDS", "EVENT_KINDS", "ORIGINS", "Command", "EngineAPI", "Event", "FrameSource",
]


class EngineAPI(Protocol):
    """The engine as the server sees it. The server decides nothing: it hands commands over
    and passes events on. Sinks may be called from any thread."""

    def submit(self, cmd: Command) -> str: ...  # op_id; abort, confirm, lights_off too

    def subscribe(self, sink: Callable[[Event], None]) -> Callable[[], None]: ...  # unsubscribe

    def snapshot(self) -> dict[str, Any]: ...  # positions, lights, running op; JSON-native


@runtime_checkable
class FrameSource(Protocol):
    """Optional: an engine that can hand over its newest camera frame. The frame bridge reads
    it when a `frame_ready` event arrives. Not part of the T-011 interface yet (raised with
    the manager). `meta` is JSON-native (t, x_um, y_um, z_um, exposure_ms, bit_depth, ...)."""

    def latest_frame(self) -> tuple[Any, dict[str, Any]] | None: ...  # (uint16 ndarray, meta)
