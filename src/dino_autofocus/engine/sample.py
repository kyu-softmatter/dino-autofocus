"""A sample's folder, without any drawing: the data half of live_focus.py's Sample/XYMap.

    <root>/<YYYYMMDD_HHMM_n>/
        sample.json        summary: hole, limits, objectives used, calibration, geometry
        map.json           {"visits": [...], "boundary": [[x, y], ...]}  (stage um)
        track_*.jsonl      live-view event logs
        scan4x_*/          4x scans (scan.json, tiles)
        focus100x_*.json   100x focus records
        <op>_<stamp>/      engine operation records (records.OpRecord)

Keys this module does not know are kept and written back, so files from the
2026-09-30 scripts survive a load/save round trip.

Geometry (F3, WP-H). `GEOMETRY_FIELDS` is the one list of geometry fields on the engine
side (docs/screens/sample.md section 2); the server serves it and the screen renders from
it. Values are entered through `sample_geometry_set` and stored as `geometry_set` sample
events (T-019 records); `geometry_view` and `loading_view` project the folded events into
what the screens show. Sample thickness and orientation have no default on purpose: a
guessed safety value must not look entered.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from .records import GRADE_MODEL, Graded

SAMPLES_ROOT = Path(r"D:\AutoFocus\samples")
ORIENTATIONS = ("upright", "flipped")  # docs/screens/sample.md; F3.1 not yet confirmed
CHAMBER_SHAPES = ("hole",)  # more to come (screen gap G5)
MAP_VISITS_KEPT = 20000  # save_map keeps the newest this many visits (live_focus.py's cap)

# sample event kinds written by the engine (records.events.fold keeps them in .other)
SAMPLE_CREATED = "sample_created"
GEOMETRY_SET = "geometry_set"  # payload: values {key: value}
LOADING_STEP = "loading_step"  # payload: step ("person" | "image"), ok, why, result_ref
LOADING_STEPS = ("person", "image")


@dataclass(frozen=True)
class GeometryField:
    key: str
    label: str
    kind: str  # "number" | "pair" | "choice"
    unit: str | None
    choices: tuple[str, ...] | None
    default: Any
    safety: bool  # feeds a safety limit (working distance, focus search range)


# provisional: PLAN section 10, F3.1 is not confirmed by the user
GEOMETRY_FIELDS: tuple[GeometryField, ...] = (
    GeometryField("sample_size_mm", "Sample size", "pair", "mm", None, (24.0, 50.0), False),
    GeometryField("chamber_shape", "Chamber", "choice", None, CHAMBER_SHAPES, "hole", False),
    GeometryField("hole_diameter_mm", "Hole diameter", "number", "mm", None, None, False),
    GeometryField("coverslip_thickness_um", "Coverslip thickness", "number", "um", None,
                  170.0, True),
    GeometryField("sample_thickness_um", "Sample thickness", "number", "um", None, None, True),
    GeometryField("orientation", "Orientation", "choice", None, ORIENTATIONS, None, True),
)
FIELDS_BY_KEY = {f.key: f for f in GEOMETRY_FIELDS}
SAFETY_KEYS = tuple(f.key for f in GEOMETRY_FIELDS if f.safety)


class GeometryError(ValueError):
    """A geometry value the engine refuses; the op reports it as preflight_failed."""


def _number(key: str, v: Any) -> float:
    if isinstance(v, Graded):
        if v.grade == GRADE_MODEL:
            raise GeometryError(f"{key}: a model output cannot be a geometry value")
        v = v.value
    if isinstance(v, bool):
        raise GeometryError(f"{key}: {v!r} is not a number")
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise GeometryError(f"{key}: {v!r} is not a number") from None
    if not math.isfinite(f) or f <= 0:
        raise GeometryError(f"{key}: {f} must be a positive number")
    return f


def validate_geometry(values: dict[str, Any]) -> dict[str, Any]:
    """Checked, normalised copy of `values` (keys of GEOMETRY_FIELDS only)."""
    if not isinstance(values, dict) or not values:
        raise GeometryError("no geometry values given")
    out: dict[str, Any] = {}
    for key, v in values.items():
        f = FIELDS_BY_KEY.get(key)
        if f is None:
            raise GeometryError(f"unknown geometry field {key!r}; known: {list(FIELDS_BY_KEY)}")
        if f.kind == "number":
            out[key] = _number(key, v)
        elif f.kind == "pair":
            if not isinstance(v, (list, tuple)) or len(v) != 2:
                raise GeometryError(f"{key}: {v!r} is not a pair of numbers")
            out[key] = [_number(key, v[0]), _number(key, v[1])]
        else:
            if v not in (f.choices or ()):
                raise GeometryError(f"{key}: {v!r} is not one of {list(f.choices or ())}")
            out[key] = v
    return out


def new_sample_id(root: Path, now: time.struct_time | None = None) -> str:
    """YYYYMMDD_HHMM_n, n counting up from 1 within the same minute."""
    stamp, n = time.strftime("%Y%m%d_%H%M", now or time.localtime()), 1
    while (root / f"{stamp}_{n}").exists():
        n += 1
    return f"{stamp}_{n}"


# A hole fit counts as a closed loop when edge_trace stopped on its full-loop condition,
# or (fits without trace_stop, e.g. 2026-09-30's 352 deg) when the arc covers at least
# this much. Unmeasured provisional.
FULL_LOOP_ARC_DEG = 330.0
FULL_LOOP_STOP = "full loop"  # edge_trace: "back where the edge was first seen: full loop"


def hole_loop(hole: dict[str, Any] | None) -> dict[str, Any]:
    """{closed, why, fitted_at, trace_stop, arc_deg} for a hole fit, next to fitted_at, so
    the re-trace rule and scan_4x can tell a partial arc from a full fit.

    edge_trace's boolean `closed_loop` flag decides when the fit has it; the trace_stop
    text and FULL_LOOP_ARC_DEG are kept only for older fits without the flag."""
    if not hole:
        return {"closed": False, "why": "no hole fit", "fitted_at": None, "trace_stop": None,
                "arc_deg": None}
    stop, arc = hole.get("trace_stop"), hole.get("arc_deg")
    try:
        arc_f = None if arc is None else float(arc)
    except (TypeError, ValueError):
        arc_f = None
    flag = hole.get("closed_loop")  # edge_trace's own flag (T-032)
    if isinstance(flag, bool):
        closed = flag
        why = "edge_trace: closed loop" if flag else f"edge_trace: partial trace ({stop})"
    elif stop is not None and FULL_LOOP_STOP in str(stop):
        closed, why = True, f"trace stopped on a full loop ({stop})"
    elif stop is not None:
        closed, why = False, f"partial trace: {stop}"
    elif arc_f is not None and arc_f >= FULL_LOOP_ARC_DEG:
        closed, why = True, f"arc {arc_f:.0f} deg >= {FULL_LOOP_ARC_DEG:.0f} deg"
    else:
        closed = False
        why = ("no arc recorded" if arc_f is None else
               f"arc {arc_f:.0f} deg < {FULL_LOOP_ARC_DEG:.0f} deg")
    return {"closed": closed, "why": why, "fitted_at": hole.get("fitted_at"),
            "trace_stop": stop, "arc_deg": arc_f}


class SampleGeometry:
    """Geometry values keyed by GEOMETRY_FIELDS, for the sample.json derived view.

    Keys this class does not know are kept in `extra` and written back, so a file from a
    newer writer still loads. Values are not validated here; ops call validate_geometry."""

    def __init__(self, extra: dict[str, Any] | None = None, **values: Any):
        self.values = {k: v for k, v in values.items() if k in FIELDS_BY_KEY}
        self.extra = {**(extra or {}),
                      **{k: v for k, v in values.items() if k not in FIELDS_BY_KEY}}

    def get(self, key: str) -> Any:
        return self.values.get(key, FIELDS_BY_KEY[key].default)

    def to_dict(self) -> dict[str, Any]:
        return {**self.extra, **self.values}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SampleGeometry:
        d = dict(d)
        extra = d.pop("extra", None)
        return cls(extra if isinstance(extra, dict) else None, **d)

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, SampleGeometry) and self.values == other.values
                and self.extra == other.extra)

    def __repr__(self) -> str:
        return f"SampleGeometry({self.to_dict()!r})"


def _source(kind: str, by: str | None = None, t: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "by": by, "t": t}


def geometry_view(entries: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{key: GeometryValue} from folded sample events in fold order (records.events.fold's
    `.other`): the last entered value wins; else the default; else not_set."""
    view = {f.key: ({"value": None, "source": _source("not_set")} if f.default is None else
                    {"value": list(f.default) if f.kind == "pair" else f.default,
                     "source": _source("default")})
            for f in GEOMETRY_FIELDS}
    for e in entries:
        if e.get("kind") != GEOMETRY_SET:
            continue
        for key, v in (e.get("values") or {}).items():
            if key in view:
                view[key] = {"value": v, "source": _source("entered", e.get("user_id"),
                                                           e.get("t"))}
    return view


