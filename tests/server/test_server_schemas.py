from __future__ import annotations

import dataclasses
import typing

import pytest
from pydantic import ValidationError

from dino_autofocus.engine import events
from dino_autofocus.server.schemas import (
    SERVER_STAMPED,
    CommandIn,
    CommandKind,
    EventKind,
    EventOut,
    Origin,
)


def test_literals_follow_engine_kind_lists():
    assert typing.get_args(CommandKind) == events.COMMAND_KINDS
    assert typing.get_args(EventKind) == events.EVENT_KINDS
    assert typing.get_args(Origin) == events.ORIGINS


def test_models_wrap_engine_dataclasses():
    """Fails when the engine gains or loses a field the wire models do not follow."""
    command_fields = {f.name for f in dataclasses.fields(events.Command)}
    assert set(CommandIn.model_fields) == command_fields - set(SERVER_STAMPED)
    assert set(SERVER_STAMPED) <= command_fields
    assert set(EventOut.model_fields) == {f.name for f in dataclasses.fields(events.Event)}


def test_command_to_engine():
    cmd = CommandIn(kind="confirm", op_id="op3", args={"key": "oil", "ok": True},
                    session_id="s1").to_engine()
    assert isinstance(cmd, events.Command)
    assert (cmd.origin, cmd.user_id, cmd.session_id) == ("human", None, "s1")
    assert cmd.t > 0
    assert events.Command.from_json(cmd.to_json()) == cmd
    # the body cannot claim a user: user_id comes from login (T-018), never from the client
    assert CommandIn.model_validate({"kind": "abort", "user_id": "x"}).to_engine().user_id is None


def test_event_from_engine():
    out = EventOut.from_engine(events.Event(kind="position", data={"z_um": 3000.0}))
    assert (out.kind, out.data) == ("position", {"z_um": 3000.0})


def test_unknown_kinds_refused():
    with pytest.raises(ValidationError):
        CommandIn(kind="move_z")
    with pytest.raises(ValidationError):
        CommandIn(kind="start", origin="robot")
    with pytest.raises(ValidationError):
        EventOut(kind="teleported", t=0.0)
