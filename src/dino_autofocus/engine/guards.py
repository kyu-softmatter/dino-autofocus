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
- Coming back from a retract, Z does not jump to its target: `approach` climbs in steps
  from where it is, each step read back (soft-matter-agents task 026: a handed-over Z is
  a goal, not a destination).
- XY targets stay in the box (+1 mm); moves longer than min(field of view, 1 mm) need Z
  retracted to z_safe, confirmed by readback (F5 moves Y by ~15-20 mm for immersion
  loading). An operation may pass its own threshold (scan_4x tiles step 3.3 mm at 4x);
  the record then says so.
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

# unmeasured provisional (checklist Q20 / Q12); every use is marked in the record
Z_SAFE_UM = 0.0  # z_safe: full retract, for every lens
RETRACTED_MAX_Z_UM = Z_SAFE_UM + 1.0  # "Z retracted" for nosepiece turns and long XY moves
LONG_XY_MOVE_MAX_UM = 1000.0  # long-move threshold = min(field of view, this)
ESCAPE_DY_UM: float | None = None  # F5 immersion-loading move; None -> preflight refuses
Z_TOL_UM = 0.25
XY_TOL_UM = 5.0


def long_move_threshold_um(fov_um: float | None) -> float:
    """The provisional long-XY-move threshold: min(field of view, 1 mm)."""
    return LONG_XY_MOVE_MAX_UM if fov_um is None else min(fov_um, LONG_XY_MOVE_MAX_UM)


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
    """'1-Plan Apo LmbdD20 4x' -> '4x'; '6-Plan Apo LmbdD0.13 100x Oil' -> '100x-Oil'."""
    m = re.search(r"(\d+)x\b", nosepiece_label)
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

    def _send(self, z: float, how: str) -> float:
        if self.dry_run:
            read, sent = z, False
            self._z_dry = z
        else:
            if not self.allow_motion:
                raise GuardError("FocusAxis was made with allow_motion=False")
            read, sent = self.b.move_z(z, token=GUARD_TOKEN), True
        rec = {"axis": "z", "how": how, "target_um": z, "read_um": read, "sent": sent,
               "tol_um": self.tol, "basis": {"tol_um": PROVISIONAL}}
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
            rb = self.b.pfs_off(token=GUARD_TOKEN)
            self.emit(Event("property_set", self.op_id, asdict(rb)))
            s = self.b.pfs()
        if s.enabled and not self.dry_run:
            raise GuardError(f"PFS still enabled: {s}")
        return s

    def sweep(self, plan: SweepPlan, grab: Callable[[], Any], score: Callable | None = None,
              settle_s: float = 0.0) -> SweepResult:
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

    def _send_step(self, z: float, step: float) -> float:
        return self.move_to(z, allow_ascent_um=step)

    def approach(self, target_um: float, step_um: float) -> float:
        """Climb from the current Z (e.g. the 0 um retract) to `target_um` in steps of at
        most `step_um`, each read back. Above the target it descends straight there."""
        z, s = plain(target_um, "approach target"), plain(step_um, "approach step")
        if not self.window[0] <= z <= self.window[1]:
            raise GuardError(f"approach target {z:.2f} um is outside the window {self.window}")
        if s <= 0:
            raise GuardError(f"approach step {s} must be > 0")
        here = self.position_um()
        if here >= z:
            return self.move_to(z)
        while here < z - self.tol:
            here = self._send(min(z, here + s), "approach")
        return here


