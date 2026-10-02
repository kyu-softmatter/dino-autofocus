"""Motion guards and the lights-off / single-owner scopes. Safety is decided here, in code.

Rules (docs/runs/2026-09-30_substrate-scan.md, scripts/change_objective.py, focus_100x.py):

- Z targets stay inside the sample window 2800-3200 um. Below it only `park_at` (descend
  only) goes, e.g. to the 0 um retract of an objective change.
- Upward moves (toward the sample) are refused unless the caller allows that much ascent
  (`move_to(z, allow_ascent_um=)`); sweeps are planned ascending and climb one step at a
  time. Descents are always allowed.
- A sweep's ceiling is min(3200, centre + 0.4 x free working distance): 130 um for the
  100x Oil. An objective with no known working distance gets no plan.
- If a sweep's peak is on its top plane it does not climb further (`at_top`); the
  operation asks the operator with `scope.ask("climb_past_top", ...)`.
- Every move is read back; off by more than the tolerance stops the operation
  (2026-09-30: commanded 3037.0, read 3036.0 -> stopped).
- Coming back from a retract, Z does not jump to its target. `approach` keeps the bench
  procedure: one move up to 2800 um (the bottom of the sample window), then steps of at
  most the objective's `approach_step_um` with readback, a rise check and the caller's
  clearance check at every step (soft-matter-agents task 026: a handed-over Z is a goal,
  not a destination).
- XY targets stay in the box (+1 mm). A move longer than the objective's `long_xy_um`
  in `OBJECTIVE_LIMITS` needs Z retracted to z_safe, confirmed by readback. The objective is read
  back from the nosepiece at each move; unreadable or not in the table means the
  strictest value (any move needs Z retracted). There is no per-operation override
  (director, PLAN section 5). At integration the table moves to soft-matter-agents
  `envelope/`.
- Values not yet measured on the stand are marked `PROVISIONAL` ("unmeasured
  provisional") here and in every motion record whose decision used them
  (docs/microscope-pc-checklist.md).
- Manual steps (oil loaded) are `scope.ask` -> `confirm` command -> `confirmed` event.
- The nosepiece turns only with Z retracted and PFS off and out of range.
- `operation()` switches Aura and DiaLamp off and reads them back on every exit path.
- One engine owns the backend at a time (`exclusive`).
- A model-graded value (`records.Graded`, grade "model") is refused as any guard input.
- `dry_run=True` records the motion and sends nothing.

Method names follow agentic_microscope's FocusAxis as the scripts call it (T-002 appendix),
so operations port from `scripts/` mechanically.
"""

from __future__ import annotations

import math
import queue
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .backend import GUARD_TOKEN, Backend, BackendInfo, PfsState, Readback
from .events import Event, EventSink, fan_out, null_sink
from .records import GRADE_MODEL, Graded, OpRecord

PROVISIONAL = "unmeasured provisional"

SAMPLE_Z_WINDOW_UM = (2800.0, 3200.0)  # measured window of the 2026-09-30 bench
RETRACT_Z_UM, RETURN_Z_UM = 0.0, 2800.0  # change_objective.py
WD_FRACTION = 0.4
FREE_WD_UM = {"4x": 20000.0, "100x-Oil": 130.0}  # lens spec; add a lens only once known
XY_BOX_MARGIN_UM = 1000.0
# Backends with no real stage. Any other kind (mm-real, or one this file does not know) is
# a bench: approach() there refuses to run without a clearance check.
SIMULATED_KINDS = frozenset({"mock", "fake", "replay", "mm-demo"})

# unmeasured provisional (checklist Q20 / Q12); every use is marked in the record
Z_SAFE_UM = 0.0  # z_safe: full retract, for every lens
RETRACTED_MAX_Z_UM = Z_SAFE_UM + 1.0  # "Z retracted" for nosepiece turns and long XY moves
# F5 immersion-loading step-out: +Y by 15 mm (user, PLAN v1.3). Stage-level, not per lens.
ESCAPE_DY_UM: float = +15000.0
Z_TOL_UM = 0.25
XY_TOL_UM = 5.0


