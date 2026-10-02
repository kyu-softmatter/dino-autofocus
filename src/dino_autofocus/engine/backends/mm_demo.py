"""mm-demo backend: the engine's Backend protocol on Micro-Manager's demo devices (T-023).

Built on `mm_demo_core.DemoDevices`, which owns the core and the bench <-> demo Z offset.
Everything here is in bench coordinates (PLAN.md 5절). Demo-only rules:

* **Below-range zone.** The demo Z reaches bench 2700-3300 only (offset 3000), but the bench
  retracts to 0 and `FocusAxis.approach` climbs back in steps. A bench z in [0, 2700) parks
  the demo stage at bench 2700 and reads back the commanded z: that readback is
  **simulated**, so the guard's retract and step checks pass without proving anything about
  a real ZDrive. Each such move is logged in `substitutions` as a `demo_retract`
  {commanded_um, physical_bench_um, physical_demo_um}. z < 0 or > 3300 is refused.
* **PFS.** The demo has none. `pfs()` is simulated: never enabled, "Out of Range" while z is
  in the below-range zone, "In Range" otherwise, so `rotate_nosepiece` can be exercised.
* **Aura lines.** Only GREEN is bench-confirmed; the others map to the nearest demo LED
  wavelength and are "unmeasured provisional".
* **Control token** (PLAN.md D15). Switching light on (`lamp_on`, `aura_line_on`) takes the
  guards' token like motion does; switching off (`lamp_off`, `aura_off`, `all_off`) takes
  none. `set_property` is an allow-list: motion devices (demo and bench names) are always
  refused and light properties need the token, both with `UnguardedMotion`; a few camera
  properties need no token; anything else raises `PropertyNotAllowed`. Light is written
  under the demo names; the bench names (Aura, DiaLamp) are not devices here.

Until `Readback` and `BackendInfo` get a `notes` field (T-015), these markings are read
through `notes()`, `substitutions`, `read_property("mm-demo", "notes")` and
`read_property("mm-demo", "demo_retract")`, never through device or property names.

pymmcore-plus is imported only when the backend opens.
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import asdict
from typing import Any

from ..backend import (
    BackendInfo,
    Frame,
    ObjectiveInfo,
    PfsState,
    Positions,
    Readback,
    StageLimits,
    UnguardedMotion,
    require_token,
)
from .mm_demo_core import (
    AURA_LINES,
    DEMO_LAMP,
    DEMO_LED,
    DEMO_NOSEPIECE,
    DEMO_XY,
    DEMO_Z,
    DemoDevices,
    DemoReadback,
    DemoZRangeError,
    ObjectiveRead,
    ZMap,
)

__all__ = ["CAMERA_PROPERTIES", "LIGHT_PROPERTIES", "MOTION_DEVICES", "PSEUDO_DEVICE",
           "MmDemoBackend", "PropertyNotAllowed"]

PROVISIONAL = "unmeasured provisional"
PSEUDO_DEVICE = "mm-demo"  # read_property(PSEUDO_DEVICE, ...) answers the interim notes
BENCH_RETRACT_UM = 0.0  # lowest bench z accepted: the full retract
MEASURED_AURA_LINES = ("GREEN",)  # 2026-09-30 bench run
#: set_property refuses these: the demo's motion devices, the bench names, and Core (whose
#: Focus / XYStage properties would re-route motion)
MOTION_DEVICES = frozenset({DEMO_Z, DEMO_XY, DEMO_NOSEPIECE, "Autofocus", "Core",
                            "ZDrive", "XYStage", "Nosepiece", "PFS", "PFSOffset"})
#: set_property allow-list (T-015). Light, token required (D15): the demo equivalents of
#: DiaLamp State and the Aura line selector. LED Shutter has no writable property: it is the
#: Aura master, switched by the light methods. The demo LED has no intensity property.
LIGHT_PROPERTIES = frozenset({(DEMO_LAMP, "State"), (DEMO_LED, "Label"), (DEMO_LED, "State")})
#: Camera, no token: exposure, binning, pixel type, and the sensor size open() sets
CAMERA_PROPERTIES = frozenset({("Camera", p) for p in (
    "Exposure", "Binning", "PixelType", "OnCameraCCDXSize", "OnCameraCCDYSize")})


class PropertyNotAllowed(ValueError):
    """set_property on a device/property outside the allow-list."""
#: bench lens facts by nosepiece State, from docs/runs/2026-09-30_substrate-scan.yaml
BENCH_PIXEL_UM = {0: 1.625, 5: 0.065}
BENCH_FREE_WD_UM = {0: 20000.0, 5: 130.0}


def _readbacks(recs: list[DemoReadback]) -> list[Readback]:
    return [Readback(**asdict(r)) for r in recs]


def _magnification(label: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[xX]\b", label)
    return float(m.group(1)) if m else 0.0  # 0 = not in the label (demo "Objective-2")


class MmDemoBackend:
    kind = "mm-demo"

    def __init__(self, *, exposure_ms: float = 10.0, roi: int = 0,
                 z_offset_um: float | None = None):
        self._exposure_ms, self._roi = exposure_ms, roi
        self.zmap = ZMap() if z_offset_um is None else ZMap(offset_um=z_offset_um)
        self.dev: DemoDevices | None = None
        self.substitutions: list[dict[str, Any]] = []
        self._below_z: float | None = None  # commanded z while in the below-range zone

    # -- life

    def open(self) -> BackendInfo:
        if self.dev is None:
            self.dev = DemoDevices.open(exposure_ms=self._exposure_ms, roi=self._roi,
                                        zmap=self.zmap)
        return self.info()

    def close(self) -> None:
        if self.dev is not None:
            dev, self.dev = self.dev, None
            dev.close()

    def __enter__(self) -> MmDemoBackend:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _d(self) -> DemoDevices:
        if self.dev is None:
            raise RuntimeError("mm-demo backend is not open")
        return self.dev

    def info(self) -> BackendInfo:
        d = self._d()
        core = d.core
        now = d.objective()
        hi = self.zmap.bench_range_um[1]
        return BackendInfo(
            kind=self.kind, config=str(d.config), camera=core.getCameraDevice(),
            sensor=(int(core.getProperty(core.getCameraDevice(), "OnCameraCCDXSize")),
                    int(core.getProperty(core.getCameraDevice(), "OnCameraCCDYSize"))),
            roi=tuple(core.getROI()), exposure_ms=float(core.getExposure()),
            pixel_um=BENCH_PIXEL_UM.get(now.state, float(core.getPixelSizeUm())),
            objective=self._label(now), intermediate_mag=None,
            bit_depth=int(core.getProperty(core.getCameraDevice(), "BitDepth")),
            objectives=[self._objective_info(o) for o in d.objectives()],
            stage_limits=StageLimits(None, None, (BENCH_RETRACT_UM, hi)),
        )

    def notes(self) -> dict[str, str]:
        """Markings that belong in `BackendInfo.notes` once T-015 adds it."""
        lo, hi = self.zmap.bench_range_um
        others = [k for k in AURA_LINES if k not in MEASURED_AURA_LINES]
        return {
            "z_offset_um": f"{self.zmap.offset_um:g} (demo z = bench z - offset)",
            "z_below_range": (f"bench z {BENCH_RETRACT_UM:g}-{lo:g} um parks the demo stage at "
                              f"{lo:g}; readback in that zone is simulated (demo_retract)"),
            "z_reachable_um": f"{lo:g}-{hi:g}",
            "pfs": "simulated: the demo has no PFS",
            "aura_lines": (f"{', '.join(MEASURED_AURA_LINES)} bench-confirmed; "
                           f"{', '.join(others)} {PROVISIONAL}"),
            "objectives": (f"Ti2 labels known for states {sorted(BENCH_PIXEL_UM)}; "
                           "other positions show the demo label"),
        }

    # -- camera

    def snap(self) -> Frame:
        d = self._d()
        img = d.snap()
        p = self.positions()
        return Frame(img, time.time(), float(d.core.getExposure()), p.x_um, p.y_um, p.z_um)

    def set_exposure(self, ms: float) -> float:
        return self._d().set_exposure(ms)

    def set_roi(self, size: int) -> tuple[int, int, int, int]:
        return self._d().set_roi(size)

    # -- reads

    def positions(self) -> Positions:
        d, p = self._d(), Positions()
        try:
            p.x_um, p.y_um = d.xy_um()
        except Exception as e:  # a failed read is a field, not an exception
            p.errors["xy"] = str(e)
        try:
            p.z_um = self._z_read()
        except Exception as e:
            p.errors["z"] = str(e)
        return p

    def read_property(self, device: str, prop: str) -> str:
        if device == PSEUDO_DEVICE:
            if prop == "notes":
                return json.dumps(self.notes())
            if prop == "demo_retract":  # the substitution in force now, "" if none
                last = next((s for s in reversed(self.substitutions)
                             if s["kind"] == "demo_retract"), None)
                return json.dumps(last) if self._below_z is not None and last else ""
            raise KeyError(f"{PSEUDO_DEVICE} has no property {prop!r}")
        return str(self._d().core.getProperty(device, prop))

    def nosepiece(self) -> str:
        return self._label(self._d().objective())

    def pfs(self) -> PfsState:
        return PfsState(False, False, "Out of Range" if self._below_z is not None else "In Range")

    def light_state(self) -> dict[str, str]:
        return self._d().light_state()

    # -- writes

    def set_property(self, device: str, prop: str, value: Any, *,
                     token: object = None) -> Readback:
        if device in MOTION_DEVICES:
            raise UnguardedMotion(f"{device!r} moves hardware; use the guarded methods")
        if (device, prop) in LIGHT_PROPERTIES:
            require_token(token)
        elif (device, prop) not in CAMERA_PROPERTIES:
            allowed = ", ".join(f"{d}.{p}" for d, p in sorted(LIGHT_PROPERTIES | CAMERA_PROPERTIES))
            raise PropertyNotAllowed(f"set_property {device}.{prop} is not allowed on mm-demo; "
                                     f"allowed: {allowed} (light ones need the token)")
        return Readback(**asdict(self._d().set_and_read(device, prop, value)))

    def lamp_on(self, *, token: object = None) -> list[Readback]:
        require_token(token)
        return _readbacks(self._d().lamp_on())

    def lamp_off(self) -> list[Readback]:
        return _readbacks(self._d().lamp_off())

    def aura_line_on(self, line: str, percent: float, *,
                     token: object = None) -> list[Readback]:
        require_token(token)
        recs = _readbacks(self._d().aura_line_on(line, percent))
        if line.upper() not in MEASURED_AURA_LINES:
            self.substitutions.append({"kind": "aura_line", "line": line.upper(),
                                       "demo_label": AURA_LINES[line.upper()],
                                       "status": PROVISIONAL, "t": time.time()})
        return recs

    def aura_off(self) -> list[Readback]:
        return _readbacks(self._d().aura_off())

    def all_off(self) -> list[Readback]:
        return _readbacks(self._d().all_off())

    # -- motion: engine.guards only

    def move_z(self, z_um: float, *, token: object) -> float:
        require_token(token)
        d = self._d()
        z = float(z_um)
        lo, hi = self.zmap.bench_range_um
        if not (math.isfinite(z) and BENCH_RETRACT_UM <= z <= hi):
            raise DemoZRangeError(f"bench z {z_um} um is outside {BENCH_RETRACT_UM:g}-{hi:g} um "
                                  "on the demo")
        if z >= lo:
            self._below_z = None
            return d.move_z(z)
        physical = d.move_z(lo)
        self.substitutions.append({"kind": "demo_retract", "commanded_um": z,
                                   "physical_bench_um": physical,
                                   "physical_demo_um": d.core.getPosition(DEMO_Z),
                                   "t": time.time()})
        if abs(physical - lo) > 0.01:  # the park itself failed: report what was read
            self._below_z = None
            return physical
        self._below_z = z
        return z

    def move_xy(self, x_um: float, y_um: float, *, token: object,
                timeout_s: float | None = None) -> tuple[float, float]:
        require_token(token)
        return self._d().move_xy(x_um, y_um, timeout_s=timeout_s)

    def set_nosepiece(self, state: int, *, token: object) -> Readback:
        require_token(token)
        return Readback(**asdict(self._d().set_objective(state)))

    def pfs_off(self, *, token: object) -> Readback:
        require_token(token)
        return Readback.of("PFS", "FocusMaintenance", "Off", "Off")  # simulated, never on

    # -- helpers

    def _z_read(self) -> float:
        z = self._d().z_um()
        return self._below_z if self._below_z is not None else z

    @staticmethod
    def _label(o: ObjectiveRead) -> str:
        return o.bench_label or o.demo_label

    def _objective_info(self, o: ObjectiveRead) -> ObjectiveInfo:
        return ObjectiveInfo(o.state, self._label(o), _magnification(self._label(o)),
                             BENCH_PIXEL_UM.get(o.state), BENCH_FREE_WD_UM.get(o.state))
