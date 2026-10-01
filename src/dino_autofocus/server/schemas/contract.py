"""What the server assumes about the engine: command/event shapes and the runner interface.

TEMPORARY MIRROR. The engine contract (T-002, `engine/events.py`) and runner (T-011,
`engine/runner.py`) are not on main yet, so the kind lists, the two dataclasses and the
`EngineAPI` protocol are copied here with the same fields. tests/server/test_server_schemas.py
compares them with the engine as soon as `dino_autofocus.engine.events` imports. When T-011
merges, this module re-exports the engine's definitions instead of defining its own.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# same order as engine/events.py (T-002, 3354ebe)
COMMAND_KINDS = ("start", "abort", "confirm", "lights_off")

EVENT_KINDS = (
    "planned", "preflight_ok", "preflight_failed", "started", "progress", "frame_ready",
    "reading", "finished", "aborted", "error",
    "position", "light_changed", "property_set", "motion",
    "confirm_required", "confirmed",
    "log",
)


@dataclass
class Command:
    kind: str
    op: str = ""
    op_id: str = ""
    args: dict = field(default_factory=dict)
    t: float = field(default_factory=time.time)


@dataclass
class Event:
    kind: str
    op_id: str = ""
    data: dict = field(default_factory=dict)
    t: float = field(default_factory=time.time)


class EngineAPI(Protocol):
    """The engine as the server sees it. The server decides nothing: it hands commands over
    and passes events on. Sinks may be called from any thread."""

    def submit(self, cmd: Command) -> str: ...  # op_id; abort, confirm, lights_off too

    def subscribe(self, sink: Callable[[Event], None]) -> Callable[[], None]: ...  # unsubscribe

    def snapshot(self) -> dict[str, Any]: ...  # positions, lights, running op; JSON-native


@runtime_checkable
class FrameSource(Protocol):
    """Optional: an engine that can hand over its newest camera frame. The frame bridge reads
    it when a `frame_ready` event arrives. Not part of the T-011 interface yet; see the T-009
    report. `meta` is JSON-native (t, x_um, y_um, z_um, exposure_ms, bit_depth, ...)."""

    def latest_frame(self) -> tuple[Any, dict[str, Any]] | None: ...  # (uint16 ndarray, meta)