@dataclass(frozen=True)
class ObjectiveLimits:
    """One row of the per-objective guard table. Every value is unmeasured provisional."""

    long_xy_um: float  # an XY move longer than this needs Z retracted first
    approach_step_um: float  # largest Z step when climbing back above 2800 um


# The per-objective guard table (registry key -> row), unmeasured provisional; it moves to
# soft-matter-agents envelope/ at integration.
# long_xy_um: free WD >= 10 mm -> 10 mm (4x tile steps of 3.3 mm stay at sample Z, as on
#   2026-09-30; the F5 escape of 15-20 mm still retracts); otherwise min(field of view,
#   1 mm), field = 2400 px x the calibrated pixel (configs/ti2_*.yaml, catalogue WD).
# approach_step_um: 10 um for every lens to start, about WD/13 for the 100x Oil (checklist
#   Q13); to be confirmed on the bench before M4.
OBJECTIVE_LIMITS: dict[str, ObjectiveLimits] = {
    "4x": ObjectiveLimits(10000.0, 10.0),  # WD 20 mm
    "10x": ObjectiveLimits(1000.0, 10.0),  # WD 4 mm, field 1.56 mm
    "20x": ObjectiveLimits(777.0, 10.0),  # WD 0.8 mm, field 0.777 mm
    "40x-WI": ObjectiveLimits(390.0, 10.0),  # WD 0.16 mm, field 0.39 mm
    "60x-Oil": ObjectiveLimits(260.0, 10.0),  # WD 0.15 mm, field 0.26 mm
    "100x-Oil": ObjectiveLimits(156.0, 10.0),  # WD 0.13 mm, field 0.156 mm
}
# objective unreadable or not in the table: retract before any XY move, smallest Z step
STRICTEST = ObjectiveLimits(0.0, min(r.approach_step_um for r in OBJECTIVE_LIMITS.values()))


def limits_for(label_or_key: str | None) -> tuple[ObjectiveLimits, str]:
    """(row, row name) for a nosepiece label or registry key; the strictest row if unknown."""
    if label_or_key is None:
        return STRICTEST, "strictest (objective unreadable)"
    key = label_or_key
    if key not in OBJECTIVE_LIMITS:
        try:
            key = registry_key(label_or_key)
        except GuardError:
            return STRICTEST, f"strictest ({label_or_key!r} has no magnification)"
    if key not in OBJECTIVE_LIMITS:
        return STRICTEST, f"strictest ({key} not in OBJECTIVE_LIMITS)"
    return OBJECTIVE_LIMITS[key], key


class GuardError(RuntimeError):
    """A guard refused; the operation stops."""


class OperationAborted(RuntimeError):
    """The operator (or an abort command) stopped the operation."""


def plain(v: Any, what: str) -> float:
    if isinstance(v, Graded):
        if v.grade == GRADE_MODEL:
            raise GuardError(f"{what}: a model output cannot drive motion ({v.source})")
        v = v.value
    f = float(v)
    if not math.isfinite(f):
        raise GuardError(f"{what}: {f} is not a finite number")
    return f


def registry_key(nosepiece_label: str) -> str:
    """'1-Plan Apo LmbdD20 4x' -> '4x'; '6-Plan Apo LmbdD0.13 100x Oil' -> '100x-Oil';
    '4-Apo LmbdS 40xC WI' -> '40x-WI'; 'Ti2 40x/1.25 water (...)' -> '40x-WI'.

    The magnification is digits then "x", followed by a letter (the "C" of 40xC) or a word
    boundary, and not part of a decimal such as LmbdD0.13."""
    m = re.search(r"(?<![\d.])(\d+)x(?=[A-Za-z]|\b)", nosepiece_label)
    if not m:
        raise GuardError(f"no magnification in objective label {nosepiece_label!r}")
    low = nosepiece_label.lower()
    suffix = "-Oil" if "oil" in low else "-WI" if (" wi" in low or "water" in low) else ""
    return f"{m.group(1)}x{suffix}"


