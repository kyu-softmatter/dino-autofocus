"""Guards refuse what the 2026-09-30 rules forbid, using the in-memory FakeBackend."""

import pytest

from dino_autofocus.engine.guards import (
    FocusAxis,
    GuardError,
    XYAxis,
    XYBox,
    best_z_um,
    registry_key,
    rotate_nosepiece,
)
from dino_autofocus.engine.records import model_value

OIL = "6-Plan Apo LmbdD0.13 100x Oil"


def axis(fake, objective="4x", **kw):
    return FocusAxis(fake, objective, allow_motion=True, sleep=lambda s: None, **kw)


def test_registry_keys():
    assert registry_key("1-Plan Apo LmbdD20 4x") == "4x"
    assert registry_key(OIL) == "100x-Oil"
    assert registry_key("4-Plan Apo 40x WI") == "40x-WI"


def test_plans_ascend_inside_the_window_and_under_the_100x_ceiling(fake):
    p = axis(fake).plan(2810, 30, 10)
    assert p.z_um == [2800, 2810, 2820, 2830, 2840]  # clipped at the window floor
    p = axis(fake, OIL).plan(2985, 80, 2)
    assert p.ceiling_um == pytest.approx(2985 + 0.4 * 130) and p.z_um[-1] <= p.ceiling_um
    assert p.z_um == sorted(p.z_um)
    with pytest.raises(GuardError, match="working distance"):
        axis(fake, "3-Plan Apo 20x").plan(3000, 10, 1)
    with pytest.raises(GuardError):
        axis(fake).plan(3400, 50, 5)


def test_moves_outside_the_window_or_too_far_up_are_refused(fake):
    a = axis(fake)
    with pytest.raises(GuardError, match="window"):
        a.move_to(3201)
    with pytest.raises(GuardError, match="move up"):
        a.move_to(2950)
    assert a.move_to(2950, allow_ascent_um=50) == 2950
    assert a.move_to(2850) == 2850  # down is always allowed
    with pytest.raises(GuardError, match="only descends"):
        a.park_at(2900)
    assert a.park_at(0) == 0


def test_readback_mismatch_stops(fake):
    fake.z_readback_offset_um = -1.0  # 3037 commanded, 3036 read
    fake.z = 3036.0
    with pytest.raises(GuardError, match="read 3036"):
        axis(fake).move_to(3037, allow_ascent_um=2)


def test_no_motion_without_permission_and_dry_run_sends_nothing(fake):
    with pytest.raises(GuardError, match="allow_motion"):
        FocusAxis(fake, "4x").move_to(2850)
    a = FocusAxis(fake, "4x", dry_run=True)
    a.sweep(a.plan(2900, 20, 10), grab=fake.snap)
    assert fake.z == 2900 and not any(c[0] == "move_z" for c in fake.calls)
    assert a.motions and not any(m["sent"] for m in a.motions)


def test_a_model_number_cannot_drive_motion(fake):
    with pytest.raises(GuardError, match="model output"):
        axis(fake).move_to(model_value(2850.0, "dino head"))


def test_sweep_finds_an_interior_peak_from_the_readback(fake):
    a = axis(fake)
    score = lambda f: {"sharp": -abs(f.z_um - 2913.0), "sat": 0.0}  # noqa: E731
    coarse = a.sweep(a.plan(2900, 30, 10), fake.snap, score=score)
    assert coarse.peak_interior and coarse.peak_z_um == 2910
    fine = a.sweep(a.plan(coarse.peak_z_um, 4, 1), fake.snap, score=score)
    assert best_z_um(coarse, fine) == (2913, "fine peak inside its span")
    assert [c[1] for c in fake.calls if c[0] == "move_z"][:4] == [2870, 2880, 2890, 2900]


def test_a_peak_on_the_top_plane_is_not_climbed(fake):
    a = axis(fake, OIL)
    res = a.sweep(a.plan(2985, 20, 5), fake.snap, score=lambda f: f.z_um)
    assert res.at_top and not res.peak_interior
    z, why = best_z_um(res, None)
    assert z is None and "operator" in why
    assert fake.z == 3005  # stopped at the plan's top


def test_approach_climbs_in_read_back_steps(fake):
    fake.z = 0.0
    a = axis(fake)
    with pytest.raises(GuardError, match="below the sample window"):
        a.sweep(a.plan(2900, 10, 5), fake.snap, score=lambda f: 0.0)
    assert a.approach(2800, step_um=700) == 2800
    assert [c[1] for c in fake.calls if c[0] == "move_z"] == [700, 1400, 2100, 2800]


def test_xy_box_and_long_moves_need_z_retracted(fake):
    box = XYBox.around((8026.0, 571.6), 3572)
    xy = XYAxis(fake, box, allow_motion=True, fov_um=3901)  # 4x: threshold min(fov, 1 mm)
    with pytest.raises(GuardError, match="outside the box"):
        xy.goto(20000, 0)
    assert xy.goto(8500.0, 571.6) == (8500.0, 571.6)
    with pytest.raises(GuardError, match="Z retracted"):
        xy.goto(9683.7, -1086.0)  # one 4x tile away, ~2.3 mm
    assert xy.motions[-1]["basis"]["long_move_um"] == "unmeasured provisional"
    tiles = XYAxis(fake, box, allow_motion=True, long_move_um=4000)  # scan_4x's own value
    assert tiles.goto(9683.7, -1086.0) == (9683.7, -1086.0)
    assert tiles.motions[-1]["basis"]["long_move_um"] == "caller"
    fake.z = 0.0
    assert xy.goto(6368.3, 2229.5) == (6368.3, 2229.5)


def test_xy_readback_mismatch_stops(fake):
    xy = XYAxis(fake, XYBox(-1e5, 1e5, -1e5, 1e5), allow_motion=True)
    fake.move_xy = lambda x, y, *, token, timeout_s=None: (x + 20.0, y)  # hand on the joystick
    with pytest.raises(GuardError, match="XY commanded"):
        xy.goto(8100.0, 571.6)


def test_nosepiece_turns_only_retracted_with_pfs_out_of_range(fake):
    a = axis(fake)
    with pytest.raises(GuardError, match="not retracted"):
        rotate_nosepiece(fake, a, 5)
    a.park_at(0)
    fake.pfs_in_range = "In Range"
    with pytest.raises(GuardError, match="refusing to rotate"):
        rotate_nosepiece(fake, a, 5)
    fake.pfs_in_range, fake.pfs_enabled = "Out of Range", True
    assert rotate_nosepiece(fake, a, 5) == OIL and not fake.pfs_enabled
