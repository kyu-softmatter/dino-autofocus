"""`/api/hardware`: the hardware screen's reads (PLAN.md 2 F2; contract docs/screens/hardware.md 1).

Read only. Scans, confirmations, status and lights are engine commands and go through
`POST /api/commands`. Everything here comes from the engine's snapshot
(`snapshot()["hardware"] = {profile, profile_path, gates, last_status, error}`, T-011). The
router reshapes it for the screen and never evaluates a gate or a permission itself (F2.2,
PLAN.md 6 rule 2). Login and remote rules are the app's middleware (server/api/__init__.py).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...engine import gates as engine_gates
from . import Engine, Refusal

router = APIRouter()

NOT_REPORTED = "not reported"


class DeviceRow(BaseModel):
    label: str
    role: str | None = None
    type: str | None = None
    library: str | None = None
    present: bool
    read_back: bool | None = None  # a read of its state succeeded and was checked
    write_verified: bool | None = None  # None: no write tested yet (operations-spec 5)
    note: str | None = None


class ObjectiveRow(BaseModel):
    label: str
    state: int | None = None
    magnification: float | None = None
    na: float | None = None
    immersion: str | None = None
    working_distance_um: float | None = None
    pixel_um: float | None = None


class ConfirmedItem(BaseModel):
    value: str
    by: str | None = None
    at: str | None = None


class CameraInfo(BaseModel):
    name: str | None = None
    sensor: tuple[int, int] | None = None
    bit_depth: int | None = None
    ceiling_adu: int | None = None
    pixel_type: str | None = None


class PiezoInfo(BaseModel):
    port: str | None = None
    connected: bool | None = None
    z_um: float | None = None
    error: str | None = None


class HardwareProfile(BaseModel):
    detected_at: str
    backend: str
    host: str | None = None
    config: dict[str, Any] | None = None
    previous_sha256: str | None = None  # None: no previous profile (contract G9)
    changed: list[str] | None = None
    devices: list[DeviceRow] = Field(default_factory=list)
    objectives: list[ObjectiveRow] = Field(default_factory=list)
    camera: CameraInfo | None = None
    piezo: PiezoInfo | None = None
    human_confirmed: dict[str, ConfirmedItem] = Field(default_factory=dict)


class HardwareProfileOut(BaseModel):
    profile: HardwareProfile | None
    path: str | None
    sha256: str | None  # of the profile as the engine reports it (canonical JSON)
    error: str | None = None  # the engine could not read its hardware state


class GateRequires(BaseModel):
    devices: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    confirmed: list[str] = Field(default_factory=list)


class GateRow(BaseModel):
    op: str
    enabled: bool
    reasons: list[str] = Field(default_factory=list)
    requires: GateRequires = Field(default_factory=GateRequires)


class StatusResultOut(BaseModel):
    op_id: str
    t: float
    user_id: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


# -- reshaping the engine's state -------------------------------------------------------


def _hardware(eng: Any) -> dict[str, Any]:
    hw = eng.snapshot().get("hardware")
    return hw if isinstance(hw, dict) else {}


def _devices(raw: Any) -> list[DeviceRow]:
    if isinstance(raw, dict):  # T-002 skeleton: role -> {present, readable, label, note}
        return [
            DeviceRow(
                label=d.get("label") or role,
                role=role,
                present=bool(d.get("present")),
                read_back=d.get("read_back", d.get("readable")),
                write_verified=d.get("write_verified"),
                note=d.get("note") or None,
                type=d.get("type"),
                library=d.get("library"),
            )
            for role, d in raw.items()
            if isinstance(d, dict)
        ]
    if isinstance(raw, list):  # operations-spec 5 shape
        return [
            DeviceRow(**{"present": True, **d}) for d in raw if isinstance(d, dict) and "label" in d
        ]
    return []


def _objectives(raw: Any) -> list[ObjectiveRow]:
    rows = []
    for o in raw if isinstance(raw, list) else []:
        if isinstance(o, str):  # T-002 skeleton: nosepiece labels only
            rows.append(ObjectiveRow(label=o))
        elif isinstance(o, dict) and "label" in o:
            rows.append(ObjectiveRow(**o))
    return rows


def _confirmed(p: dict[str, Any]) -> dict[str, ConfirmedItem]:
    raw = p.get("human_confirmed", p.get("confirmed"))
    out = {}
    for item, v in raw.items() if isinstance(raw, dict) else []:
        if isinstance(v, dict):
            out[item] = ConfirmedItem(
                value=str(v.get("value", NOT_REPORTED)), by=v.get("by"), at=v.get("at")
            )
        else:  # T-002 skeleton keeps only "who/when" (contract G5)
            out[item] = ConfirmedItem(value=NOT_REPORTED, by=str(v))
    return out


def _camera(p: dict[str, Any]) -> CameraInfo | None:
    cam = p.get("camera")
    if isinstance(cam, dict):
        return CameraInfo(**cam)
    if p.get("camera_bit_depth") is not None:
        return CameraInfo(bit_depth=p["camera_bit_depth"])
    return None


def normalize_profile(p: dict[str, Any]) -> HardwareProfile:
    """The engine's profile, in either the T-002 skeleton or the operations-spec 5 shape,
    reshaped for the screen. Fields the engine does not report stay None."""
    return HardwareProfile(
        detected_at=str(p.get("detected_at", NOT_REPORTED)),
        backend=str(p.get("backend", p.get("backend_kind", NOT_REPORTED))),
        host=p.get("host"),
        config=p.get("config") if isinstance(p.get("config"), dict) else None,
        previous_sha256=p.get("previous_sha256"),
        changed=p.get("changed"),
        devices=_devices(p.get("devices")),
        objectives=_objectives(p.get("objectives")),
        camera=_camera(p),
        piezo=PiezoInfo(**p["piezo"]) if isinstance(p.get("piezo"), dict) else None,
        human_confirmed=_confirmed(p),
    )


def _requires(op: str, entry: dict[str, Any]) -> GateRequires:
    if isinstance(entry.get("requires"), dict):
        return GateRequires(**entry["requires"])
    for g in engine_gates.GATES:  # the requirement table the verdict came from
        if g.op == op:
            return GateRequires(
                devices=list(g.devices), objectives=list(g.objectives), confirmed=list(g.confirmed)
            )
    return GateRequires()


def gate_rows(raw: Any) -> list[GateRow]:
    """Off rows first, then by op. The verdict is the engine's, copied as it is."""
    rows = []
    for op, v in raw.items() if isinstance(raw, dict) else []:
        entry = v if isinstance(v, dict) else {}
        rows.append(
            GateRow(
                op=op,
                enabled=bool(entry.get("enabled")),
                reasons=[str(r) for r in entry.get("reasons", [])],
                requires=_requires(op, entry),
            )
        )
    return sorted(rows, key=lambda r: (r.enabled, r.op))


