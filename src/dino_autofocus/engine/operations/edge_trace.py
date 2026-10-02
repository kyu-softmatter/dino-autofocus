"""`edge_trace`: follow the chamber edge with XY moves only and fit the hole (operations-spec 8).

Port of `scripts/edge_track.py` (`EdgeTracker` and its image functions) and the `t` tracking
of `scripts/live_focus.py`. The script stays as it is; this module is the engine version.

What it does, in order:

1. preflight: XY readable, a camera pixel size, the objective (4x recommended; another lens
   is a warning, calibration is stored per lens), the arguments in range.
2. a sample with a hole fit or boundary asks `replace_hole_fit`; yes backs up `map.json` and
   `sample.json` as `*_before_rescan_<stamp>.json` and clears the boundary only (visits stay).
3. `start_trace` asks the operator: XY moves only, within `max_radius_um` of here.
4. inside the record scope: brightfield on (unless `light="keep"`), then calibration: +x and
   back, +y and back by `cal_um`, image shift by phase correlation -> M (px per um), checked
   against the camera pixel (0.7-1.4) and the reference calibration's handedness and angle.
   `calibrate=False` uses the reference instead (the sample's own for this lens, else the
   2026-09-30 4x bench M).
5. tracking: find the edge nearest the field centre, map it to the stage with
   `stage + inv(M) @ (centre - p)`, step along it (at most 200 um, no faster than
   `speed_um_s`), steer by the fitted chamber circle once it is trustworthy. Every
   `point_every_um` of travel an edge point goes to the sample boundary.
6. stops on: more than `max_radius_um` from the start, path or time limit, the edge lost,
   a full loop, abort, an error. Z never moves.
7. the hole is fitted to all boundary points (`robust_circle`) and written to sample.json with
   `fitted_at`, `trace_stop`, `closed_loop` (True only when the trace came round to where it
   first saw the edge), `boundary_limits_um` and `stage_camera_calibration`. A diameter more than
   20 % off `hole_diameter_mm` is a warning in the result.
8. every exit path switches the lights off (DiaLamp too, unlike live_focus: 9/30 problem 4).

Image vectors are (x, y) = (column, row) in full-resolution pixels; stage vectors are (x, y)
in um as the XY stage reports them (Ti2; piezo offsets are not added yet).

Seams for the pieces that are not on main yet, each one argument of `run_edge_trace`:
- `grab`: the acquisition stream (T-011 / T-015 `start_stream` / `next_frame`). The default
  uses `next_frame` while the backend streams, else `snap`.
- `move_rel`: an XY relative move through the guards. The default is `XYAxis.goto_rel`
  (T-002-4: box, long-move rule and readback apply).
- `on_point`: boundary points. The default appends to `map.json` through `engine.sample`;
  T-027's `boundary_mark` replaces it.
- `confirm`, `check`, `sleep`, `clock`: the runner's `ctx.confirm`, abort check, abortable
  sleep and time.

`UPDATABLE` names the one argument the runner's `update` command may change mid-run
(`speed_um_s`, the `+` / `-` keys). `WATCHED` marks it operator-watched (D14).
"""

from __future__ import annotations

import math
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any

import numpy as np

from ..backend import Backend
from ..events import Event, EventSink, null_sink
from ..guards import GuardError, OperationAborted, XYAxis, XYBox, operation, registry_key
from ..records import stamp
from ..sample import Sample
from .light_set import LightRequest, switch

NAME = "edge_trace"
WATCHED = True  # D14: abort when every local viewer is gone
UPDATABLE = frozenset({"speed_um_s"})
RECOMMENDED_OBJECTIVE = "4x"

MAX_SPEED_UM_S, MIN_SPEED_UM_S = 1000.0, 10.0
MAX_STEP_UM, MIN_STEP_UM = 200.0, 20.0
MIN_BLOB_UM = 500.0  # regions smaller than (500 um)^2 are debris or bubbles
CAL_MIN_PEAK = 8.0  # phase-correlation peak sharpness below this: too little structure
CAL_SCALE_RANGE = (0.7, 1.4)  # measured um/px over the camera pixel
CAL_MAX_ANGLE_DIFF_DEG = 10.0  # against the reference calibration
DIAMETER_WARN_FRACTION = 0.2
FULL_LOOP = "back where the edge was first seen: full loop"

# docs/runs/2026-09-30_substrate-scan.yaml calibration_4x: the image is mirrored vs the stage
REFERENCE_CAL_4X = {
    "objective": "4x", "um_per_px": 1.62524, "angle_deg": 0.117,
    "M_px_per_um": [[0.61602, 0.00236], [0.00126, -0.61456]],
    "source": "2026-09-30 bench, docs/runs/2026-09-30_substrate-scan.yaml",
}


