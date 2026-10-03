"""`/api/hardware`: the hardware screen's reads (PLAN.md 2 F2; contract docs/screens/hardware.md 1).

Read only. Scans, confirmations, status and lights are engine commands and go through
`POST /api/commands`. Everything here comes from the engine's snapshot
(`snapshot()["hardware"]`: T-028 `HardwareState` {profile, profile_path, sha256, previous,
gates, objective_options} plus the runner's last_status and error, T-011). The
router reshapes it for the screen and never evaluates a gate or a permission itself (F2.2,
PLAN.md 6 rule 2). Login and remote rules are the app's middleware (server/api/__init__.py).

`/config` is the one read that is not the snapshot: it parses a Micro-Manager `.cfg` file
(`engine.mm_config_tree`, text only, no core) so the screen can list what the config declares,
with the hub tree, and join it with the scan. Only files from a fixed list are read: the cfg
the last scan loaded, the cfg mm-real would load (`mm_real.config_path()`), and the repo's
`configs/micromanager/*.cfg`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...engine.mm_config_tree import read_cfg
from . import Engine, Refusal

router = APIRouter()

NOT_REPORTED = "not reported"
#: the repo's Micro-Manager configs (src/dino_autofocus/server/api -> repo root)
REPO_MM_CONFIGS = Path(__file__).resolve().parents[4] / "configs" / "micromanager"


class DeviceRow(BaseModel):
    label: str
    role: str | None = None
    type: str | None = None
    library: str | None = None
    description: str | None = None
    present: bool
    read_back: bool | None = None  # a read of its state succeeded and was checked
    write_verified: bool | None = None  # None: no write tested yet (operations-spec 5)
    note: str | None = None


class ObjectiveRow(BaseModel):
    label: str
    state: int | None = None
    magnification: float | None = None
    registry_key: str | None = None
    na: float | None = None
    immersion: str | None = None
    working_distance_um: float | None = None
    wd_source: str | None = None
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
    """T-028 `engine.gates.HardwareProfile`, reshaped for the screen."""

    detected_at: str
    backend_kind: str
    host: str | None = None
    bench: bool | None = None
    objective: str | None = None  # nosepiece label at detection time
    config: dict[str, Any] | None = None
    devices: list[DeviceRow] = Field(default_factory=list)
    objectives: list[ObjectiveRow] = Field(default_factory=list)
    camera: CameraInfo | None = None
    piezo: PiezoInfo | None = None
    human_confirmed: dict[str, ConfirmedItem] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)  # section -> why its read failed


class ProfileChange(BaseModel):
    key: str
    before: Any = None
    after: Any = None


class PreviousProfile(BaseModel):
    """The latest version's diff against the one before (T-028 `ProfileStore.previous`)."""

    sha256: str | None = None
    detected_at: str | None = None
    changed: list[ProfileChange] = Field(default_factory=list)


class HardwareProfileOut(BaseModel):
    profile: HardwareProfile | None
    path: str | None
    sha256: str | None  # of hardware_profile.json as the engine read it
    previous: PreviousProfile | None = None  # None: no previous profile
    error: str | None = None  # the engine could not read its hardware state


class GateRequires(BaseModel):
    devices: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    confirmed: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)  # profile checks, e.g. camera_bit_depth
    arg: dict[str, str] | None = None  # the row is for this argument value (light_set mode)


class GateRow(BaseModel):
    op: str  # the gate key: the op, or `op:value` for a per-argument row (light_set:aura)
    enabled: bool
    reasons: list[str] = Field(default_factory=list)
    requires: GateRequires = Field(default_factory=GateRequires)


class StatusResultOut(BaseModel):
    op_id: str
    t: float
    user_id: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class ConfigChoice(BaseModel):
    path: str
    name: str
    #: "scanned" (the last scan loaded it) | "scanned-copy" (not here, same sha256 as the
    #: scanned one) | "server" (mm-real's choice) | "repo"
    source: str