# -- Z ------------------------------------------------------------------------------------
@dataclass
class SweepPlan:
    objective: str
    centre_um: float
    half_um: float
    step_um: float
    ceiling_um: float
    z_um: list[float]

    def describe(self) -> str:
        return (f"{self.objective}: {len(self.z_um)} planes {self.z_um[0]:.2f} -> "
                f"{self.z_um[-1]:.2f} um, step {self.step_um} (ascending), "
                f"ceiling {self.ceiling_um:.2f}")


@dataclass
class SweepPoint:
    z_um: float
    z_readback_um: float
    score: float | None
    diagnostics: dict = field(default_factory=dict)


@dataclass
class SweepResult:
    plan: SweepPlan
    points: list[SweepPoint]
    argmax_index: int | None
    peak_z_um: float | None  # the readback of the best plane, not the commanded z
    peak_interior: bool
    at_top: bool


def best_z_um(coarse: SweepResult, fine: SweepResult | None) -> tuple[float | None, str]:
    if fine is not None and fine.peak_interior:
        return fine.peak_z_um, "fine peak inside its span"
    if coarse.peak_interior:
        return coarse.peak_z_um, "coarse peak (no fine pass, or its peak on an end)"
    if coarse.at_top:
        return None, "peak at the top end: focus may be higher; the operator decides"
    if coarse.argmax_index is None:
        return None, "no scored planes"
    return None, "peak at the low end: focus is below the span; re-centre lower"


def _score(fn: Callable | None, frame: Any) -> tuple[float | None, dict]:
    r = frame if fn is None else fn(frame)
    if isinstance(r, Mapping):
        s = r.get("score", r.get("sharp"))
        return (None if s is None else float(s)), dict(r)
    if isinstance(r, tuple):
        return float(r[0]), dict(r[1])
    return float(r), {}


