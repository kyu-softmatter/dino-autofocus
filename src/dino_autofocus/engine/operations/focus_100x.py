"""`focus_100x`: guarded 100x Oil focus search with ZDrive, particle light (operations-spec 7).

Port of `scripts/focus_100x.py`. The guards decide the motion: PFS off, every sweep ascends,
each move is read back, and the sweep ceiling is min(3200, centre + 0.4 x 130 um WD) from
`FocusAxis`. A coarse peak on the top end of the span is **not** climbed: Z goes back down to
the low end and the operator is asked (`climb_past_top`) whether to extend upward. A yes
re-sweeps from the low end in steps, up to one span higher but never past the guards'
ceiling (at most `MAX_EXTENSIONS` times). A peak on the low end is reported
("re-centre lower"); no fine pass follows either end.

Metric: `peak` (brightest 4 x 4-binned spot minus the binned median, for sparse particle
fields) by default, or `vollath`. Warnings (classical, not model): two separate maxima on the
coarse curve -> "check immersion oil"; clipped pixels -> "reduce exposure"; a first frame at
the dark level -> "signal at dark level".

Centre: `centre_um` if given; else the sample's 4x focus plane at the current XY plus the
4x -> 100x parfocal offset (about -60 um on 2026-09-30, unmeasured provisional); else 2930.
A centre above the 4x focus is asked first (`centre_above_4x`). No immersion loading recorded
this session (`oil_loaded` not True) is asked first (`oil_applied`).

Record `<sample>/focus100x_<stamp>/`: engine `log.jsonl` + `summary.json` with the script's
fields (coarse, fine, z_focus_um, why, z_parked_um, position) plus the run arguments, `sat`
per point, warnings and grades.
"""

from __future__ import annotations

import json
import math
import queue
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from ...focus.classical import (
    MAX_SATURATED_FRACTION,
    OIL_WARNING,
    double_peak,
    peak_brightness,
    vollath4,
)
from ..backend import PROVISIONAL, Backend
from ..events import Event, EventSink, null_sink
from ..guards import FocusAxis, GuardError, SweepResult, best_z_um, operation
from ..records import GRADE_COMPUTED, GRADE_MEASURED
from ..runner import Operation, register_operation
from ..sample import SAMPLES_ROOT, Sample
from .scan_4x import Host, _checks, focus_plane_4x, runner_folder

NAME = "focus_100x"
PREFIX = "focus100x"
OBJECTIVE_100X = "6-Plan Apo LmbdD0.13 100x Oil"
OBJECTIVE_KEY = "100x-Oil"
DEFAULT_CENTRE_UM = 2930.0
PARFOCAL_4X_TO_100X_UM = -60.0  # 2026-09-30, one sample; unmeasured provisional
DARK_OFFSET_ADU = 102.0  # Kinetix_red dark offset on 2026-09-30
SIGNAL_MIN_ADU = 50.0  # a first frame whose max is within this of the dark offset: no signal
DEFAULT_EXPOSURE_MS = 20.0  # provisional (2026-09-30, one run)
SETTLE_COARSE_S, SETTLE_FINE_S = 0.1, 0.15
MAX_EXTENSIONS = 3
METRICS = ("peak", "vollath")
REDUCE_EXPOSURE = "reduce exposure"
DARK_SIGNAL = "signal at dark level"


@dataclass(frozen=True)
class FocusArgs:
    centre_um: float | None = None  # None: 4x plane + parfocal offset, else 2930
    half_um: float = 40.0
    step_um: float = 2.0
    fine_half_um: float = 3.0
    fine_step_um: float = 0.2
    # provisional (2026-09-30, one run): 20 ms gave a clean peak without saturation; the
    # script's default was 30
    exposure_ms: float = DEFAULT_EXPOSURE_MS
    aura_line: str = "GREEN"
    aura_percent: float = 1.0
    metric: str = "peak"
    oil_loaded: bool | None = None  # True when this session recorded load_immersion


