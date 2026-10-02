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
)


def test_literals_follow_engine_kind_lists():
    assert typing.get_args(CommandKind) == events.COMMAND_KINDS
    assert typing.get_args(EventKind) == events.EVENT_KINDS


def test_models_wrap_engine_dataclasses():
    """Fails when the engine gains or loses a field the wire models do not follow."""
    command_fields = {f.name for f in dataclasses.fields(events.Command)}
    assert set(CommandIn.model_fields) == command_fields - set(SERVER_STAMPED)
    assert set(SERVER_STAMPED) <= command_fields
    assert set(EventOut.model_fields) == {f.name for f in dataclasses.fields(events.Event)}


def test_command_to_engine():
    cmd = CommandIn(kind="confirm", op_id="op3", args={"key": "oil", "ok": True}).to_engine(
        remote=False, user_id="op@example.test", session_id="s1", control_grant="g1")
    assert isinstance(cmd, events.Command)
    stamped = (cmd.origin, cmd.user_id, cmd.session_id, cmd.remote, cmd.control_grant)
    assert stamped == ("human", "op@example.test", "s1", False, "g1")
    assert (cmd.proposal_id, cmd.conversation_id, cmd.confirmed_by) == (None, None, None)
    assert cmd.t > 0
    assert events.Command.from_json(cmd.to_json()) == cmd
    assert CommandIn(kind="abort").to_engine(remote=True).remote is True


@pytest.mark.parametrize("field", SERVER_STAMPED)
def test_body_cannot_set_server_stamped_fields(field):
    """remote, control_grant, user_id, session_id and the assistant provenance come from the
    server, never from the browser: a body that carries one is refused, not half-applied."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CommandIn.model_validate({"kind": "abort", field: "x"})


def test_event_from_engine():
    out = EventOut.from_engine(events.Event(kind="position", data={"z_um": 3000.0}))
    assert (out.kind, out.data) == ("position", {"z_um": 3000.0})
    assert (out.user_id, out.session_id) == (None, None)
    ev = events.Event(kind="finished", op_id="scan_4x_1", user_id="op@example.test",
                      session_id="s1")
    out = EventOut.from_engine(ev)
    assert (out.user_id, out.session_id) == ("op@example.test", "s1")


def test_unknown_kinds_refused():
    with pytest.raises(ValidationError):
        CommandIn(kind="move_z")
    with pytest.raises(ValidationError):
        EventOut(kind="teleported", t=0.0)
