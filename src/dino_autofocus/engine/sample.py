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
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

SAMPLES_ROOT = Path(r"D:\AutoFocus\samples")
ORIENTATIONS = ("upright", "inverted")


def new_sample_id(root: Path, now: time.struct_time | None = None) -> str:
    """YYYYMMDD_HHMM_n, n counting up from 1 within the same minute."""
    stamp, n = time.strftime("%Y%m%d_%H%M", now or time.localtime()), 1
    while (root / f"{stamp}_{n}").exists():
        n += 1
    return f"{stamp}_{n}"


@dataclass
class SampleGeometry:
    """F3 sample loading. Fields and serialisation only; the checks and the safety limits
    they feed (working distance, focus search range) belong to WP-H."""

    size_mm: tuple[float, float] = (24.0, 50.0)
    chamber: str = "hole"
    hole_diameter_mm: float | None = None  # ~6 mm on 2026-09-30
    coverslip_um: float = 170.0
    thickness_um: float | None = None
    orientation: str = "upright"  # "upright" | "inverted"
    confirmed_by_operator: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> SampleGeometry:
        d = dict(d)
        if "size_mm" in d:
            d["size_mm"] = tuple(d["size_mm"])
        return cls(**d)


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
        d["geometry"] = None if self.geometry is None else asdict(self.geometry)
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
        self.dir.mkdir(parents=True, exist_ok=True)
        d = {**m.extra, "visits": m.visits[-20000:], "boundary": m.boundary}
        self.map_json.write_text(json.dumps(d, indent=0), encoding="utf-8")
        return self.map_json
