"""Engine runner contract with FakeBackend and fake operations: normal end, abort, lights-off
pre-emption, confirm pairing, single ownership, exception exit paths, proposals, rule 12
(control grant, experiment session, permission table), update, awaiting_return, D13 remote
abort, D14 viewer loss, the acquisition stream, frames, plan-only, shutdown and the
unclean-shutdown mark.

Every runner a test builds is shut down by the `make` fixture, so no thread outlives a test.
"""

from __future__ import annotations

import json
import threading

import pytest

from dino_autofocus.engine import Command, Event
from dino_autofocus.engine.backend import GUARD_TOKEN  # test fakes stand in for the guards
from dino_autofocus.engine.runner import (
    PERMISSIONS,
    AllowAll,
    CommandRefused,
    EngineAPI,
    Operation,
    Registry,
    Runner,
    RunnerConfig,
    folder_records,
    permission,
)

T = 5.0  # generous wait; every wait returns as soon as its event arrives
USER, SESSION = "op@example.test", "20261001_1540_1"
QUIET = RunnerConfig(position_interval_s=None)


class Collect:
    """A sink that lets the test wait for an event."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self._cond = threading.Condition()

    def __call__(self, ev: Event) -> None:
        with self._cond:
            self.events.append(ev)
            self._cond.notify_all()

    def wait(self, kind: str, op_id: str | None = None) -> Event:
        def find() -> Event | None:
            return next((e for e in self.events
                         if e.kind == kind and (op_id is None or e.op_id == op_id)), None)

        with self._cond:
            assert self._cond.wait_for(lambda: find() is not None, T), (kind, op_id, self.kinds())
            return find()

    def kinds(self, op_id: str | None = None) -> list[str]:
        return [e.kind for e in self.events
                if (op_id is None or e.op_id == op_id) and e.kind != "position"]

    def logs(self, rule: str) -> list[Event]:
        return [e for e in self.events if e.kind == "log" and e.data.get("rule") == rule]


class MemRecord:
    def __init__(self, meta: dict) -> None:
        self.meta, self.events, self.end = meta, [], None
        self.dir = f"mem://{meta['op_id']}"

    def event(self, ev: Event) -> None:
        self.events.append(ev)

    def close(self, end: dict) -> None:
        self.end = end


# -- fake operations


class Steps(Operation):
    name = "steps"

    def plan(self) -> dict:
        return {"n": self.args.get("n", 3)}

    def run(self) -> dict:
        self.ctx.backend.lamp_on(token=GUARD_TOKEN)
        for i in range(self.args.get("n", 3)):
            self.ctx.check()
            self.ctx.progress(f"step {i}", step=i, n_steps=self.args.get("n", 3))
        return {"done": True}


class Hold(Operation):
    """Lamp on, then waits until aborted."""

    name = "hold"

    def run(self) -> dict:
        self.ctx.backend.lamp_on(token=GUARD_TOKEN)
        self.ctx.progress("holding")
        self.ctx.sleep(60)
        return {}


class Watched(Hold):
    name = "watched"
    watched = True


class Boom(Operation):
    name = "boom"

    def run(self) -> dict:
        self.ctx.backend.lamp_on(token=GUARD_TOKEN)
        raise RuntimeError("stage lost")


class Oil(Operation):
    name = "oil"

    def run(self) -> dict:
        ans = self.ctx.confirm("load_immersion", "Load oil, then press Loading done",
                               options=("done",), kind="manual_step",
                               context={"step": "load_immersion", "immersion": "oil"})
        return {"answer": ans["answer"]}


class Tare(Operation):
    name = "tare"
    exclusive = False
    motion = False

    def run(self) -> dict:
        return {"tared": True}


class Trace(Operation):
    name = "trace"
    updatable = frozenset({"speed_um_s"})

    def run(self) -> dict:
        self.ctx.progress("tracing")
        while self.args.get("speed_um_s", 0) < 500:
            self.ctx.sleep(0.01)
        return {"speed_um_s": self.args["speed_um_s"]}


class Escape(Operation):
    name = "escape"

    def run(self) -> dict:
        return {"state": "awaiting_return", "return_xy": [8026.0, 571.6]}


class GoBack(Operation):
    """Stands in for objective_change: only `resume=True` is the return."""

    name = "go_back"

    def returns_to_sample(self) -> bool:
        return bool(self.args.get("resume"))

    def run(self) -> dict:
        return {}


class Snapper(Operation):
    name = "snapper"
    snaps = True

    def plan(self) -> dict:
        return {"tiles": self.args.get("tiles", 4)}

    def run(self) -> dict:
        self.ctx.publish_frame(self.ctx.backend.snap())
        if self.args.get("fail"):
            raise ValueError("bad frame")
        return {}


class Peeks(Operation):
    """A bad plan(): it touches the backend."""

    name = "peeks"

    def plan(self) -> dict:
        return {"z": self.ctx.backend.positions().z_um}


class SampleOpen(Operation):
    name = "sample_open"
    exclusive = False
    motion = False

    def run(self) -> dict:
        sid = self.args.get("sample_id")
        self.ctx.set_current_sample(sid, reserved=self.ctx.session_started_at is None)
        return {"sample_id": sid}


class Status(Operation):
    name = "status"
    motion = False

    def run(self) -> dict:
        return {"objective": "4x", "z_um": 2900.0}


class LightSet(Operation):
    name = "light_set"
    motion = False
    keep_lights_on_finish = True

    def run(self) -> dict:
        self.ctx.backend.lamp_on(token=GUARD_TOKEN)
        return {}


class Approach(Operation):
    """Stands in for an op that calls FocusAxis.approach()."""

    name = "approach_op"
    approaches = True

    def clearance(self):
        return (lambda z: True) if self.args.get("clear") else None

    def run(self) -> dict:
        return {}


class Stream:
    def __init__(self) -> None:
        self.on, self.calls = True, []

    def running(self) -> bool:
        return self.on

    def pause(self) -> None:
        self.on = False
        self.calls.append("pause")

    def resume(self) -> None:
        self.on = True
        self.calls.append("resume")

    def stop(self) -> None:
        self.on = False
        self.calls.append("stop")


REG = Registry()
for _cls in (Steps, Hold, Watched, Boom, Oil, Tare, Trace, Escape, GoBack, Snapper, Peeks,
             SampleOpen, Status, LightSet, Approach):
    REG.register(_cls)


def start(op: str, origin: str = "human", **args) -> Command:
    return Command("start", op=op, args=args, origin=origin, user_id=USER, session_id=SESSION)


def cmd(kind: str, op_id: str = "", **args) -> Command:
    return Command(kind, op_id=op_id, args=args, user_id=USER, session_id=SESSION)


def refuse(r: Runner, c: Command) -> CommandRefused:
    with pytest.raises(CommandRefused) as e:
        r.submit(c)
    return e.value


@pytest.fixture
def records() -> dict[str, MemRecord]:
    return {}


@pytest.fixture
def make(fake, records):
    made: list[Runner] = []

    def build(session: str | None = SESSION, **kw) -> tuple[Runner, Collect]:
        def factory(meta: dict) -> MemRecord:
            records[meta["op_id"]] = MemRecord(meta)
            return records[meta["op_id"]]

        kw.setdefault("control", AllowAll())
        kw.setdefault("config", QUIET)
        r = Runner(fake, registry=REG, records=factory, **kw)
        made.append(r)
        sink = Collect()
        r.subscribe(sink)
        r.start()
        if session:
            r.set_experiment_session(session, 1000.0)
        return r, sink

    yield build
    for r in made:  # aborts what is left, switches off, joins the poller
        fake.all_off_raises = False
        r.shutdown("test teardown", timeout=T)
        assert r.wait_idle(T)


# -- life cycle


def test_runner_is_the_engine_api(make):
    r, _ = make()
    assert isinstance(r, EngineAPI)
    snap = r.snapshot()
    json.dumps(snap)
    assert "steps" in snap["operations"] and "lights_off" not in snap["operations"]
    assert snap["session"] == {"session_id": SESSION, "started_at": 1000.0}


def test_normal_run_ends_with_lights_off_readback_and_a_record(make, fake, records):
    r, sink = make()
    op_id = r.submit(start("steps", n=2))
    fin = sink.wait("finished", op_id)
    assert sink.kinds(op_id) == ["planned", "preflight_ok", "started", "progress", "progress",
                                 "property_set", "property_set", "light_changed", "finished"]
    assert fin.data["summary"] == {"done": True}
    assert fin.data["end_state"]["lights"]["verified"] is True
    assert fake.lights == {"DiaLamp": "0", "Aura": "0"}
    assert fin.user_id == USER and fin.session_id == SESSION
    started = sink.wait("started", op_id).data
    assert started["origin"] == "human" and started["confirmed_by"] == USER
    rec = records[op_id]
    assert [e.kind for e in rec.events][-1] == "finished"
    assert rec.end["state"] == "finished" and fin.data["record_dir"] == rec.dir
    snap = r.snapshot()
    assert snap["recent"][-1]["state"] == "finished" and snap["owner"] is None


def test_abort_stops_the_operation_and_still_switches_off(make, fake):
    r, sink = make()
    op_id = r.submit(start("hold"))
    sink.wait("progress", op_id)
    assert fake.lights["DiaLamp"] == "1"
    r.submit(cmd("abort", op_id, why="Esc"))
    ab = sink.wait("aborted", op_id)
    assert ab.data["why"] == "Esc"
    assert ab.data["end_state"]["lights"]["off"] is True
    assert fake.lights == {"DiaLamp": "0", "Aura": "0"}


def test_lights_off_preempts_the_running_operation(make, fake):
    r, sink = make()
    held = r.submit(start("hold"))
    sink.wait("progress", held)
    off = r.submit(Command("lights_off"))  # no grant, no session: stops always get through
    fin = sink.wait("finished", off)
    ab = sink.wait("aborted", held)
    assert ab.data["why"] == "lights_off"
    assert sink.events.index(ab) < sink.events.index(fin)
    assert fin.data["summary"] == {"ok": True, "aura_state": "0", "dialamp_state": "0",
                                   "verified": True}
    assert fake.lights == {"DiaLamp": "0", "Aura": "0"}
    assert r.wait_idle(T) and r.snapshot()["owner"] is None


def test_lights_off_is_a_command_kind_and_reports_an_unverified_readback(make, fake):
    r, sink = make()
    assert "command kind" in refuse(r, start("lights_off")).why
    fake.stuck.add("DiaLamp")
    fake.lights["DiaLamp"] = "1"
    op_id = r.submit(Command("lights_off"))
    fin = sink.wait("finished", op_id)
    assert fin.data["summary"]["verified"] is False
    assert sink.wait("error", op_id).data["where"] == "readback"
    fake.stuck.clear()
    fake.all_off = lambda: []  # an empty readback proves nothing
    empty = r.submit(Command("lights_off"))
    assert sink.wait("finished", empty).data["summary"]["verified"] is False
    del fake.all_off


# -- confirm, ownership, exits


def test_confirm_pairs_by_op_id_and_key_and_records_the_manual_step(make, records):
    r, sink = make()
    op_id = r.submit(start("oil"))
    req = sink.wait("confirm_required", op_id)
    assert req.data["kind"] == "manual_step"
    assert r.snapshot()["pending_confirms"][0]["key"] == "load_immersion"
    wrong = refuse(r, cmd("confirm", op_id, key="wrong", ok=True))
    assert "no confirm_required 'wrong'" in wrong.why
    refuse(r, cmd("confirm", "steps_999", key="load_immersion", ok=True))
    assert sink.wait("refused", "steps_999")
    r.submit(cmd("confirm", op_id, key="load_immersion", answer="done"))
    fin = sink.wait("finished", op_id)
    conf = sink.wait("confirmed", op_id)
    assert sink.events.index(conf) < sink.events.index(fin)
    assert conf.data["by"] == USER
    step = fin.data["manual_steps"][0]
    assert step["step"] == "load_immersion" and step["immersion"] == "oil"
    assert step["by"] == USER and step["ok"] is True
    assert fin.data["summary"] == {"answer": "done"}
    assert any(e.kind == "confirmed" for e in records[op_id].events)
    refuse(r, cmd("confirm", op_id, key="load_immersion", ok=True))  # answered once only


def test_abort_wakes_a_confirm_wait(make):
    r, sink = make()
    op_id = r.submit(start("oil"))
    sink.wait("confirm_required", op_id)
    r.submit(cmd("abort", op_id))
    sink.wait("aborted", op_id)
    assert r.snapshot()["pending_confirms"] == []


def test_one_exclusive_operation_at_a_time_but_record_ops_run_alongside(make):
    r, sink = make()
    held = r.submit(start("hold"))
    sink.wait("progress", held)
    e = refuse(r, start("steps"))
    assert e.why.startswith(f"busy: {held}") and sink.wait("refused", e.op_id)
    tare = r.submit(start("tare"))
    assert sink.wait("finished", tare).data["summary"] == {"tared": True}
    assert "light_changed" not in sink.kinds(tare)  # record-only: lights untouched
    assert r.snapshot()["owner"] == held


def test_concurrent_submits_admit_exactly_one(make):
    r, _ = make()
    admitted: list[str] = []
    refused: list[str] = []
    gate = threading.Barrier(8)

    def go() -> None:
        gate.wait()
        try:
            admitted.append(r.submit(start("hold")))
        except CommandRefused as e:
            refused.append(e.op_id)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(T)
    assert len(admitted) == 1 and len(refused) == 7


def test_exception_path_records_lights_off_and_error(make, fake, records):
    r, sink = make()
    op_id = r.submit(start("boom"))
    err = sink.wait("error", op_id)
    assert "stage lost" in err.data["message"] and err.data["where"]
    assert err.data["end_state"]["lights"]["verified"] is True
    assert fake.lights == {"DiaLamp": "0", "Aura": "0"}
    assert records[op_id].end["state"] == "error"


def test_failing_lights_off_is_reported_and_the_op_still_ends(make, fake):
    r, sink = make()
    fake.all_off_raises = True
    op_id = r.submit(start("boom"))
    assert r.wait_idle(T)
    errors = [e for e in sink.events if e.kind == "error" and e.op_id == op_id]
    assert errors[0].data["where"] == "exit"
    assert errors[-1].data["end_state"]["lights"]["verified"] is False
    assert r.snapshot()["owner"] is None


def test_unknown_or_empty_operation_and_unknown_abort_are_refused(make):
    r, sink = make()
    assert "unknown operation 'teleport'" in refuse(r, start("teleport")).why
    assert "unknown operation ''" in refuse(r, start("")).why
    refuse(r, cmd("abort", "hold_404"))
    sink.wait("refused", "hold_404")
    assert r.submit(cmd("abort")) == ""  # abort-all with nothing running is fine


# -- proposals


def test_assistant_start_is_a_proposal_until_a_person_approves(make, fake):
    r, sink = make()
    c = start("steps", origin="assistant")
    c.proposal_id, c.conversation_id = "prop_1", "conv_1"
    op_id = r.submit(c)
    prop = sink.wait("proposed", op_id)
    assert prop.data["proposal_id"] == "prop_1" and prop.data["conversation_id"] == "conv_1"
    assert fake.calls == [] and r.snapshot()["proposals"][0]["op_id"] == op_id
    approve = Command("approve", op_id=op_id, origin="assistant", user_id=USER,
                      session_id=SESSION)
    assert "assistant only proposes" in refuse(r, approve).why
    assert fake.calls == []
    r.submit(cmd("approve", op_id))
    started = sink.wait("started", op_id).data
    assert started["origin"] == "assistant" and started["confirmed_by"] == USER
    assert started["proposal_id"] == "prop_1"
    assert sink.kinds(op_id)[:3] == ["proposed", "refused", "approved"]
    sink.wait("finished", op_id)


def test_a_proposal_confirmed_in_t013_arrives_confirmed(make):
    r, sink = make()
    shape = {"kind": "start", "op": "steps", "args": {"n": 1}, "origin": "assistant",
             "proposal_id": "prop_9", "conversation_id": "conv_3", "confirmed_by": USER,
             "user_id": USER, "session_id": SESSION}
    op_id = r.submit(Command(**shape))
    fin = sink.wait("finished", op_id)
    assert sink.kinds(op_id)[0] == "approved"
    started = sink.wait("started", op_id).data
    assert started["proposal_id"] == "prop_9" and started["conversation_id"] == "conv_3"
    assert started["confirmed_by"] == USER and fin.user_id == USER


def test_rejected_proposal_never_runs(make, fake):
    r, sink = make()
    op_id = r.submit(start("hold", origin="assistant"))
    r.submit(cmd("reject", op_id))
    assert sink.wait("rejected", op_id).data["by"] == USER
    assert fake.calls == [] and r.snapshot()["proposals"] == []
    refuse(r, cmd("approve", op_id))


# -- rule 12


class GrantHolder:
    """The T-018 control seat: only USER holding grant g-1 has the equipment."""

    def check(self, user_id, grant):
        return user_id == USER and grant == "g-1"


def granted(c: Command) -> Command:
    c.control_grant = "g-1"
    return c


def test_rule_12_needs_the_grant_from_the_server_and_an_open_session(make, fake):
    r, sink = make(control=GrantHolder())
    assert "does not hold equipment control" in refuse(r, start("steps")).why
    smuggled = start("steps", grant="g-1", control_grant="g-1", token="g-1")
    assert "does not hold equipment control" in refuse(r, smuggled).why  # args are ignored
    other = granted(Command("start", op="steps", user_id="viewer@example.test",
                            session_id=SESSION))
    refuse(r, other)
    wrong = granted(Command("start", op="steps", user_id=USER, session_id="20260930_0900_1"))
    assert "is not the open session" in refuse(r, wrong).why
    assert fake.calls == []
    held = r.submit(granted(start("hold")))
    sink.wait("progress", held)
    r.submit(Command("abort", op_id=held, user_id="viewer@example.test"))  # anyone may stop
    sink.wait("aborted", held)
    sink.wait("finished", r.submit(Command("lights_off")))


def test_rule_12_refuses_motion_and_light_without_a_session(make):
    r, sink = make(session=None)
    assert "no open experiment session" in refuse(r, start("steps")).why
    assert permission("light_set").session and permission("light_set").control  # D15
    assert "no open experiment session" in refuse(r, start("light_set")).why
    sink.wait("finished", r.submit(start("sample_open", sample_id="s1")))  # no session needed
    r.set_experiment_session(SESSION, 2000.0)
    lit = r.submit(start("light_set"))
    assert sink.wait("finished", lit).data["end_state"]["lights"]["state"]["DiaLamp"] == "1"
    sink.wait("finished", r.submit(start("steps")))
    r.set_experiment_session(None)
    refuse(r, start("steps"))
    changes = [e.data for e in sink.events if e.kind == "session_changed"]
    assert changes == [{"session_id": SESSION, "started_at": 2000.0, "state": "open"},
                       {"session_id": SESSION, "started_at": None, "state": "closed"}]


def test_default_control_refuses_everything_but_stops(fake):
    r = Runner(fake, registry=REG, config=QUIET)
    sink = Collect()
    r.subscribe(sink)
    try:
        assert "not started" in refuse(r, start("steps")).why
        r.start()
        r.set_experiment_session(SESSION, 1000.0)
        assert "equipment control" in refuse(r, start("steps")).why
        sink.wait("finished", r.submit(Command("lights_off")))
    finally:
        r.shutdown("test", timeout=T)


def test_permission_table_covers_the_screen_ops_and_defaults_to_motion():
    for op in ("hardware_scan", "hardware_confirm", "status", "light_set", "edge_trace",
               "boundary_mark", "boundary_undo", "boundary_reset", "scan_4x", "sample_map",
               "goto_xy", "map_flag", "map_flag_retire", "candidate_confirm",
               "candidate_reject"):
        assert op in PERMISSIONS
    assert permission("abort").action == "stop" and not permission("lights_off").control
    assert permission("something_new") == permission("scan_4x")


# -- update, awaiting_return, stream, frames, plan


def test_update_changes_declared_args_only(make):
    r, sink = make()
    op_id = r.submit(start("trace", speed_um_s=100))
    sink.wait("progress", op_id)
    assert "cannot update ['step_um']" in refuse(r, cmd("update", op_id, step_um=50)).why
    r.submit(cmd("update", op_id, speed_um_s=800))
    assert sink.wait("updated", op_id).data["args"] == {"speed_um_s": 800}
    assert sink.wait("finished", op_id).data["summary"] == {"speed_um_s": 800}
    assert "no running operation" in refuse(r, cmd("update", op_id, speed_um_s=10)).why


def test_awaiting_return_blocks_other_motion_until_the_return_op(make):
    seen: list = []
    r, sink = make(on_awaiting_return=seen.append)
    esc = r.submit(start("escape"))
    fin = sink.wait("finished", esc)
    assert fin.data["end_state"]["state"] == "awaiting_return"
    assert r.snapshot()["awaiting_return"]["return_xy"] == [8026.0, 571.6]
    for blocked in (r.submit(start("steps")), r.submit(start("go_back"))):  # no resume
        failed = sink.wait("preflight_failed", blocked)
        assert failed.data["checks"][0]["name"] == "awaiting_return"
        assert sink.wait("error", blocked).data["where"] == "preflight"
    sink.wait("finished", r.submit(start("tare")))  # no motion: still allowed
    sink.wait("finished", r.submit(start("go_back", resume=True)))
    assert r.snapshot()["awaiting_return"] is None
    assert seen[0]["op_id"] == esc and seen[-1] is None
    sink.wait("finished", r.submit(start("steps")))


def test_awaiting_return_survives_an_engine_restart(make):
    r, sink = make(awaiting_return={"op": "objective_change", "op_id": "objective_change_7"})
    sink.wait("preflight_failed", r.submit(start("steps")))


@pytest.mark.parametrize("fail", [False, True])
def test_snapping_op_pauses_the_stream_and_puts_it_back(make, fail):
    stream = Stream()
    r, sink = make(stream=stream)
    op_id = r.submit(start("snapper", fail=fail))
    sink.wait("error" if fail else "finished", op_id)
    assert stream.calls == ["pause", "resume"] and stream.on
    held = r.submit(start("hold"))  # not a snapping op: the stream stays on
    sink.wait("progress", held)
    assert stream.calls == ["pause", "resume"]


def test_latest_frame_keeps_only_the_newest_and_events_carry_no_pixels(make):
    r, sink = make()
    assert r.latest_frame() is None
    first = r.submit(start("snapper"))
    sink.wait("finished", first)
    second = r.submit(start("snapper"))
    sink.wait("finished", second)
    image, meta = r.latest_frame()
    ready = [e for e in sink.events if e.kind == "frame_ready"]
    assert [e.op_id for e in ready] == [first, second]
    assert meta["frame_id"] == ready[-1].data["frame_id"] == 2
    assert meta["source_op"] == "snapper" and image.dtype.name == "uint16"
    assert "image" not in ready[-1].data
    json.dumps([e.data for e in ready])


def test_plan_runs_without_hardware_and_emits_nothing(make, fake):
    r, sink = make()
    before = len(sink.events)
    assert r.plan(start("snapper", tiles=9)) == {"op": "snapper", "args": {"tiles": 9},
                                                 "plan": {"tiles": 9}}
    with pytest.raises(RuntimeError, match="must not use the backend"):
        r.plan(start("peeks"))
    with pytest.raises(CommandRefused):
        r.plan(start("teleport"))
    assert len(sink.events) == before and fake.calls == []


# -- D13, D14


def test_d13_remote_abort_ends_with_lights_off_readback(make, fake, records):
    r, sink = make()
    held = r.submit(start("hold"))
    sink.wait("progress", held)
    r.submit(Command("abort", op_id=held, user_id="far@example.test", remote=True))
    ab = sink.wait("aborted", held)
    lights = ab.data["end_state"]["lights"]
    assert lights["off"] is True and lights["verified"] is True
    assert {x["device"] for x in lights["records"]} == {"Aura", "DiaLamp"}
    assert fake.lights == {"DiaLamp": "0", "Aura": "0"}
    note = sink.logs("D13")[0]
    assert note.op_id == held and note.data["trigger"] == "far@example.test"
    assert any(e.kind == "light_changed" for e in records[held].events)


def test_d13_remote_lights_off_and_other_commands_are_refused(make):
    r, sink = make()
    off = refuse(r, Command("lights_off", remote=True))
    assert off.why == "a remote client may send abort only (D13)"
    assert sink.wait("refused").data["remote"] is True
    for kind, op in (("start", "hold"), ("confirm", ""), ("update", ""), ("approve", "")):
        c = Command(kind, op=op, op_id="hold_1", remote=True, user_id=USER,
                    session_id=SESSION)
        assert "D13" in refuse(r, c).why


def test_d13_remote_abort_can_be_switched_off(make):
    r, sink = make(config=RunnerConfig(position_interval_s=None, allow_remote_abort=False))
    held = r.submit(start("hold"))
    sink.wait("progress", held)
    assert "switched off" in refuse(r, Command("abort", op_id=held, remote=True)).why
    assert r.snapshot()["owner"] == held


def test_d14_watched_op_aborts_after_local_viewers_drop(make):
    r, sink = make(config=RunnerConfig(position_interval_s=None, local_gone_abort_s=0.05))
    r.set_local_viewers(1)
    watched = r.submit(start("watched"))
    sink.wait("progress", watched)
    r.set_local_viewers(0)
    ab = sink.wait("aborted", watched)
    assert ab.data["why"] == "D14: no local viewer"
    assert ab.data["end_state"]["lights"]["off"] is True
    note = sink.logs("D14")[0]
    assert note.op_id == watched and note.data["last_viewer_dropped_at"] is not None


def test_d14_reconnect_cancels_and_unwatched_ops_keep_going(make):
    r, sink = make(config=RunnerConfig(position_interval_s=None, local_gone_abort_s=0.2))
    r.set_local_viewers(1)
    watched = r.submit(start("watched"))
    sink.wait("progress", watched)
    r.set_local_viewers(0)
    r.set_local_viewers(2)  # back inside the window
    assert not r.wait_idle(0.4)
    r.submit(cmd("abort", watched))
    sink.wait("aborted", watched)
    held = r.submit(start("hold"))  # not watched: no timer at all
    sink.wait("progress", held)
    r.set_local_viewers(0)
    assert not r.wait_idle(0.4)
    assert sink.logs("D14") == []


def test_d14_can_be_switched_off(make):
    r, sink = make(config=RunnerConfig(position_interval_s=None, abort_when_local_gone=False,
                                       local_gone_abort_s=0.05))
    r.set_local_viewers(0)
    watched = r.submit(start("watched"))
    sink.wait("progress", watched)
    assert not r.wait_idle(0.3)


# -- shutdown and state files


def test_shutdown_switches_off_first_then_aborts_and_stops_the_stream(make, fake, tmp_path):
    stream = Stream()
    r, sink = make(stream=stream, state_dir=tmp_path)
    held = r.submit(start("hold"))
    sink.wait("progress", held)
    rec = r.shutdown("operator pressed Quit", timeout=T)
    first_off = next(e for e in sink.events if e.kind == "light_changed")
    ab = sink.wait("aborted", held)
    assert first_off.op_id != held and sink.events.index(first_off) < sink.events.index(ab)
    assert ab.data["why"] == "shutdown: operator pressed Quit"
    assert sink.logs("shutdown")[0].data["reason"] == "operator pressed Quit"
    assert stream.calls[-1] == "stop"
    assert rec["reason"] == "operator pressed Quit" and rec["all_off"] is True
    assert fake.lights == {"DiaLamp": "0", "Aura": "0"}
    assert not (tmp_path / "running.json").exists()
    assert json.loads((tmp_path / "last_shutdown_lights.json").read_text()) == rec
    assert "shutting down" in refuse(r, start("steps")).why
    assert r.shutdown("again") is rec  # once only


def test_last_shutdown_lights_are_shown_at_the_next_start(fake, tmp_path):
    first = Runner(fake, registry=REG, control=AllowAll(), config=QUIET, state_dir=tmp_path)
    first.start()
    assert first.snapshot()["last_shutdown_lights"] is None
    fake.lamp_on(token=GUARD_TOKEN)
    saved = first.shutdown("end of day", timeout=T)
    again = Runner(fake, registry=REG, config=QUIET, state_dir=tmp_path).start()
    try:
        snap = again.snapshot()
        assert snap["last_shutdown_lights"] == saved and snap["unclean_shutdown"] is None
        assert {x["device"] for x in saved["records"]} == {"Aura", "DiaLamp"}
    finally:
        again.shutdown("test", timeout=T)


def test_unclean_shutdown_is_reported_before_any_command(fake, tmp_path):
    crashed = Runner(fake, registry=REG, control=AllowAll(), config=QUIET, state_dir=tmp_path)
    crashed.start()  # never shut down: the running mark stays, as after a crash
    fake.lamp_on(token=GUARD_TOKEN)
    nxt = Runner(fake, registry=REG, control=AllowAll(), config=QUIET, state_dir=tmp_path)
    sink = Collect()
    nxt.subscribe(sink)
    nxt.start()
    try:
        unclean = nxt.snapshot()["unclean_shutdown"]
        assert unclean["mark"]["pid"] and unclean["lights"]["state"]["DiaLamp"] == "1"
        assert sink.logs("unclean_shutdown")[0].data["lights"] == unclean["lights"]
        logged = (tmp_path / "unclean_shutdowns.jsonl").read_text().splitlines()
        assert json.loads(logged[-1])["detected_at"] == unclean["detected_at"]
    finally:
        nxt.shutdown("test", timeout=T)
        crashed.shutdown("test", timeout=T)  # its threads, not its mark, are what is left


def test_snapshot_hardware_and_last_status(make):
    r, sink = make(hardware=lambda: {"profile": "bench", "profile_path": "cfg/bench.yaml",
                                     "gates": {"scan_4x": True}})
    hw = r.snapshot()["hardware"]
    assert hw["profile"] == "bench" and hw["gates"] == {"scan_4x": True}
    assert hw["last_status"] is None
    sink.wait("finished", r.submit(start("status")))
    assert r.snapshot()["hardware"]["last_status"]["summary"]["objective"] == "4x"


def test_snapshot_sample_block(make):
    r, sink = make(session=None)
    assert r.snapshot()["sample"] == {"sample_id": None, "reserved": False, "session_id": None}
    sink.wait("finished", r.submit(start("sample_open", sample_id="20261001_1540_1")))
    assert r.snapshot()["sample"] == {"sample_id": "20261001_1540_1", "reserved": True,
                                      "session_id": None}
    r.set_experiment_session(SESSION, 3000.0)
    assert r.snapshot()["sample"]["session_id"] == SESSION


def test_folder_records_write_log_and_summary(fake, tmp_path):
    r = Runner(fake, registry=REG, control=AllowAll(), config=QUIET,
               records=folder_records(lambda meta: tmp_path / "samples" / "s1"))
    r.start()
    r.set_experiment_session(SESSION, 1000.0)
    sink = Collect()
    r.subscribe(sink)
    try:
        fin = sink.wait("finished", r.submit(start("steps", n=1)))
        folder = tmp_path / "samples" / "s1"
        (rec_dir,) = [p for p in folder.iterdir() if p.name.startswith("steps_")]
        assert fin.data["record_dir"] == str(rec_dir)
        summary = json.loads((rec_dir / "summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "finished" and summary["session_id"] == SESSION
        assert summary["lights_off"]["verified"] is True
        assert summary["result"]["op_id"] == fin.op_id
        assert summary["result"]["summary"] == {"done": True}
        kinds = [json.loads(line)["kind"] for line in
                 (rec_dir / "log.jsonl").read_text(encoding="utf-8").splitlines()]
        assert kinds[0] == "planned" and kinds[-1] == "finished"
    finally:
        r.shutdown("test", timeout=T)


# -- misc


def test_position_events_are_periodic_and_carry_no_op(make):
    r, sink = make(config=RunnerConfig(position_interval_s=0.01))
    ev = sink.wait("position")
    assert ev.op_id == "" and ev.data["z_um"] == 2900.0
    assert r.snapshot()["positions"]["x_um"] == 8026.0


def test_a_failing_sink_does_not_stop_the_engine(make):
    r, sink = make()

    def bad(ev: Event) -> None:
        raise RuntimeError("socket gone")

    unsubscribe = r.subscribe(bad)
    sink.wait("finished", r.submit(start("steps")))
    unsubscribe()
    unsubscribe()  # twice is fine


def test_bench_backend_refuses_an_approach_without_clearance(make, fake):
    r, sink = make()
    sink.wait("finished", r.submit(start("approach_op")))  # fake backend: not the bench
    info = fake.info()
    info.kind = "mm-real"
    fake.info = lambda: info
    blocked = r.submit(start("approach_op"))
    failed = sink.wait("preflight_failed", blocked)
    assert failed.data["checks"][0]["name"] == "approach_clearance"
    sink.wait("finished", r.submit(start("approach_op", clear=True)))
    del fake.info


def test_check_explains_what_is_allowed_now(make):
    r, sink = make(control=GrantHolder())
    me = {"user_id": USER, "control_grant": "g-1", "session_id": SESSION}
    got = r.check(["steps", "tare", "abort", "lights_off", "scan_4x"], me)
    assert got["steps"] == {"allowed": True, "reason": None}
    assert got["abort"]["allowed"] and got["lights_off"]["allowed"]
    assert got["scan_4x"] == {"allowed": False, "reason": "scan_4x is not available yet"}
    viewer = r.check(["steps", "lights_off"], {"user_id": "viewer@example.test"})
    assert "equipment control" in viewer["steps"]["reason"]
    assert viewer["lights_off"]["allowed"]
    held = r.submit(granted(start("hold")))
    sink.wait("progress", held)
    busy = r.check(["steps", "tare"], me)
    assert busy["steps"]["reason"] == f"busy: {held} holds the core"
    assert busy["tare"]["allowed"]  # record-only runs alongside
    r.submit(cmd("abort", held))
    sink.wait("aborted", held)
    sink.wait("finished", r.submit(granted(start("escape"))))
    away = r.check(["steps", "go_back", "tare"], {**me, "args": {"go_back": {"resume": True}}})
    assert "return it first" in away["steps"]["reason"]
    assert away["go_back"]["allowed"] and away["tare"]["allowed"]
    assert set(r.check(context=me)) >= set(PERMISSIONS)
    r.set_experiment_session(None)
    assert r.check(["steps"], me)["steps"]["reason"] == "no open experiment session"
    json.dumps(r.check(context=me))


def test_registry_refuses_reserved_and_duplicate_names():
    reg = Registry()
    reg.register(Steps)
    reg.register(Steps)  # the same class again is fine
    with pytest.raises(ValueError):
        reg.register(type("Other", (Steps,), {"name": "steps"}))
    with pytest.raises(ValueError):
        reg.register(type("Off", (Operation,), {"name": "lights_off"}))