def parse(args: dict) -> FocusArgs:
    known = set(FocusArgs.__dataclass_fields__)
    extra = sorted(set(args) - known - {"sample_id"})
    if extra:
        raise ValueError(f"unknown focus_100x arguments: {extra}")
    a = FocusArgs(**{k: v for k, v in args.items() if k in known})
    if a.metric not in METRICS:
        raise ValueError(f"metric {a.metric!r} is not one of {METRICS}")
    for name in ("half_um", "step_um", "fine_half_um", "fine_step_um", "exposure_ms"):
        v = float(getattr(a, name))
        if not math.isfinite(v) or v <= 0:
            raise ValueError(f"{name} {v} must be a finite number > 0")
    return a


def default_centre(sample: Sample | None, x_um: float | None, y_um: float | None) -> dict:
    """The suggested sweep centre and where it came from (computed, not model)."""
    if sample is not None and x_um is not None and y_um is not None:
        p = focus_plane_4x(sample, x_um, y_um)
        if p is not None:
            return {"centre_um": p["z_um"] + PARFOCAL_4X_TO_100X_UM, "z_4x_um": p["z_um"],
                    "source": f"4x plane of {p['scan']} + parfocal "
                              f"{PARFOCAL_4X_TO_100X_UM:g} um ({PROVISIONAL})",
                    "grade": GRADE_COMPUTED}
    return {"centre_um": DEFAULT_CENTRE_UM, "z_4x_um": None,
            "source": "script default (no 4x scan)", "grade": None}


def plan(args: dict | FocusArgs, centre: dict) -> dict:
    a = args if isinstance(args, FocusArgs) else parse(args)
    c = float(a.centre_um) if a.centre_um is not None else float(centre["centre_um"])
    coarse = FocusAxis(None, OBJECTIVE_KEY).plan(c, a.half_um, a.step_um)
    return {"op": NAME, "centre_um": c,
            "centre_source": "argument" if a.centre_um is not None else centre["source"],
            "z_4x_um": centre.get("z_4x_um"), "coarse": coarse.describe(),
            "ceiling_um": coarse.ceiling_um,
            "fine": f"+-{a.fine_half_um:g} um @ {a.fine_step_um:g} around an interior coarse peak",
            "metric": a.metric, "exposure_ms": a.exposure_ms,
            "light": f"Aura {a.aura_line.upper()} {a.aura_percent:g} %"}


def preflight(backend: Backend) -> list[str]:
    try:
        label = backend.nosepiece()
    except Exception as exc:  # noqa: BLE001
        label = f"unreadable ({exc})"
    return [] if label == OBJECTIVE_100X else [f"nosepiece reads {label!r}, not {OBJECTIVE_100X!r}"]


def run_focus_100x(backend: Backend, sample: Sample, args: dict, sink: EventSink = null_sink, *,
                   answers: queue.Queue | None = None, confirm_timeout_s: float | None = None,
                   user_id: str | None = None, session_id: str | None = None,
                   sleep: Callable[[float], None] = time.sleep) -> dict:
    """Run the search. Returns {"status", "record", "result"} (or preflight_failed)."""
    a = parse(args)
    problems = preflight(backend)
    pos = backend.positions()
    centre = default_centre(sample, pos.x_um, pos.y_um)
    try:
        pl = plan(a, centre)
    except GuardError as exc:
        problems.append(str(exc))
    if problems:
        sink(Event("preflight_failed", "", {"op": NAME, "reasons": problems}))
        return {"status": "preflight_failed", "reasons": problems, "record": None}
    sink(Event("planned", "", pl))
    sink(Event("preflight_ok", "", {"op": NAME}))

    was_streaming = backend.streaming()
    if was_streaming:
        backend.stop_stream()
    out: dict[str, Any] = {"status": "error", "record": None}
    try:
        with operation(backend, sample.dir, NAME, sink, args={**asdict(a), "sample_id": sample.id},
                       prefix=PREFIX, user_id=user_id, session_id=session_id) as scope:
            if answers is not None:
                scope.answers = answers
            out["record"] = str(scope.record.dir)
            host = Host.of_scope(scope, timeout_s=confirm_timeout_s, sleep=sleep,
                                 session_started=None)
            scope.result = run_body(backend, a, pl, host)
        out["status"] = "finished"
    finally:
        if was_streaming:
            backend.start_stream()
    out["result"] = json.loads((Path(out["record"]) / "summary.json").read_text())["result"]
    return out


