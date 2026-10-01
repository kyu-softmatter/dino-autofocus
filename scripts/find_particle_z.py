"""Find a particle whose focus lies in a Z band, searching 100x fields in a spiral.

    python scripts/find_particle_z.py --band 3004 3015 --stack 2984 3022

Per field: one ascending ZDrive stack (FocusAxis: PFS off, ceiling, readback), frames
8x8-binned. A spot counts when its brightness peaks *inside* the band and well inside the
stack: a particle resting lower only fades as Z rises, so its maximum sits at the stack's
bottom end and is rejected. The best hit is centred (pixel -> stage through the sample's
stage-camera calibration signs) and Z is parked at its peak. XY stays inside the hole.
Light off on exit.
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
from mm_grab import aura_off, aura_on, open_core, positions  # noqa: E402
from scan_4x import Preview  # noqa: E402

OBJECTIVE_100X = "6-Plan Apo LmbdD0.13 100x Oil"
XY = "XYStage"
BIN = 8


def spiral(n: int):
    """(i, j) offsets of a square spiral starting at (0, 0)."""
    i = j = 0
    yield 0, 0
    k, step = 1, 1
    while k < n:
        for di, dj, reps in ((0, 1, step), (1, 0, step), (0, -1, step + 1), (-1, 0, step + 1)):
            for _ in range(reps):
                i, j = i + di, j + dj
                yield i, j
                k += 1
                if k >= n:
                    return
        step += 2


def binned(f: np.ndarray) -> np.ndarray:
    h, w = (f.shape[0] // BIN) * BIN, (f.shape[1] // BIN) * BIN
    return f[:h, :w].reshape(h // BIN, BIN, w // BIN, BIN).mean(axis=(1, 3), dtype=np.float32)


def find_hits(stack: np.ndarray, zs: np.ndarray, band, min_snr: float = 8.0, margin: float = 3.0,
              min_peak: float = 300.0, particle_um: float = 7.0, pixel_um: float = 0.065,
              ring_frac: float = 0.6, falloff_um: float = 3.0):
    """stack (nz, H, W) binned frames -> list of hits sorted by brightness."""
    bg = np.median(stack, axis=(1, 2), keepdims=True)
    a = stack - bg
    noise = 1.4826 * np.median(np.abs(a - np.median(a)))
    k = np.argmax(a, axis=0)
    peak = np.take_along_axis(a, k[None], 0)[0]
    zpk = zs[k]
    ok = ((peak > min_snr * max(noise, 1.0)) & (peak > min_peak)
          & (zpk >= band[0]) & (zpk <= band[1])
          & (zpk >= zs[0] + margin) & (zpk <= zs[-1] - margin))
    # a real focus has fallen off on both sides (falloff_um away, whatever the step); a tail
    # does not
    dk = max(1, int(round(falloff_um / abs(zs[1] - zs[0]))))
    lo = np.take_along_axis(a, np.clip(k - dk, 0, len(zs) - 1)[None], 0)[0]
    hi = np.take_along_axis(a, np.clip(k + dk, 0, len(zs) - 1)[None], 0)[0]
    ok &= (lo < 0.7 * peak) & (hi < 0.7 * peak)
    diag = {"n_band_px": int(ok.sum()),
            "max_band_peak": round(float(peak[ok].max()), 1) if ok.any() else None}
    hits = []
    taken = np.zeros_like(ok)
    for idx in np.argsort(np.where(ok, peak, -1), axis=None)[::-1]:
        r, c = np.unravel_index(idx, ok.shape)
        if not ok[r, c]:
            break
        if taken[max(r - 4, 0):r + 5, max(c - 4, 0):c + 5].any():
            continue  # same particle as a brighter hit
        # compact spot, not a piece of a lower particle's defocus ring: at the peak z, all
        # 8 points ring_r bins away must be well below it (a ring arc has bright neighbours
        # along itself, and every pixel on an expanding ring peaks "inside" the stack)
        fr = a[int(k[r, c])]
        # test just outside the particle's own radius (2026-09-30: the particles are ~6.7 um
        # across at FWHM, so a 1.6 um test radius sat inside the particle and rejected it)
        r_in = (particle_um / 2 + 1.0) / (pixel_um * BIN)
        nb = []
        for rad in (r_in, r_in + 1.0 / (pixel_um * BIN)):  # 16 directions, two radii
            for t in np.arange(16) * (np.pi / 8):
                rr, cc = int(round(r + rad * np.sin(t))), int(round(c + rad * np.cos(t)))
                if 0 <= rr < fr.shape[0] and 0 <= cc < fr.shape[1]:
                    nb.append(fr[rr, cc])
        if len(nb) < 32 or max(nb) > ring_frac * peak[r, c]:
            continue
        taken[r, c] = True
        # sub-step z: parabola on this pixel's own profile
        kk = int(k[r, c])
        z = float(zs[kk])
        if 0 < kk < len(zs) - 1:
            y0, y1, y2 = a[kk - 1, r, c], a[kk, r, c], a[kk + 1, r, c]
            den = y0 - 2 * y1 + y2
            if den < 0:
                z += 0.5 * (y0 - y2) / den * (zs[1] - zs[0])
        hits.append({"row_px": int(r * BIN + BIN // 2), "col_px": int(c * BIN + BIN // 2),
                     "z_um": round(z, 2), "peak_adu": round(float(peak[r, c]), 1),
                     "snr": round(float(peak[r, c] / max(noise, 1.0)), 1)})
    return hits, float(noise), diag


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", nargs=2, type=float, default=[3004.0, 3015.0])
    ap.add_argument("--stack", nargs=2, type=float, default=[2984.0, 3022.0])
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--exposure", type=float, default=20.0)
    ap.add_argument("--aura", nargs=2, default=["GREEN", "1"])
    ap.add_argument("--pitch", type=float, default=150.0, help="um between fields")
    ap.add_argument("--max-fields", type=int, default=25)
    ap.add_argument("--sample", default="20260930_1849_1")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--particle-um", type=float, default=7.0,
                    help="particle diameter (FWHM, um); sets the compact-spot test radius")
    args = ap.parse_args()

    sdir = Path(r"D:\AutoFocus\samples") / args.sample
    sinfo = json.loads((sdir / "sample.json").read_text())
    hole_c = np.array(sinfo["hole"]["centre_um"])
    hole_r = sinfo["hole"]["diameter_mm"] * 500
    M = np.array(sinfo["stage_camera_calibration"]["M_px_per_um"])
    sx = -1.0 if M[0, 0] > 0 else 1.0  # stage x per +column, sign
    sy = 1.0 if M[1, 1] < 0 else -1.0  # stage y per +row, sign

    core, info = open_core(args.exposure, 0)
    if core.getProperty("Nosepiece", "Label") != OBJECTIVE_100X:
        raise SystemExit("not on 100x Oil; refusing")
    from hardware.focus import FocusAxis

    px = core.getPixelSizeUm()
    H, W = core.getImageHeight(), core.getImageWidth()
    axis = FocusAxis(core, "100x-Oil", allow_motion=True)
    centre_z = 0.5 * (args.stack[0] + args.stack[1])
    span = axis.plan(centre_z, 0.5 * (args.stack[1] - args.stack[0]), args.step)
    print(span.describe())
    x0, y0 = core.getXYPosition(XY)
    out = sdir / f"find_particle_{datetime.now():%Y%m%d-%H%M%S}.json"
    rec = {"band_um": args.band, "stack": span.describe(), "start": [x0, y0],
           "pixel_um": px, "fields": []}
    frames: list[np.ndarray] = []
    preview = None if args.no_preview else Preview()
    cur = {"field": 0}

    def grab():
        core.snapImage()
        f = np.asarray(core.getImage(), dtype=np.uint16)
        b = binned(f)
        frames.append(b)
        if preview is not None:
            z = axis.position_um()
            pk = float(b.max() - np.median(b))
            preview.show(f, f"field {cur['field']}   ZDrive {z:8.2f} um   "
                            f"band {args.band[0]:.0f}-{args.band[1]:.0f}   brightest {pk:6.0f} ADU"
                            f"   max {int(f.max())}", z, pk)
        return f

    lights, best = [], None
    try:
        axis.require_pfs_quiet(disable=True)
        lights = aura_on(core, args.aura[0], float(args.aura[1]))
        for n, (i, j) in enumerate(spiral(args.max_fields)):
            x, y = x0 + j * args.pitch, y0 + i * args.pitch
            if np.hypot(x - hole_c[0], y - hole_c[1]) > hole_r - 300:
                continue  # stay well inside the hole
            core.setXYPosition(XY, x, y)
            core.waitForDevice(XY)
            time.sleep(0.3)
            frames.clear()
            cur["field"] = n
            if preview is not None:
                preview.new_tile(f"field {n} ({x:.0f}, {y:.0f})")
            curve = axis.sweep(span, grab, score=lambda f: {"sharp": 0.0}, settle_s=0.05)
            zs = np.array([p.z_readback_um for p in curve.points])
            stack = np.stack(frames)
            np.savez_compressed(out.with_name(out.stem + f"_field{n:02d}.npz"),
                                stack=stack.astype(np.float32), z_um=zs,
                                xy_um=np.array(core.getXYPosition(XY)), bin=BIN)
            hits, noise, diag = find_hits(stack, zs, args.band, particle_um=args.particle_um,
                                          pixel_um=px)
            xr, yr = core.getXYPosition(XY)
            fld = {"n": n, "x_um": round(xr, 1), "y_um": round(yr, 1), "noise": round(noise, 2),
                   **diag, "hits": hits[:10]}
            rec["fields"].append(fld)
            out.write_text(json.dumps(rec, indent=1))
            print(json.dumps({"field": n, "x": fld["x_um"], "y": fld["y_um"],
                              "n_hits": len(hits), **diag, "best": hits[0] if hits else None}))
            axis.move_to(span.lo_um)  # retract to the stack bottom before moving XY
            if hits:
                h = hits[0]
                # stage position that puts this pixel at the image centre
                tx = xr + sx * (h["col_px"] - W / 2) * px
                ty = yr + sy * (h["row_px"] - H / 2) * px
                best = {**h, "field": n, "stage_x_um": round(tx, 2), "stage_y_um": round(ty, 2)}
                break
        if best is None:
            print("no particle peaking inside the band in any field searched")
        else:
            core.setXYPosition(XY, best["stage_x_um"], best["stage_y_um"])
            core.waitForDevice(XY)
            # climb from the stack bottom in 1 um steps (the guard allows no long ascent)
            z = axis.position_um()
            while z < best["z_um"] - 0.25:
                z = axis.move_to(min(z + 1.0, best["z_um"]), allow_ascent_um=1.5)
            best["z_parked_um"] = z
            best["position"] = positions(core)
            print("FOUND:", json.dumps(best))
        rec["best"] = best
    finally:
        if lights:
            aura_off(core)
        out.write_text(json.dumps(rec, indent=1, default=str))
        print(f"record: {out}")


if __name__ == "__main__":
    main()
