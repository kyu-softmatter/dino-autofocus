from __future__ import annotations

import dataclasses
import typing

import pytest
from pydantic import ValidationError

from dino_autofocus.server.schemas import (
    COMMAND_KINDS,
    EVENT_KINDS,
    Command,
    CommandIn,
    CommandKind,
    Event,
    EventKind,
    EventOut,
)


def test_literals_follow_kind_lists():
    assert typing.get_args(CommandKind) == COMMAND_KINDS
    assert typing.get_args(EventKind) == EVENT_KINDS


def test_matches_engine_contract():
    """Fails as soon as the server's mirror and the engine contract (T-002) disagree."""
    events = pytest.importorskip("dino_autofocus.engine.events")
    assert events.COMMAND_KINDS == COMMAND_KINDS
    assert events.EVENT_KINDS == EVENT_KINDS
    for mine, theirs in ((Command, events.Command), (Event, events.Event)):
        assert [f.name for f in dataclasses.fields(mine)] == \
            [f.name for f in dataclasses.fields(theirs)]
    # what the server builds, the engine accepts, and back
    cmd = CommandIn(kind="start", op="status", args={"a": 1}).to_engine()
    assert events.Command(**dataclasses.asdict(cmd)).op == "status"
    ev = events.Event(kind="position", data={"z_um": 3000.0})
    assert EventOut.from_engine(ev).data == {"z_um": 3000.0}


def test_models_wrap_dataclasses():
    cmd = CommandIn(kind="confirm", op_id="op3", args={"key": "oil", "ok": True}).to_engine()
    assert isinstance(cmd, Command)
    assert set(dataclasses.asdict(cmd)) == {f.name for f in dataclasses.fields(Command)}
    out = EventOut.from_engine(Event(kind="log", data={"msg": "hi"}))
    assert set(out.model_dump()) == {f.name for f in dataclasses.fields(Event)}
    with pytest.raises(ValidationError):
        CommandIn(kind="move_z")
    with pytest.raises(ValidationError):
        EventOut(kind="teleported", t=0.0)
