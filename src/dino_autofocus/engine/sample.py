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
