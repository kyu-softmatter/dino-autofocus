"""mm-demo backend: the Backend protocol on Micro-Manager's demo devices (T-023).

The contract checks of tests/engine/test_contract.py run here against both the in-memory
FakeBackend and mm-demo. The mm-demo cases skip without the demo adapters. Each test opens
its own core and closes it, and no test opens a window.
"""

import json
import subprocess
import sys

import numpy as np
import pytest

from dino_autofocus.engine.backend import GUARD_TOKEN, Backend, UnguardedMotion
from dino_autofocus.engine.backends.mm_demo import (
    CAMERA_PROPERTIES,
    LIGHT_PROPERTIES,
    MOTION_DEVICES,
    MmDemoBackend,
    PropertyNotAllowed,
)
from dino_autofocus.engine.backends.mm_demo_core import DemoUnavailable, DemoZRangeError

T = GUARD_TOKEN  # tests stand in for engine.guards


@pytest.fixture
def demo():
    b = MmDemoBackend(roi=256)
    try:
        b.open()
    except DemoUnavailable as e:
        pytest.skip(f"Micro-Manager demo adapters not available: {e}")
    try:
        yield b
    finally:
        b.close()


@pytest.fixture(params=["fake", "mm-demo"])
def backend(request):
    return request.getfixturevalue("fake" if request.param == "fake" else "demo")


def light_kw(b) -> dict:
    """D15 token for light-on calls. FakeBackend gets it with T-015; until then it takes none."""
    return {"token": T} if isinstance(b, MmDemoBackend) else {}


# -- the T-002 contract, parametrised


def test_meets_protocol_and_info_is_json(backend):
    assert isinstance(backend, Backend)
    json.dumps(backend.info().to_dict())
    assert backend.info().ceiling_adu >= 4095


def test_refuses_unguarded_motion(backend):
    for call in (lambda: backend.move_z(3000.0, token=None),
                 lambda: backend.move_xy(0.0, 0.0, token=None),
                 lambda: backend.set_nosepiece(0, token=None),
                 lambda: backend.pfs_off(token=None)):
        with pytest.raises(UnguardedMotion):
            call()


def test_light_read_back_and_off(backend):
    assert all(r.verified for r in backend.aura_line_on("GREEN", 1, **light_kw(backend)))
    assert backend.light_state()["Aura"] == "1"
    assert all(r.verified for r in backend.all_off())
    assert backend.light_state()["Aura"] == "0" and backend.light_state()["DiaLamp"] == "0"


def test_guarded_z_reads_back_in_bench_coordinates(backend):
    assert backend.move_z(2950.0, token=T) == pytest.approx(2950.0)
    assert backend.positions().z_um == pytest.approx(2950.0)
    f = backend.snap()
    assert f.image.dtype == np.uint16 and f.image.ndim == 2
    assert f.z_um == pytest.approx(2950.0)


# -- mm-demo only


def test_import_does_not_load_pymmcore():
    code = ("import sys, dino_autofocus.engine.backends.mm_demo; "
            "sys.exit('pymmcore_plus' in sys.modules or 'pymmcore' in sys.modules)")
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_info(demo):
    info = demo.info()
    assert info.kind == "mm-demo" and info.bit_depth == 16
    assert info.sensor == (2400, 2400) and info.roi[2:] == (256, 256)
    assert info.stage_limits.z_um == (0.0, 3300.0)
    by_state = {o.state: o for o in info.objectives}
    assert len(by_state) == 6
    assert by_state[0].label == "1-Plan Apo LmbdD20 4x" and by_state[0].magnification == 4
    assert by_state[5].free_wd_um == 130.0 and by_state[5].pixel_um == 0.065
    notes = json.loads(demo.read_property("mm-demo", "notes"))
    assert "simulated" in notes["z_below_range"] and "simulated" in notes["pfs"]
    assert "unmeasured provisional" in notes["aura_lines"]


def test_retract_zone_parks_at_demo_floor_and_reads_commanded(demo):
    demo.move_z(2900.0, token=T)
    assert demo.pfs().in_range == "In Range"
    assert demo.read_property("mm-demo", "demo_retract") == ""
    assert demo.move_z(0.0, token=T) == 0.0  # the full retract
    assert demo.positions().z_um == 0.0
    assert demo.dev.core.getPosition("Z") == pytest.approx(-300.0)  # physically at bench 2700
    sub = json.loads(demo.read_property("mm-demo", "demo_retract"))
    assert sub["kind"] == "demo_retract" and sub["commanded_um"] == 0.0
    assert sub["physical_bench_um"] == pytest.approx(2700.0)
    assert sub["physical_demo_um"] == pytest.approx(-300.0)
    assert demo.pfs().out_of_range


