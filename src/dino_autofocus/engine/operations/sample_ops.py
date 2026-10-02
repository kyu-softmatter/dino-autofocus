"""Sample operations (F3, WP-H): choose a sample, enter its geometry, confirm the loading,
and mark the hole boundary. Op names follow docs/screens/sample.md section 4.

    sample_open{sample_id}          choose the sample for the next session; nothing moves
    sample_new{}                    reserve a new id and its legacy folder; no event
    sample_geometry_set{sample_id, values}
    loading_confirm_person{sample_id}
    loading_check_image{sample_id}  brightfield on, one 4x frame, light off; classical check
    boundary_mark{sample_id, x_um, y_um} / boundary_undo{sample_id} / boundary_reset{sample_id}

Storage (manager decision): the truth is the open experiment session's sample events
(T-019 `records/sample_events.jsonl`), written through `session.sample_event()` and read
back through `engine.sample.read_sample`, which projects the one fold. The legacy sample
folder keeps derived sample.json / map.json and each op's record folder (`<op>_<stamp>/`,
as edge_trace does).

One sample per experiment session: sample_open and sample_new run with no session open, or
with the session of that same sample, and refuse otherwise; every other op needs the open
session of its sample. A refusal is a `preflight_failed` event with `why` and writes
nothing. Who may send these ops (OPERATE + an open session, rule 12, D15) is the runner's
permission table, not this module.

Until the T-011 runner lands, `run_sample_op` drives the T-002 record lifecycle directly.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..backend import Backend
from ..events import Event, EventSink, fan_out, null_sink
from ..guards import GuardError, operation, plain, registry_key
from ..records import OpRecord
from ..sample import (
    BOUNDARY_UNDO,
    GEOMETRY_SET,
    LOADING_STEP,
    SAMPLE_CREATED,
    SAMPLES_ROOT,
    GeometryError,
    Sample,
    read_sample,
    validate_geometry,
    write_derived_views,
)

SAMPLE_OPEN, SAMPLE_NEW = "sample_open", "sample_new"
GEOMETRY_SET_OP = "sample_geometry_set"
CONFIRM_PERSON, CHECK_IMAGE = "loading_confirm_person", "loading_check_image"
BOUNDARY_MARK, BOUNDARY_UNDO_OP, BOUNDARY_RESET = "boundary_mark", "boundary_undo", "boundary_reset"
OPS = (SAMPLE_OPEN, SAMPLE_NEW, GEOMETRY_SET_OP, CONFIRM_PERSON, CHECK_IMAGE, BOUNDARY_MARK,
       BOUNDARY_UNDO_OP, BOUNDARY_RESET)

# loading_check_image: the frame must be readable and show structure (the hole edge, the
# chamber) rather than a flat field. Unmeasured provisional (checklist: brightfield 4x).
CHECK_OBJECTIVE = "4x"
MAX_SATURATED_FRACTION = 0.001  # same limit as focus.classical
MIN_RANGE_ADU = 20.0  # p99.9 - p0.1; focus.verdict's MIN_DYNAMIC_RANGE_ADU
MIN_STRUCTURE_RATIO = 3.0  # image spread / pixel noise; ~1 for a flat or dark field

NO_LIGHT = {"switched_off": False, "why": "record-only operation; no light was touched",
            "verified": None}


class Refused(Exception):
    """A preflight refusal: reported as preflight_failed, nothing written."""


@dataclass
class SampleContext:
    """What the sample ops need from their caller (the runner): the records store, the
    legacy root, the open experiment session object (or None) and the user."""

    store: Any  # records.store.RecordsStore
    samples_root: Path = SAMPLES_ROOT
    session: Any = None  # records.session.ExperimentSession, open, or None
    user_id: str | None = None

    @property
    def session_id(self) -> str | None:
        return self.session.session_id if self._open() else None

    def _open(self) -> bool:
        return self.session is not None and bool(self.session.writable)

    def open_sample(self) -> str | None:
        return self.session.info.sample_id if self._open() else None


def ensure_sample_created(session: Any, store: Any) -> bool:
    """Write `sample_created` as the first event when a session opens for a sample with no
    events yet. The runner calls it from set_experiment_session. True if it wrote."""
    from dino_autofocus.records.session import sample_state

    if session is None or not session.writable:
        return False
    if sample_state(store, session.info.sample_id).n_events:
        return False
    session.sample_event(SAMPLE_CREATED)
    return True


# -- preflight helpers ------------------------------------------------------------------
def _sample_id(args: dict) -> str:
    from dino_autofocus.records.layout import check_id

    sid = args.get("sample_id")
    try:
        return check_id(sid)
    except ValueError:
        raise Refused(f"not a valid sample id: {sid!r}") from None


def _only(args: dict, allowed: set[str]) -> None:
    extra = sorted(set(args) - allowed)
    if extra:
        raise Refused(f"unknown arguments: {extra}")


def _no_other_session(ctx: SampleContext, sample_id: str | None) -> None:
    open_for = ctx.open_sample()
    if open_for is not None and open_for != sample_id:
        raise Refused(f"an experiment session is open for sample {open_for}; close it first "
                      "(one sample per session)")


def _need_session(ctx: SampleContext, sample_id: str) -> Any:
    open_for = ctx.open_sample()
    if open_for is None:
        raise Refused("needs an open experiment session for this sample")
    if open_for != sample_id:
        raise Refused(f"the open experiment session is for sample {open_for}, not {sample_id}")
    return ctx.session


# -- the record-only lifecycle -------------------------------------------------------------
def _record_only(ctx: SampleContext, op: str, sample_id: str, args: dict, sink: EventSink,
                 work: Callable[[], dict]) -> dict:
    rec = OpRecord(Sample(sample_id, ctx.samples_root).dir, op, user_id=ctx.user_id,
                   session_id=ctx.session_id)
    emit = fan_out(rec.sink, sink)
    emit(Event("started", rec.op_id, {"op": op, "args": dict(args), "user_id": ctx.user_id,
                                      "session_id": ctx.session_id}))
    status, error, summary = "error", None, None
    try:
        summary = work()
        status = "finished"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        emit(Event("error", rec.op_id, {"error": error}))
        raise
    finally:
        if status == "finished":
            emit(Event("finished", rec.op_id, {"op": op, "error": None, "summary": summary}))
        rec.finish(status, lights=NO_LIGHT, result=summary, error=error)
    return {"status": status, "op_id": rec.op_id, "summary": summary, "record": str(rec.dir)}


def _view(ctx: SampleContext, sample_id: str):
    return read_sample(ctx.store, sample_id, ctx.samples_root, ctx.session_id)


# -- ops -------------------------------------------------------------------------------------
def _sample_new(ctx: SampleContext, args: dict, sink: EventSink, backend: Any) -> dict:
    _only(args, set())
    _no_other_session(ctx, None)
    s = Sample.create(ctx.samples_root)  # reserves the id and the folder; no event
    return _record_only(ctx, SAMPLE_NEW, s.id, args, sink,
                        lambda: {"sample_id": s.id, "dir": str(s.dir)})


def _sample_open(ctx: SampleContext, args: dict, sink: EventSink, backend: Any) -> dict:
    _only(args, {"sample_id"})
    sid = _sample_id(args)
    _no_other_session(ctx, sid)
    if not _view(ctx, sid).exists:
        raise Refused(f"no sample {sid} (no legacy folder and no session)")
    return _record_only(ctx, SAMPLE_OPEN, sid, args, sink, lambda: _view(ctx, sid).summary())


def _geometry_set(ctx: SampleContext, args: dict, sink: EventSink, backend: Any) -> dict:
    _only(args, {"sample_id", "values"})
    sid = _sample_id(args)
    session = _need_session(ctx, sid)
    try:
        values = validate_geometry(args.get("values"))
    except GeometryError as exc:
        raise Refused(str(exc)) from None

    def work() -> dict:
        session.sample_event(GEOMETRY_SET, values=values)
        view = _view(ctx, sid)
        write_derived_views(view, ctx.samples_root)
        return {"sample_id": sid, "geometry": view.geometry, "loading": view.loading}

    return _record_only(ctx, GEOMETRY_SET_OP, sid, args, sink, work)


def _confirm_person(ctx: SampleContext, args: dict, sink: EventSink, backend: Any) -> dict:
    _only(args, {"sample_id"})
    sid = _sample_id(args)
    session = _need_session(ctx, sid)

    def work() -> dict:
        session.manual_step(CONFIRM_PERSON, sample_id=sid)
        session.sample_event(LOADING_STEP, step="person", ok=True)
        return {"sample_id": sid, "loading": _view(ctx, sid).loading}

    return _record_only(ctx, CONFIRM_PERSON, sid, args, sink, work)


def structure_check(img: np.ndarray, ceiling: int) -> dict:
    """Classical loading check on one brightfield frame: readable (not clipped, some range)
    and showing structure, measured as the frame's spread over its pixel noise (the noise
    from neighbouring-pixel differences). grade "computed", never a model number."""
    a = np.asarray(img, dtype=np.float64)
    sat = float(np.mean(a >= ceiling))
    lo, hi = np.percentile(a, (0.1, 99.9))
    d = np.diff(a, axis=1)
    noise = float(1.4826 * np.median(np.abs(d - np.median(d))) / math.sqrt(2.0))
    ratio = float(a.std() / max(noise, 1e-6))
    why = None
    if sat > MAX_SATURATED_FRACTION:
        why = f"{100 * sat:.2f} % of pixels clipped; lower the exposure"
    elif hi - lo < MIN_RANGE_ADU:
        why = f"brightness range {hi - lo:.0f} ADU < {MIN_RANGE_ADU:.0f}: no light or no sample"
    elif ratio < MIN_STRUCTURE_RATIO:
        why = (f"structure ratio {ratio:.2f} < {MIN_STRUCTURE_RATIO:.1f}: a flat field, "
               "nothing in view")
    return {"ok": why is None, "metric": "structure_ratio", "value": round(ratio, 3),
            "grade": "computed", "why": why, "saturated_fraction": sat,
            "range_adu": float(hi - lo),
            "thresholds": {"min_structure_ratio": MIN_STRUCTURE_RATIO,
                           "min_range_adu": MIN_RANGE_ADU,
                           "basis": "unmeasured provisional"}}


def _check_image(ctx: SampleContext, args: dict, sink: EventSink, backend: Backend | None
                 ) -> dict:
    _only(args, {"sample_id"})
    sid = _sample_id(args)
    session = _need_session(ctx, sid)
    if backend is None:
        raise Refused("loading_check_image needs the microscope backend")
    try:
        key = registry_key(backend.nosepiece())
    except Exception as exc:  # noqa: BLE001 - unreadable objective: refuse, do not turn
        raise Refused(f"objective unreadable ({exc}); {CHECK_OBJECTIVE} must be in place"
                      ) from None
    if key != CHECK_OBJECTIVE:
        raise Refused(f"the {CHECK_OBJECTIVE} objective must be in place (reads {key}); "
                      "the image check does not change the objective")
    sample = Sample(sid, ctx.samples_root)
    with operation(backend, sample.dir, CHECK_IMAGE, sink, args=dict(args),
                   user_id=ctx.user_id, session_id=ctx.session_id) as scope:
        scope.lamp_on()
        frame = backend.snap()
        result = structure_check(frame.image, backend.info().ceiling_adu)
        np.save(scope.record.dir / "frame.npy", np.asarray(frame.image))
        result["frame_ref"] = f"{scope.op_id}/frame.npy"
        result["frame"] = frame.meta()
        session.sample_event(LOADING_STEP, step="image", ok=result["ok"], why=result["why"],
                             result_ref=result["frame_ref"], metric=result["metric"],
                             value=result["value"], grade="computed")
        result["loading"] = _view(ctx, sid).loading
        scope.result = result
    return {"status": "finished", "op_id": scope.op_id, "summary": result,
            "record": str(scope.record.dir)}


def _boundary(op: str) -> Callable[..., dict]:
    def run(ctx: SampleContext, args: dict, sink: EventSink, backend: Any) -> dict:
        _only(args, {"sample_id", "x_um", "y_um"} if op == BOUNDARY_MARK else {"sample_id"})
        sid = _sample_id(args)
        session = _need_session(ctx, sid)
        if op == BOUNDARY_MARK:
            try:
                x, y = plain(args.get("x_um"), "x_um"), plain(args.get("y_um"), "y_um")
            except (GuardError, TypeError, ValueError) as exc:
                raise Refused(f"boundary point: {exc}") from None
        elif op == BOUNDARY_UNDO_OP and not _view(ctx, sid).boundary:
            raise Refused("no boundary point to undo")

        def work() -> dict:
            if op == BOUNDARY_MARK:
                session.sample_event("boundary_point", x_um=x, y_um=y)
            elif op == BOUNDARY_UNDO_OP:
                session.sample_event(BOUNDARY_UNDO)
            else:
                session.sample_event("boundary_clear")
            view = _view(ctx, sid)
            write_derived_views(view, ctx.samples_root, with_map=True)
            return {"sample_id": sid, "n_points": len(view.boundary),
                    "boundary": [[p["x_um"], p["y_um"]] for p in view.boundary]}

        return _record_only(ctx, op, sid, args, sink, work)

    return run


_RUN = {SAMPLE_NEW: _sample_new, SAMPLE_OPEN: _sample_open, GEOMETRY_SET_OP: _geometry_set,
        CONFIRM_PERSON: _confirm_person, CHECK_IMAGE: _check_image,
        BOUNDARY_MARK: _boundary(BOUNDARY_MARK), BOUNDARY_UNDO_OP: _boundary(BOUNDARY_UNDO_OP),
        BOUNDARY_RESET: _boundary(BOUNDARY_RESET)}


def run_sample_op(op: str, ctx: SampleContext, args: dict | None = None,
                  sink: EventSink = null_sink, backend: Backend | None = None) -> dict:
    """Run one sample op. Returns {status, op_id, summary, record} ("finished"), or
    {status: "refused", why} after a preflight_failed event (nothing written)."""
    args = dict(args or {})
    if op not in _RUN:
        raise ValueError(f"unknown sample op {op!r}; known: {list(OPS)}")
    try:
        return _RUN[op](ctx, args, sink, backend)
    except Refused as exc:
        why = str(exc)
        sink(Event("preflight_failed", "", {"op": op, "why": why, "args": args}))
        return {"status": "refused", "why": why}