def _points(sw: SweepResult) -> list[dict]:
    return [{"z_um": p.z_readback_um, "score": p.score, "vollath": p.diagnostics.get("vollath"),
             "mean": p.diagnostics.get("mean"), "max": p.diagnostics.get("max"),
             "sat": p.diagnostics.get("sat")} for p in sw.points]


def run_body(backend: Backend, a: FocusArgs, pl: dict, host: Host) -> dict:
    """The search itself, inside whatever exit path the host provides. Returns the result."""
    op, emit = host.op_id, host.emit
    centre = pl["centre_um"]
    if a.oil_loaded is not True and not host.ask(
            "oil_applied", "no immersion loading recorded this session; oil applied?", {}):
        raise GuardError("operator declined: no immersion oil")
    z4 = pl.get("z_4x_um")
    if z4 is not None and centre > z4 and not host.ask(
            "centre_above_4x", f"centre {centre:.1f} is above the 4x focus {z4:.1f}; 100x focus "
            "is usually 60-100 um below. Go on?", {"centre_um": centre, "z_4x_um": z4}):
        raise GuardError("operator declined: centre above the 4x focus")

    ceiling = backend.info().ceiling_adu
    backend.set_exposure(a.exposure_ms)
    axis = FocusAxis(backend, OBJECTIVE_KEY, allow_motion=True, sink=emit, op_id=op,
                     sleep=host.sleep)
    cur = {"pass": ""}

    def grab() -> np.ndarray:
        return backend.snap().image

    def score(f: np.ndarray) -> dict:
        v = vollath4(f)
        d = {"sharp": peak_brightness(f) if a.metric == "peak" else v, "vollath": v,
             "mean": float(f.mean()), "max": int(f.max()), "sat": float(np.mean(f >= ceiling))}
        emit(Event("progress", op, {"pass": cur["pass"], "z_um": axis.position_um(), **d}))
        return d

    axis.require_pfs_quiet(disable=True)
    light = [asdict(r) for r in host.light_on(a.aura_line, a.aura_percent)]

    warnings: list[str] = []
    first = grab()
    if float(first.max()) <= DARK_OFFSET_ADU + SIGNAL_MIN_ADU:
        warnings.append(DARK_SIGNAL)
        emit(Event("reading", op, {"warning": DARK_SIGNAL, "max_adu": int(first.max()),
                                   "dark_offset_adu": DARK_OFFSET_ADU}))

    cur["pass"] = "coarse"
    coarse = axis.sweep(axis.plan(centre, a.half_um, a.step_um), grab, score=score,
                        settle_s=SETTLE_COARSE_S)
    spans = [[coarse.plan.z_um[0], coarse.plan.z_um[-1]]]
    while coarse.at_top and len(spans) <= MAX_EXTENSIONS:
        lo, hi = coarse.points[0].z_um, coarse.points[-1].z_um
        axis.move_to(lo)  # back down to the low end (the retract direction), as the script
        # the extension re-sweeps from the low end in steps, so Z never jumps upward
        nxt = axis.plan(hi, hi - lo, a.step_um)
        if nxt.z_um[-1] <= hi + 1e-6:  # the ceiling leaves nothing above
            emit(Event("reading", op, {"peak_at": "top_end", "ceiling_um": nxt.ceiling_um}))
            break
        if not host.ask("climb_past_top", f"peak at the top end of {lo:.1f}-{hi:.1f} um; "
                        f"extend upward to {nxt.z_um[-1]:.1f}?",
                        {"span_um": [lo, hi], "new_top_um": nxt.z_um[-1],
                         "ceiling_um": nxt.ceiling_um}):
            break
        host.check()
        coarse = axis.sweep(nxt, grab, score=score, settle_s=SETTLE_COARSE_S)
        spans.append([nxt.z_um[0], nxt.z_um[-1]])
    fine = None
    if coarse.at_top:
        peak_at = "top_end"
        axis.move_to(coarse.points[0].z_um)
    elif coarse.argmax_index == 0:
        peak_at = "low_end"
        emit(Event("reading", op, {"peak_at": "low_end",
                                   "text": "focus is below the span; re-centre lower"}))
    else:
        peak_at = "interior"
        cur["pass"] = "fine"
        fine = axis.sweep(axis.plan(coarse.peak_z_um, a.fine_half_um, a.fine_step_um), grab,
                          score=score, settle_s=SETTLE_FINE_S)
    zf, why = best_z_um(coarse, fine)
    if double_peak([p.z_readback_um for p in coarse.points], [p.score for p in coarse.points]):
        warnings.append(OIL_WARNING)
    if any((p.diagnostics.get("sat") or 0) > MAX_SATURATED_FRACTION
           for p in coarse.points + (fine.points if fine else [])):
        warnings.append(REDUCE_EXPOSURE)
    parked = axis.park_at(zf) if zf is not None else None
    for w in warnings:
        emit(Event("reading", op, {"warning": w}))
    return {
        "args": asdict(a), "centre_um": centre, "centre_source": pl["centre_source"],
        "ceiling_um": pl["ceiling_um"], "light": light, "coarse_spans_um": spans,
        "coarse": _points(coarse), "fine": _points(fine) if fine else None,
        "z_focus_um": zf, "why": why, "peak_at": peak_at, "z_parked_um": parked,
        "position": asdict(backend.positions()), "warnings": warnings,
        "grades": {"z_focus_um": GRADE_MEASURED if zf is not None else None,
                   "z_parked_um": GRADE_MEASURED, "score": GRADE_COMPUTED,
                   "centre_um": "argument" if a.centre_um is not None else centre_grade(pl)},
    }


