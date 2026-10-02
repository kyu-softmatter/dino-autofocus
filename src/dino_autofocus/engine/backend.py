"""What the engine needs from a microscope: the Backend protocol and its plain records.

Implementations live in `engine/backends/` (mock, replay, mm-demo, mm-real). Rules every
implementation follows:

- z is always in bench coordinates (ZDrive um, increasing = toward the sample, sample
  window 2800-3200). A device with another origin (the Micro-Manager demo Z) offsets
  inside the backend; guards and records never see its own numbers.
- Every write returns a `Readback`: what was wanted, what was read afterwards, verified.
- Light is set through meaning-level methods, not property writes, so a device with no
  `State` property (the demo LED shutter) is covered. Aura percent is converted to the
  device's per-mille inside the backend (1 % -> GREEN_Intensity 10).
- A position read that fails is a field (`Positions.errors`), never an exception: a
  missing stage must not stop the camera.
- The backend does not judge safety. Motion methods take the guards' `MotionToken` and
  call `require_token` first, so only `engine.guards` can move the stage or focus.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np


@dataclass
class Readback:
    device: str
    prop: str
    wanted: str
    read: str
    verified: bool
    t: float = field(default_factory=time.time)

    @classmethod
    def of(cls, device: str, prop: str, wanted: Any, read: Any) -> Readback:
        return cls(device, prop, str(wanted), str(read), str(read) == str(wanted))


@dataclass
class Positions:
    """Stage readback in um; None where the read failed, with the reason in `errors`."""

    x_um: float | None = None
    y_um: float | None = None
    z_um: float | None = None
    piezo_um: dict[str, float] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    t: float = field(default_factory=time.time)


@dataclass
class PfsState:
    enabled: bool | None
    locked: bool | None
    in_range: str | None  # the device's own text, e.g. "In Range" / "Out of Range"

    @property
    def out_of_range(self) -> bool:
        return self.in_range is not None and "out" in self.in_range.lower()


@dataclass
class ObjectiveInfo:
    state: int  # nosepiece position
    label: str  # e.g. "6-Plan Apo LmbdD0.13 100x Oil"
    magnification: float
    pixel_um: float | None  # camera pixel in the sample plane
    free_wd_um: float | None  # None until measured; guards then plan no sweep for it


@dataclass
class StageLimits:
    """Travel the backend reports or was configured with, um. None = not known yet."""

    x_um: tuple[float, float] | None = None
    y_um: tuple[float, float] | None = None
    z_um: tuple[float, float] | None = None


@dataclass
class BackendInfo:
    kind: str  # "mock" | "replay" | "mm-demo" | "mm-real"
    config: str
    camera: str
    sensor: tuple[int, int]
    roi: tuple[int, int, int, int]
    exposure_ms: float
    pixel_um: float
    objective: str
    intermediate_mag: str | None
    bit_depth: int
    objectives: list[ObjectiveInfo] = field(default_factory=list)
    stage_limits: StageLimits = field(default_factory=StageLimits)

    @property
    def ceiling_adu(self) -> int:
        return 2**self.bit_depth - 1  # 4095 for the Kinetix 100 MHz 12-bit readout

    def to_dict(self) -> dict:
        return {**asdict(self), "ceiling_adu": self.ceiling_adu}


@dataclass
class Frame:
    """A mono uint16 image. Positions are read when the frame is popped (`t_read`), which
    during motion can differ from the exposure by the buffer latency."""

    image: np.ndarray
    t_read: float
    exposure_ms: float
    x_um: float | None = None
    y_um: float | None = None
    z_um: float | None = None

    def meta(self) -> dict:
        return {"t_read": self.t_read, "exposure_ms": self.exposure_ms, "x_um": self.x_um,
                "y_um": self.y_um, "z_um": self.z_um, "shape": list(self.image.shape)}


class MotionToken:
    """Held by `engine.guards`. A motion call without it is refused by the backend."""

    __slots__ = ()


GUARD_TOKEN = MotionToken()  # used outside engine/guards.py (and test fakes) = review failure


class UnguardedMotion(RuntimeError):
    pass


def require_token(token: object) -> None:
    if token is not GUARD_TOKEN:
        raise UnguardedMotion("motion must go through engine.guards (FocusAxis / XYAxis)")


@runtime_checkable
class Backend(Protocol):
    # -- life
    def open(self) -> BackendInfo: ...
    def close(self) -> None: ...
    def info(self) -> BackendInfo: ...

    # -- camera
    def snap(self) -> Frame: ...
    def set_exposure(self, ms: float) -> float: ...  # returns the exposure read back
    def set_roi(self, size: int) -> tuple[int, int, int, int]: ...  # 0 = full sensor

    # -- reads
    def positions(self) -> Positions: ...
    def read_property(self, device: str, prop: str) -> str: ...
    def nosepiece(self) -> str: ...  # label, e.g. "1-Plan Apo LmbdD20 4x"
    def pfs(self) -> PfsState: ...
    def light_state(self) -> dict[str, str]: ...  # e.g. {"DiaLamp": "0", "Aura": "0"}

    # -- writes, each returning what it read back
    def set_property(self, device: str, prop: str, value: Any) -> Readback: ...
    def lamp_on(self) -> list[Readback]: ...  # transmitted lamp (DiaLamp)
    def lamp_off(self) -> list[Readback]: ...
    def aura_line_on(self, line: str, percent: float) -> list[Readback]: ...  # lamp off first
    def aura_off(self) -> list[Readback]: ...
    def all_off(self) -> list[Readback]: ...  # Aura and DiaLamp

    # -- motion: engine.guards only
    def move_z(self, z_um: float, *, token: MotionToken) -> float: ...  # returns z read back
    def move_xy(self, x_um: float, y_um: float, *, token: MotionToken,
                timeout_s: float | None = None) -> tuple[float, float]: ...
    def set_nosepiece(self, state: int, *, token: MotionToken) -> Readback: ...
    def pfs_off(self, *, token: MotionToken) -> Readback: ...