def loading_view(entries: Iterable[dict[str, Any]], session_id: str | None) -> dict[str, Any]:
    """LoadingState for the open session (docs/screens/sample.md sections 3 and 6).

    Step 1 is done when every safety field has an entered or default value. Steps 2 and 3
    count only in `session_id`, and a change of a safety value after them clears them
    (screen decision G6). `confirmed` needs all three, with the image check ok."""
    entries = list(entries)
    geo: dict[str, Any] = {}
    person: dict[str, Any] | None = None
    image: dict[str, Any] | None = None
    last_geo: dict[str, Any] | None = None
    for e in entries:
        if e.get("kind") == GEOMETRY_SET:
            values = e.get("values") or {}
            changed = [k for k in SAFETY_KEYS if k in values and geo.get(k) != values[k]]
            geo.update(values)
            if changed:
                last_geo = e
                person = image = None  # G6: a safety change after confirmation clears 2-3
        elif e.get("kind") == LOADING_STEP and session_id and e.get("session_id") == session_id:
            if e.get("step") == "person":
                person = e
            elif e.get("step") == "image":
                image = e
    gview = geometry_view(entries)
    geo_done = all(gview[k]["source"]["kind"] in ("entered", "default") for k in SAFETY_KEYS)
    out = {
        "session_id": session_id,
        "geometry": {"done": geo_done, "by": (last_geo or {}).get("user_id"),
                     "t": (last_geo or {}).get("t")},
        "person": {"done": person is not None, "by": (person or {}).get("user_id"),
                   "t": (person or {}).get("t")},
        "image": {"done": image is not None, "ok": bool((image or {}).get("ok")),
                  "by": (image or {}).get("user_id"), "t": (image or {}).get("t"),
                  "why": (image or {}).get("why"), "result_ref": (image or {}).get("result_ref")},
    }
    out["confirmed"] = geo_done and person is not None and image is not None and out["image"]["ok"]
    return out


