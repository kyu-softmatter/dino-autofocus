"""One scripted M1 day on the mock (PLAN 8 M1: F1-F5 without hardware), step by step.

The steps run in file order on one shared `day` bench (conftest) and go through the T-011
runner with `Command`s, as the server will send them; T-009's server is the last step. A step
whose operation has not landed skips with its task number. When it lands, `pending(...)`
turns into a skip saying the step is still to be written here (a T-035 follow-up), so
nothing passes by accident.
"""

from __future__ import annotations

import json
import math

import pytest
from conftest import OFF, OPERATOR, after, need, read_jsonl

from dino_autofocus.auth import ControlBusy, ControlError
from dino_autofocus.engine.backends.mock_world import SampleSpec
from dino_autofocus.engine.runner import CommandRefused
from dino_autofocus.engine.sample import SampleGeometry, SampleInfo
from dino_autofocus.records import GitFolderStore, SessionClosedError, open_session, sample_state

SPEC = SampleSpec()  # the sample MockBackend(seed=0) holds: 6.144 mm hole at (8026, 571.6)
#: a 1200 px ROI keeps the trace near 20 s; the full 2400 px sensor works too (about 100 s)
TRACE_ROI_PX = 1200


def pending(module: str, task: str) -> None:
    need(module, task)
    pytest.skip(f"{task} is on main; this step of the day is still to be written (T-035)")


def summaries(day) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(day.sample.dir.glob("*/summary.json"))]


# -- morning: who is at the microscope ------------------------------------------------------

def test_01_operator_logs_in(day):
    assert not day.logins.login(OPERATOR, "not-the-password").ok
    day.login_token = day.login(OPERATOR)
    assert day.logins.get(day.login_token).role == "operator"
    day.done.add("login")


def test_02_nothing_runs_until_the_operator_holds_control(day):
    after(day, "login")
    with pytest.raises(CommandRefused, match="equipment control"):
        day.start("status", grant=None)
    with pytest.raises(ControlError):  # remote viewing never takes control
        day.control.acquire(day.login_token, local=False)
    with pytest.raises(ControlError):  # a viewer cannot operate
        day.control.acquire(day.login("vera@example.test"), local=True)

    day.control_token = day.control.acquire(day.login_token, local=True).token
    assert day.control.holder().user_id == OPERATOR
    with pytest.raises(ControlBusy):  # one operator at a time
        day.control.acquire(day.login("olga@example.test"), local=True)
    with pytest.raises(CommandRefused, match="equipment control"):  # not Olga's grant
        day.start("status", user="olga@example.test")
    day.runner.set_local_viewers(1)  # the operator's own browser on the microscope PC
    day.done.add("control")


def test_03_status_before_the_session(day):
    after(day, "control")
    end = day.run("status")
    assert end.kind == "finished", end.data
    st = end.data["summary"]["status"]
    assert st["nosepiece_label"].endswith("4x") and st["lights"] == OFF
    with pytest.raises(CommandRefused, match="no open experiment session"):
        day.start("light_set", {"mode": "brightfield"})  # light needs a session (D15)
    day.done.add("status_before")


def test_04_operator_opens_an_experiment_session(day):
    after(day, "control")
    s = day.open_session()
    assert open_session(day.store)["session_id"] == s.session_id
    info = json.loads((s.layout.root / "session.json").read_text(encoding="utf-8"))
    assert (info["user_id"], info["sample_id"], info["status"]) == (
        OPERATOR, day.sample.id, "open")
    assert day.runner.snapshot()["sample"]["sample_id"] == day.sample.id
    day.done.add("session")


# -- F2: what hardware is there ---------------------------------------------------------------

def test_05_f2_hardware_scan_and_gates(day):
    after(day, "session")
    pending("dino_autofocus.engine.operations.hardware_scan", "T-028")


# -- F3: the sample goes on -------------------------------------------------------------------

