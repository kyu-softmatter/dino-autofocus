"""`objective_change` (T-029): the F5 seven steps on the runner over MockBackend.

Every runner a test builds is shut down by the `make` fixture, so no thread outlives a test.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from dino_autofocus.engine import Command, Event
from dino_autofocus.engine.backend import GUARD_TOKEN
from dino_autofocus.engine.backends.mock import MockBackend
from dino_autofocus.engine.guards import PROVISIONAL, GuardError
from dino_autofocus.engine.operations.objective_change import (
    LOAD_KEY,
    NAME,
    ObjectiveChange,
    escape_plan,
    immersion_of,
    step_out_target,
)
from dino_autofocus.engine.runner import AllowAll, Registry, Runner, RunnerConfig

T = 10.0
USER, SESSION = "op@example.test", "20261001_1540_1"
REG = Registry()
REG.register(ObjectiveChange)
HOLE = (8026.0, 571.6)


class Collect:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self._cond = threading.Condition()

    def __call__(self, ev: Event) -> None:
        with self._cond:
            self.events.append(ev)
            self._cond.notify_all()

    def wait(self, kind: str, op_id: str) -> Event:
        def find():
            return next((e for e in self.events if e.kind == kind and e.op_id == op_id), None)

        with self._cond:
            assert self._cond.wait_for(lambda: find() is not None, T), (kind, self.kinds(op_id))
            return find()

    def kinds(self, op_id: str) -> list[str]:
        return [e.kind for e in self.events if e.op_id == op_id]

    def of(self, kind: str, op_id: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind and e.op_id == op_id]


def start(**args) -> Command:
    return Command("start", op=NAME, args=args, user_id=USER, session_id=SESSION)


def confirm(op_id: str, ok: bool = True) -> Command:
    return Command("confirm", op_id=op_id, user_id=USER, session_id=SESSION,
                   args={"key": LOAD_KEY, "ok": ok, "answer": "done" if ok else "not done"})


@pytest.fixture
def make():
    made: list[Runner] = []

    def build(nosepiece: int = 0, z_um: float = 3048.7, xy=HOLE):
        be = MockBackend(seed=1)
        w = be.world
        w.set_nosepiece(nosepiece)
        w.move_xy(*xy)
        w.move_z(z_um)
        be.open()
        r = Runner(be, registry=REG, control=AllowAll(),
                   config=RunnerConfig(position_interval_s=None))
        made.append(r)
        sink = Collect()
        r.subscribe(sink)
        r.start()
        r.set_experiment_session(SESSION, 1000.0)
        return r, sink, be

    yield build
    for r in made:
        r.shutdown("test teardown", timeout=T)
        assert r.wait_idle(T)


def steps_seen(sink: Collect, op_id: str) -> list[int]:
    return [e.data["step"] for e in sink.of("progress", op_id)]


# ---------------------------------------------------------------- the full rotation


def test_4x_to_100x_runs_the_seven_steps_and_waits_for_loading(make):
    r, sink, be = make()
    w = be.world
    be.lamp_on(token=GUARD_TOKEN)
    op_id = r.submit(start(target_state=5, approach_target_um=2850.0))
    req = sink.wait("confirm_required", op_id)
    assert req.data["kind"] == "manual_step" and req.data["context"]["immersion"] == "oil"
    # while waiting: Z retracted, stepped out +15 mm in Y, 100x in place, lights off
    assert w.z_um == pytest.approx(0.0)
    assert (w.x_um, w.y_um) == pytest.approx((HOLE[0], HOLE[1] + 15000.0))
    assert w.objective.key == "100x-Oil"
    assert not w.light.dia_on and not w.light.aura_on
    assert steps_seen(sink, op_id) == [1, 2, 3, 4]
    r.submit(confirm(op_id))
    fin = sink.wait("finished", op_id)
    s = fin.data["summary"]
    assert s["state"] == "done" and s["mode"] == "rotate"
    assert fin.data["end_state"]["state"] == "returned"
    assert (w.x_um, w.y_um) == pytest.approx(HOLE)
    assert w.z_um == pytest.approx(2850.0) and s["z_end_um"] == pytest.approx(2850.0)
    assert fin.data["manual_steps"][0]["step"] == LOAD_KEY
    assert r.snapshot()["awaiting_return"] is None


def test_progress_carries_the_contract_fields(make):
    r, sink, _ = make()
    op_id = r.submit(start(target_state=5, approach_target_um=2850.0))
    sink.wait("confirm_required", op_id)
    r.submit(confirm(op_id))
    sink.wait("finished", op_id)
    prog = sink.of("progress", op_id)
    for e in prog:
        if e.data["step"] in (2, 3, 4, 6):
            assert {"axis", "commanded", "readback", "pfs_in_range", "label_read"} <= set(
                e.data["data"]), e.data
    by_step = {e.data["step"]: e.data["data"] for e in prog if e.data["step"] != 7}
    assert by_step[2]["pfs_in_range"] == "Out of Range" and by_step[2]["commanded"] == 0.0
    assert by_step[3]["commanded"][1] == pytest.approx(HOLE[1] + 15000.0)
    assert by_step[4]["label_read"] == "6-Plan Apo LmbdD0.13 100x Oil"
    approach = [e.data["data"] for e in prog if e.data["step"] == 7]
    assert [a["step_index"] for a in approach] == list(range(1, len(approach) + 1))
    z = [a["commanded"] for a in approach]
    assert z[0] == 2800.0 and z[-1] == pytest.approx(2850.0)  # one move to the window, then
    assert all(0 < b - a <= 10.0 + 1e-9 for a, b in zip(z[1:], z[2:], strict=False))
    assert len(z) == 6  # 2800, 2810, ... 2850: never a jump to the target


def test_step_out_basis_and_approach_step_are_marked_provisional(make):
    r, sink, _ = make()
    op_id = r.submit(start(target_state=5))
    sink.wait("confirm_required", op_id)
    r.submit(confirm(op_id))
    sink.wait("finished", op_id)
    motions = sink.of("motion", op_id)
    assert any(PROVISIONAL in str(m.data.get("basis")) for m in motions if m.data["axis"] == "z"
               and str(m.data.get("how")).startswith("approach"))
    step3 = next(e for e in sink.of("progress", op_id) if e.data["step"] == 3)
    assert step3.data["data"]["basis"]["basis"]["escape_dy_um"] == PROVISIONAL


# ---------------------------------------------------------------- interruptions


def test_abort_while_loading_leaves_awaiting_return_and_resume_brings_it_back(make):
    r, sink, be = make()
    w = be.world
    op_id = r.submit(start(target_state=5))
    sink.wait("confirm_required", op_id)
    r.submit(Command("abort", op_id=op_id, user_id=USER, session_id=SESSION))
    ab = sink.wait("aborted", op_id)
    assert ab.data["end_state"]["state"] == "awaiting_return"
    aw = r.snapshot()["awaiting_return"]
    assert aw["return_xy"] == pytest.approx(list(HOLE)) and aw["op"] == NAME
    assert w.z_um == pytest.approx(0.0)  # no exit path raises Z
    # any other motion is refused until the return
    other = r.submit(start(target_state=0))
    failed = sink.wait("preflight_failed", other)
    assert failed.data["checks"][0]["name"] == "awaiting_return"
    back = r.submit(start(resume=True))
    fin = sink.wait("finished", back)
    assert steps_seen(sink, back)[:1] == [6] and set(steps_seen(sink, back)) == {6, 7}
    assert (w.x_um, w.y_um) == pytest.approx(HOLE) and w.z_um == pytest.approx(2800.0)
    assert fin.data["summary"]["start"]["resumed_from"] == op_id
    assert r.snapshot()["awaiting_return"] is None


def test_loading_not_done_finishes_away_from_the_sample(make):
    r, sink, be = make()
    op_id = r.submit(start(target_state=5))
    sink.wait("confirm_required", op_id)
    r.submit(confirm(op_id, ok=False))
    fin = sink.wait("finished", op_id)
    assert fin.data["end_state"]["state"] == "awaiting_return"
    assert r.snapshot()["awaiting_return"]["return_xy"] == pytest.approx(list(HOLE))
    assert be.world.z_um == pytest.approx(0.0)


def test_z_readback_error_stops_at_the_retract_and_nothing_moves_in_xy(make):
    r, sink, be = make()
    be.inject_faults(z_readback_error_um=-1.0)  # commanded 0, reads -1
    op_id = r.submit(start(target_state=5))
    err = sink.wait("error", op_id)
    assert "ZDrive" in err.data["message"] or "commanded" in err.data["message"]
    assert (be.world.x_um, be.world.y_um) == pytest.approx(HOLE)
    assert be.world.objective.key == "4x"
    assert r.snapshot()["awaiting_return"] is None  # still at the sample: no return needed


# ---------------------------------------------------------------- other modes


def test_100x_to_4x_dry_target_skips_step_out_and_loading(make):
    r, sink, be = make(nosepiece=5, z_um=2989.4)
    op_id = r.submit(start(target_state=0))
    fin = sink.wait("finished", op_id)
    assert "confirm_required" not in sink.kinds(op_id)
    assert steps_seen(sink, op_id)[:5] == [1, 2, 4, 6, 7]
    assert be.world.objective.key == "4x" and be.world.z_um == pytest.approx(2800.0)
    assert (be.world.x_um, be.world.y_um) == pytest.approx(HOLE)
    assert fin.data["summary"]["state"] == "done"


def test_reload_steps_out_and_back_without_rotating(make):
    r, sink, be = make(nosepiece=5, z_um=2989.4)
    op_id = r.submit(start(reload=True))
    sink.wait("confirm_required", op_id)
    assert be.world.y_um == pytest.approx(HOLE[1] + 15000.0)
    r.submit(confirm(op_id))
    fin = sink.wait("finished", op_id)
    assert 4 not in steps_seen(sink, op_id)
    assert be.world.objective.key == "100x-Oil" and fin.data["summary"]["mode"] == "reload"


# ---------------------------------------------------------------- preflight refusals


@pytest.mark.parametrize("args, check", [
    ({"target_state": 0}, "target_differs"),  # already on 4x
    ({"target_state": 1}, "target_working_distance"),  # 10x: no free WD in the guards yet
    ({"target_state": 3}, "target"),  # 40x WI: no WD (and its label is not readable yet)
    ({"target_state": 9}, "target_lens"),
    ({}, "mode"),
    ({"target_state": 5, "resume": True}, "mode"),
    ({"target_state": 5, "approach_step_um": 20.0}, "approach_step"),
    ({"target_state": 5, "approach_target_um": 3300.0}, "approach_target"),
    ({"resume": True}, "awaiting_return"),
])
def test_preflight_refusals(make, args, check):
    r, sink, be = make()
    op_id = r.submit(start(**args))
    failed = sink.wait("preflight_failed", op_id)
    bad = [c["name"] for c in failed.data["checks"] if not c["ok"]]
    assert any(n.startswith(check) for n in bad), failed.data["checks"]
    assert be.world.z_um == pytest.approx(3048.7)  # nothing moved


def test_step_out_past_the_stage_y_limit_is_refused(make):
    r, sink, be = make(xy=(HOLE[0], 30000.0))  # +15 mm passes the 37.5 mm mock travel
    op_id = r.submit(start(target_state=5))
    failed = sink.wait("preflight_failed", op_id)
    step = next(c for c in failed.data["checks"] if c["name"] == "step_out")
    assert not step["ok"] and "outside the stage Y travel" in step["why"]


# ---------------------------------------------------------------- plan and clearance


def test_plan_has_the_screen_shape_without_hardware(make):
    r, _, _ = make()
    p = r.plan(start(target_state=5))["plan"]
    esc = p["escape"]
    assert set(esc) >= {"allowed", "reason", "sign", "dy_um", "mark", "default"}
    assert esc["sign"] == "+" and esc["dy_um"] == pytest.approx(15000.0)
    assert esc["mark"] == PROVISIONAL and esc["default"] is True
    assert p["immersion"] == "oil" and [s["step"] for s in p["steps"]] == list(range(1, 8))
    assert p["approach"]["step_um"] == 10.0 and p["approach"]["mark"] == PROVISIONAL
    dry = r.plan(start(target_state=0))["plan"]["escape"]
    assert dry["default"] is False


def test_escape_plan_reads_the_refusal_from_step_out_target():
    ok = escape_plan((HOLE[0], HOLE[1]), (-37500.0, 37500.0), True)
    assert ok["allowed"] is True and ok["target_y_um"] == pytest.approx(HOLE[1] + 15000.0)
    no = escape_plan((HOLE[0], 30000.0), (-37500.0, 37500.0), True)
    assert no["allowed"] is False and "outside the stage Y travel" in no["reason"]
    unknown = escape_plan(None, None, True)
    assert unknown["allowed"] is None and unknown["reason"].startswith("checked at preflight")


def test_step_out_target_refuses_without_y_travel():
    be = SimpleNamespace(info=lambda: SimpleNamespace(stage_limits=SimpleNamespace(y_um=None)))
    with pytest.raises(GuardError, match="no stage Y limit"):
        step_out_target(be, 0.0, 0.0)


def test_clearance_is_always_a_real_check():
    assert ObjectiveChange.approaches is True
    labels = ["6-Plan Apo LmbdD0.13 100x Oil"]
    ctx = SimpleNamespace(aborted=False, args={"approach_target_um": 2850.0},
                          backend=SimpleNamespace(nosepiece=lambda: labels[0]))
    op = ObjectiveChange(ctx)
    op._approach_label = labels[0]
    clear = op.clearance()
    assert clear is not None
    assert clear(2800.0) and clear(2850.0)
    assert not clear(2851.0)  # past the asked target
    labels[0] = "1-Plan Apo LmbdD20 4x"
    assert not clear(2810.0)  # the lens changed under the approach
    labels[0] = "6-Plan Apo LmbdD0.13 100x Oil"
    ctx.aborted = True
    assert not clear(2810.0)


def test_immersion_kinds():
    assert immersion_of("100x-Oil") == "oil" and immersion_of("40x-WI") == "water"
    assert immersion_of("4x") is None and immersion_of(None) is None
