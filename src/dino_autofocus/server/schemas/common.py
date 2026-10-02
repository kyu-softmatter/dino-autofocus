"""Shared wire models. These are the one place the API contract is written down: FastAPI turns
them into OpenAPI and the web shell generates its TypeScript types from that.

Each model wraps an engine dataclass field for field; `kind` is a Literal built from the
engine's kind list and `data` stays a dict. Area routers (`server/api/<area>.py`) type their
own payloads.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from .contract import COMMAND_KINDS, EVENT_KINDS, ORIGINS, Command, Event

CommandKind = Literal[COMMAND_KINDS]  # type: ignore[valid-type]
EventKind = Literal[EVENT_KINDS]  # type: ignore[valid-type]
Origin = Literal[ORIGINS]  # type: ignore[valid-type]

# Command fields the client does not send: the server stamps them
SERVER_STAMPED = ("user_id", "t")


class CommandIn(BaseModel):
    """A command for the engine. `start` names an operation in `op` with its `args`; `abort`
    and `confirm` name the running operation by `op_id`; `lights_off` pre-empts anything.
    An `assistant` command is a proposal until a human confirms it."""

    kind: CommandKind
    op: str = ""
    op_id: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    origin: Origin = "human"
    session_id: str | None = None

    def to_engine(self) -> Command:
        # user_id stays None until login exists (T-018); it will come from the session
        # cookie, never from the request body. t is when the server received the command.
        return Command(kind=self.kind, op=self.op, op_id=self.op_id, args=dict(self.args),
                       origin=self.origin, user_id=None, session_id=self.session_id,
                       t=time.time())


class CommandAccepted(BaseModel):
    op_id: str


class EventOut(BaseModel):
    kind: EventKind
    op_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    t: float

    @classmethod
    def from_engine(cls, ev: Event) -> EventOut:
        return cls(kind=ev.kind, op_id=ev.op_id, data=ev.data, t=ev.t)


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    engine: str
    remote_view: bool
    remote_abort: bool  # D13: a remote viewer may send abort, and nothing else


class ApiError(BaseModel):
    detail: str


class ShutdownIn(BaseModel):
    reason: str = "api"


class ShutdownAccepted(BaseModel):
    """The engine has stopped (abort, lights off with readback, records finished); the server
    exits next. `already` is true when another exit path had stopped the engine first."""

    reason: str
    already: bool


# --- WebSocket messages (not REST routes; added to the OpenAPI components by app.py) ---


class WsEvent(BaseModel):
    """`/ws/events`, server -> client."""

    type: Literal["event"] = "event"
    event: EventOut


class WsCommand(BaseModel):
    """`/ws/events`, client -> server. Accepted only from the microscope PC (loopback)."""

    type: Literal["command"] = "command"
    command: CommandIn


class WsAccepted(BaseModel):
    """`/ws/events`, server -> client: reply to a `WsCommand`."""

    type: Literal["accepted"] = "accepted"
    op_id: str


class WsError(BaseModel):
    """`/ws/events`, server -> client: a refused or malformed message. `status` follows HTTP
    (400 refused by the engine, 403 not allowed from here, 422 bad message,
    503 shutting down)."""

    type: Literal["error"] = "error"
    status: int
    detail: str


class WsFrame(BaseModel):
    """`/ws/frames`, server -> client. Always sent as a text message immediately followed by
    one binary message holding the JPEG (`jpeg_bytes` long). Pixel values were mapped
    linearly from `display_min..display_max` (raw counts) to 0..255."""

    type: Literal["frame"] = "frame"
    seq: int
    t: float
    width: int
    height: int
    binning: int
    source_width: int
    source_height: int
    display_min: float
    display_max: float
    jpeg_bytes: int
    meta: dict[str, Any] = Field(default_factory=dict)


WS_MODELS: tuple[type[BaseModel], ...] = (WsEvent, WsCommand, WsAccepted, WsError, WsFrame)