class FocusAxis:
    def __init__(self, backend: Backend, objective: str, *, allow_motion: bool = False,
                 dry_run: bool = False, sink: EventSink = null_sink, op_id: str = "",
                 window: tuple[float, float] = SAMPLE_Z_WINDOW_UM, tol_um: float = Z_TOL_UM,
                 sleep: Callable[[float], None] = time.sleep):
        self.b, self.allow_motion, self.dry_run = backend, allow_motion, dry_run
        self.key = objective if objective in FREE_WD_UM else registry_key(objective)
        self.emit, self.op_id, self.window = sink, op_id, window
        self.tol, self.sleep = tol_um, sleep
        self.motions: list[dict] = []
        self._z_dry: float | None = None

    def position_um(self) -> float:
        if self.dry_run and self._z_dry is not None:
            return self._z_dry
        p = self.b.positions()
        if p.z_um is None:
            raise GuardError(f"ZDrive unreadable: {p.errors.get('z', p.errors)}")
        return p.z_um

    def ceiling_um(self, centre_um: float) -> float:
        if self.key not in FREE_WD_UM:
            raise GuardError(f"no free working distance recorded for {self.key!r}")
        return min(self.window[1], centre_um + WD_FRACTION * FREE_WD_UM[self.key])

    def plan(self, centre_um: float, half_um: float, step_um: float) -> SweepPlan:
        c, h, s = plain(centre_um, "centre"), plain(half_um, "half"), plain(step_um, "step")
        if s <= 0 or h < 0:
            raise GuardError(f"step {s} must be > 0 and half range {h} >= 0")
        top = self.ceiling_um(c)
        lo, hi = max(self.window[0], c - h), min(top, c + h)
        if lo > hi:
            raise GuardError(f"sweep {c - h:.2f}..{c + h:.2f} um is outside "
                             f"{self.window[0]:.0f}..{top:.2f} um")
        n = int(math.floor((hi - lo) / s + 1e-9)) + 1
        return SweepPlan(self.key, c, h, s, top, [round(lo + i * s, 4) for i in range(n)])

    def _send(self, z: float, how: str, basis: dict | None = None) -> float:
        if self.dry_run:
            read, sent = z, False
            self._z_dry = z
        else:
            if not self.allow_motion:
                raise GuardError("FocusAxis was made with allow_motion=False")
            read, sent = self.b.move_z(z, token=GUARD_TOKEN), True
        rec = {"axis": "z", "how": how, "target_um": z, "read_um": read, "sent": sent,
               "tol_um": self.tol, "basis": {"tol_um": PROVISIONAL, **(basis or {})}}
        self.motions.append(rec)
        self.emit(Event("motion", self.op_id, rec))
        if abs(read - z) > self.tol:
            raise GuardError(f"ZDrive commanded {z:.3f}, read {read:.3f} um "
                             f"(tolerance {self.tol} um)")
        return read

    def move_to(self, z_um: float, allow_ascent_um: float = 0.0) -> float:
        z, up = plain(z_um, "z target"), plain(allow_ascent_um, "allowed ascent")
        if not self.window[0] <= z <= self.window[1]:
            raise GuardError(f"z {z:.2f} um is outside the window {self.window}")
        rise = z - self.position_um()
        if rise > up + self.tol:
            raise GuardError(f"move up by {rise:.2f} um; only {up:.2f} um allowed")
        return self._send(z, "move_to")

    def park_at(self, z_um: float) -> float:
        z = plain(z_um, "park z")
        if z < RETRACT_Z_UM or z > self.window[1]:
            raise GuardError(f"park z {z:.2f} um outside {RETRACT_Z_UM}..{self.window[1]}")
        if z > self.position_um() + self.tol:
            raise GuardError("park_at only descends")
        return self._send(z, "park_at")

    def require_pfs_quiet(self, disable: bool = True) -> PfsState:
        s = self.b.pfs()
        if s.enabled and disable and not self.dry_run:
            if not self.allow_motion:
                raise GuardError("PFS is on and FocusAxis was made with allow_motion=False")
            rb = self.b.pfs_off(token=GUARD_TOKEN)
            self.emit(Event("property_set", self.op_id, asdict(rb)))
            s = self.b.pfs()
        if s.enabled and not self.dry_run:
            raise GuardError(f"PFS still enabled: {s}")
        return s

    def sweep(self, plan: SweepPlan, grab: Callable[[], Any], score: Callable | None = None,
              settle_s: float = 0.0) -> SweepResult:
        self._check_plan(plan)
        first, here = plan.z_um[0], self.position_um()
        if here < self.window[0] - self.tol:
            raise GuardError(f"Z {here:.2f} um is below the sample window; bring it up first")
        if here > first:
            self.park_at(first)
        else:
            self.move_to(first, allow_ascent_um=first - here)
        pts: list[SweepPoint] = []
        for i, z in enumerate(plan.z_um):
            read = self._send_step(z, plan.step_um) if i else self.position_um()
            if self.dry_run:
                pts.append(SweepPoint(z, read, None))
                continue
            self.sleep(settle_s)
            s, diag = _score(score, grab())
            pts.append(SweepPoint(z, read, s, diag))
        ok = [i for i, p in enumerate(pts) if p.score is not None and math.isfinite(p.score)]
        k = max(ok, key=lambda i: pts[i].score) if ok else None
        return SweepResult(plan, pts, k, None if k is None else pts[k].z_readback_um,
                           k is not None and 0 < k < len(pts) - 1,
                           k is not None and k == len(pts) - 1 and len(pts) > 1)

    def _simulated(self) -> bool:
        try:
            return self.b.info().kind in SIMULATED_KINDS
        except Exception:  # noqa: BLE001 - an unreadable backend counts as a bench
            return False

    def _check_plan(self, plan: SweepPlan) -> None:
        """A plan is re-checked here, so a hand-built one cannot pass the ceiling."""
        z = [plain(v, "plan z") for v in plan.z_um]
        if plan.objective != self.key:
            raise GuardError(f"plan is for {plan.objective!r}, this axis is {self.key!r}")
        if not z:
            raise GuardError("empty sweep plan")
        top = self.ceiling_um(plain(plan.centre_um, "plan centre"))
        if z[0] < self.window[0] or z[-1] > top + 1e-6:
            raise GuardError(f"plan {z[0]:.2f}..{z[-1]:.2f} um leaves "
                             f"{self.window[0]:.0f}..{top:.2f} um")
        step = plain(plan.step_um, "plan step")
        if any(not 0 < b - a <= step + 1e-6 for a, b in zip(z, z[1:], strict=False)):
            raise GuardError(f"plan z is not ascending in steps of at most {step} um")

    def _send_step(self, z: float, step: float) -> float:
        return self.move_to(z, allow_ascent_um=step)

    def approach(self, target_um: float, step_um: float | None = None,
                 clearance: Callable[[float], bool] | None = None) -> float:
        """Climb to `target_um` by the bench procedure: from below 2800 um one move to 2800,
        then steps of at most the objective's `approach_step_um` (a smaller `step_um` may
        be asked for, never a larger one). After every move the readback must match and
        rise, and `clearance(z_read)` must return True, or the approach stops with
        GuardError. On a bench backend (kind not in SIMULATED_KINDS) `clearance` is
        required. Above the target it descends straight there."""
        z = plain(target_um, "approach target")
        if not self.window[0] <= z <= self.window[1]:
            raise GuardError(f"approach target {z:.2f} um is outside the window {self.window}")
        if clearance is None and not self.dry_run and not self._simulated():
            raise GuardError("approach on a bench backend needs a clearance check "
                             "(clearance=callable(z_read) -> bool)")
        row, name = limits_for(self.key)
        step = row.approach_step_um
        if step_um is not None:
            asked = plain(step_um, "approach step")
            if asked > step:
                raise GuardError(f"approach step {asked} um is larger than {name}'s "
                                 f"{step} um ({PROVISIONAL})")
            step = asked
        if step <= self.tol:
            raise GuardError(f"approach step {step} um must exceed the readback tolerance "
                             f"{self.tol} um")
        basis = {"approach_step_um": f"OBJECTIVE_LIMITS[{name}].approach_step_um, {PROVISIONAL}"}
        here = self.position_um()
        if here >= z:
            return self.move_to(z)

        def check(read: float, before: float) -> float:
            if read <= before:
                raise GuardError(f"Z did not rise: read {read:.3f} um after {before:.3f} um")
            if clearance is not None and not clearance(read):
                raise GuardError(f"clearance check stopped the approach at {read:.3f} um")
            return read

        if here < RETURN_Z_UM - self.tol:
            here = check(self._send(RETURN_Z_UM, "approach_to_window", basis), here)
        for _ in range(int(math.ceil((z - here) / step)) + 1):
            if here >= z - self.tol:
                return here
            here = check(self._send(min(z, here + step), "approach", basis), here)
        if here >= z - self.tol:
            return here
        raise GuardError(f"approach to {z:.2f} um did not arrive (Z reads {here:.2f} um)")