def centre_grade(pl: dict) -> str | None:
    return GRADE_COMPUTED if pl.get("z_4x_um") is not None else None


# -- the engine runner (T-011) ------------------------------------------------------------


@register_operation
class Focus100x(Operation):
    """`start("focus_100x", {"sample_id": ..., <FocusArgs>})`. Motion class (control +
    session). `oil_loaded` should come from this session's `load_immersion` record; until
    the runner passes it, the operation asks."""

    name = NAME
    record_prefix = PREFIX
    snaps = True
    samples_root: ClassVar[Path] = SAMPLES_ROOT

    def _sample(self) -> Sample:
        sid = self.args.get("sample_id")
        if not sid:
            raise ValueError("focus_100x needs a sample_id")
        return Sample(str(sid), self.samples_root)

    def _args(self) -> FocusArgs:
        return parse({k: v for k, v in self.args.items() if k != "sample_id"})

    def plan(self) -> dict:
        try:  # no hardware here: the 4x plane is taken at the scan's hole centre
            sample, a = self._sample(), self._args()
            hole = sample.load_info().hole or {}
            xy = hole.get("centre_um") or (None, None)
            return plan(a, default_centre(sample, *xy))
        except (ValueError, GuardError) as exc:
            return {"op": NAME, "error": str(exc)}

    def preflight(self) -> list[dict]:
        try:
            self._args()
            self._sample()
        except ValueError as exc:
            return _checks([str(exc)], NAME)
        return _checks(preflight(self.ctx.backend), NAME)

    def run(self) -> dict:
        b, a, sample = self.ctx.backend, self._args(), self._sample()
        p = b.positions()
        pl = plan(a, default_centre(sample, p.x_um, p.y_um))
        host = Host.of_runner(self.ctx, runner_folder(self.ctx, sample, PREFIX))
        return run_body(b, a, pl, host)
