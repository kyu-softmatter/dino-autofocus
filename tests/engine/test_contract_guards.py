"""Guards refuse what the 2026-09-30 rules forbid, using the in-memory FakeBackend."""

import pytest

from dino_autofocus.engine.guards import (
    FocusAxis,
    GuardError,
    SweepPlan,
    XYAxis,
    XYBox,
    best_z_um,
    registry_key,
    rotate_nosepiece,
    step_out_target,
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


def test_approach_keeps_the_bench_procedure(fake):
    fake.z = 0.0
    a = axis(fake, OIL)
    with pytest.raises(GuardError, match="below the sample window"):
        a.sweep(a.plan(2900, 10, 5), fake.snap, score=lambda f: 0.0)
    assert a.approach(2840) == 2840
    moves = [c[1] for c in fake.calls if c[0] == "move_z"]
    assert moves == [2800, 2810, 2820, 2830, 2840]  # one move to 2800, then 10 um steps
    assert a.motions[-1]["basis"]["approach_step_um"] == (
        "OBJECTIVE_LIMITS[100x-Oil].approach_step_um, unmeasured provisional")
    with pytest.raises(GuardError, match="larger than"):
        a.approach(2900, step_um=700)


def test_the_clearance_check_runs_at_every_step(fake):
    fake.z = 0.0
    seen = []

    def clearance(z):
        seen.append(z)
        return z < 2825

    with pytest.raises(GuardError, match="clearance check stopped the approach at 2830"):
        axis(fake, OIL).approach(2900, clearance=clearance)
    assert seen == [2800, 2810, 2820, 2830] and fake.z == 2830


def test_xy_long_moves_follow_the_objective_table(fake):
    box = XYBox.around((8026.0, 571.6), 3572)
    xy = XYAxis(fake, box, allow_motion=True)
    with pytest.raises(GuardError, match="outside the box"):
        xy.goto(20000, 0)
    assert xy.goto(9683.7, -1086.0) == (9683.7, -1086.0)  # 4x: one tile at sample Z
    assert xy.motions[-1]["basis"]["long_move_um"] == (
        "OBJECTIVE_LIMITS[4x].long_xy_um, unmeasured provisional")
    fake.state = 5  # 100x Oil read back from the nosepiece
    assert xy.goto(9783.7, -1086.0)  # 100 um, under one 100x field
    with pytest.raises(GuardError, match=r"over 156 um \(100x-Oil\) needs Z retracted"):
        xy.goto(10683.7, -1086.0)
    fake.z = 0.0
    assert xy.goto(10683.7, -1086.0) == (10683.7, -1086.0)
    assert "caller" not in str(xy.motions)


@pytest.mark.parametrize("why", ["unreadable", "not in the table"])
def test_unknown_objective_means_retract_before_any_move(fake, why):
    if why == "unreadable":
        def broken():
            raise OSError("Nosepiece not answering")
        fake.nosepiece = broken
    else:
        fake.nosepiece = lambda: "7-Plan Fluor 2x"
    xy = XYAxis(fake, XYBox(-1e5, 1e5, -1e5, 1e5), allow_motion=True)
    with pytest.raises(GuardError, match="strictest"):
        xy.goto(8030.0, 571.6)  # even 4 um
    fake.z = 0.0
    assert xy.goto(8030.0, 571.6) == (8030.0, 571.6)
    assert xy.motions[-1]["basis"]["long_move_um"].startswith("OBJECTIVE_LIMITS[strictest")


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


def test_a_hand_built_plan_cannot_pass_the_ceiling(fake):
    a = axis(fake, OIL)
    bad = SweepPlan("100x-Oil", 2985, 200, 20, 3200, [2985 + 20 * i for i in range(11)])
    with pytest.raises(GuardError, match="leaves"):
        a.sweep(bad, fake.snap, score=lambda f: 0.0)
    assert not any(c[0] == "move_z" for c in fake.calls)
    jump = SweepPlan("100x-Oil", 2985, 20, 2, 3037, [2970.0, 2980.0])
    with pytest.raises(GuardError, match="steps of at most"):
        a.sweep(jump, fake.snap, score=lambda f: 0.0)
    with pytest.raises(GuardError, match="plan is for"):
        axis(fake).sweep(a.plan(2985, 10, 2), fake.snap, score=lambda f: 0.0)


def test_approach_stops_when_the_stage_stalls(fake):
    fake.z = 0.0
    a = axis(fake)
    with pytest.raises(GuardError, match="exceed the readback tolerance"):
        a.approach(2900, step_um=0.1)
    fake.move_z = lambda z_um, *, token: fake.z  # stage does not move
    with pytest.raises(GuardError):
        a.approach(2900)
    assert len(a.motions) == 1
    fake.z = 2800.0  # already in the window: the first table step must rise
    with pytest.raises(GuardError):
        a.approach(2900)


def test_pfs_is_not_touched_without_allow_motion(fake):
    fake.z, fake.pfs_enabled = 0.0, True
    with pytest.raises(GuardError, match="allow_motion"):
        rotate_nosepiece(fake, FocusAxis(fake, "4x"), 5)
    with pytest.raises(GuardError, match="allow_motion"):
        FocusAxis(fake, "4x").require_pfs_quiet()
    assert fake.pfs_enabled


def test_relative_xy_moves_go_through_the_absolute_guard(fake):
    xy = XYAxis(fake, XYBox.around((8026.0, 571.6), 3572), allow_motion=True)
    assert xy.goto_rel(200.0, 0.0) == (8226.0, 571.6)  # an edge_trace step
    assert xy.motions[-1]["target_um"] == [8226.0, 571.6]
    with pytest.raises(GuardError, match="outside the box"):
        xy.goto_rel(5000.0, 0.0)
    fake.state = 5  # 100x Oil: 200 um is over its 156 um row
    with pytest.raises(GuardError, match="needs Z retracted"):
        xy.goto_rel(200.0, 0.0)
    assert not any(c[0] == "move_xy_rel" for c in fake.calls)


@pytest.mark.parametrize("kind", ["mm-real", "something-new"])
def test_approach_on_a_bench_needs_a_clearance_check(fake, kind):
    real_info = fake.info

    def bench_info():
        info = real_info()
        info.kind = kind
        return info
    fake.info = bench_info  # a bench-flagged FakeBackend
    fake.z = 0.0
    a = axis(fake, OIL)
    with pytest.raises(GuardError, match="needs a clearance check"):
        a.approach(2840)
    assert not any(c[0] == "move_z" for c in fake.calls)
    assert a.approach(2840, clearance=lambda z: True) == 2840


def test_the_step_out_is_plus_y_and_stays_inside_the_stage_travel(fake):
    x, y, basis = step_out_target(fake, 8026.0, 571.6)  # fake Y travel -35..35 mm
    assert (x, y) == (8026.0, 15571.6)
    assert basis["basis"]["escape_dy_um"] == "unmeasured provisional"
    with pytest.raises(GuardError, match="outside the stage Y travel"):
        step_out_target(fake, 8026.0, 25000.0)
    real_info = fake.info

    def no_limits():
        info = real_info()
        info.stage_limits.y_um = None
        return info
    fake.info = no_limits
    with pytest.raises(GuardError, match="no stage Y limit"):
        step_out_target(fake, 8026.0, 571.6)