def rotate_nosepiece(backend: Backend, focus: FocusAxis, state: int) -> str:
    """Turn the nosepiece: only with Z retracted, PFS off and out of range. Returns the label."""
    z = focus.position_um()
    basis = {"z_um": z, "retracted_max_um": RETRACTED_MAX_Z_UM,
             "basis": {"retracted_max_um": PROVISIONAL}}
    if z > RETRACTED_MAX_Z_UM:
        raise GuardError(f"Z {z:.2f} um is not retracted (<= {RETRACTED_MAX_Z_UM})")
    if not focus.allow_motion and not focus.dry_run:
        raise GuardError("FocusAxis was made with allow_motion=False")
    s = focus.require_pfs_quiet(disable=True)
    if not s.out_of_range and not focus.dry_run:
        raise GuardError(f"PFS reads {s.in_range!r} after retract; refusing to rotate")
    if focus.dry_run:
        focus.emit(Event("motion", focus.op_id, {"axis": "nosepiece", "target": state,
                                                 "sent": False, **basis}))
        return backend.nosepiece()
    rb = backend.set_nosepiece(int(state), token=GUARD_TOKEN)
    focus.emit(Event("motion", focus.op_id, {"axis": "nosepiece", "target": state,
                                             "sent": True, "read": rb.read, **basis}))
    if not rb.verified:
        raise GuardError(f"Nosepiece reads {rb.read}, not {state}")
    return backend.nosepiece()