# ---------------------------------------------------------------- image helpers (ported)
def block_mean(img: np.ndarray, b: int) -> np.ndarray:
    h, w = (img.shape[0] // b) * b, (img.shape[1] // b) * b
    return img[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3), dtype=np.float64)


def gaussian(a: np.ndarray, sigma: float) -> np.ndarray:
    r = max(1, int(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="reflect")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, p)


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, float]:
    """Shift (x, y) in pixels of b relative to a (b(x) ~ a(x - shift)), and peak sharpness."""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    fa = np.fft.rfft2((a - a.mean()) * win)
    fb = np.fft.rfft2((b - b.mean()) * win)
    r = np.conj(fa) * fb
    c = np.fft.irfft2(r / np.maximum(np.abs(r), 1e-12), s=a.shape)
    iy, ix = np.unravel_index(np.argmax(c), c.shape)

    def sub(cm: float, c0: float, cp: float) -> float:  # parabolic sub-pixel peak
        d = cm - 2 * c0 + cp
        return 0.0 if abs(d) < 1e-12 else 0.5 * (cm - cp) / d

    dy = sub(c[iy - 1, ix], c[iy, ix], c[(iy + 1) % c.shape[0], ix])
    dx = sub(c[iy, ix - 1], c[iy, ix], c[iy, (ix + 1) % c.shape[1]])
    sy = iy + dy if iy <= c.shape[0] // 2 else iy + dy - c.shape[0]
    sx = ix + dx if ix <= c.shape[1] // 2 else ix + dx - c.shape[1]
    sharp = float(c.max() / max(np.abs(c).mean(), 1e-12))
    return np.array([sx, sy]), sharp


def otsu(v: np.ndarray) -> float:
    hist, edges = np.histogram(v, bins=256)
    p = hist / max(hist.sum(), 1)
    mids = 0.5 * (edges[:-1] + edges[1:])
    w0 = np.cumsum(p)
    m0 = np.cumsum(p * mids)
    mt = m0[-1]
    between = (mt * w0 - m0) ** 2 / np.maximum(w0 * (1 - w0), 1e-12)
    return float(mids[np.argmax(between)])


def remove_small_regions(mask: np.ndarray, min_area: int) -> np.ndarray:
    """Flip connected regions (4-neighbour, either value) smaller than `min_area` blocks.

    Debris and bubbles are small closed blobs; the chamber's two sides are large. The script
    used a Python flood fill (no scipy in the system Python); scipy's labelling is the same
    4-neighbour rule."""
    from scipy import ndimage

    out = mask.copy()
    for value in (True, False):
        labels, n = ndimage.label(mask == value)
        if n == 0:
            continue
        sizes = np.bincount(labels.ravel())
        small = np.nonzero(sizes < min_area)[0]
        small = small[small != 0]
        if small.size:
            out[np.isin(labels, small)] = not value
    return out