def test_06_f3_sample_geometry_is_recorded(day):
    """Until T-027's sample_geometry_set, the geometry goes into the sample and the session
    the way that operation will write it."""
    after(day, "session")
    geometry = SampleGeometry(size_mm=SPEC.size_mm, chamber="hole",
                              hole_diameter_mm=SPEC.hole_diameter_mm,
                              coverslip_um=SPEC.coverslip_um, orientation="upright",
                              confirmed_by_operator=True)
    day.sample.save_info(SampleInfo(day.sample.id, geometry=geometry))
    saved = day.sample.load_info().to_dict()["geometry"]
    day.session.record("sample_geometry", {"sample_id": day.sample.id, "geometry": saved})
    assert day.sample.load_info().geometry == geometry
    (line,) = read_jsonl(day.session.layout.operation_record("sample_geometry"))
    assert (line["user_id"], line["session_id"]) == (OPERATOR, day.session.session_id)
    day.done.add("geometry")


def test_07_f3_loading_confirm(day):
    after(day, "geometry")
    pending("dino_autofocus.engine.operations.sample_ops", "T-027")


# -- F4: find the hole, map the sample ---------------------------------------------------------

def test_08_f4_edge_trace_fits_the_hole(day):
    after(day, "geometry")
    b, world = day.backend, day.backend.world
    assert b.nosepiece().endswith("4x")
    # the operator's hands: joystick to the chamber edge, focus knob to the 4x focus there
    r = SPEC.hole_diameter_mm * 500 + 300
    world.move_xy(SPEC.hole_centre_um[0] + r * math.cos(0.7),
                  SPEC.hole_centre_um[1] + r * math.sin(0.7))
    world.move_z(world.in_focus_z())
    b.set_roi(TRACE_ROI_PX)
    z_before = b.positions().z_um

    end = day.run("edge_trace", {"speed_um_s": 1000.0,
                                 "hole_diameter_mm": SPEC.hole_diameter_mm})
    b.set_roi(0)
    assert end.kind == "finished", end.data
    asked = [e.data["key"] for e in day.events
             if e.kind == "confirmed" and e.op_id == end.op_id]
    assert asked == ["start_trace"]  # a fresh sample: no earlier fit to replace
    out = end.data["summary"]
    assert out["why"] == "back where the edge was first seen: full loop"
    hole = out["hole"]
    assert math.dist(hole["centre_um"], SPEC.hole_centre_um) < 30
    assert hole["diameter_mm"] == pytest.approx(SPEC.hole_diameter_mm, rel=0.02)
    assert b.positions().z_um == pytest.approx(z_before)  # Z never moved
    assert day.lights() == OFF and end.data["end_state"]["lights"]["rule"] == "restore"
    assert [e for e in day.events if e.kind == "motion" and e.op_id == end.op_id]
    day.trace = out
    day.done.add("edge_trace")


def test_09_sample_events_fold_to_the_traced_hole(day):
    """Until T-027's boundary_mark writes them, the day records the trace as sample events
    the way that operation will; the fold must give back the traced hole."""
    after(day, "edge_trace")
    s, hole = day.session, day.trace["hole"]
    boundary = day.sample.load_map().boundary
    s.sample_event("boundary_clear")
    for x, y in boundary:
        s.sample_event("boundary_point", x_um=x, y_um=y)
    s.sample_event("hole_fit", **hole)

    st = sample_state(day.store, day.sample.id)
    assert st.hole["centre_um"] == hole["centre_um"]
    assert st.hole["diameter_mm"] == hole["diameter_mm"]
    assert [(p["x_um"], p["y_um"]) for p in st.boundary] == [tuple(p) for p in boundary]
    assert len(st.boundary) == day.trace["n_points"]
    assert st.sessions == [s.session_id]
    assert all(e.user_id == OPERATOR and e.session_id == s.session_id for e in s.events())
    day.done.add("fold")


def test_10_f4_scan_4x(day):
    after(day, "fold")
    pending("dino_autofocus.engine.operations.scan_4x", "T-031")


