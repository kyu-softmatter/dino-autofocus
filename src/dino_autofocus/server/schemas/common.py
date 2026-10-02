"""Shared wire models. These are the one place the API contract is written down: FastAPI turns
them into OpenAPI and the web shell generates its TypeScript types from that.

Each model wraps an engine dataclass; `kind` is a Literal built from the engine's kind list
and `data` stays a dict. Area routers (`server/api/<area>.py`) type their own payloads.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .contract import COMMAND_KINDS, EVENT_KINDS, Command, Event

CommandKind = Literal[COMMAND_KINDS]  # type: ignore[valid-type]
EventKind = Literal[EVENT_KINDS]  # type: ignore[valid-type]

# Command fields the browser does not send: the server sets them from the request and its
# own state. Who (user_id, from the login cookie, T-018), where (remote: a non-loopback
# client, D13), with what right (control_grant, from the operator's control, T-018), in which
# experiment session (session_id, the one the server opened, T-019), and the assistant's
# provenance (origin, proposal_id, conversation_id, confirmed_by: set only by the assistant
# routes, T-013, from the proposal card; this endpoint is the human path). t is when the
# server received it.
SERVER_STAMPED = ("origin", "user_id", "session_id", "proposal_id", "conversation_id",
                  "confirmed_by", "remote", "control_grant", "t")


class CommandIn(BaseModel):
    """A command for the engine, as the browser sends it. `start` names an operation in `op`
    with its `args`; `abort`, `confirm` and `update` name the running operation by `op_id`;
    `approve` / `reject` name a proposal by `op_id`; `lights_off` pre-empts anything. Any
    other field is refused (422): the server sets the rest (see SERVER_STAMPED)."""

    model_config = ConfigDict(extra="forbid")

    kind: CommandKind
    op: str = ""
    op_id: str = ""
    args: dict[str, Any] = Field(default_factory=dict)

    def to_engine(
        self, *, remote: bool, user_id: str | None = None, session_id: str | None = None,
        control_grant: str | None = None,
    ) -> Command:
        """The caller (server) passes what it knows about the request; until login and
        sessions are wired in (T-009b) user_id, session_id and control_grant stay None."""
        return Command(kind=self.kind, op=self.op, op_id=self.op_id, args=dict(self.args),
                       origin="human", user_id=user_id, session_id=session_id,
                       remote=remote, control_grant=control_grant, t=time.time())


class CommandAccepted(BaseModel):
    op_id: str


class EventOut(BaseModel):
    """`user_id` / `session_id` are the operation's (rule 12); None for engine-wide events."""

    kind: EventKind
    op_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    t: float
    user_id: str | None = None
    session_id: str | None = None

    @classmethod
    def from_engine(cls, ev: Event) -> EventOut:
        return cls(kind=ev.kind, op_id=ev.op_id, data=ev.data, t=ev.t, user_id=ev.user_id,
                   session_id=ev.session_id)


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
