"""Stage<->camera calibration and slow chamber-edge tracking, for the live view.

numpy only (the system Python running the live view has no scipy). Moves the XY stage
only -- never Z -- in relative steps of at most `step_um`, no faster than `speed_um_s` on
average, and stops on: Esc/t, the edge lost for 3 frames, leaving a disc of `max_radius_um`
around the start, a full turn, `max_path_um` of travel, or `max_time_s`.

Coordinates: image vectors are (x, y) = (column, row) in full-resolution pixels; stage
vectors are (x, y) in um as the XYStage reports them. Calibration measures the 2x2 matrix
M with d_pixels = M @ d_stage, so it absorbs any flip or rotation of the camera.
"""

from __future__ import annotations

import math
import time

import numpy as np

XY = "XYStage"


# ---------------------------------------------------------------- image helpers
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

    def sub(cm, c0, cp):  # parabolic sub-pixel peak
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
    """Flip connected regions (4-neighbour, either value) smaller than min_area blocks.

    Debris and bubbles are small closed blobs; the chamber's two sides are large. numpy +
    a Python flood fill, which is fine on the ~150 x 150 block grid.
    """
    from collections import deque

    out = mask.copy()
    seen = np.zeros(mask.shape, bool)
    h, w = mask.shape
    for y0 in range(h):
        for x0 in range(w):
            if seen[y0, x0]:
                continue
            v = mask[y0, x0]
            q, comp = deque([(y0, x0)]), []
            seen[y0, x0] = True
            while q:
                y, x = q.popleft()
                comp.append((y, x))
                for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= yy < h and 0 <= xx < w and not seen[yy, xx] and mask[yy, xx] == v:
                        seen[yy, xx] = True
                        q.append((yy, xx))
            if len(comp) < min_area:
                ys, xs = zip(*comp)
                out[list(ys), list(xs)] = not v
    return out


def find_edge(img: np.ndarray, block: int | None = None, sigma: float = 2.0,
              min_contrast: float = 8.0, prefer_n: np.ndarray | None = None,
              min_blob_px: float = 0.0):
    """Nearest boundary point to the centre and its normal (dark -> bright), or None.

    Returns dict(p=(x, y) full-res px, n=unit normal (x, y), contrast) -- the boundary
    between the two brightness populations Otsu finds in the smoothed block-mean image,
    placed where the smoothed profile crosses the threshold (interpolated between block
    centres, so it carries no half-block bias). Blocks default to ~150 across the frame.
    """
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
    # threshold crossings between vertically and horizontally adjacent block centres;
    # block i's centre is at (i + 0.5) in block units
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


def robust_circle(points: np.ndarray, floor: float = 150.0, rounds: int = 3):
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