class ConfigDevice(BaseModel):
    label: str
    library: str
    adapter: str
    parent: str | None = None  # the device it hangs under; None = top level
    link: str | None = None  # "parent" (Parent line) | "port" (serial port) | "inferred"
    port: str | None = None  # Port / Connection setting, also when no device is that port
    roles: list[str] = Field(default_factory=list)  # Core roles (Camera, Focus, ...)
    state_labels: dict[str, str] = Field(default_factory=dict)
    preinit: dict[str, str] = Field(default_factory=dict)
    line: int = 0


class ConfigTreeOut(BaseModel):
    path: str | None  # the file parsed; None when no config file is found
    sha256: str | None = None
    source: str | None = None
    available: list[ConfigChoice] = Field(default_factory=list)
    devices: list[ConfigDevice] = Field(default_factory=list)
    startup: list[str] = Field(default_factory=list)  # System/Startup preset, "dev.prop=value"
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None  # the file could not be read


# -- reshaping the engine's state -------------------------------------------------------


def _hardware(eng: Any) -> dict[str, Any]:
    hw = eng.snapshot().get("hardware")
    return hw if isinstance(hw, dict) else {}


def _devices(p: dict[str, Any]) -> list[DeviceRow]:
    """`device_list` (T-028, one row per loaded device) plus every role from `devices` that no
    loaded device fills, so a missing role shows as a problem row."""
    roles = p.get("devices") if isinstance(p.get("devices"), dict) else {}
    rows = [
        DeviceRow(**{"present": True, **{k: v for k, v in d.items() if k != "properties"}})
        for d in p.get("device_list") or []
        if isinstance(d, dict) and "label" in d
    ]
    covered = {r.role for r in rows}
    for role, d in roles.items():
        if role in covered or not isinstance(d, dict):
            continue
        rows.append(
            DeviceRow(
                label=d.get("label") or role,
                role=role,
                present=bool(d.get("present")),
                read_back=d.get("readable"),
                note=d.get("note") or None,
            )
        )
    return rows


def _objectives(p: dict[str, Any]) -> list[ObjectiveRow]:
    rich = [ObjectiveRow(**o) for o in p.get("objective_rows") or [] if isinstance(o, dict)]
    if rich:
        return rich
    return [ObjectiveRow(label=o) for o in p.get("objectives") or [] if isinstance(o, str)]


def _confirmed(p: dict[str, Any]) -> dict[str, ConfirmedItem]:
    out = {}
    for item, v in (p.get("confirmed") or {}).items():
        if isinstance(v, dict):
            out[item] = ConfirmedItem(
                value=str(v.get("value", NOT_REPORTED)), by=v.get("by"), at=v.get("at")
            )
        else:  # the T-002 skeleton kept only "who/when"
            out[item] = ConfirmedItem(value=NOT_REPORTED, by=str(v))
    return out


def _camera(p: dict[str, Any]) -> CameraInfo | None:
    cam = p.get("camera")
    if isinstance(cam, dict) and cam:
        return CameraInfo(**cam)
    if p.get("camera_bit_depth") is not None:
        return CameraInfo(bit_depth=p["camera_bit_depth"])
    return None


def normalize_profile(p: dict[str, Any]) -> HardwareProfile:
    """`asdict(engine.gates.HardwareProfile)` (T-028), reshaped for the screen. Fields the
    engine does not report stay None or empty."""
    piezo = p.get("piezo")
    return HardwareProfile(
        detected_at=str(p.get("detected_at", NOT_REPORTED)),
        backend_kind=str(p.get("backend_kind", NOT_REPORTED)),
        host=p.get("host") or None,
        bench=p.get("bench"),
        objective=p.get("objective"),
        config=p.get("config") or None,
        devices=_devices(p),
        objectives=_objectives(p),
        camera=_camera(p),
        piezo=PiezoInfo(**piezo) if isinstance(piezo, dict) and piezo else None,
        human_confirmed=_confirmed(p),
        notes=p.get("notes") or {},
        errors=p.get("errors") or {},
    )


def _row(op: str, entry: dict[str, Any]) -> GateRow:
    return GateRow(
        op=op,
        enabled=entry.get("enabled") is True,  # anything but a plain yes is off
        reasons=[str(r) for r in entry.get("reasons", [])],
        requires=GateRequires(**(entry.get("requires") or {})),
    )