def step_out_target(backend: Backend, x_um: float, y_um: float) -> tuple[float, float, dict]:
    """(x, y, basis) of the F5 step-out from (x_um, y_um): +ESCAPE_DY_UM in Y. Refused when
    the backend reports no Y travel or the target is outside it. The move itself still goes
    through XYAxis.goto (box, Z retracted for a long move, readback)."""
    x, y = plain(x_um, "x"), plain(y_um, "y")
    target = y + ESCAPE_DY_UM
    try:
        limits = backend.info().stage_limits.y_um
    except Exception as exc:  # noqa: BLE001 - no limits read means no step-out
        raise GuardError(f"stage Y limit unreadable ({type(exc).__name__}: {exc}); "
                         "refusing the step-out") from None
    if limits is None:
        raise GuardError("the backend reports no stage Y limit; refusing the step-out")
    lo, hi = limits
    if not lo <= target <= hi:
        raise GuardError(f"step-out to y {target:.0f} um is outside the stage Y travel "
                         f"{lo:.0f}..{hi:.0f} um")
    basis = {"escape_dy_um": ESCAPE_DY_UM, "basis": {"escape_dy_um": PROVISIONAL},
             "stage_y_um": [lo, hi]}
    return x, target, basis


# -- XY -----------------------------------------------------------------------------------
@dataclass
class XYBox:
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @classmethod
    def around(cls, centre: tuple[float, float], half_um: float,
               margin_um: float = XY_BOX_MARGIN_UM) -> XYBox:
        r = half_um + margin_um
        return cls(centre[0] - r, centre[0] + r, centre[1] - r, centre[1] + r)

    def contains(self, x: float, y: float) -> bool:
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max


class XYAxis:
    """XY moves inside the box, read back. The long-move threshold is `long_xy_um` in
    `OBJECTIVE_LIMITS` for the objective read back at each move; the motion record names
    the table row."""

    def __init__(self, backend: Backend, box: XYBox, *, allow_motion: bool = False,
                 dry_run: bool = False, sink: EventSink = null_sink, op_id: str = "",
                 timeout_s: float | None = None, tol_um: float = XY_TOL_UM):
        self.b, self.box, self.allow_motion, self.dry_run = backend, box, allow_motion, dry_run
        self.emit, self.op_id, self.timeout, self.tol = sink, op_id, timeout_s, tol_um
        self.motions: list[dict] = []

    def long_move_um(self) -> tuple[float, str]:
        """(threshold, table row) for the objective in place now, read back."""
        try:
            label = self.b.nosepiece()
        except Exception:  # noqa: BLE001 - unreadable objective: the strictest row
            label = None
        row, name = limits_for(label)
        return row.long_xy_um, name

    def goto_rel(self, dx_um: float, dy_um: float) -> tuple[float, float]:
        """Relative move (edge_trace steps): readback + delta becomes an absolute target and
        goes through `goto`, so the box, the long-move rule and the readback check apply.
        The backend's own move_xy_rel is never called from here."""
        dx, dy = plain(dx_um, "dx"), plain(dy_um, "dy")
        p = self.b.positions()
        if p.x_um is None or p.y_um is None:
            raise GuardError(f"position unreadable before a relative XY move: {p.errors}")
        return self.goto(p.x_um + dx, p.y_um + dy)

    def goto(self, x_um: float, y_um: float) -> tuple[float, float]:
        x, y = plain(x_um, "x target"), plain(y_um, "y target")
        if not self.box.contains(x, y):
            raise GuardError(f"XY ({x:.0f}, {y:.0f}) is outside the box {self.box}")
        p = self.b.positions()
        if p.x_um is None or p.y_um is None or p.z_um is None:
            raise GuardError(f"position unreadable before an XY move: {p.errors}")
        long_um, row = self.long_move_um()
        basis = {"long_move_um": f"OBJECTIVE_LIMITS[{row}].long_xy_um, {PROVISIONAL}",
                 "tol_um": PROVISIONAL,
                 "retracted_max_um": PROVISIONAL}
        if math.hypot(x - p.x_um, y - p.y_um) > long_um and p.z_um > RETRACTED_MAX_Z_UM:
            raise GuardError(f"XY move over {long_um:.0f} um ({row}) needs Z retracted; "
                             f"Z reads {p.z_um:.2f} um")
        if self.dry_run:
            read, sent = (x, y), False
        else:
            if not self.allow_motion:
                raise GuardError("XYAxis was made with allow_motion=False")
            read = self.b.move_xy(x, y, token=GUARD_TOKEN, timeout_s=self.timeout)
            sent = True
        rec = {"axis": "xy", "target_um": [x, y], "read_um": list(read), "sent": sent,
               "z_um": p.z_um, "long_move_um": long_um, "tol_um": self.tol, "basis": basis}
        self.motions.append(rec)
        self.emit(Event("motion", self.op_id, rec))
        if math.hypot(read[0] - x, read[1] - y) > self.tol:
            raise GuardError(f"XY commanded ({x:.1f}, {y:.1f}), read ({read[0]:.1f}, "
                             f"{read[1]:.1f}) um")
        return read


