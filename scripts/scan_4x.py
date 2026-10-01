"""4x tile scan of a sample: every tile autofocused, xyz + in-focus frame recorded.

    python scripts/scan_4x.py --sample 20260930_1849_1            # hole + 0.5 mm margin
    python scripts/scan_4x.py --sample 20260930_1849_1 --dry-run  # print the plan only

Runs on the system Python (pymmcore-plus, cv2), like mm_grab. Plots: scripts/plot_scan.py.

Motion, and what guards it:
  * Z: ZDrive only, through agentic_microscope's FocusAxis (allow_motion, PFS off,
    ceiling = SAMPLE_Z_WINDOW_UM top, every sweep ascends, readback-verified). 4x has
    20 mm of free WD, so the 2800..3200 window is the binding bound.
  * XY: absolute XYStage moves to grid points, refused outside the scan box + 1 mm.
  * Light: Aura line on at the start, off in `finally` (also on Ctrl+C).
  * Nosepiece: read only; the run refuses unless it is on 4x.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r"C:\agentic_microscope")
from mm_grab import aura_off, aura_on, open_core, vollath4  # noqa: E402

SAMPLES_ROOT = Path(r"D:\AutoFocus\samples")
XY = "XYStage"
OBJECTIVE_4X = "1-Plan Apo LmbdD20 4x"
BLOCKS = 6  # per-tile sub-regions per side for the local z map


def grid(centre, half_side_um: float, fov_um: float, overlap: float):
    """Serpentine tile centres covering a square of half-side `half_side_um`."""
    pitch = fov_um * (1 - overlap)
    n = max(1, math.ceil((2 * half_side_um - fov_um) / pitch) + 1)
    offs = (np.arange(n) - (n - 1) / 2) * pitch
    pts = []
    for r, dy in enumerate(offs):
        row = [(centre[0] + dx, centre[1] + dy, r, c) for c, dx in enumerate(offs)]
        pts += row if r % 2 == 0 else row[::-1]
    return pts, pitch, n


def block_scores(img: np.ndarray, n: int = BLOCKS) -> list[float]:
    h, w = img.shape[0] // n, img.shape[1] // n
    return [vollath4(img[i * h:(i + 1) * h, j * w:(j + 1) * w])
            for i in range(n) for j in range(n)]


def parabola_peak(z: np.ndarray, s: np.ndarray) -> float | None:
    """Three-point parabola through the argmax; None if the max sits on an end."""
    o = np.argsort(z)
    z, s = z[o], s[o]
    i = int(np.argmax(s))
    if i == 0 or i == len(s) - 1:
        return None
    z0, z1, z2 = z[i - 1:i + 2]
    s0, s1, s2 = s[i - 1:i + 2]
    den = (z0 - z1) * (z0 - z2) * (z1 - z2)
    a = (z2 * (s1 - s0) + z1 * (s0 - s2) + z0 * (s2 - s1)) / den
    b = (z2**2 * (s0 - s1) + z1**2 * (s2 - s0) + z0**2 * (s1 - s2)) / den
    if a >= 0:
        return float(z1)
    return float(np.clip(-b / (2 * a), z0, z2))


class Preview:
    """Tk window refreshed from the scan loop itself (no mainloop): each grabbed frame,
    binned and percentile-stretched, plus the current tile's sharpness-vs-z curve."""

    def __init__(self, size: int = 700, plot_h: int = 180):
        import tkinter as tk

        self.tk, self.size, self.plot_h = tk, size, plot_h
        self.root = tk.Tk()
        self.root.title("scan_4x preview")
        self.canvas = tk.Canvas(self.root, width=size, height=size + plot_h, bg="white")
        self.canvas.pack()
        self.label = tk.Label(self.root, font=("Consolas", 11), anchor="w", justify="left")
        self.label.pack(fill="x")
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self.photo, self.curve, self.tile = None, [], ""
        self.closed = False
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.update()

    def _close(self):  # closing the window hides the preview; the scan carries on
        self.closed = True
        self.root.destroy()

    def new_tile(self, name: str) -> None:
        self.tile, self.curve = name, []

    def show(self, img: np.ndarray, text: str, z: float | None = None,
             sharp: float | None = None) -> None:
        if self.closed:
            return
        k = max(1, math.ceil(max(img.shape) / self.size))
        h, w = (img.shape[0] // k) * k, (img.shape[1] // k) * k
        small = img[:h, :w].reshape(h // k, k, w // k, k).mean(axis=(1, 3), dtype=np.float32)
        lo, hi = np.percentile(small[::2, ::2], (0.5, 99.8))
        g = np.clip((small - lo) * (255.0 / max(hi - lo, 1.0)), 0, 255).astype(np.uint8)
        self.photo = self.tk.PhotoImage(data=b"P5 %d %d 255\n" % g.shape[::-1] + g.tobytes(),
                                        format="PPM")
        self.canvas.itemconfigure(self.item, image=self.photo)
        if z is not None and sharp is not None:
            self.curve.append((z, sharp))
        self._plot()
        self.label.configure(text=text)
        self.root.update()

    def _plot(self) -> None:
        c, top, W, H = self.canvas, self.size, self.size, self.plot_h
        c.delete("plot")
        c.create_text(8, top + 4, anchor="nw", tags="plot", fill="#52514e",
                      text=f"{self.tile}: Vollath F4 vs ZDrive (um)")
        if len(self.curve) < 2:
            return
        z = np.array([p[0] for p in self.curve])
        v = np.array([p[1] for p in self.curve])
        zl, zh = z.min(), max(z.max(), z.min() + 1)
        vl, vh = v.min(), max(v.max(), v.min() + 1e-9)
        px = 40 + (z - zl) / (zh - zl) * (W - 60)
        py = top + H - 20 - (v - vl) / (vh - vl) * (H - 45)
        for x, y in zip(px, py):
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#2a78d6", outline="", tags="plot")
        c.create_text(40, top + H - 4, anchor="sw", text=f"{zl:.0f}", tags="plot")
        c.create_text(W - 20, top + H - 4, anchor="se", text=f"{zh:.0f}", tags="plot")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--margin", type=float, default=500.0, help="um around the hole")
    ap.add_argument("--overlap", type=float, default=0.15)
    ap.add_argument("--exposure", type=float, default=None, help="ms; default: auto")
    ap.add_argument("--aura", nargs=2, metavar=("LINE", "PERCENT"), default=["GREEN", "1"])
    ap.add_argument("--z-guess", type=float, default=None,
                    help="ZDrive um to centre the first search on (default: the current Z if "
                         "inside 2800..3200, e.g. where brightfield was focused; else 2960)")
    ap.add_argument("--first-half-range", type=float, default=160.0)
    ap.add_argument("--tile-half-range", type=float, default=50.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-preview", action="store_true", help="no live preview window")
    args = ap.parse_args()

    sdir = SAMPLES_ROOT / args.sample
    sinfo = json.loads((sdir / "sample.json").read_text())
    hole = sinfo["hole"]
    centre = hole["centre_um"]
    half = hole["diameter_mm"] * 500 + args.margin
    cal = sinfo.get("stage_camera_calibration") or {}
    um_px = float(cal.get("um_per_px", 1.625))
    core, info = open_core(args.exposure or 30.0, 0)
    w, h = core.getImageWidth(), core.getImageHeight()
    fov = min(w, h) * um_px
    tiles, pitch, n = grid(centre, half, fov, args.overlap)
    box = (centre[0] - half - 1000, centre[0] + half + 1000,
           centre[1] - half - 1000, centre[1] + half + 1000)
    print(f"scan: {n} x {n} tiles, FOV {fov:.0f} um, pitch {pitch:.0f} um, "
          f"square {2 * half:.0f} um about ({centre[0]:.0f}, {centre[1]:.0f})")
    for x, y, r, c in tiles:
        print(f"  tile r{r}c{c}: x {x:9.1f}  y {y:9.1f}")

    label = core.getProperty("Nosepiece", "Label")
    if label != OBJECTIVE_4X:
        raise SystemExit(f"Nosepiece reads {label!r}, not {OBJECTIVE_4X!r}; refusing")

    from hardware.focus import FocusAxis, best_z_um

    axis = FocusAxis(core, "4x", allow_motion=True, dry_run=args.dry_run)
    if args.z_guess is None:
        z_now = axis.position_um()
        args.z_guess = z_now if 2800.0 <= z_now <= 3200.0 else 2960.0
    print(f"first focus search centred on ZDrive {args.z_guess:.1f} um")
    if args.dry_run:
        print(axis.plan(args.z_guess, args.first_half_range, 10.0).describe())
        return

    out = sdir / f"scan4x_{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True)
    rec = {"sample": args.sample, "started": datetime.now().isoformat(timespec="seconds"),
           "header": info, "objective": label, "um_per_px": um_px, "fov_um": fov,
           "pitch_um": pitch, "grid_n": n, "hole": hole, "margin_um": args.margin,
           "coordinates": "x/y = XYStage readback at the tile centre; z = ZDrive (um)",
           "tiles": []}

    def save():
        (out / "scan.json").write_text(json.dumps(rec, indent=1, default=str))

    ceiling = 2 ** core.getImageBitDepth() - 1  # 4095 in the 100MHz 12-bit readout
    rec["camera_ceiling_adu"] = ceiling
    preview = None if args.no_preview else Preview()
    cur = {"tile": "", "k": 0}

    def grab():
        core.snapImage()
        img = np.asarray(core.getImage(), dtype=np.uint16)
        if preview is not None:
            z = axis.position_um()
            v = vollath4(img)
            preview.show(img, f"{cur['tile']}  ({cur['k'] + 1}/{len(tiles)})   "
                              f"ZDrive {z:8.2f} um   Vollath {v:7.4f}   "
                              f"max {int(img.max())}/{ceiling}   exp {core.getExposure():.0f} ms",
                         z, v)
        return img

    def score(frame):
        sat = float(np.mean(frame >= ceiling))
        return {"sharp": vollath4(frame), "blocks": block_scores(frame),
                "mean": float(frame.mean()), "p999": float(np.percentile(frame, 99.9)),
                "saturated_frac": sat}

    def goto_xy(x, y):
        if not (box[0] <= x <= box[1] and box[2] <= y <= box[3]):
            raise RuntimeError(f"XY ({x:.0f}, {y:.0f}) outside the scan box {box}")
        core.setXYPosition(XY, float(x), float(y))
        core.waitForDevice(XY)
        time.sleep(0.2)
        return core.getXYPosition(XY)

    def sweep_pair(z_centre, half_range, coarse_step, fine_half, fine_step):
        coarse = axis.sweep(axis.plan(z_centre, half_range, coarse_step), grab,
                            score=score, settle_s=0.1)
        fine = None
        if coarse.peak_interior:
            fine = axis.sweep(axis.plan(coarse.peak_z_um, fine_half, fine_step), grab,
                              score=score, settle_s=0.2)
        return coarse, fine

    lights = []
    try:
        axis.require_pfs_quiet(disable=True)
        lights = aura_on(core, args.aura[0], float(args.aura[1]))
        rec["light"] = lights

        x0, y0, *_ = tiles[0]
        goto_xy(x0, y0)
        if args.exposure is None:  # brightest 0.1 % at ~50 % of the camera's ceiling
            axis.move_to(min(args.z_guess, 3200.0),
                         allow_ascent_um=max(0.0, args.z_guess - axis.position_um()) + 0.5)
            for _ in range(6):
                p = float(np.percentile(grab(), 99.9))
                f = float(np.clip(0.5 * ceiling / max(p, 1.0), 0.25, 4.0))
                if 0.7 < f < 1.4:
                    break
                core.setExposure(float(np.clip(core.getExposure() * f, 1.0, 2000.0)))
            print(f"exposure {core.getExposure():.1f} ms (p99.9 {p:.0f} ADU)")
        rec["exposure_ms"] = core.getExposure()

        z_ref, first = args.z_guess, True
        for k, (x, y, r, c) in enumerate(tiles):
            t0 = time.monotonic()
            cur.update(tile=f"tile_r{r}c{c}", k=k)
            if preview is not None:
                preview.new_tile(cur["tile"])
            xr, yr = goto_xy(x, y)
            hr = args.first_half_range if first else args.tile_half_range
            coarse, fine = sweep_pair(z_ref, hr, 10.0 if first else 6.0, 12.0, 2.0)
            zf, why = best_z_um(coarse, fine)
            if zf is None and not first:  # widen once before giving up on the tile
                coarse, fine = sweep_pair(z_ref, args.first_half_range, 10.0, 12.0, 2.0)
                zf, why = best_z_um(coarse, fine)
            # A frame whose mean is >2 % off the sweep's median is a light dropout, not a
            # focus change (2026-09-30: one fine frame at -23 % read 2.7x sharper than the
            # rest and became the "peak"). Drop such frames and re-take the fine peak.
            pts_all = coarse.points + (fine.points if fine else [])
            med = float(np.median([p.diagnostics["mean"] for p in pts_all]))
            pts = [p for p in pts_all if abs(p.diagnostics["mean"] - med) <= 0.02 * med]
            dropped = [round(p.z_readback_um, 2) for p in pts_all if p not in pts]
            if dropped and fine is not None:
                fp = [p for p in fine.points if p in pts]
                zc = parabola_peak(np.array([p.z_readback_um for p in fp]),
                                   np.array([p.score for p in fp])) if len(fp) >= 3 else None
                if zc is not None:
                    zf, why = zc, f"fine pass without light-dropout frames at {dropped}"
            zs = np.array([p.z_readback_um for p in pts])
            bz = []
            for b in range(BLOCKS * BLOCKS):
                bz.append(parabola_peak(zs, np.array([p.diagnostics["blocks"][b] for p in pts])))
            z_img = zf if zf is not None else z_ref
            z_landed = axis.park_at(min(z_img, 3200.0))
            img = grab()
            name = f"tile_r{r}c{c}"
            np.save(out / f"{name}.npy", img)
            t = {"name": name, "row": r, "col": c, "x_cmd_um": x, "y_cmd_um": y,
                 "x_um": round(xr, 2), "y_um": round(yr, 2),
                 "z_focus_um": None if zf is None else round(zf, 3), "focus_note": why,
                 "z_image_um": round(z_landed, 3),
                 "block_z_um": [None if v is None else round(v, 2) for v in bz],
                 "blocks_per_side": BLOCKS,
                 "dropout_z_um": dropped,
                 "curve": [{"z": round(p.z_readback_um, 3), "sharp": round(p.score, 5),
                            "mean": round(p.diagnostics["mean"], 1),
                            "sat": p.diagnostics["saturated_frac"]} for p in pts_all],
                 "frame_mean": float(img.mean()), "frame_max": int(img.max()),
                 "seconds": round(time.monotonic() - t0, 1)}
            rec["tiles"].append(t)
            save()
            print(json.dumps({"tile": name, "x": t["x_um"], "y": t["y_um"],
                              "z_focus": t["z_focus_um"], "note": why, "s": t["seconds"]}))
            if zf is not None:
                z_ref, first = zf, False
        rec["finished"] = datetime.now().isoformat(timespec="seconds")
    finally:
        if lights:
            rec["light_off"] = aura_off(core)
        rec["z_end_um"] = axis.position_um()
        save()
        print(f"scan record: {out / 'scan.json'}")


if __name__ == "__main__":
    main()