def test_approach_steps_from_retract(demo):
    demo.move_z(0.0, token=T)
    n0 = len(demo.substitutions)
    for z in np.arange(100.0, 2801.0, 100.0):  # FocusAxis.approach-like climb
        assert demo.move_z(float(z), token=T) == pytest.approx(z)
    assert len(demo.substitutions) - n0 == 26  # 100 .. 2600 were in the zone; 2700, 2800 real
    assert demo.dev.core.getPosition("Z") == pytest.approx(-200.0)
    assert demo.read_property("mm-demo", "demo_retract") == ""
    assert not demo.pfs().out_of_range


@pytest.mark.parametrize("bad", [-0.1, 3300.1, float("nan")])
def test_z_outside_demo_refused_without_moving(demo, bad):
    demo.move_z(3010.0, token=T)
    with pytest.raises(DemoZRangeError):
        demo.move_z(bad, token=T)
    assert demo.positions().z_um == pytest.approx(3010.0)


def test_nosepiece_turn_from_retract(demo):
    demo.move_z(0.0, token=T)
    assert demo.pfs().out_of_range and demo.pfs_off(token=T).verified
    rb = demo.set_nosepiece(5, token=T)
    assert rb.verified and demo.nosepiece() == "6-Plan Apo LmbdD0.13 100x Oil"
    assert demo.info().pixel_um == 0.065


def test_set_property_refuses_motion_devices(demo):
    for dev in sorted(MOTION_DEVICES):
        with pytest.raises(UnguardedMotion):
            demo.set_property(dev, "State", 0, token=T)  # even with the token


def test_light_on_needs_token_off_does_not(demo):
    with pytest.raises(UnguardedMotion):
        demo.lamp_on()
    with pytest.raises(UnguardedMotion):
        demo.aura_line_on("GREEN", 1.0)
    for dev, prop in sorted(LIGHT_PROPERTIES):
        with pytest.raises(UnguardedMotion):
            demo.set_property(dev, prop, 1)
    assert demo.light_state() == {"DiaLamp": "0", "Aura": "0", "AuraLine": ""}
    assert all(r.verified for r in demo.lamp_on(token=T))
    assert all(r.verified for r in demo.lamp_off())
    assert all(r.verified for r in demo.aura_line_on("GREEN", 1.0, token=T))
    assert all(r.verified for r in demo.aura_off())
    assert demo.set_property("LED", "Label", "470nm", token=T).verified


def test_camera_property_needs_no_token(demo):
    assert ("Camera", "Exposure") in CAMERA_PROPERTIES
    rb = demo.set_property("Camera", "Binning", 2)
    assert rb.verified and rb.device == "Camera"


@pytest.mark.parametrize("dev, prop", [("Camera", "SimulateCrash"), ("Camera", "Gain"),
                                       ("Aura", "State"), ("DiaLamp", "State"),
                                       ("LED Shutter", "State Device"), ("Dichroic", "State")])
def test_set_property_outside_allow_list_refused(demo, dev, prop):
    with pytest.raises(PropertyNotAllowed, match="allowed:"):
        demo.set_property(dev, prop, 1, token=T)


def test_provisional_aura_line_is_logged_not_named(demo):
    recs = demo.aura_line_on("CYAN", 2.0, token=T)
    assert all(r.verified for r in recs)
    assert all("provisional" not in r.device + r.prop for r in recs)
    sub = demo.substitutions[-1]
    assert sub == {**sub, "kind": "aura_line", "line": "CYAN", "demo_label": "470nm",
                   "status": "unmeasured provisional"}
    n = len(demo.substitutions)
    demo.aura_line_on("GREEN", 1.0, token=T)
    assert len(demo.substitutions) == n  # GREEN is bench-confirmed


def test_close_is_idempotent_and_dark():
    b = MmDemoBackend(roi=64)
    try:
        b.open()
    except DemoUnavailable as e:
        pytest.skip(f"Micro-Manager demo adapters not available: {e}")
    try:
        b.lamp_on(token=T)
    finally:
        b.close()
    b.close()
    assert b.dev is None