def find_edge(img: np.ndarray, block: int | None = None, sigma: float = 2.0,
              min_contrast: float = 8.0, prefer_n: np.ndarray | None = None,
              min_blob_px: float = 0.0) -> dict | None:
    """Nearest boundary point to the centre and its normal (dark -> bright), or None.

    Returns dict(p=(x, y) full-res px, n=unit normal (x, y), contrast): the boundary between
    the two brightness populations Otsu finds in the smoothed block-mean image, placed where
    the smoothed profile crosses the threshold. Blocks default to ~150 across the frame."""
    block = block or max(1, min(img.shape) // 150)
    m = block_mean(img, block)
    s = gaussian(m, sigma)
    noise = 1.4826 * np.median(np.abs(m - s))
    thr = otsu(s)
    hi, lo = s[s > thr], s[s <= thr]
    if hi.size < 0.03 * s.size or lo.size < 0.03 * s.size:
        return None
    contrast = (hi.mean() - lo.mean()) / max(noise / math.sqrt(2 * sigma**2 * math.pi), 1e-6)
    if contrast < min_contrast:
        return None
    mask = s > thr
    if min_blob_px > 0:  # blobs smaller than (min_blob)^2 are debris, not the chamber
        mask = remove_small_regions(mask, int((min_blob_px / block) ** 2))
    pts = []
    vy, vx = np.nonzero(mask[:-1, :] != mask[1:, :])
    f = np.clip((thr - s[vy, vx]) / (s[vy + 1, vx] - s[vy, vx] + 1e-12), 0, 1)
    pts.append(np.column_stack([vx + 0.5, vy + 0.5 + f]))
    hy, hx = np.nonzero(mask[:, :-1] != mask[:, 1:])
    f = np.clip((thr - s[hy, hx]) / (s[hy, hx + 1] - s[hy, hx] + 1e-12), 0, 1)
    pts.append(np.column_stack([hx + 0.5 + f, hy + 0.5]))
    pts = np.vstack(pts)
    if len(pts) < 5:
        return None
    c = np.array([s.shape[1] / 2, s.shape[0] / 2])
    gy, gx = np.gradient(s)
    d2 = ((pts - c) ** 2).sum(1)
    if prefer_n is not None:  # ignore boundaries facing the other way (debris, bubbles)
        iy = np.clip(pts[:, 1].astype(int), 0, s.shape[0] - 1)
        ix = np.clip(pts[:, 0].astype(int), 0, s.shape[1] - 1)
        g = np.column_stack([gx[iy, ix], gy[iy, ix]])
        cos = (g @ prefer_n) / np.maximum(np.linalg.norm(g, axis=1), 1e-12)
        d2 = np.where(cos > 0.5, d2, np.inf)
        if not np.isfinite(d2).any():
            return None
    i = int(np.argmin(d2))
    near = ((pts - pts[i]) ** 2).sum(1) <= 36  # average the normal over ~6 blocks
    iy = np.clip(pts[near, 1].astype(int), 0, s.shape[0] - 1)
    ix = np.clip(pts[near, 0].astype(int), 0, s.shape[1] - 1)
    g = np.array([gx[iy, ix].mean(), gy[iy, ix].mean()])
    if np.linalg.norm(g) < 1e-9:
        return None
    return {"p": pts[i] * block, "n": g / np.linalg.norm(g), "contrast": float(contrast)}


def kasa_circle(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Least-squares circle (Kasa): centre (x, y) and radius, same units as the points."""
    b = np.asarray(points, float)
    A = np.column_stack([2 * b[:, 0], 2 * b[:, 1], np.ones(len(b))])
    (cx, cy, c0), *_ = np.linalg.lstsq(A, (b**2).sum(1), rcond=None)
    return np.array([cx, cy]), float(np.sqrt(max(c0 + cx**2 + cy**2, 0.0)))


def fixed_radius_centre(points: np.ndarray, r: float, init: np.ndarray) -> np.ndarray:
    """Centre of a circle of known radius through the points (Gauss-Newton)."""
    b = np.asarray(points, float)
    c = np.asarray(init, float).copy()
    for _ in range(30):
        v = c - b
        d = np.maximum(np.hypot(v[:, 0], v[:, 1]), 1e-9)
        J = v / d[:, None]  # d(|c - p|)/dc
        step, *_ = np.linalg.lstsq(J, -(d - r), rcond=None)
        c += step
        if np.linalg.norm(step) < 1e-3:
            break
    return c


def arc_degrees(points: np.ndarray, c: np.ndarray) -> float:
    a = np.unwrap(np.arctan2(points[:, 1] - c[1], points[:, 0] - c[0]))
    return float(np.degrees(a.max() - a.min()))


def robust_circle(points: np.ndarray, floor: float = 150.0,
                  rounds: int = 3) -> tuple[np.ndarray, float, np.ndarray]:
    """Kasa fit, then drop points off it by > max(3 MAD, floor) and refit. (centre, r, kept)."""
    b = np.asarray(points, float)
    keep = np.ones(len(b), bool)
    for _ in range(rounds):
        c, r = kasa_circle(b[keep])
        res = np.abs(np.hypot(*(b - c).T) - r)
        cut = max(3 * 1.4826 * np.median(res[keep]), floor)
        new = res <= cut
        if new.sum() < 6 or (new == keep).all():
            break
        keep = new
    c, r = kasa_circle(b[keep])
    return c, r, keep


def calibration_of(M: np.ndarray) -> dict:
    """um/px and image angle of a px-per-um matrix (the script's cal_result fields)."""
    um_per_px = 1 / math.sqrt(abs(float(np.linalg.det(M))))
    angle = math.degrees(math.atan2(M[1, 0], M[0, 0]))
    return {"M_px_per_um": np.asarray(M, float).tolist(), "um_per_px": um_per_px,
            "angle_deg": angle}


def hole_fit(points: np.ndarray) -> dict | None:
    """sample.json `hole` from the boundary points (stage um), or None under 6 points."""
    b = np.asarray(points, float)
    if len(b) < 6:
        return None
    c, r, keep = robust_circle(b)
    kept = b[keep]
    rms = float(np.sqrt(np.mean((np.hypot(*(kept - c).T) - r) ** 2)))
    return {"centre_um": [round(float(c[0]), 1), round(float(c[1]), 1)],
            "diameter_mm": round(2 * r / 1000, 4), "fit_rms_um": round(rms, 1),
            "n_points": int(len(kept)), "arc_deg": round(arc_degrees(kept, c), 1)}


# ---------------------------------------------------------------- arguments
@dataclass
class EdgeTraceArgs:
    hole_diameter_mm: float | None = None
    speed_um_s: float = 100.0
    exposure_ms: float | None = None
    light: str = "brightfield"  # "brightfield" | "keep" (the light already set stays)
    calibrate: bool = True
    cal_um: float = 200.0
    point_every_um: float = 250.0
    max_radius_um: float = 7000.0
    max_path_um: float = 25000.0
    max_time_s: float = 360.0
    min_radius_um: float = 1000.0

    @classmethod
    def from_dict(cls, d: dict) -> EdgeTraceArgs:
        known = {f.name for f in fields(cls)}
        extra = sorted(set(d) - known)
        if extra:
            raise ValueError(f"unknown edge_trace arguments: {extra}")
        a = cls(**d)
        if a.light not in ("brightfield", "keep"):
            raise ValueError(f"light {a.light!r} is not 'brightfield' or 'keep'")
        for name in ("speed_um_s", "cal_um", "point_every_um", "max_radius_um", "max_path_um",
                     "max_time_s", "min_radius_um"):
            v = getattr(a, name)
            if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                raise ValueError(f"{name} must be a positive number, got {v!r}")
        if a.cal_um > MAX_STEP_UM:
            raise ValueError(f"cal_um {a.cal_um} exceeds the {MAX_STEP_UM:g} um step limit")
        for name in ("hole_diameter_mm", "exposure_ms"):
            v = getattr(a, name)
            if v is not None and (not isinstance(v, (int, float)) or not math.isfinite(v)
                                  or v <= 0):
                raise ValueError(f"{name} must be a positive number or null, got {v!r}")
        return a


def pace(speed_um_s: float) -> tuple[float, float]:
    """(speed, step): speed clamped to 10-1000 um/s, step = 0.5 s of it, 20-200 um."""
    speed = float(min(max(speed_um_s, MIN_SPEED_UM_S), MAX_SPEED_UM_S))
    return speed, float(min(max(speed * 0.5, MIN_STEP_UM), MAX_STEP_UM))


# ---------------------------------------------------------------- the routine
class EdgeTracer:
    """The tracking loop, with the hardware behind plain callables.

    `grab(not_before)` returns an image taken after the wall time `not_before`; `move_rel(d)`
    moves the stage by d um (guarded) and returns the position read back; `xy()` reads the
    stage. `log(dict)` gets the script's event dicts (`event` = track_start, cal, cal_result,
    move, edge_point, track_speed, track_stop). `check()` raises on abort; `sleep` and
    `clock` are the runner's abortable sleep and a monotonic clock."""

    def __init__(self, *, grab: Callable[[float], np.ndarray],
                 move_rel: Callable[[np.ndarray], Any], xy: Callable[[], np.ndarray],
                 pixel_um: float, exposure_ms: float,
                 args: EdgeTraceArgs, log: Callable[[dict], None],
                 on_point: Callable[[float, float], None] | None = None,
                 reference: dict | None = None, check: Callable[[], None] = lambda: None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time):
        self.grab, self.move_rel, self.xy = grab, move_rel, xy
        self.px, self.args = float(pixel_um), args
        self.settle_s = 2 * exposure_ms / 1000 + 0.08
        self.log, self.on_point, self.reference = log, on_point, reference
        self.check, self.sleep, self.clock, self.wall = check, sleep, clock, wall
        self.expect_r = None if not args.hole_diameter_mm else args.hole_diameter_mm * 500.0
        self.speed, self.step = pace(args.speed_um_s)
        self.M: np.ndarray | None = None
        self.calibration: dict | None = None
        self.circle_info: dict | None = None
        self.status, self.why = "starting", None
        self.path_um, self.n_moves, self.points = 0.0, 0, []
        self._ready_at, self._ready_wall = 0.0, 0.0

    def set_speed(self, speed_um_s: float) -> None:
        """Change pace while running; the step grows with it (0.5 s per step) up to 200 um."""
        self.speed, self.step = pace(speed_um_s)
        self.log({"event": "track_speed", "speed_um_s": self.speed, "step_um": self.step})

    # -- plumbing
    def _stop(self, why: str) -> str:
        self.why, self.status = why, f"stopped: {why}"
        self.log({"event": "track_stop", "why": why})
        return why

    def _frame(self) -> np.ndarray:
        wait = self._ready_at - self.clock()
        if wait > 0:
            self.sleep(wait)
        self.check()
        return self.grab(self._ready_wall)

    def _wait(self, s: float) -> None:
        self._ready_at = max(self._ready_at, self.clock() + s)
        self._ready_wall = max(self._ready_wall, self.wall() + s)

    def _move(self, d_um: np.ndarray, why: str) -> None:
        self.check()
        d_um = np.asarray(d_um, float)
        n = float(np.linalg.norm(d_um))
        limit = self.args.cal_um if why == "calibration" else self.step
        if n > limit + 1e-6:
            d_um = d_um * (limit / n)
        at = self.move_rel(d_um)
        self.n_moves += 1
        self._ready_at = self.clock() + self.settle_s
        self._ready_wall = self.wall() + self.settle_s
        self.log({"event": "move", "why": why, "d_um": [round(float(v), 2) for v in d_um],
                  "at_um": [round(float(v), 2) for v in at]})

    def _circle(self, hist: list[np.ndarray]) -> tuple[np.ndarray, float] | None:
        """The chamber circle to steer by, or None while it isn't trustworthy yet.

        With a known diameter the radius is held at it until the arc reaches 60 degrees. The
        circle is used only if the points sit on it (rms < 60 um) and its radius is plausible:
        a wrong circle would reject the true edge, which is worse than having none."""
        if len(hist) < 6:
            return None
        hb = np.array(hist[-300:])
        if np.ptp(hb, axis=0).max() < 800:
            return None
        c, r, keep = robust_circle(hb)
        hb = hb[keep]
        r_exp = self.expect_r
        if r_exp is not None and (arc_degrees(hb, c) < 60 or abs(r - r_exp) > 0.2 * r_exp):
            mean = hb.mean(axis=0)
            toward = (c - mean) / max(np.linalg.norm(c - mean), 1e-9)  # curvature side
            c = fixed_radius_centre(hb, r_exp, mean + r_exp * toward)
            r = r_exp
        rms = float(np.sqrt(np.mean((np.hypot(*(hb - c).T) - r) ** 2)))
        plausible = (r >= self.args.min_radius_um
                     and (r_exp is None or abs(r - r_exp) < 0.3 * r_exp))
        self.circle_info = {"centre": c.tolist(), "r": r, "rms": rms, "n": len(hb)}
        return (c, r) if rms < 60 and plausible else None

    # -- calibration
    def _check_against_reference(self, cal: dict) -> str | None:
        ref = self.reference
        if not ref:
            return None
        Mr = np.asarray(ref["M_px_per_um"], float)
        if np.sign(np.linalg.det(Mr)) != np.sign(np.linalg.det(np.asarray(cal["M_px_per_um"]))):
            return "calibration is mirrored the other way from the reference"
        diff = (cal["angle_deg"] - float(ref.get("angle_deg", calibration_of(Mr)["angle_deg"]))
                + 180) % 360 - 180
        if abs(diff) > CAL_MAX_ANGLE_DIFF_DEG:
            return (f"calibration angle {cal['angle_deg']:.1f} deg is {diff:+.1f} deg off the "
                    f"reference")
        return None

    def _calibrate(self, frame: np.ndarray) -> tuple[np.ndarray | None, np.ndarray]:
        if not self.args.calibrate:
            if not self.reference:
                self._stop("calibrate=false needs a reference calibration for this objective")
                return None, frame
            M = np.asarray(self.reference["M_px_per_um"], float)
            cal = calibration_of(M)
            self.log({"event": "cal_result", **cal, "source": self.reference.get("source")})
        else:
            self.status, b, cols = "calibrating", 4, []
            for axis in (0, 1):
                ref = block_mean(frame, b)
                d = np.zeros(2)
                d[axis] = self.args.cal_um
                self._move(d, "calibration")
                frame = self._frame()
                shift, sharp = phase_shift(ref, block_mean(frame, b))
                cols.append(shift * b / self.args.cal_um)
                self.log({"event": "cal", "axis": "xy"[axis], "shift_px": (shift * b).tolist(),
                          "peak": sharp})
                self._move(-d, "calibration")
                frame = self._frame()
                if sharp < CAL_MIN_PEAK:
                    self._stop("calibration: image has too little structure to measure a shift")
                    return None, frame
            M = np.column_stack(cols)
            if abs(np.linalg.det(M)) < 1e-12:
                self._stop("calibration: the image did not move with the stage")
                return None, frame
            cal = calibration_of(M)
            self.log({"event": "cal_result", **cal, "source": "measured"})
        lo, hi = CAL_SCALE_RANGE
        if not lo < cal["um_per_px"] / self.px < hi:
            self._stop(f"calibration gives {cal['um_per_px']:.3f} um/px against "
                       f"{self.px:.3f} expected")
            return None, frame
        bad = self._check_against_reference(cal) if self.args.calibrate else None
        if bad:
            self._stop(bad)
            return None, frame
        self.M, self.calibration = M, {**cal, "source": "measured" if self.args.calibrate
                                       else self.reference.get("source")}
        return M, frame

    # -- the routine itself
    def run(self) -> str:
        """Calibrate, then follow the edge until a stop condition. Returns why it stopped."""
        frame = self._frame()
        start = np.asarray(self.xy(), float)
        self.log({"event": "track_start", "start_um": start.tolist(), "pixel_um": self.px})
        M, frame = self._calibrate(frame)
        if M is None:
            return self.why
        Minv = np.linalg.inv(M)
        self.status = "tracking"
        a = self.args
        t0, since_point, lost = self.clock(), a.point_every_um, 0
        prev_t = prev_n = last_dir = loop_start = None
        last_move, sense = -math.inf, 0.0
        hist: list[np.ndarray] = []
        min_blob_px = MIN_BLOB_UM / self.px
        while True:
            here = np.asarray(self.xy(), float)
            centre = np.array([(frame.shape[1] - 1) / 2, (frame.shape[0] - 1) / 2])
            circ = self._circle(hist)
            e = find_edge(frame, prefer_n=prev_n, min_blob_px=min_blob_px)
            edge_stage = None if e is None else here + Minv @ (centre - e["p"])
            if (e is not None and circ is not None
                    and abs(np.linalg.norm(edge_stage - circ[0]) - circ[1]) > 200):
                e, edge_stage = None, None  # a boundary, but not on the chamber's circle
            if np.linalg.norm(here - start) > a.max_radius_um:
                return self._stop(f"more than {a.max_radius_um / 1000:g} mm from the start")
            if self.path_um > a.max_path_um or self.clock() - t0 > a.max_time_s:
                return self._stop("travel or time limit")
            if e is None:
                lost += 1
                limit = max(10, int(2000 / self.step)) if circ is not None else 3
                if lost > limit:
                    return self._stop(f"edge not found in {limit} frames"
                                      + (" (coasted along the fitted circle)" if circ else ""))
                self.status = (f"coasting on fitted circle ({lost}/{limit})" if circ
                               else f"edge lost ({lost}/{limit})")
                if circ is None:  # nothing to steer by yet: wait for a better frame
                    self._wait(0.15)
                    frame = self._frame()
                    continue
            else:
                lost = 0
                prev_n = e["n"]
                hist.append(edge_stage)
                if since_point >= a.point_every_um:
                    since_point = 0.0
                    pt = [float(edge_stage[0]), float(edge_stage[1])]
                    self.points.append(pt)
                    if self.on_point:
                        self.on_point(*pt)
                    self.log({"event": "edge_point", "um": pt, "contrast": e["contrast"]})
                if loop_start is None:
                    loop_start = edge_stage
                elif (self.path_um > 3000
                      and np.linalg.norm(edge_stage - loop_start) < 3 * self.step):
                    return self._stop(FULL_LOOP)
            wait = self.step / self.speed - (self.clock() - last_move)
            if wait > 0:
                self._wait(wait)
                frame = self._frame()
                continue
            if circ is not None:
                c0, r0 = circ
                rvec = (edge_stage if e is not None else here) - c0
                rhat = rvec / max(np.linalg.norm(rvec), 1e-9)
                tan = np.array([-rhat[1], rhat[0]])  # counter-clockwise
                if sense == 0.0:
                    sense = 1.0 if last_dir is None or tan @ last_dir >= 0 else -1.0
                if e is not None:
                    # along the circle, plus the image's centring (radial part only)
                    corr = Minv @ (0.5 * (centre - e["p"]))
                    d = sense * tan * self.step + (corr @ rhat) * rhat
                else:  # coast: field centre onto the circle, one step further round
                    ang = sense * self.step / r0
                    rot = np.array([[math.cos(ang), -math.sin(ang)],
                                    [math.sin(ang), math.cos(ang)]])
                    d = c0 + r0 * (rot @ rhat) - here
            else:
                n = e["n"]
                t = np.array([-n[1], n[0]])
                if prev_t is not None and t @ prev_t < 0:
                    t = -t  # keep going the same way round
                if last_dir is not None and (Minv @ -t) @ last_dir < 0:
                    t = -t  # ...and never reverse the stage's direction of travel
                prev_t = t
                # image content moves opposite to the view; 0.5 x pulls the edge to the centre
                d = Minv @ (0.5 * (centre - e["p"]) - t * (self.step / self.px))
            if e is not None:
                self.status = (f"tracking {self.speed:.0f} um/s  path {self.path_um / 1000:.2f}"
                               f" mm  contrast {e['contrast']:.0f}"
                               + (f"  circle d {2 * circ[1] / 1000:.2f} mm" if circ else ""))
            self._move(d, "track" if e is not None else "coast")
            last_move = self.clock()
            moved = min(float(np.linalg.norm(d)), self.step)
            last_dir = d / max(np.linalg.norm(d), 1e-9)
            self.path_um += moved
            since_point += moved
            frame = self._frame()


# ---------------------------------------------------------------- the operation
def reference_calibration(info_cal: dict | None, objective: str) -> dict | None:
    """The sample's calibration for this lens, else the 2026-09-30 bench M for the 4x."""
    if info_cal and info_cal.get("objective") == objective and info_cal.get("M_px_per_um"):
        return {**info_cal, "source": info_cal.get("source") or "sample calibration"}
    if objective == RECOMMENDED_OBJECTIVE:
        return dict(REFERENCE_CAL_4X)
    return None


def plan(args: dict, start_um: tuple[float, float] | None = None) -> dict:
    a = EdgeTraceArgs.from_dict(args)
    speed, step = pace(a.speed_um_s)
    return {
        "op": NAME, "start_um": None if start_um is None else list(start_um),
        "max_radius_um": a.max_radius_um, "max_path_um": a.max_path_um,
        "max_time_s": a.max_time_s, "speed_um_s": speed, "step_um": step,
        "calibration": ([f"+x {a.cal_um:g} um and back", f"+y {a.cal_um:g} um and back"]
                        if a.calibrate else ["reference calibration, no moves"]),
        "text": (f"Trace the edge: XY moves only, steps up to {step:g} um at {speed:g} um/s, "
                 f"within {a.max_radius_um / 1000:g} mm of the start. Z does not move."),
    }


def preflight(backend: Backend, args: dict) -> list[dict]:
    """Checks as `{name, ok, want, read, why}`; a warning is ok with a `warning` text."""
    checks: list[dict] = []
    try:
        EdgeTraceArgs.from_dict(args)
        checks.append({"name": "args", "ok": True, "want": "valid", "read": "valid", "why": ""})
    except (TypeError, ValueError) as exc:
        checks.append({"name": "args", "ok": False, "want": "valid", "read": str(exc),
                       "why": str(exc)})
    p = backend.positions()
    xy_ok = p.x_um is not None and p.y_um is not None
    checks.append({"name": "xy_readable", "ok": xy_ok, "want": "x and y read",
                   "read": [p.x_um, p.y_um], "why": "" if xy_ok else f"unreadable: {p.errors}"})
    info = backend.info()
    px_ok = bool(info.pixel_um and info.pixel_um > 0)
    checks.append({"name": "pixel_um", "ok": px_ok, "want": "> 0", "read": info.pixel_um,
                   "why": "" if px_ok else "no camera pixel size for the calibration check"})
    try:
        key = registry_key(backend.nosepiece())
    except Exception as exc:  # noqa: BLE001 - unreadable lens is a warning; calibration says
        key = f"unreadable: {exc}"
    c = {"name": "objective", "ok": True, "want": RECOMMENDED_OBJECTIVE, "read": key, "why": ""}
    if key != RECOMMENDED_OBJECTIVE:
        c["warning"] = (f"edge_trace is meant for the {RECOMMENDED_OBJECTIVE}; calibration is "
                        f"stored for {key!r}")
    checks.append(c)
    return checks


def _backup_and_clear(sample: Sample, when: str) -> list[str]:
    """Back up map.json and sample.json, then clear the boundary only (visits stay)."""
    saved = []
    for src, name in ((sample.map_json, f"map_before_rescan_{when}.json"),
                      (sample.sample_json, f"sample_before_rescan_{when}.json")):
        if src.exists():
            shutil.copy2(src, sample.dir / name)
            saved.append(name)
    m = sample.load_map()
    m.boundary = []
    sample.save_map(m)
    return saved


class _MapPoints:
    """Default `on_point`: append to map.json (T-027's boundary_mark replaces this)."""

    def __init__(self, sample: Sample):
        self.sample = sample

    def __call__(self, x: float, y: float) -> None:
        m = self.sample.load_map()
        m.boundary.append([round(x, 1), round(y, 1)])
        self.sample.save_map(m)


def _default_grab(backend: Backend) -> Callable[[float], np.ndarray]:
    """A frame taken after `not_before` (wall time): the stream while it runs, else snap."""

    def grab(not_before: float) -> np.ndarray:
        streaming = getattr(backend, "streaming", None)
        if callable(streaming) and streaming():
            for _ in range(50):
                f = backend.next_frame(timeout_s=2.0)
                if f is not None and f.t_read >= not_before:
                    return f.image
            raise GuardError("no fresh frame from the acquisition stream")
        return backend.snap().image

    return grab


def run_edge_trace(backend: Backend, sample: Sample, args: dict, sink: EventSink = null_sink, *,
                   confirm: Callable[[str, str], bool],
                   check: Callable[[], None] = lambda: None,
                   sleep: Callable[[float], None] = time.sleep,
                   clock: Callable[[], float] = time.monotonic,
                   wall: Callable[[], float] = time.time,
                   grab: Callable[[float], np.ndarray] | None = None,
                   move_rel: Callable[[np.ndarray], Any] | None = None,
                   on_point: Callable[[float, float], None] | None = None,
                   on_tracer: Callable[[EdgeTracer], None] | None = None,
                   user_id: str | None = None, session_id: str | None = None) -> dict:
    """Run edge_trace on the T-002 lifecycle (record in `<sample>/edge_trace_<stamp>/`).

    `confirm(key, text)` answers `replace_hole_fit` and `start_trace`; a no raises
    OperationAborted before anything moves. `on_tracer` receives the tracer once it exists,
    so the caller can route `update{speed_um_s}` to `tracer.set_speed`. Returns the result
    (also the summary's `result`). Preflight failures raise GuardError before any record."""
    checks = preflight(backend, args)
    failed = [c for c in checks if not c["ok"]]
    if failed:
        raise GuardError("preflight failed: " + "; ".join(f"{c['name']}: {c['why']}"
                                                          for c in failed))
    a = EdgeTraceArgs.from_dict(args)
    info = sample.load_info()
    m = sample.load_map()
    backups: list[str] = []
    if m.boundary or info.hole:
        when = (info.hole or {}).get("fitted_at") or "an earlier trace"
        if not confirm("replace_hole_fit", f"replace the hole fit from {when}? (backed up)"):
            raise OperationAborted("the operator kept the previous hole fit")
        backups = _backup_and_clear(sample, stamp())
        info = sample.load_info()
    if not confirm("start_trace", f"trace the edge: XY moves only, within "
                                  f"{a.max_radius_um / 1000:g} mm of here"):
        raise OperationAborted("the operator did not start the trace")

    with operation(backend, sample.dir, NAME, sink, args=dict(args), user_id=user_id,
                   session_id=session_id) as scope:
        def log(d: dict) -> None:
            ev = dict(d)
            name = ev.pop("event")
            scope.emit(Event("progress", scope.op_id, {"op": NAME, "status": name, "data": ev}))

        warnings = [c["warning"] for c in checks if c.get("warning")]
        for w in warnings:
            scope.emit(Event("log", scope.op_id, {"level": "warning", "text": w}))
        if a.light == "brightfield":
            switch(backend, scope, LightRequest("brightfield"))
        if a.exposure_ms is not None:
            backend.set_exposure(a.exposure_ms)
        binfo = backend.info()
        try:
            objective = registry_key(backend.nosepiece())
        except GuardError:
            objective = "unknown"
        p = backend.positions()
        start = (float(p.x_um), float(p.y_um))
        axis = XYAxis(backend, XYBox.around(start, a.max_radius_um), allow_motion=True,
                      sink=scope.emit, op_id=scope.op_id)
        tracer = EdgeTracer(
            grab=grab or _default_grab(backend),
            move_rel=move_rel or (lambda d: axis.goto_rel(float(d[0]), float(d[1]))),
            xy=lambda: np.array(_xy(backend)), pixel_um=binfo.pixel_um,
            exposure_ms=binfo.exposure_ms,
            args=a, log=log, on_point=on_point or _MapPoints(sample),
            reference=reference_calibration(info.stage_camera_calibration, objective),
            check=check, sleep=sleep, clock=clock, wall=wall)
        if on_tracer:
            on_tracer(tracer)
        result: dict[str, Any] = {"backups": backups, "warnings": warnings,
                                  "objective": objective, "start_um": list(start)}
        scope.result = result
        try:
            why = tracer.run()
        except (OperationAborted, KeyboardInterrupt):
            tracer.log({"event": "track_stop", "why": "aborted"})
            raise
        finally:
            result.update(_finish(sample, tracer, objective, a, warnings))
        result["why"] = why
    return result


def _xy(backend: Backend) -> tuple[float, float]:
    p = backend.positions()
    if p.x_um is None or p.y_um is None:
        raise GuardError(f"XY unreadable: {p.errors}")
    return p.x_um, p.y_um


def _finish(sample: Sample, tracer: EdgeTracer, objective: str, a: EdgeTraceArgs,
            warnings: list[str]) -> dict:
    """Write the hole fit and calibration to sample.json; also on abort and error."""
    out: dict[str, Any] = {"path_um": round(tracer.path_um, 1), "n_moves": tracer.n_moves,
                           "n_points": len(tracer.points), "calibration": None, "hole": None}
    info = sample.load_info()
    changed = False
    if tracer.calibration is not None:
        info.stage_camera_calibration = {**tracer.calibration, "objective": objective,
                                         "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        out["calibration"] = info.stage_camera_calibration
        changed = True
    pts = np.asarray(sample.load_map().boundary, float)
    hole = hole_fit(pts) if len(pts) else None
    if hole is not None:
        hole["fitted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        hole["trace_stop"] = tracer.why or "aborted or failed"  # a partial arc says so
        hole["closed_loop"] = tracer.why == FULL_LOOP  # stable flag for sample.hole_loop()
        info.hole = hole
        info.boundary_limits_um = {"x": [float(pts[:, 0].min()), float(pts[:, 0].max())],
                                   "y": [float(pts[:, 1].min()), float(pts[:, 1].max())]}
        out["hole"] = hole
        changed = True
        if a.hole_diameter_mm:
            off = abs(hole["diameter_mm"] - a.hole_diameter_mm) / a.hole_diameter_mm
            if off > DIAMETER_WARN_FRACTION:
                warnings.append(f"fitted diameter {hole['diameter_mm']:.3f} mm is "
                                f"{100 * off:.0f} % off the expected {a.hole_diameter_mm:g} mm")
    if changed:
        sample.save_info(info)
    out["warnings"] = warnings
    return out