def test_11_f4_sample_map(day):
    after(day, "fold")
    pending("dino_autofocus.engine.operations.sample_map", "T-032")


def test_12_f4_flag_and_goto_xy(day):
    after(day, "fold")
    pending("dino_autofocus.engine.operations.sample_map", "T-032")


# -- F5: 4x -> 100x Oil and focus -------------------------------------------------------------

def test_13_f5_objective_change_to_100x_oil(day):
    after(day, "fold")
    pending("dino_autofocus.engine.operations.objective_change", "T-029")


def test_14_f5_focus_100x(day):
    after(day, "fold")
    pending("dino_autofocus.engine.operations.focus_100x", "T-031")


# -- evening: lights, records, close ------------------------------------------------------------

def test_15_light_set_stays_through_status_then_lights_off(day):
    after(day, "session")
    end = day.run("light_set", {"mode": "brightfield"})
    assert end.kind == "finished" and end.data["end_state"]["lights"]["rule"] == "keep"
    assert day.lights()["DiaLamp"] == "1"
    assert day.run("status").kind == "finished"
    assert day.lights()["DiaLamp"] == "1"  # a status does not switch the light set before
    stop = day.submit("lights_off", grant=None)  # the stop needs no control grant
    end = day.wait_end(stop)
    assert end.kind == "finished" and end.data["summary"]["verified"]
    assert day.lights() == OFF
    day.done.add("lights")


def test_16_every_record_carries_the_user_and_the_session(day):
    after(day, "lights", "edge_trace")
    sid = day.session.session_id
    recs = summaries(day)
    ops = [r["op"] for r in recs]
    assert {"edge_trace", "light_set", "status", "lights_off"} <= set(ops)
    for r in recs:  # the runner's records and the edge_trace code's own record
        assert r["user_id"] == OPERATOR, r["op_id"]
        assert r["session_id"] == sid, r["op_id"]
    lay = day.session.layout
    for path in (lay.log, lay.sample_events, lay.operation_record("sample_geometry")):
        for line in read_jsonl(path):
            assert (line["user_id"], line["session_id"]) == (OPERATOR, sid), path.name
    for ev in day.events:  # what every screen heard
        if ev.op_id and ev.kind in ("started", "finished"):
            assert ev.user_id == OPERATOR, (ev.kind, ev.op_id)
    day.done.add("records")


def test_17_the_day_closes(day):
    after(day, "session")
    s = day.session
    day.runner.set_experiment_session(None)  # closing is a stop: lights off
    with pytest.raises(CommandRefused, match="no open experiment session"):
        day.start("light_set", {"mode": "brightfield"}, session_id=s.session_id)
    day.control.release(day.login_token)
    assert day.control.holder() is None
    with pytest.raises(CommandRefused, match="equipment control"):
        day.start("status")
    s.close("end of the M1 mock day")
    with pytest.raises(SessionClosedError):
        s.log("after close")
    assert open_session(day.store) is None
    assert day.logins.logout(day.login_token)
    assert day.lights() == OFF

    released = [e for e in day.audit.entries() if e["kind"] == "control_released"]
    assert released[-1]["user_id"] == OPERATOR
    assert released[-1]["session_id"] == s.session_id  # stamped while the session was open
    if isinstance(day.store, GitFolderStore):  # the records repository holds the day
        log = day.store._git("log", "--format=%ae %s").stdout.splitlines()
        assert log and all(line.startswith(OPERATOR) for line in log)
        assert not day.store.uncommitted(day.store._rel(s.session_id))
    day.done.add("closed")


def test_18_the_same_day_through_the_server(day):
    pending("dino_autofocus.server.app", "T-009")


def test_19_stand_ins_in_use_are_the_unregistered_ones(day):
    """The suite says which merged operations still run through a conftest stand-in."""
    from dino_autofocus.engine.runner import OPERATIONS

    assert set(day.stand_ins) == {n for n in ("status", "light_set", "edge_trace")
                                  if OPERATIONS.get(n) is None}