def rotate_nosepiece(backend: Backend, focus: FocusAxis, state: int) -> str:
    """Turn the nosepiece: only with Z retracted, PFS off and out of range. Returns the label."""
    z = focus.position_um()
    basis = {"z_um": z, "retracted_max_um": RETRACTED_MAX_Z_UM,
             "basis": {"retracted_max_um": PROVISIONAL}}
    if z > RETRACTED_MAX_Z_UM:
        raise GuardError(f"Z {z:.2f} um is not retracted (<= {RETRACTED_MAX_Z_UM})")
    s = focus.require_pfs_quiet(disable=True)
    if not s.out_of_range and not focus.dry_run:
        raise GuardError(f"PFS reads {s.in_range!r} after retract; refusing to rotate")
    if focus.dry_run:
        focus.emit(Event("motion", focus.op_id, {"axis": "nosepiece", "target": state,
                                                 "sent": False, **basis}))
        return backend.nosepiece()
    if not focus.allow_motion:
        raise GuardError("FocusAxis was made with allow_motion=False")
    rb = backend.set_nosepiece(int(state), token=GUARD_TOKEN)
    focus.emit(Event("motion", focus.op_id, {"axis": "nosepiece", "target": state,
                                             "sent": True, "read": rb.read, **basis}))
    if not rb.verified:
        raise GuardError(f"Nosepiece reads {rb.read}, not {state}")
    return backend.nosepiece()


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
    """Moves longer than the threshold need Z retracted, read back before the move.

    The threshold is the provisional min(`fov_um`, 1 mm) unless the operation passes its
    own `long_move_um`; each motion record names which one decided."""

    def __init__(self, backend: Backend, box: XYBox, *, allow_motion: bool = False,
                 dry_run: bool = False, sink: EventSink = null_sink, op_id: str = "",
                 fov_um: float | None = None, long_move_um: float | None = None,
                 timeout_s: float | None = None, tol_um: float = XY_TOL_UM):
        self.b, self.box, self.allow_motion, self.dry_run = backend, box, allow_motion, dry_run
        self.emit, self.op_id, self.timeout, self.tol = sink, op_id, timeout_s, tol_um
        if long_move_um is None:
            self.long, long_basis = long_move_threshold_um(fov_um), PROVISIONAL
        else:
            self.long, long_basis = plain(long_move_um, "long move threshold"), "caller"
        self.basis = {"long_move_um": long_basis, "tol_um": PROVISIONAL,
                      "retracted_max_um": PROVISIONAL}
        self.motions: list[dict] = []

    def goto(self, x_um: float, y_um: float) -> tuple[float, float]:
        x, y = plain(x_um, "x target"), plain(y_um, "y target")
        if not self.box.contains(x, y):
            raise GuardError(f"XY ({x:.0f}, {y:.0f}) is outside the box {self.box}")
        p = self.b.positions()
        if p.x_um is None or p.y_um is None or p.z_um is None:
            raise GuardError(f"position unreadable before an XY move: {p.errors}")
        if math.hypot(x - p.x_um, y - p.y_um) > self.long and p.z_um > RETRACTED_MAX_Z_UM:
            raise GuardError(f"XY move over {self.long:.0f} um needs Z retracted; "
                             f"Z reads {p.z_um:.2f} um")
        if self.dry_run:
            read, sent = (x, y), False
        else:
            if not self.allow_motion:
                raise GuardError("XYAxis was made with allow_motion=False")
            read = self.b.move_xy(x, y, token=GUARD_TOKEN, timeout_s=self.timeout)
            sent = True
        rec = {"axis": "xy", "target_um": [x, y], "read_um": list(read), "sent": sent,
               "z_um": p.z_um, "long_move_um": self.long, "tol_um": self.tol,
               "basis": self.basis}
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
        return {"readbacks": [asdict(r) for r in rbs], "verified": all(r.verified for r in rbs),
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


@contextmanager
def operation(backend: Backend, parent: Path, op: str, sink: EventSink = null_sink,
              args: dict | None = None, prefix: str | None = None) -> Iterator[OpScope]:
    """One operation's record folder, events, and lights-off on every exit path.

    Enter it before switching any light on, and switch lights through `scope.lights(...)`.
    Set `scope.result` inside the block; it lands in summary.json. `prefix` names the
    folder (`scan4x` keeps the 2026-09-30 `scan4x_<stamp>/` layout).

    `lights_off()` itself needs no ownership: a pre-emptive lights-off command may call it
    while another operation holds the backend (the runner aborts that operation)."""
    rec = OpRecord(parent, op, start_state=snapshot(backend), prefix=prefix)
    scope = OpScope(rec.op_id, rec, fan_out(rec.sink, sink))
    scope.emit(Event("started", rec.op_id, {"op": op, "args": args or {}}))
    status, error = "finished", None
    try:
        yield scope
    except (OperationAborted, KeyboardInterrupt) as exc:
        status, error = "aborted", f"{type(exc).__name__}: {exc}"
        raise
    except BaseException as exc:
        status, error = "error", f"{type(exc).__name__}: {exc}"
        scope.emit(Event("error", rec.op_id, {"error": error}))
        raise
    finally:
        lights = lights_off(backend)
        scope.emit(Event("light_changed", rec.op_id, lights))
        end = snapshot(backend)
        if status != "error":
            scope.emit(Event(status, rec.op_id, {"error": error}))
        rec.finish(status, lights=lights, end_state=end, result=scope.result, error=error)
