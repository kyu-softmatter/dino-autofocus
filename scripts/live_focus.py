"""Full-sensor live view at ~10 fps with a focus-score panel.

    python scripts/live_focus.py                       # view only
    python scripts/live_focus.py --record --out D:/AutoFocus/frames/run1

Left: the whole 2400 x 2400 Kinetix_red frame, binned for display, with the scored
centre ROI outlined. Right: the -10..10 focus gauge (filled in once the DINO head is
trained -- step 4), then traces of a classical sharpness on that ROI and of ZDrive.

Frames arrive at the camera's rate (1 / exposure); this keeps one every 1/fps s by the
camera's own timestamps, for display and for --record. Recording is raw uint16 at
11.5 MB a frame, ~115 MB/s at 10 fps.

Camera and position reads only, through mm_grab.open_core: no stage, focus, lamp or
light-engine command is sent.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from mm_grab import (  # noqa: E402
    PiezoReader,
    aura_off,
    aura_on,
    brenner,
    open_core,
    positions,
    set_and_read,
    vollath4,
)

GAUGE_W, PANEL_W, MAP_W = 150, 470, 470
INK, MUTED, GRID, SERIES = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
IN_FOCUS_BAND = "#d6f0d6"  # |score| <= 1 DoF
CURRENT, BOUNDARY = "#eb6834", "#e34948"


SAMPLES_ROOT = Path(r"D:\AutoFocus\samples")


def new_sample_id(root: Path) -> str:
    """YYYYMMDD_HHMM_n, n counting up from 1 within the same minute."""
    stamp, n = time.strftime("%Y%m%d_%H%M"), 1
    while (root / f"{stamp}_{n}").exists():
        n += 1
    return f"{stamp}_{n}"


class Sample:
    """One sample's folder: map.json (boundary, fields), track_*.jsonl, and sample.json --
    the summary (hole centre/diameter, limits, objectives used, stage-camera calibration)."""

    def __init__(self, sid: str, root: Path, canvas, size: int, header: dict):
        self.id, self.dir = sid, root / sid
        self.dir.mkdir(parents=True, exist_ok=True)
        self.map = XYMap(canvas, size, self.dir / "map.json")
        old = self.dir / "sample.json"
        prev = json.loads(old.read_text()) if old.exists() else {}
        self.created = prev.get("created", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.calibration = prev.get("stage_camera_calibration")
        self.objectives = set(prev.get("objectives_used", []))
        # per objective: the raw score read where the person called the image in focus
        self.offsets: dict[str, float] = prev.get("score_offset_dof", {}) or {}
        self.header = header
        self.track = (self.dir / f"track_{time.strftime('%Y%m%d-%H%M%S')}.jsonl").open(
            "w", encoding="utf-8")
        self.track.write(json.dumps({"header": header, "sample": sid}, default=str) + "\n")
        print(f"sample {sid}: {self.dir}")

    def save(self) -> None:
        self.map.save()
        circ, lim = self.map.circle(), self.map.limits()
        hole = None
        if circ is not None:
            from edge_track import arc_degrees

            b = np.array(self.map.boundary)
            hole = {"centre_um": [round(circ[0], 1), round(circ[1], 1)],
                    "diameter_mm": round(2 * circ[2] / 1000, 4), "fit_rms_um": round(circ[3], 1),
                    "n_points": len(b), "arc_deg": round(arc_degrees(b, circ[:2]), 0)}
        info = {
            "sample_id": self.id, "created": self.created,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "coordinates": "sum = Ti2 XYStage/ZDrive + piezo, um (piezo axis signs unverified)",
            "hole": hole,
            "boundary_limits_um": None if lim is None else
            {"x": [round(lim[0], 1), round(lim[1], 1)], "y": [round(lim[2], 1), round(lim[3], 1)]},
            "n_fields_visited": len(self.map.visits),
            "objectives_used": sorted(self.objectives),
            "stage_camera_calibration": self.calibration,
            "score_offset_dof": self.offsets,
            "config": self.header.get("config"), "camera": self.header.get("camera"),
        }
        (self.dir / "sample.json").write_text(json.dumps(info, indent=1, default=str))

    def close(self) -> None:
        self.save()
        self.track.close()


def sample_xyz(p: dict) -> tuple[float, float, float]:
    """Where the field of view is: Ti2 stage + piezo, each axis summed.

    Assumes the piezo's x/y/z point the same way as the Ti2's -- not verified yet; until it
    is, a nonzero piezo offset makes the sum approximate (the parts are shown separately).
    """
    nan = float("nan")
    return tuple(p.get(f"{a}_um", nan) + p.get(f"piezo_{a}_um", 0.0) for a in "xyz")


class XYMap:
    """Stage-coordinate map: visited fields of view, boundary marks, and where we are now.

    Persisted as JSON so a low-magnification boundary scan is still there after switching
    to 100x; each visit keeps its own field size, so objectives can be mixed on one map.
    """

    def __init__(self, canvas, size: int, path: Path, flip_x: bool = True, flip_y: bool = True):
        self.c, self.size, self.path = canvas, size, path
        # On this stand +stage x reads to the left and +y downwards relative to the joystick
        # (seen 2026-09-30), so both are flipped by default.
        self.flip_x, self.flip_y = flip_x, flip_y
        self.visits: list[dict] = []
        self.boundary: list[list[float]] = []
        if path.exists():
            d = json.loads(path.read_text())
            self.visits, self.boundary = d.get("visits", []), d.get("boundary", [])
        self.dirty_t = 0.0

    def add(self, x, y, fov_um, objective, score=None, sharp=None) -> None:
        if not (np.isfinite(x) and np.isfinite(y)) or fov_um <= 0:
            return
        for v in reversed(self.visits[-400:]):  # same place, same objective: update it
            if (v["objective"] == objective and abs(v["x"] - x) < 0.25 * fov_um
                    and abs(v["y"] - y) < 0.25 * fov_um):
                v.update(t=time.time(), score=score, sharp=sharp)
                return
        self.visits.append({"x": x, "y": y, "fov_um": fov_um, "objective": objective,
                            "score": score, "sharp": sharp, "t": time.time()})

    def mark_boundary(self, x, y) -> None:
        if np.isfinite(x) and np.isfinite(y):
            self.boundary.append([x, y])
            self.save()

    def undo_boundary(self) -> None:
        if self.boundary:
            self.boundary.pop()
            self.save()

    def circle(self):
        """Circle through the boundary marks: (cx, cy, r, rms of the points kept).

        Kasa fit with outlier rejection once there are enough points, so a mark on a speck of
        debris doesn't drag the chamber's centre.
        """
        if len(self.boundary) < 3:
            return None
        from edge_track import kasa_circle, robust_circle

        b = np.array(self.boundary, dtype=float)
        if len(b) >= 8:
            c, r, keep = robust_circle(b)
        else:
            (c, r), keep = kasa_circle(b), np.ones(len(b), bool)
        res = np.hypot(b[keep, 0] - c[0], b[keep, 1] - c[1]) - r
        return float(c[0]), float(c[1]), float(r), float(np.sqrt(np.mean(res**2)))

    def save(self) -> None:
        self.path.write_text(json.dumps({"visits": self.visits[-20000:],
                                         "boundary": self.boundary}, indent=0))

    def limits(self):
        if len(self.boundary) < 2:
            return None
        b = np.array(self.boundary)
        return b[:, 0].min(), b[:, 0].max(), b[:, 1].min(), b[:, 1].max()

    def draw(self, x, y, fov_um) -> None:
        c, n, pad = self.c, self.size, 14
        c.delete("map")
        pts = [(v["x"], v["y"], v["fov_um"]) for v in self.visits]
        pts += [(bx, by, 0) for bx, by in self.boundary]
        circ = self.circle()
        if circ is not None:  # keep the whole fitted hole in view
            pts.append((circ[0], circ[1], 2 * circ[2]))
        if np.isfinite(x) and np.isfinite(y):
            pts.append((x, y, fov_um))
        if not pts:
            return
        xs = [p[0] - p[2] / 2 for p in pts] + [p[0] + p[2] / 2 for p in pts]
        ys = [p[1] - p[2] / 2 for p in pts] + [p[1] + p[2] / 2 for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 3 * max(fov_um, 1.0)) * 1.1
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        k = (n - 2 * pad) / span

        sx, sy = (-1 if self.flip_x else 1), (-1 if self.flip_y else 1)
        half = (n - 2 * pad) / 2

        def to(px, py):  # default: drawn the way the joystick moves the view
            return pad + sx * (px - cx) * k + half, n - pad - (sy * (py - cy) * k + half)

        c.create_rectangle(pad, pad, n - pad, n - pad, outline=GRID, tags="map")
        for v in self.visits:
            x0, y0 = to(v["x"] - v["fov_um"] / 2, v["y"] + v["fov_um"] / 2)
            x1, y1 = to(v["x"] + v["fov_um"] / 2, v["y"] - v["fov_um"] / 2)
            s = v.get("score")
            fill = ("#bfe3bf" if s is not None and abs(s) <= 1 else
                    "#cfe0f5" if s is not None and abs(s) <= 3 else "#ecebe7")
            c.create_rectangle(x0, y0, x1, y1, fill=fill, outline="", tags="map")
        if circ is not None:
            x0, y0 = to(circ[0] - circ[2], circ[1] + circ[2])
            x1, y1 = to(circ[0] + circ[2], circ[1] - circ[2])
            c.create_oval(x0, y0, x1, y1, outline=BOUNDARY, width=2, tags="map")
            px, py = to(circ[0], circ[1])
            c.create_line(px - 5, py - 5, px + 5, py + 5, fill=BOUNDARY, tags="map")
            c.create_line(px - 5, py + 5, px + 5, py - 5, fill=BOUNDARY, tags="map")
        elif len(self.boundary) == 2:
            c.create_line(*to(*self.boundary[0]), *to(*self.boundary[1]), fill=BOUNDARY,
                          width=2, tags="map")
        for bx, by in self.boundary:
            px, py = to(bx, by)
            c.create_oval(px - 4, py - 4, px + 4, py + 4, fill=BOUNDARY, outline="white",
                          tags="map")
        if np.isfinite(x) and np.isfinite(y):
            x0, y0 = to(x - fov_um / 2, y + fov_um / 2)
            x1, y1 = to(x + fov_um / 2, y - fov_um / 2)
            c.create_rectangle(x0, y0, x1, y1, outline=CURRENT, width=2, tags="map")
            px, py = to(x, y)
            c.create_line(px - 6, py, px + 6, py, fill=CURRENT, tags="map")
            c.create_line(px, py - 6, px, py + 6, fill=CURRENT, tags="map")
        arrows = (("←" if self.flip_x else "→"), ("↓" if self.flip_y else "↑"))
        c.create_text(pad + 2, n - pad - 2, anchor="sw", fill=MUTED, font=("Segoe UI", 8),
                      text=f"{span:.0f} um across   +stage x {arrows[0]}  +y {arrows[1]}",
                      tags="map")


def bin_for_display(img: np.ndarray, size: int) -> np.ndarray:
    """Mean-bin to at most `size` px on a side, then a robust 8-bit stretch."""
    k = max(1, math.ceil(max(img.shape) / size))
    h, w = (img.shape[0] // k) * k, (img.shape[1] // k) * k
    small = img[:h, :w].reshape(h // k, k, w // k, k).mean(axis=(1, 3), dtype=np.float32)
    lo, hi = np.percentile(small[::4, ::4], (0.5, 99.8))
    return np.clip((small - lo) * (255.0 / max(hi - lo, 1.0)), 0, 255).astype(np.uint8)


def centre_crop(img: np.ndarray, n: int) -> np.ndarray:
    y0, x0 = (img.shape[0] - n) // 2, (img.shape[1] - n) // 2
    return img[y0 : y0 + n, x0 : x0 + n]


class Trace:
    """A titled, auto-scaled time trace drawn on a tk canvas region."""

    def __init__(self, canvas, top: int, height: int, title: str, fmt: str, left: int = 12):
        self.c, self.top, self.h, self.fmt = canvas, top, height, fmt
        self.left, self.right = left, PANEL_W - 12
        canvas.create_text(self.left, top, text=title, anchor="nw", fill=INK,
                           font=("Segoe UI", 10, "bold"))
        self.y0, self.y1 = top + 22, top + height - 4
        canvas.create_rectangle(self.left, self.y0, self.right, self.y1, outline=GRID)
        self.line = canvas.create_line(0, 0, 0, 0, fill=SERIES, width=2)
        self.lo = canvas.create_text(self.right - 2, self.y1 - 2, anchor="se", fill=MUTED,
                                     font=("Segoe UI", 8))
        self.hi = canvas.create_text(self.right - 2, self.y0 + 2, anchor="ne", fill=MUTED,
                                     font=("Segoe UI", 8))
        self.now = canvas.create_text(self.left + 4, self.y0 + 2, anchor="nw", fill=INK,
                                      font=("Consolas", 10, "bold"))

    def draw(self, values: deque, capacity: int) -> None:
        v = np.array([x for x in values if x is not None and np.isfinite(x)], dtype=float)
        if len(v) < 2:
            return
        lo, hi = float(v.min()), float(v.max())
        pad = max((hi - lo) * 0.1, 1e-9)
        lo, hi = lo - pad, hi + pad
        dx = (self.right - self.left) / max(capacity - 1, 1)
        x0 = self.right - (len(v) - 1) * dx
        pts = []
        for i, val in enumerate(v):
            pts += [x0 + i * dx, self.y1 - (val - lo) / (hi - lo) * (self.y1 - self.y0)]
        self.c.coords(self.line, *pts)
        self.c.itemconfigure(self.lo, text=self.fmt.format(lo))
        self.c.itemconfigure(self.hi, text=self.fmt.format(hi))
        self.c.itemconfigure(self.now, text=self.fmt.format(v[-1]))


class Gauge:
    """Vertical -10..+10 focus gauge: +10 at the top, 0 = in focus, -10 at the bottom.

    Units are depths of field, dz = stage - best focus (psf-autofocus convention);
    which way is physically 'up' on this stand is to be checked against a real z-stack.
    """

    def __init__(self, canvas, height: int):
        self.c = canvas
        self.x = GAUGE_W // 2 - 10
        self.top, self.bot = 80, height - 120
        canvas.create_text(GAUGE_W // 2, 8, text="Focus score", anchor="n", fill=INK,
                           font=("Segoe UI", 10, "bold"))
        canvas.create_text(GAUGE_W // 2, 28, text="depths of field", anchor="n", fill=MUTED,
                           font=("Segoe UI", 8))
        y_hi, y_lo = self.y(1), self.y(-1)
        canvas.create_rectangle(self.x - 16, y_hi, self.x + 16, y_lo, fill=IN_FOCUS_BAND,
                                outline="")
        canvas.create_line(self.x, self.top, self.x, self.bot, fill=GRID, width=8,
                           capstyle="round")
        for s in range(-10, 11, 2):
            y = self.y(s)
            major = s % 10 == 0 or s % 5 == 0
            canvas.create_line(self.x - (10 if major else 5), y, self.x + (10 if major else 5),
                               y, fill=INK if s == 0 else MUTED, width=2 if s == 0 else 1)
        for s in (10, 5, 0, -5, -10):
            canvas.create_text(self.x + 16, self.y(s), text=f"{s:+d}" if s else "0 focus",
                               anchor="w", fill=INK if s == 0 else MUTED,
                               font=("Segoe UI", 9, "bold" if s == 0 else "normal"))
        canvas.create_text(self.x, self.top - 18, text="above", fill=MUTED, font=("Segoe UI", 8))
        canvas.create_text(self.x, self.bot + 18, text="below", fill=MUTED, font=("Segoe UI", 8))
        self.err = canvas.create_line(0, 0, 0, 0, fill=SERIES, width=3, state="hidden")
        self.marker = canvas.create_polygon(0, 0, 0, 0, 0, 0, fill=SERIES, outline="white",
                                            state="hidden")
        self.value = canvas.create_text(GAUGE_W // 2, height - 72, fill=INK,
                                        font=("Consolas", 18, "bold"), text="--")
        self.note = canvas.create_text(GAUGE_W // 2, height - 44, fill=MUTED, width=GAUGE_W - 12,
                                       anchor="n", justify="center", font=("Segoe UI", 8),
                                       text="DINO head not trained yet")

    def y(self, s: float) -> float:
        s = max(-10.0, min(10.0, s))
        return self.top + (10.0 - s) / 20.0 * (self.bot - self.top)

    def show(self, score: float | None, sigma: float | None = None, note: str = "") -> None:
        if score is None or not np.isfinite(score):
            for item in (self.marker, self.err):
                self.c.itemconfigure(item, state="hidden")
            self.c.itemconfigure(self.value, text="--")
            self.c.itemconfigure(self.note, text=note)
            return
        y = self.y(score)
        self.c.coords(self.marker, self.x - 26, y - 9, self.x - 26, y + 9, self.x - 8, y)
        self.c.itemconfigure(self.marker, state="normal")
        if sigma is not None:
            self.c.coords(self.err, self.x - 18, self.y(score + sigma), self.x - 18,
                          self.y(score - sigma))
            self.c.itemconfigure(self.err, state="normal")
        self.c.itemconfigure(self.value, text=f"{score:+.1f}")
        self.c.itemconfigure(self.note, text=note)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exposure", type=float, default=30.0, help="ms")
    ap.add_argument("--fps", type=float, default=10.0, help="display / record rate")
    ap.add_argument("--display", type=int, default=800, help="display size, px")
    ap.add_argument("--score-roi", type=int, default=518, help="scored centre crop, px")
    ap.add_argument("--history", type=float, default=30.0, help="trace length, s")
    ap.add_argument("--record", action="store_true", help="write kept frames to --out")
    ap.add_argument("--out", type=Path, default=Path(r"D:\AutoFocus\frames"))
    ap.add_argument("--demo", action="store_true", help="Micro-Manager demo devices, no hardware")
    ap.add_argument("--screenshot", type=Path, default=None,
                    help="save the window to this PNG after ~3 s and exit (layout check)")
    ap.add_argument("--config", type=Path, default=None,
                    help="Micro-Manager config (default: single_cam_red_noDMD_nocom10.cfg; "
                         "single_cam_red_noDMD.cfg also loads the CSU-W1 on COM10)")
    ap.add_argument("--set", nargs=3, action="append", default=[],
                    metavar=("DEVICE", "PROPERTY", "VALUE"),
                    help="set and read back a property before the light goes on; repeatable, "
                         "e.g. --set CSUW1-Bright State 1")
    ap.add_argument("--aura", nargs=2, metavar=("LINE", "PERCENT"), default=None,
                    help="switch an Aura line on, e.g. --aura GREEN 5; switched off on close")
    ap.add_argument("--leave-light-on", action="store_true",
                    help="with --aura, do not switch the Aura off when the window closes")
    ap.add_argument("--piezo", default="COM4",
                    help="piezo controller address for read-only position ('' = don't open)")
    ap.add_argument("--sample", default=None,
                    help="sample ID to continue, e.g. 20260930_1849_1 (default: a new one from "
                         "the clock); 'n' in the window starts the next sample")
    ap.add_argument("--samples-root", type=Path, default=SAMPLES_ROOT,
                    help="where sample folders (map.json, sample.json, track_*.jsonl) live")
    ap.add_argument("--head", type=Path, default=None,
                    help="trained focus head (scripts/train_head.py); needs the uv env (torch)")
    ap.add_argument("--tiles", type=int, default=4, help="224-px tiles scored per frame")
    ap.add_argument("--score-offset", type=float, default=None,
                    help="DoF subtracted from the head's score (overrides the sample's saved "
                         "tare; 'z' in the window tares at the current focus)")
    ap.add_argument("--hole-diameter", type=float, default=None,
                    help="expected chamber diameter, mm (e.g. 6): steadies the circle the edge "
                         "tracker steers by while the followed arc is still short")
    ap.add_argument("--track-speed", type=float, default=100.0,
                    help="edge-tracking pace, um/s (max 1000; +/- keys double/halve it live)")
    args = ap.parse_args()

    import tkinter as tk

    if sys.platform == "win32":  # 1 image px = 1 screen px under display scaling
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)

    core, info = open_core(args.exposure, 0, demo=args.demo, config=args.config)
    info["set"] = []
    for dev, prop, value in args.set:
        rec = set_and_read(core, dev, prop, value)
        if core.hasProperty(dev, "Label"):  # state devices: show what the position is called
            rec["label_read"] = core.getProperty(dev, "Label")
        info["set"].append(rec)
        if not rec["verified"]:
            print(f"WARNING: {dev}.{prop} read back {rec['read']!r}, wanted {value!r}")
    if args.aura and not args.demo:
        info["light"] = aura_on(core, args.aura[0], float(args.aura[1]))
        if not all(r["verified"] for r in info["light"]):
            print("WARNING: an Aura setting did not read back as written")
    core.setCircularBufferMemoryFootprint(2048)  # MB; ~175 full frames of slack
    h, w = core.getImageHeight(), core.getImageWidth()
    # Clip level from the camera's own bit depth: the Kinetix in its 'Standard' readout is
    # 12-bit and clips at 4095, not 65535, although frames arrive as uint16.
    sat_level = 2 ** core.getImageBitDepth() - 1
    info["bit_depth"] = core.getImageBitDepth()

    piezo = None
    if args.piezo and not args.demo:
        try:
            piezo = PiezoReader(args.piezo)
            info["piezo"] = {"address": args.piezo, **piezo.read()}
        except OSError as exc:
            print(f"piezo not read: {exc}")
    info["position"] = positions(core, piezo)
    print(json.dumps({"position": info["position"]}))

    scorer = None
    if args.head is not None:
        from dino_autofocus.live import FocusScorer  # torch; only in the uv env

        scorer = FocusScorer(args.head, k_tiles=args.tiles, saturated=sat_level)
        info["head"] = str(args.head)

    raw = meta = None
    if args.record:
        args.out.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        raw = (args.out / f"video_{stamp}_uint16_{h}x{w}.raw").open("wb")
        meta = (args.out / f"video_{stamp}_meta.jsonl").open("w", encoding="utf-8")
        meta.write(json.dumps({"header": info, "dtype": "uint16", "shape": [h, w],
                               "order": "C", "fps_target": args.fps}, default=str) + "\n")
        print(f"recording to {raw.name}")

    root = tk.Tk()
    root.title("Kinetix_red full sensor -- focus score")
    root.configure(bg="white")
    probe = np.zeros((h, w), np.uint16)
    disp_h, disp_w = bin_for_display(probe, args.display).shape
    scale = disp_w / w
    img_canvas = tk.Canvas(root, width=disp_w, height=disp_h, bg="black", highlightthickness=0)
    img_canvas.grid(row=0, column=0)
    panel = tk.Canvas(root, width=PANEL_W, height=disp_h, bg="white", highlightthickness=0)
    panel.grid(row=0, column=1, sticky="n")
    map_canvas = tk.Canvas(root, width=MAP_W, height=disp_h, bg="white", highlightthickness=0)
    map_canvas.grid(row=0, column=2, sticky="n")
    status = tk.Label(root, font=("Consolas", 10), anchor="w", bg="white", fg=INK)
    status.grid(row=1, column=0, columnspan=3, sticky="we")

    image_item = img_canvas.create_image(0, 0, anchor="nw")
    r = args.score_roi * scale
    cx, cy = disp_w / 2, disp_h / 2
    img_canvas.create_rectangle(cx - r / 2, cy - r / 2, cx + r / 2, cy + r / 2,
                                outline="#eda100", width=2)

    map_canvas.create_text(12, 12, anchor="nw", fill=INK, font=("Segoe UI", 10, "bold"),
                           text="Sample map (stage um)    b: mark edge   u: undo")
    xymap_canvas = tk.Canvas(map_canvas, width=MAP_W - 20, height=MAP_W - 20, bg="white",
                             highlightthickness=0)
    map_canvas.create_window(10, 36, anchor="nw", window=xymap_canvas)
    # One folder per sample; the track inside it is the always-on record of where the stage
    # was and what the frame looked like, at the display rate (numbers only, no pixels).
    header = {**info, "fov_px": [h, w]}
    cur = {"s": Sample(args.sample or new_sample_id(args.samples_root), args.samples_root,
                       xymap_canvas, MAP_W - 20, header)}

    def S() -> Sample:
        return cur["s"]

    pos_text = map_canvas.create_text(12, MAP_W + 22, anchor="nw", fill=INK, justify="left",
                                      font=("Consolas", 10), text="")

    gauge = Gauge(panel, disp_h)
    gauge.show(None, note="no head loaded (--head)" if scorer is None else "starting...")

    # Scoring runs off the UI thread: DINO on a few tiles takes tens of ms on the GPU.
    import threading

    work = {"frame": None, "reading": None, "busy": False, "lock": threading.Lock(),
            "event": threading.Event(), "stop": False, "box_first": True}
    # the orange box: read focus inside it first, the rest of the frame only if it's empty
    box_region = ((h - args.score_roi) // 2, (w - args.score_roi) // 2, args.score_roi)

    def toggle_box(_event=None) -> None:
        work["box_first"] = not work["box_first"]
        st["corr_hist"].clear()
        print("focus read in: " + ("orange box first" if work["box_first"] else "whole frame"))

    root.bind("o", toggle_box)

    def score_loop() -> None:
        while not work["stop"]:
            if not work["event"].wait(0.2):
                continue
            work["event"].clear()
            with work["lock"]:
                frame, work["frame"] = work["frame"], None
            if frame is not None:
                reading = scorer(frame, region=box_region if work["box_first"] else None)
                with work["lock"]:
                    work["reading"] = (time.monotonic(), reading)

    if scorer is not None:
        threading.Thread(target=score_loop, daemon=True).start()
    tile_items: list[int] = []

    def mark(_event=None) -> None:
        x, y, _ = sample_xyz(st["pos"])
        S().map.mark_boundary(x, y)
        print(f"boundary point {len(S().map.boundary)}: x {x:.1f}  y {y:.1f} um")

    def undo(_event=None) -> None:
        S().map.undo_boundary()
        print(f"boundary points: {len(S().map.boundary)}")

    # --- edge tracking: the only part of the live view that moves anything (XY only) ---
    tracker = {"obj": None}

    def track_log(event: dict) -> None:
        S().track.write(json.dumps({"t": round(time.time(), 3), **event}, default=str) + "\n")
        S().track.flush()
        if event.get("event") == "cal_result":  # kept with the sample: it maps pixels to stage
            S().calibration = {k: event[k] for k in ("um_per_px", "angle_deg", "M_px_per_um")}
            S().calibration["objective"] = st.get("objective")
        print(json.dumps(event, default=str))

    def edge_point(x_ti2: float, y_ti2: float) -> None:  # the map is in sum coordinates
        p = st["pos"]
        S().map.mark_boundary(x_ti2 + p.get("piezo_x_um", 0.0), y_ti2 + p.get("piezo_y_um", 0.0))

    def toggle_track(_event=None) -> None:
        tr = tracker["obj"]
        if tr is not None and not tr.done:
            tr.stop("stopped by key")
            return
        if args.demo:
            print("edge tracking needs the real stage")
            return
        from edge_track import EdgeTracker

        tracker["obj"] = EdgeTracker(core, (h, w), core.getPixelSizeUm(), core.getExposure(),
                                     track_log, on_point=edge_point,
                                     speed_um_s=st.get("track_speed", args.track_speed),
                                     expect_diameter_um=(args.hole_diameter or 0) * 1000)

    def faster(_event=None, factor=2.0) -> None:
        st["track_speed"] = min(st.get("track_speed", args.track_speed) * factor, 1000.0)
        st["track_speed"] = max(st["track_speed"], 10.0)
        if tracker["obj"] is not None and not tracker["obj"].done:
            tracker["obj"].set_speed(st["track_speed"])
        print(f"edge-tracking speed {st['track_speed']:.0f} um/s")

    servo = {"obj": None}

    def toggle_servo(_event=None) -> None:
        sv = servo["obj"]
        if sv is not None and not sv.done:
            sv.stop("stopped by key")
            return
        if piezo is None or scorer is None:
            print("focus servo needs the piezo (COM4) and a focus head (--head)")
            return
        if tracker["obj"] is not None and not tracker["obj"].done:
            print("stop edge tracking first")
            return
        from focus_servo import FocusServo

        def read_z() -> float:
            return float(piezo.read()["piezo_z_um"])

        servo["obj"] = FocusServo(piezo.move_z, read_z, track_log)
        print("focus servo started")

    sweep = {"obj": None}

    def toggle_sweep(_event=None, full: bool = False) -> None:
        """'w': autofocus near here (Vollath peak, DINO for direction when far out);
        'W': the diagnostic sweep, +-5 um around here at 0.25 um."""
        sw = sweep["obj"]
        if sw is not None and not sw.done:
            sw.stop("stopped by key")
            return
        if piezo is None or scorer is None:
            print("piezo focus needs the piezo (COM4) and a focus head (--head)")
            return
        if any(o["obj"] is not None and not o["obj"].done for o in (tracker, servo)):
            print("stop edge tracking / focus servo first")
            return
        from focus_servo import AutoFocusZ, ZSweep

        kind = "zsweep" if full else "autofocus"
        out = S().dir / f"{kind}_{time.strftime('%Y%m%d-%H%M%S')}.json"
        read_z = lambda: float(piezo.read()["piezo_z_um"])  # noqa: E731
        try:
            cls = ZSweep if full else AutoFocusZ
            sweep["obj"] = cls(piezo.move_z, read_z, track_log, out)
            # hands-off reference: the stand's own focus and XY must stay put meanwhile
            sweep["ref"] = {k: st["pos"].get(k) for k in ("x_um", "y_um", "z_um")}
        except Exception as exc:  # noqa: BLE001 - say why on screen; nothing has moved
            print(f"{kind} not started: {exc}")
            track_log({"event": f"{kind}_refused", "why": str(exc)})
            return
        print(f"{kind} started -> {out}")

    def stop_track(_event=None) -> None:
        for o in (tracker, servo, sweep):
            if o["obj"] is not None:
                o["obj"].stop("stopped by Esc")

    def next_sample(_event=None) -> None:
        if tracker["obj"] is not None and not tracker["obj"].done:
            print("stop edge tracking before starting a new sample")
            return
        S().close()
        cur["s"] = Sample(new_sample_id(args.samples_root), args.samples_root, xymap_canvas,
                          MAP_W - 20, header)

    root.bind("b", mark)
    root.bind("u", undo)
    root.bind("n", next_sample)
    root.bind("t", toggle_track)
    root.bind("f", toggle_servo)
    root.bind("w", toggle_sweep)
    root.bind("W", lambda e: toggle_sweep(e, full=True))
    root.bind("<Escape>", stop_track)
    for key in ("+", "=", "<KP_Add>"):
        root.bind(key, faster)
    for key in ("-", "<KP_Subtract>"):
        root.bind(key, lambda e: faster(e, 0.5))
    panel.create_line(GAUGE_W, 10, GAUGE_W, disp_h - 10, fill=GRID)
    cap = max(int(args.history * args.fps), 2)
    rows = (disp_h - 20) // 2
    t_sharp = Trace(panel, 10, rows, f"Sharpness, centre {args.score_roi} px",
                    "{:.4g}", left=GAUGE_W + 12)
    t_z = Trace(panel, 10 + rows, rows, "z_sum = ZDrive + piezo z (um)", "{:.3f}",
                left=GAUGE_W + 12)
    sharp_hist, z_hist = deque(maxlen=cap), deque(maxlen=cap)

    st = {"photo": None, "next_ms": None, "kept": 0, "seen": 0, "t0": time.monotonic(),
          "pos": positions(core, piezo), "pos_t": time.monotonic(), "latest": None,
          "map_t": 0.0, "save_t": time.monotonic(), "score": None,
          "objective": info.get("objective") or "?", "fov_um": w * (info["pixel_um"] or 0.0),
          "raw_hist": deque(maxlen=200), "corr_hist": deque(maxlen=5), "score_raw": None}

    def score_offset() -> float:
        if args.score_offset is not None:
            return args.score_offset
        return float(S().offsets.get(st["objective"], 0.0))

    def tare(_event=None) -> None:
        """'z': the image is in focus now -- take the median raw score of the last 2 s as 0."""
        now = time.monotonic()
        recent = [s for t, s in st["raw_hist"] if now - t < 2.0]
        if len(recent) < 3:
            print("tare: fewer than 3 readings in the last 2 s; nothing changed")
            return
        off = float(np.median(recent))
        S().offsets[st["objective"]] = round(off, 3)
        st["corr_hist"].clear()
        S().save()
        S().track.write(json.dumps({"t": round(time.time(), 3), "event": "score_tare",
                                    "objective": st["objective"], "offset_dof": off,
                                    "n_readings": len(recent),
                                    "z_sum_um": sample_xyz(st["pos"])[2]}) + "\n")
        print(f"tare: {st['objective']}: offset {off:+.2f} DoF from {len(recent)} readings")

    def clear_tare(_event=None) -> None:
        S().offsets.pop(st["objective"], None)
        st["corr_hist"].clear()
        S().save()
        print(f"tare cleared for {st['objective']}")

    root.bind("z", tare)
    root.bind("Z", clear_tare)
    period_ms = 1000.0 / args.fps

    def handle(img: np.ndarray, md) -> None:
        if time.monotonic() - st["pos_t"] > 0.5:
            st["pos"], st["pos_t"] = positions(core, piezo), time.monotonic()
        st["kept"] += 1
        st["latest"] = img
        if raw is not None:
            raw.write(img.tobytes())
            meta.write(json.dumps({"n": st["kept"] - 1, "ImageNumber": md.get("ImageNumber", None),
                                   "ElapsedTime-ms": md.get("ElapsedTime-ms", None),
                                   "host_t": time.time(), **st["pos"]}) + "\n")

    def tick() -> None:
        while core.getRemainingImageCount():
            img, md = core.popNextImageAndMD()
            st["seen"] += 1
            try:
                t_ms = float(md.get("ElapsedTime-ms", None))
            except (TypeError, ValueError):
                t_ms = (time.monotonic() - st["t0"]) * 1000.0
            if st["next_ms"] is None or t_ms >= st["next_ms"]:
                due = t_ms if st["next_ms"] is None else st["next_ms"]
                # fell behind by more than a period: resync instead of bursting
                st["next_ms"] = due + period_ms if due + period_ms > t_ms else t_ms + period_ms
                handle(np.asarray(img, dtype=np.uint16), md)

        img = st.pop("latest", None)
        st["latest"] = None
        if img is not None:
            g = bin_for_display(img, args.display)
            st["photo"] = tk.PhotoImage(data=b"P5 %d %d 255\n" % g.shape[::-1] + g.tobytes(),
                                        format="PPM")
            img_canvas.itemconfigure(image_item, image=st["photo"])

            tr = tracker["obj"]
            if tr is not None and not tr.done:
                tr.feed(img)
            if args.demo:  # exercise the gauge; not a measurement
                s = 8.0 * math.sin((time.monotonic() - st["t0"]) / 3.0)
                gauge.show(s, 0.8, "demo value, not a measurement")
            if scorer is not None:
                with work["lock"]:
                    work["frame"] = img  # newest frame wins; the scorer never queues up
                    got, work["reading"] = work["reading"], None
                work["event"].set()
                if got is not None:
                    t_read, rd = got
                    off = score_offset()
                    st["score_raw"] = rd.score
                    sv = servo["obj"]
                    if sv is not None and not sv.done:
                        sv.feed(t_read, None if rd.score is None else rd.score - off)
                    sw = sweep["obj"]
                    if sw is not None and not sw.done:
                        sw.feed_dino(t_read, None if rd.score is None else rd.score - off)
                    if rd.score is not None:
                        st["raw_hist"].append((t_read, rd.score))
                        st["corr_hist"].append(rd.score - off)
                        # the gauge shows the median of the last 5 readings: one frame's
                        # score scatters by ~1 DoF, the median of five by much less
                        st["score"] = float(np.median(st["corr_hist"]))
                    else:
                        st["score"] = None
                        st["corr_hist"].clear()
                    note = (f"{rd.where}: {rd.n_used}/{len(rd.tiles)} tiles"
                            + ("" if rd.sign_known or rd.score is None else ", sign unsure")
                            + (f", offset {off:+.1f}" if off else ""))
                    gauge.show(st["score"], rd.sigma,
                               note if rd.score is not None else "no readable sample in view")
                    for it in tile_items:
                        img_canvas.delete(it)
                    tile_items.clear()
                    for t in rd.tiles:
                        x0, y0 = t.x0 * scale, t.y0 * scale
                        x1, y1 = (t.x0 + scorer.tile) * scale, (t.y0 + scorer.tile) * scale
                        ok = t.p_valid >= 0.5
                        tile_items.append(img_canvas.create_rectangle(
                            x0, y0, x1, y1, outline=SERIES if ok else MUTED, width=2,
                            dash=() if ok else (3, 3)))
                        tile_items.append(img_canvas.create_text(
                            x0 + 3, y0 + 2, anchor="nw", fill="white",
                            font=("Consolas", 9, "bold"),
                            text=f"{t.dz - off:+.1f}" if ok else "?"))
            box = centre_crop(img, args.score_roi)
            sharp_hist.append(brenner(box))
            sw = sweep["obj"]
            if sw is not None and not sw.done:
                ref, p_now = sweep.get("ref", {}), st["pos"]
                moved = [(k, p_now[k] - ref[k]) for k in ("z_um", "x_um", "y_um")
                         if ref.get(k) is not None and p_now.get(k) is not None
                         and abs(p_now[k] - ref[k]) > (0.3 if k == "z_um" else 2.0)]
                if moved:
                    k, dv = moved[0]
                    sw.stop(f"{'ZDrive' if k == 'z_um' else 'XY stage'} moved by hand "
                            f"({dv:+.2f} um) during the run")
            if sw is not None and not sw.done:
                sw.feed_frame(time.monotonic(), {"vollath": vollath4(box), "brenner": sharp_hist[-1],
                                                 "box_mean": float(box.mean()),
                                                 "box_max": float(box.max())})
            z_hist.append(sample_xyz(st["pos"])[2])
            t_sharp.draw(sharp_hist, cap)
            t_z.draw(z_hist, cap)

            el = time.monotonic() - st["t0"]
            sat = float(np.mean(img >= sat_level)) * 100
            p = st["pos"]
            sx, sy, sz = sample_xyz(p)
            if time.monotonic() - st["map_t"] > 0.5:
                # the turret can change by hand or by --set: re-read what is in the path
                try:
                    st["objective"] = core.getProperty("Nosepiece", "Label")
                    st["fov_um"] = w * core.getPixelSizeUm()
                except Exception:  # noqa: BLE001 - demo config has no Nosepiece
                    pass
                objective, fov_um = st["objective"], st["fov_um"]
                S().objectives.add(objective)
                S().map.add(sx, sy, fov_um, objective, st["score"], sharp_hist[-1])
                S().map.draw(sx, sy, fov_um)
                lim = S().map.limits()
                nan = float("nan")
                lines = [
                    f"{'um':<6} {'x':>10} {'y':>10} {'z':>10}",
                    f"{'Ti2':<6} {p.get('x_um', nan):10.2f} {p.get('y_um', nan):10.2f} "
                    f"{p.get('z_um', nan):10.3f}",
                    f"{'piezo':<6} {p.get('piezo_x_um', nan):10.3f} "
                    f"{p.get('piezo_y_um', nan):10.3f} {p.get('piezo_z_um', nan):10.3f}",
                    f"{'sum':<6} {sx:10.2f} {sy:10.2f} {sz:10.3f}",
                    "",
                    f"sample {S().id}   (n: new sample)",
                    f"{objective}",
                    f"field {fov_um:.1f} um   map: {len(S().map.visits)} fields",
                ]
                if lim is not None:
                    lines += [f"boundary x {lim[0]:.0f} .. {lim[1]:.0f}",
                              f"         y {lim[2]:.0f} .. {lim[3]:.0f}"]
                circ = S().map.circle()
                if circ is not None:
                    d_here = math.hypot(sx - circ[0], sy - circ[1])
                    lines += [f"hole   centre {circ[0]:.0f}, {circ[1]:.0f}",
                              f"       d {2 * circ[2] / 1000:.3f} mm  rms {circ[3]:.0f} um"
                              f"  ({len(S().map.boundary)} pts)",
                              f"here   {d_here:.0f} um from centre",
                              f"       {circ[2] - d_here:.0f} um inside the edge"]
                if piezo is None:
                    lines.append("(piezo not read)")
                tr = tracker["obj"]
                lines += ["", "t: track edge  Esc: stop  +/-: speed" if tr is None else
                          f"edge track: {tr.status}"]
                if scorer is not None:
                    lines.append(f"z: tare focus here  Z: clear   (offset {score_offset():+.2f})")
                    sv = servo["obj"]
                    lines.append("f: piezo to score 0" if sv is None else f"piezo: {sv.status}")
                    sw = sweep["obj"]
                    lines.append("w: autofocus (piezo)  W: full z sweep" if sw is None
                                 else f"piezo focus: {sw.status}")
                    lines.append("o: read focus in " + ("whole frame" if work["box_first"]
                                                         else "orange box first"))
                map_canvas.itemconfigure(pos_text, text="\n".join(lines))
                st["map_t"] = time.monotonic()
            if time.monotonic() - st["save_t"] > 10:
                S().save()
                st["save_t"] = time.monotonic()
            S().track.write(json.dumps({"t": round(time.time(), 3), **p,
                                    "sample_um": [sx, sy, sz], "score": st["score"],
                                    "score_raw": st.get("score_raw"),
                                    "score_offset": score_offset() if scorer else None,
                                    "sharpness": round(sharp_hist[-1], 6),
                                    "mean": round(float(img.mean()), 1), "max": int(img.max()),
                                    "sat_pct": round(sat, 3)}, default=str) + "\n")
            status.configure(text=(
                f" shown {st['kept'] / el:4.1f} fps (camera {st['seen'] / el:4.1f})   "
                f"mean {img.mean():7.0f}  max {img.max():5d}  sat {sat:5.2f}%   "
                f"x {p.get('x_um', float('nan')):.2f}  y {p.get('y_um', float('nan')):.2f}  "
                f"z {p.get('z_um', float('nan')):.3f} um"
                + ("   REC" if raw is not None else "")))
        root.after(10, tick)

    if args.screenshot is not None:
        def snap_window() -> None:
            from PIL import ImageGrab  # only needed for the layout check

            root.update()
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(
                args.screenshot)
            root.destroy()

        root.after(3000, snap_window)

    core.startContinuousSequenceAcquisition(0.0)
    try:
        root.after(10, tick)
        root.mainloop()
    finally:
        if tracker["obj"] is not None:
            tracker["obj"].stop("window closed")
        for o in (servo, sweep):
            if o["obj"] is not None:
                o["obj"].stop("window closed")
        if core.isSequenceRunning():
            core.stopSequenceAcquisition()
        work["stop"] = True
        if args.aura and not args.demo and not args.leave_light_on:
            aura_off(core)  # don't keep bleaching the sample after the view is gone
        S().close()
        if piezo is not None:
            piezo.close()
        if raw is not None:
            raw.close()
            meta.close()
            print(f"recorded {st['kept']} frames")


if __name__ == "__main__":
    main()