# -- scopes -------------------------------------------------------------------------------
_OWNER = threading.Lock()


@contextmanager
def exclusive(backend: Backend, sink: EventSink = null_sink) -> Iterator[BackendInfo]:
    """Open the backend as its only owner in this process; lights off and close on exit."""
    if not _OWNER.acquire(blocking=False):
        raise GuardError("another engine already owns the microscope")
    try:
        info = backend.open()
        try:
            yield info
        finally:
            sink(Event("light_changed", "", lights_off(backend)))
            backend.close()
    finally:
        _OWNER.release()


def lights_off(backend: Backend) -> dict:
    """Aura and DiaLamp off with readback. Never raises: the result says what happened."""
    try:
        rbs = backend.all_off()
        ok = bool(rbs) and all(r.verified for r in rbs)  # an empty readback proves nothing
        return {"readbacks": [asdict(r) for r in rbs], "verified": ok,
                "error": None}
    except Exception as exc:  # noqa: BLE001 - recorded, and the caller's own error goes on
        return {"readbacks": [], "verified": False, "error": f"{type(exc).__name__}: {exc}"}


def snapshot(backend: Backend) -> dict:
    out: dict = {}
    for key, read in (("positions", lambda: asdict(backend.positions())),
                      ("lights", backend.light_state), ("objective", backend.nosepiece)):
        try:
            out[key] = read()
        except Exception as exc:  # noqa: BLE001 - a state read must not stop the record
            out[key] = f"unreadable: {type(exc).__name__}: {exc}"
    return out


