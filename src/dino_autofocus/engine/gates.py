"""F2 gates: which operations are enabled, decided in code from the hardware profile.

A `HardwareProfile` (written by the hardware-scan operation, WP-G) says what was detected
and what a person confirmed. Each `Gate` names the device roles, objectives and operator
confirmations an operation needs. `evaluate` returns, per operation, whether it is enabled
and every reason it is not, so the UI can show a disabled feature with its reasons.
Neither a model nor a UI dialog opens a gate.

Device roles are backend-neutral: camera, xy_stage, z_drive, dia_lamp, aura, nosepiece,
pfs, piezo. This file is the skeleton; the real gate list is WP-G's.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .guards import GuardError, registry_key

ROLES = ("camera", "xy_stage", "z_drive", "dia_lamp", "aura", "nosepiece", "pfs", "piezo")


@dataclass
class DeviceStatus:
    present: bool
    readable: bool  # a read of its state succeeded and was checked
    label: str = ""  # the backend's own device name, e.g. "Kinetix_red", "ZDrive"
    note: str = ""


@dataclass
class HardwareProfile:
    backend_kind: str
    detected_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    devices: dict[str, DeviceStatus] = field(default_factory=dict)  # role -> status
    objectives: list[str] = field(default_factory=list)  # nosepiece labels
    camera_bit_depth: int | None = None
    confirmed: dict[str, str] = field(default_factory=dict)  # item -> who/when (operator)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1)

    @classmethod
    def from_json(cls, s: str) -> HardwareProfile:
        d = json.loads(s)
        d["devices"] = {k: DeviceStatus(**v) for k, v in d.get("devices", {}).items()}
        return cls(**d)

    def save(self, path: Path) -> Path:
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    def objective_keys(self) -> set[str]:
        keys = set()
        for label in self.objectives:
            try:
                keys.add(registry_key(label))
            except GuardError:
                continue
        return keys


@dataclass(frozen=True)
class Gate:
    op: str
    devices: tuple[str, ...] = ()
    objectives: tuple[str, ...] = ()  # registry keys, e.g. "4x", "100x-Oil"
    confirmed: tuple[str, ...] = ()  # operator confirmations the profile must hold


@dataclass
class GateResult:
    op: str
    enabled: bool
    reasons: list[str]


# Examples to fix the shape; WP-G replaces them with the measured list.
GATES = (
    Gate("status", devices=("camera",)),
    Gate("lights_off", devices=("dia_lamp", "aura")),
    Gate("sample_map", devices=("camera", "xy_stage", "z_drive", "dia_lamp"),
         objectives=("4x",)),
)


def evaluate(profile: HardwareProfile, gates: tuple[Gate, ...] = GATES) -> dict[str, GateResult]:
    keys = profile.objective_keys()
    out = {}
    for g in gates:
        why = []
        for role in g.devices:
            d = profile.devices.get(role)
            if d is None or not d.present:
                why.append(f"{role} not detected")
            elif not d.readable:
                why.append(f"{role} detected but its state did not read back")
        why += [f"objective {k} not on the nosepiece" for k in g.objectives if k not in keys]
        why += [f"not confirmed by the operator: {c}" for c in g.confirmed
                if c not in profile.confirmed]
        out[g.op] = GateResult(g.op, not why, why)
    return out