# -- routes -----------------------------------------------------------------------------


@router.get("/profile", response_model=HardwareProfileOut)
def profile(eng: Engine) -> HardwareProfileOut:
    """The last hardware profile, or `profile: null` before the first scan."""
    hw = _hardware(eng)
    raw = hw.get("profile")
    if not isinstance(raw, dict):
        return HardwareProfileOut(
            profile=None, path=hw.get("profile_path"), sha256=None, error=hw.get("error")
        )
    digest = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()
    return HardwareProfileOut(
        profile=normalize_profile(raw),
        path=hw.get("profile_path"),
        sha256=digest,
        error=hw.get("error"),
    )


@router.get("/gates", response_model=list[GateRow])
def gates(eng: Engine) -> list[GateRow]:
    """Every gated operation: on/off, the reasons it is off, what it needs."""
    return gate_rows(_hardware(eng).get("gates"))


@router.get(
    "/gates/{op}",
    response_model=GateRow,
    responses={404: {"description": "no gate for this operation"}},
)
def gate(op: str, eng: Engine) -> GateRow:
    for row in gate_rows(_hardware(eng).get("gates")):
        if row.op == op:
            return row
    raise Refusal(404, "unknown_gate", f"no gate for {op!r}").http()


@router.get("/status", response_model=StatusResultOut | None)
def status(eng: Engine) -> StatusResultOut | None:
    """The last `status` result since the engine started, or null."""
    last = _hardware(eng).get("last_status")
    if not isinstance(last, dict):
        return None
    return StatusResultOut(
        op_id=str(last.get("op_id", "")),
        t=float(last.get("t", 0.0)),
        user_id=last.get("user_id"),
        summary=last.get("summary") or {},
    )