@dataclass
class OpScope:
    """`answers` receives `confirm` Commands from whoever dispatches commands (the UI)."""

    op_id: str
    record: OpRecord
    emit: EventSink
    result: Any = None
    answers: queue.Queue = field(default_factory=queue.Queue)
    backend: Backend | None = None

    def lamp_on(self) -> list[Readback]:
        """Transmitted lamp on: the one legal way for an operation (D15). Off is the scope's
        exit path, or `backend.lamp_off()` / `all_off()`, which need no token."""
        return self.lights(self._backend().lamp_on(token=GUARD_TOKEN))

    def aura_line_on(self, line: str, percent: float) -> list[Readback]:
        """One Aura line on at `percent` (the backend converts to per-mille); lamp off first."""
        pct = plain(percent, "Aura percent")
        if not 0.0 < pct <= 100.0:
            raise GuardError(f"Aura percent {pct} is outside (0, 100]")
        return self.lights(self._backend().aura_line_on(str(line), pct, token=GUARD_TOKEN))

    def _backend(self) -> Backend:
        if self.backend is None:
            raise GuardError("this scope has no backend (made outside operation())")
        return self.backend

    def lights(self, readbacks: list[Readback]) -> list[Readback]:
        """Record a light change; any readback that does not verify stops the operation."""
        rbs = [asdict(r) for r in readbacks]
        self.emit(Event("light_changed", self.op_id, {"readbacks": rbs}))
        bad = [f"{r.device}.{r.prop} wanted {r.wanted}, read {r.read}" for r in readbacks
               if not r.verified]
        if bad:
            raise GuardError("light not verified: " + "; ".join(bad))
        return readbacks

    def ask(self, key: str, text: str, timeout_s: float | None = None, **data: Any) -> bool:
        """A manual step: emit `confirm_required`, wait for the matching confirm, record it.
        No answer within `timeout_s` aborts the operation."""
        self.emit(Event("confirm_required", self.op_id, {"key": key, "text": text, **data}))
        while True:
            try:
                cmd = self.answers.get(timeout=timeout_s)
            except queue.Empty:
                raise OperationAborted(f"no answer to {key!r} within {timeout_s} s") from None
            if cmd.kind == "abort":
                raise OperationAborted(f"aborted while waiting for {key!r}")
            if cmd.kind == "confirm" and cmd.args.get("key") == key:
                ok = bool(cmd.args.get("ok"))
                self.emit(Event("confirmed", self.op_id, {"key": key, "ok": ok,
                                                          "origin": cmd.origin}))
                return ok


def _emit_safely(ev: Event, rec: OpRecord, sink: EventSink, error: str | None) -> str | None:
    """Emit to the record and the external sink; a failure in either is noted in `error`
    instead of replacing the operation's own exception."""
    for name, target in (("record writer", rec.sink), ("event sink", sink)):
        try:
            target(ev)
        except Exception as exc:  # noqa: BLE001 - the operation's own error comes first
            note = f"{name} failed on {ev.kind}: {type(exc).__name__}: {exc}"
            error = note if error is None else f"{error}; {note}"
    return error


@contextmanager
def operation(backend: Backend, parent: Path, op: str, sink: EventSink = null_sink,
              args: dict | None = None, prefix: str | None = None,
              user_id: str | None = None, session_id: str | None = None) -> Iterator[OpScope]:
    """One operation's record folder, events, and lights-off on every exit path.

    Enter it before switching any light on, and switch lights on only through
    `scope.lamp_on()` / `scope.aura_line_on(line, percent)`, which pass the guard token.
    Set `scope.result` inside the block; it lands in summary.json. `prefix` names the
    folder (`scan4x` keeps the 2026-09-30 `scan4x_<stamp>/` layout).

    `lights_off()` itself needs no ownership: a pre-emptive lights-off command may call it
    while another operation holds the backend (the runner aborts that operation)."""
    rec = OpRecord(parent, op, start_state=snapshot(backend), prefix=prefix,
                   user_id=user_id, session_id=session_id)
    scope = OpScope(rec.op_id, rec, fan_out(rec.sink, sink), backend=backend)
    scope.emit(Event("started", rec.op_id, {"op": op, "args": args or {}, "user_id": user_id,
                                            "session_id": session_id}))
    status, error = "finished", None
    try:
        yield scope
    except (OperationAborted, KeyboardInterrupt) as exc:
        status, error = "aborted", f"{type(exc).__name__}: {exc}"
        raise
    except BaseException as exc:
        status, error = "error", f"{type(exc).__name__}: {exc}"
        error = _emit_safely(Event("error", rec.op_id, {"error": error}), rec, sink, error)
        raise
    finally:
        lights = lights_off(backend)
        end = snapshot(backend)
        closing = [Event("light_changed", rec.op_id, lights)]
        if status != "error":
            closing.append(Event(status, rec.op_id, {"error": error}))
        for ev in closing:
            error = _emit_safely(ev, rec, sink, error)
        rec.finish(status, lights=lights, end_state=end, result=scope.result, error=error)