# ---------------------------------------------------------------- the routine
class EdgeTracker:
    """A generator-driven routine: `feed(frame)` whenever a frame arrives; it decides
    when a frame is fresh enough (taken after the last move settled) to use."""

    def __init__(self, core, shape, pixel_um: float, exposure_ms: float, log,
                 on_point=None, step_um: float = 50.0, speed_um_s: float = 100.0,
                 cal_um: float = 200.0, point_every_um: float = 250.0,
                 max_radius_um: float = 7000.0, max_path_um: float = 25000.0,
                 max_time_s: float = 360.0, min_radius_um: float = 1000.0,
                 expect_diameter_um: float | None = None):
        self.expect_r = None if not expect_diameter_um else expect_diameter_um / 2
        self.circle_info = None
        self.min_radius_um = min_radius_um  # a fitted circle smaller than this is not trusted
        self.min_blob_um = 500.0  # regions smaller than (500 um)^2 are debris or bubbles
        self.core, self.shape, self.px = core, shape, pixel_um
        self.settle_s = 2 * exposure_ms / 1000 + 0.08
        self.log, self.on_point = log, on_point
        self.step, self.speed, self.cal_um = step_um, speed_um_s, cal_um
        self.every, self.rmax, self.pmax, self.tmax = (point_every_um, max_radius_um,
                                                       max_path_um, max_time_s)
        if speed_um_s <= self.MAX_SPEED_UM_S:  # (the offline simulation passes an unpaced 1e9)
            self.set_speed(speed_um_s)
        self.M = None
        self.status = "starting"
        self.done = False
        self._ready_at = 0.0
        self._gen = self._run()
        next(self._gen)

    MAX_SPEED_UM_S, MAX_STEP_UM = 1000.0, 200.0

    def set_speed(self, speed_um_s: float) -> None:
        """Change pace while running; the step grows with it (0.5 s per step) up to 200 um."""
        self.speed = float(min(max(speed_um_s, 10.0), self.MAX_SPEED_UM_S))
        self.step = float(min(max(self.speed * 0.5, 20.0), self.MAX_STEP_UM))
        self.log({"event": "track_speed", "speed_um_s": self.speed, "step_um": self.step})

    # -- plumbing
    def stop(self, why: str) -> None:
        if not self.done:
            self.done, self.status = True, f"stopped: {why}"
            self.log({"event": "track_stop", "why": why})

    def feed(self, frame: np.ndarray) -> None:
        if self.done or time.monotonic() < self._ready_at:
            return
        try:
            self._gen.send(frame)
        except StopIteration:
            self.done = True
        except Exception as exc:  # noqa: BLE001 - any failure stops motion, says why
            self.stop(f"error: {exc}")

    def _xy(self) -> np.ndarray:
        return np.array(self.core.getXYPosition(XY))

    def _move(self, d_um: np.ndarray, why: str) -> None:
        d_um = np.asarray(d_um, float)
        n = float(np.linalg.norm(d_um))
        if n > self.step + 1e-6 and why != "calibration":
            d_um = d_um * (self.step / n)
        self.core.setRelativeXYPosition(XY, float(d_um[0]), float(d_um[1]))
        self.core.waitForDevice(XY)
        self._ready_at = time.monotonic() + self.settle_s
        self.log({"event": "move", "why": why, "d_um": [round(float(v), 2) for v in d_um],
                  "at_um": [round(float(v), 2) for v in self._xy()]})

    def _circle(self, hist):
        """The chamber circle to steer by, or None while it isn't trustworthy yet.

        A short arc pins the curvature badly, so with a known diameter the radius is held
        at it until the arc reaches 60 degrees. The circle is used only if the points sit on
        it (rms < 60 um) and its radius is plausible -- a wrong circle would reject the
        true edge, which is worse than having none.
        """
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
        plausible = r >= self.min_radius_um and (r_exp is None or abs(r - r_exp) < 0.3 * r_exp)
        self.circle_info = {"centre": c.tolist(), "r": r, "rms": rms, "n": len(hb)}
        return (c, r) if rms < 60 and plausible else None

    # -- the routine itself
    def _run(self):
        frame = yield
        start = self._xy()
        self.log({"event": "track_start", "start_um": start.tolist(), "pixel_um": self.px})

        # 1. calibration: +x then back, +y then back, image shift by phase correlation
        self.status = "calibrating"
        b = 4
        cols = []
        for axis in (0, 1):
            ref = block_mean(frame, b)
            d = np.zeros(2)
            d[axis] = self.cal_um
            self._move(d, "calibration")
            frame = yield
            shift, sharp = phase_shift(ref, block_mean(frame, b))
            cols.append(shift * b / self.cal_um)
            self.log({"event": "cal", "axis": "xy"[axis], "shift_px": (shift * b).tolist(),
                      "peak": sharp})
            self._move(-d, "calibration")
            frame = yield
            if sharp < 8:
                self.stop("calibration: image has too little structure to measure a shift")
                return
        self.M = np.column_stack(cols)
        um_per_px = 1 / math.sqrt(abs(np.linalg.det(self.M)))
        angle = math.degrees(math.atan2(self.M[1, 0], self.M[0, 0]))
        self.log({"event": "cal_result", "M_px_per_um": self.M.tolist(),
                  "um_per_px": um_per_px, "angle_deg": angle})
        if not 0.7 < um_per_px / self.px < 1.4:
            self.stop(f"calibration gives {um_per_px:.3f} um/px against {self.px:.3f} expected")
            return
        Minv = np.linalg.inv(self.M)
        self.calibration = {"um_per_px": um_per_px, "angle_deg": angle}

        # 2. follow the edge
        self.status = "tracking"
        t0, path, since_point, lost = time.monotonic(), 0.0, self.every, 0
        prev_t = prev_n = last_dir = loop_start = None
        last_move, sense = 0.0, 0.0
        hist: list[np.ndarray] = []  # every accepted edge position, stage um
        centre = np.array([(self.shape[1] - 1) / 2, (self.shape[0] - 1) / 2])
        while True:
            here = self._xy()
            # Once the edge has been followed for ~1 mm, the chamber's own circle predicts it:
            # its tangent gives the direction (no flips at debris), and a boundary far from
            # it is something else. Before that, only the local normal is available.
            circ = self._circle(hist)
            e = find_edge(frame, prefer_n=prev_n, min_blob_px=self.min_blob_um / self.px)
            edge_stage = None if e is None else here + Minv @ (centre - e["p"])
            if e is not None and circ is not None:
                off = abs(np.linalg.norm(edge_stage - circ[0]) - circ[1])
                if off > 200:
                    e, edge_stage = None, None  # a boundary, but not on the chamber's circle
            # stop conditions
            if np.linalg.norm(here - start) > self.rmax:
                self.stop(f"more than {self.rmax / 1000:.0f} mm from the start")
                return
            if path > self.pmax or time.monotonic() - t0 > self.tmax:
                self.stop("travel or time limit")
                return
            if e is None:
                lost += 1
                # on the fitted circle, coast up to ~2 mm of arc across a gap in the edge
                limit = max(10, int(2000 / self.step)) if circ is not None else 3
                if lost > limit:
                    self.stop(f"edge not found in {limit} frames"
                              + (" (coasted along the fitted circle)" if circ else ""))
                    return
                self.status = (f"coasting on fitted circle ({lost}/{limit})" if circ
                               else f"edge lost ({lost}/{limit})")
                if circ is None:  # nothing to steer by yet: wait for a better frame
                    self._ready_at = time.monotonic() + 0.15
                    frame = yield
                    continue
            else:
                lost = 0
                prev_n = e["n"]
                hist.append(edge_stage)
                if since_point >= self.every:
                    since_point = 0.0
                    if self.on_point:
                        self.on_point(float(edge_stage[0]), float(edge_stage[1]))
                    self.log({"event": "edge_point", "um": edge_stage.tolist(),
                              "contrast": e["contrast"]})
                if loop_start is None:
                    loop_start = edge_stage
                elif path > 3000 and np.linalg.norm(edge_stage - loop_start) < 3 * self.step:
                    self.stop("back where the edge was first seen: full loop")
                    return
            # pace: one step of at most `step` um no faster than `speed`
            wait = self.step / self.speed - (time.monotonic() - last_move)
            if wait > 0:
                self._ready_at = time.monotonic() + wait
                frame = yield
                continue
            if circ is not None:
                c0, r0 = circ
                rvec = (edge_stage if e is not None else here) - c0
                rhat = rvec / max(np.linalg.norm(rvec), 1e-9)
                tan = np.array([-rhat[1], rhat[0]])  # counter-clockwise
                if sense == 0.0:
                    sense = 1.0 if last_dir is None or tan @ last_dir >= 0 else -1.0
                if e is not None:
                    # along the circle, plus the image's centring -- radial part only, so a
                    # stale edge point behind us (an edge that ends) can't cancel the advance
                    corr = Minv @ (0.5 * (centre - e["p"]))
                    d = sense * tan * self.step + (corr @ rhat) * rhat
                else:  # coast: field centre onto the circle, one step further round
                    a = sense * self.step / r0
                    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
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
                self.status = (f"tracking {self.speed:.0f} um/s  path {path / 1000:.2f} mm  "
                               f"contrast {e['contrast']:.0f}"
                               + (f"  circle d {2 * circ[1] / 1000:.2f} mm" if circ else ""))
            self._move(d, "track" if e is not None else "coast")
            last_move = time.monotonic()
            moved = min(float(np.linalg.norm(d)), self.step)
            last_dir = d / max(np.linalg.norm(d), 1e-9)
            path += moved
            since_point += moved
            frame = yield