def gate_rows(raw: Any) -> list[GateRow]:
    """Off rows first, then by key. The verdict is the engine's (T-028 `gates.gate_rows`, a
    list), copied as it is. A dict keyed by op is the runner's empty default."""
    if isinstance(raw, list):
        rows = [_row(str(e["op"]), e) for e in raw if isinstance(e, dict) and "op" in e]
    elif isinstance(raw, dict):
        rows = [_row(op, e if isinstance(e, dict) else {}) for op, e in raw.items()]
    else:
        rows = []
    return sorted(rows, key=lambda r: (r.enabled, r.op))


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return str(a) == str(b)


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def config_choices(hw: dict[str, Any]) -> list[ConfigChoice]:
    """The cfg files `/config` may read, best first, each once, existing files only.

    When the scanned cfg is not on this machine (a desktop or remote viewer), a listed file
    with the same sha256 as the scan's `config.sha256` takes its place first, as
    `scanned-copy`: it is byte for byte the file the scan loaded."""
    found: list[tuple[Path, str]] = []
    raw = hw.get("profile")
    cfg = raw.get("config") if isinstance(raw, dict) else None
    scanned = cfg.get("path") if isinstance(cfg, dict) else None
    scanned_sha = cfg.get("sha256") if isinstance(cfg, dict) else None
    if isinstance(scanned, str) and scanned.lower().endswith(".cfg"):
        found.append((Path(scanned), "scanned"))
    try:
        from ...engine.backends.mm_real import config_path

        found.append((config_path(), "server"))
    except Exception:  # noqa: BLE001 - a broken settings file must not break the list
        pass
    if REPO_MM_CONFIGS.is_dir():
        found += [(p, "repo") for p in sorted(REPO_MM_CONFIGS.glob("*.cfg"))]
    out: list[ConfigChoice] = []
    kept: list[Path] = []
    for path, source in found:
        if not path.is_file() or any(_same(path, k) for k in kept):
            continue
        kept.append(path)
        out.append(ConfigChoice(path=str(path), name=path.name, source=source))
    if isinstance(scanned_sha, str) and not any(c.source == "scanned" for c in out):
        copy = next((c for c in out if _sha256(Path(c.path)) == scanned_sha), None)
        if copy is not None:
            out.remove(copy)
            out.insert(0, copy.model_copy(update={"source": "scanned-copy"}))
    return out


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
    prev = hw.get("previous")
    return HardwareProfileOut(
        profile=normalize_profile(raw),
        path=hw.get("profile_path"),
        sha256=hw.get("sha256"),
        previous=PreviousProfile(**prev) if isinstance(prev, dict) else None,
        error=hw.get("error"),
    )


@router.get("/gates", response_model=list[GateRow])
def gates(eng: Engine) -> list[GateRow]:
    """Every gate row: on/off, the reasons it is off, what it needs. `light_set` has one row
    per mode (`light_set:brightfield`, `light_set:aura`, `light_set:off`)."""
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


@router.get(
    "/config",
    response_model=ConfigTreeOut,
    responses={404: {"description": "path is not one of the listed config files"}},
)
def config(eng: Engine, path: str | None = None) -> ConfigTreeOut:
    """The devices a Micro-Manager `.cfg` declares, with the hub each hangs under. `path`
    picks one of `available`; without it, the first (the scanned cfg when there is one)."""
    choices = config_choices(_hardware(eng))
    if path is None:
        chosen = choices[0] if choices else None
    else:
        chosen = next((c for c in choices if c.path == path), None)
        if chosen is None:
            raise Refusal(404, "unknown_config", f"{path!r} is not a listed config").http()
    if chosen is None:
        return ConfigTreeOut(path=None, error="no Micro-Manager config found")
    try:
        tree, sha = read_cfg(Path(chosen.path))
    except OSError as e:
        return ConfigTreeOut(path=chosen.path, source=chosen.source, available=choices,
                             error=f"{type(e).__name__}: {e}")
    return ConfigTreeOut(
        path=chosen.path,
        sha256=sha,
        source=chosen.source,
        available=choices,
        devices=[ConfigDevice(**d) for d in tree.to_dict()["devices"]],
        startup=tree.startup,
        warnings=tree.warnings,
    )