@dataclass
class SampleInfo:
    sample_id: str
    created: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated: str | None = None
    coordinates: str = "sum = Ti2 XYStage/ZDrive + piezo, um (piezo axis signs unverified)"
    # centre_um, diameter_mm, fit_rms_um, n_points, arc_deg, fitted_at (ISO time: the
    # "re-trace every session" rule compares it with the session start)
    hole: dict | None = None
    boundary_limits_um: dict | None = None
    n_fields_visited: int = 0
    objectives_used: list[str] = field(default_factory=list)
    stage_camera_calibration: dict | None = None
    score_offset_dof: dict = field(default_factory=dict)
    config: str | None = None
    camera: str | None = None
    geometry: SampleGeometry | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self) if f.name != "extra"}
        d["geometry"] = None if self.geometry is None else self.geometry.to_dict()
        return {**self.extra, **d}

    @classmethod
    def from_dict(cls, d: dict) -> SampleInfo:
        known = {f.name for f in fields(cls)} - {"extra"}
        kw = {k: v for k, v in d.items() if k in known}
        if kw.get("geometry") is not None:
            kw["geometry"] = SampleGeometry.from_dict(kw["geometry"])
        return cls(**kw, extra={k: v for k, v in d.items() if k not in known})


@dataclass
class SampleMap:
    visits: list[dict] = field(default_factory=list)
    boundary: list[list[float]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class Sample:
    def __init__(self, sample_id: str, root: Path = SAMPLES_ROOT):
        self.id, self.root = sample_id, Path(root)
        self.dir = self.root / sample_id

    @classmethod
    def create(cls, root: Path = SAMPLES_ROOT, now: time.struct_time | None = None) -> Sample:
        s = cls(new_sample_id(Path(root), now), root)
        s.dir.mkdir(parents=True)
        return s

    @property
    def sample_json(self) -> Path:
        return self.dir / "sample.json"

    @property
    def map_json(self) -> Path:
        return self.dir / "map.json"

    def track_path(self, when: str | None = None) -> Path:
        return self.dir / f"track_{when or time.strftime('%Y%m%d-%H%M%S')}.jsonl"

    def scans_4x(self) -> list[Path]:
        return sorted(p.parent for p in self.dir.glob("scan4x_*/scan.json"))

    def load_info(self) -> SampleInfo:
        if not self.sample_json.exists():
            return SampleInfo(self.id)
        return SampleInfo.from_dict(json.loads(self.sample_json.read_text(encoding="utf-8")))

    def save_info(self, info: SampleInfo) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        info.updated = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.sample_json.write_text(json.dumps(info.to_dict(), indent=1, default=str),
                                    encoding="utf-8")
        return self.sample_json

    def load_map(self) -> SampleMap:
        if not self.map_json.exists():
            return SampleMap()
        d = json.loads(self.map_json.read_text(encoding="utf-8"))
        return SampleMap(d.pop("visits", []), d.pop("boundary", []), d)

    def save_map(self, m: SampleMap) -> Path:
        """Write map.json. Only the newest MAP_VISITS_KEPT visits are kept (the cap
        live_focus.py used); older visits stay in the sample events, which are the truth."""
        self.dir.mkdir(parents=True, exist_ok=True)
        d = {**m.extra, "visits": m.visits[-MAP_VISITS_KEPT:], "boundary": m.boundary}
        self.map_json.write_text(json.dumps(d, indent=0), encoding="utf-8")
        return self.map_json


# -- the reader: one fold (records.events.fold, T-019), one projection ---------------------
BOUNDARY_UNDO = "boundary_undo"  # drops the latest boundary point still standing
# F5 step-out / return, written by objective_change (T-029); the latest one decides
STEPPED_OUT, STEPPED_BACK = "objective_stepped_out", "objective_stepped_back"
# an objective change, written by objective_change (T-029): {from_key, to_key, label}
OBJECTIVE_CHANGED = "objective_changed"


def objectives_used(legacy: list[str], visits: list[dict[str, Any]],
                    other: list[dict[str, Any]]) -> list[str]:
    """Objectives the sample has seen, in order of first use, each once: the legacy
    sample.json list first, then field visits and objective changes in fold order."""
    timeline = [(_order(v), [v.get("objective")]) for v in visits]
    timeline += [(_order(o), [o.get("from_key"), o.get("to_key")]) for o in other
                 if o.get("kind") == OBJECTIVE_CHANGED]
    out: list[str] = []
    for key in list(legacy) + [k for _, keys in sorted(timeline, key=lambda x: x[0])
                               for k in keys]:
        if key and str(key) not in out:
            out.append(str(key))
    return out


def _order(rec: dict[str, Any]) -> tuple:
    """The fold's own order: parsed time, session, seq (seq orders events in one second)."""
    from datetime import datetime

    t = datetime.fromisoformat(rec["t"])
    return (t if t.tzinfo else t.astimezone(), rec.get("session_id", ""), int(rec.get("seq", 0)))


def boundary_view(points: list[dict[str, Any]], other: list[dict[str, Any]]) -> list[dict]:
    """Boundary points still standing: fold's `boundary` (after its last clear) with every
    `boundary_undo` applied in order. An undo removes the latest point before it; an undo
    from before the last clear finds no earlier point and does nothing."""
    timeline = [(_order(p), 0, p) for p in points]
    timeline += [(_order(o), 1, o) for o in other if o.get("kind") == BOUNDARY_UNDO]
    standing: list[dict[str, Any]] = []
    for _, is_undo, rec in sorted(timeline, key=lambda x: x[0]):
        if not is_undo:
            standing.append(rec)
        elif standing:
            standing.pop()
    return standing


@dataclass
class SampleView:
    """Everything the sample, map and sessions screens read about one sample."""

    sample_id: str
    exists: bool
    created: str | None
    hole: dict[str, Any] | None
    hole_loop: dict[str, Any]
    boundary: list[dict[str, Any]]
    visits: list[dict[str, Any]]
    flags: dict[str, dict[str, Any]]
    candidates: dict[str, dict[str, Any]]
    confirmed_particles: dict[str, dict[str, Any]]
    geometry: dict[str, dict[str, Any]]
    loading: dict[str, Any]
    sessions: list[str]
    last_session: dict[str, Any] | None
    awaiting_return: bool
    objectives_used: list[str]
    n_events: int
    updated: str | None

    def active_flags(self) -> dict[str, dict[str, Any]]:
        """Flags not retired. `flags` keeps retired ones too (`retired`, `history`), so the
        map can show them on a toggle (ui-spec 7.4)."""
        return {k: f for k, f in self.flags.items() if not f.get("retired")}

    def open_candidates(self) -> dict[str, dict[str, Any]]:
        """Candidates nobody has rejected yet. `candidates` keeps rejected ones, with their
        `history` (who and when), for the grey cross on the map."""
        return {k: c for k, c in self.candidates.items() if c.get("status") != "rejected"}

    def summary(self) -> dict[str, Any]:
        """SampleSummary of docs/screens/sample.md section 3."""
        return {"sample_id": self.sample_id, "created": self.created,
                "fitted_at": (self.hole or {}).get("fitted_at"),
                "closed_loop": self.hole_loop["closed"],
                "objectives_used": self.objectives_used, "last_session": self.last_session,
                "awaiting_return": self.awaiting_return}


def read_sample(store: Any, sample_id: str, samples_root: Path = SAMPLES_ROOT,
                session_id: str | None = None) -> SampleView:
    """Project the folded sample events (all sessions) into one view. `session_id` is the
    open experiment session, for the loading state. A sample from before the event store
    (2026-09-30) falls back to its legacy sample.json for hole and created."""
    from dino_autofocus.records.session import sample_state, sessions_of_sample

    state = sample_state(store, sample_id)
    legacy = Sample(sample_id, samples_root)
    info = legacy.load_info() if legacy.sample_json.exists() else None
    other = list(state.other)
    created = next((o["t"] for o in other if o.get("kind") == SAMPLE_CREATED), None)
    if created is None and info is not None:
        created = info.created
    hole = state.hole if state.hole is not None else (info.hole if info else None)
    sessions = sessions_of_sample(store, sample_id)
    last = max(sessions, key=lambda i: i.get("started_at", ""), default=None)
    steps = [o for o in other if o.get("kind") in (STEPPED_OUT, STEPPED_BACK)]
    objectives = objectives_used(list(info.objectives_used) if info else [],
                                 list(state.visits), other)
    return SampleView(
        sample_id=sample_id,
        exists=legacy.dir.is_dir() or bool(sessions),
        created=created, hole=hole, hole_loop=hole_loop(hole),
        boundary=boundary_view(state.boundary, other), visits=list(state.visits),
        flags=dict(state.flags),
        candidates={k: p for k, p in state.particles.items() if p.get("status") != "confirmed"},
        confirmed_particles={k: p for k, p in state.particles.items()
                             if p.get("status") == "confirmed"},
        geometry=geometry_view(other), loading=loading_view(other, session_id),
        sessions=[i["session_id"] for i in sessions],
        last_session=None if last is None else {"session_id": last["session_id"],
                                                "opened_at": last.get("started_at")},
        awaiting_return=bool(steps) and steps[-1].get("kind") == STEPPED_OUT,
        objectives_used=objectives, n_events=state.n_events, updated=state.updated)


def write_derived_views(view: SampleView, samples_root: Path = SAMPLES_ROOT,
                        with_map: bool = False) -> None:
    """Regenerate the legacy sample.json (and, with `with_map`, map.json) from the view, so
    the 2026-09-30 tools keep working. Keys these files hold that the view does not know
    are kept. map.json is written only when asked (an op that changed the boundary or the
    visits), so a sample whose map exists only in the legacy file is not wiped."""
    s = Sample(view.sample_id, samples_root)
    info = s.load_info() if s.sample_json.exists() else SampleInfo(view.sample_id)
    if view.created:
        info.created = view.created
    if view.hole is not None:
        info.hole = view.hole
    info.objectives_used = view.objectives_used
    entered = {k: v["value"] for k, v in view.geometry.items()
               if v["source"]["kind"] == "entered"}
    if entered:
        old = info.geometry or SampleGeometry()
        info.geometry = SampleGeometry(old.extra, **{**old.values, **entered})
    if with_map:
        pts = [[float(p["x_um"]), float(p["y_um"])] for p in view.boundary]
        info.boundary_limits_um = None if len(pts) < 2 else {
            "x": [min(p[0] for p in pts), max(p[0] for p in pts)],
            "y": [min(p[1] for p in pts), max(p[1] for p in pts)]}
        info.n_fields_visited = len(view.visits)
        m = s.load_map()
        m.boundary = pts
        m.visits = [{**v, "x": v.get("x_um", v.get("x")), "y": v.get("y_um", v.get("y"))}
                    for v in view.visits]
        s.save_map(m)
    s.save_info(info)
