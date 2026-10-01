"""Guarded 100x Oil focus search with ZDrive, under the particle light.

    python scripts/focus_100x.py --centre 2930 --half 40      # coarse 2 um, fine 0.2 um

Through agentic_microscope's FocusAxis: PFS off, the sweep's ceiling is
min(3200, centre + 0.4 x 130 um WD), every sweep ascends, each move is verified. If the
coarse peak sits on the top end, it stops without climbing further -- the true focus may
be above, and that is the operator's call (objective-offsets.yaml: a wrong centre nearly
ran a high-NA lens into the coverslip on 2026-09-07). Light off on exit.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r"C:\agentic_microscope")
from mm_grab import aura_off, aura_on, open_core, positions, vollath4  # noqa: E402

OBJECTIVE_100X = "6-Plan Apo LmbdD0.13 100x Oil"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--centre", type=float, default=2930.0)
    ap.add_argument("--half", type=float, default=40.0)
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--fine-half", type=float, default=3.0)
    ap.add_argument("--fine-step", type=float, default=0.2)
    ap.add_argument("--exposure", type=float, default=30.0)
    ap.add_argument("--aura", nargs=2, default=["GREEN", "1"])
    ap.add_argument("--metric", choices=["vollath", "peak"], default="peak",
                    help="peak: brightest 4x4-binned spot over the median -- right for a sparse "
                         "field of point-like particles, where a whole-frame sharpness barely "
                         "moves; vollath: textured / dense fields")
    ap.add_argument("--out", type=Path, default=Path(r"D:\AutoFocus\samples\20260930_1849_1"))
    args = ap.parse_args()

    core, info = open_core(args.exposure, 0)
    label = core.getProperty("Nosepiece", "Label")
    if label != OBJECTIVE_100X:
        raise SystemExit(f"Nosepiece reads {label!r}; refusing")
    from hardware.focus import FocusAxis, best_z_um

    axis = FocusAxis(core, "100x-Oil", allow_motion=True)
    ceiling = 2 ** core.getImageBitDepth() - 1

    def grab():
        core.snapImage()
        return np.asarray(core.getImage(), dtype=np.uint16)

    def peak(f):
        h, w = (f.shape[0] // 4) * 4, (f.shape[1] // 4) * 4
        b = f[:h, :w].reshape(h // 4, 4, w // 4, 4).mean(axis=(1, 3), dtype=np.float32)
        return float(b.max() - np.median(b))  # 4x4 binning: one hot pixel can't win

    def score(f):
        return {"sharp": peak(f) if args.metric == "peak" else vollath4(f),
                "vollath": vollath4(f), "mean": float(f.mean()), "max": int(f.max()),
                "sat": float(np.mean(f >= ceiling))}

    rec = {"started": datetime.now().isoformat(timespec="seconds"), "header": info}
    lights = []
    try:
        axis.require_pfs_quiet(disable=True)
        lights = aura_on(core, args.aura[0], float(args.aura[1]))
        coarse = axis.sweep(axis.plan(args.centre, args.half, args.step), grab, score=score,
                            settle_s=0.1)
        rec["coarse"] = [(p.z_readback_um, p.score, p.diagnostics["mean"],
                          p.diagnostics["max"]) for p in coarse.points]
        print("coarse:", coarse.verdict()[1])
        i = coarse.argmax_index
        fine = None
        if i == len(coarse.points) - 1:
            print("PEAK AT THE TOP END -- focus may be higher; not climbing further.")
            axis.move_to(coarse.points[0].z_um)  # back down to the low end (retract direction)
        elif i == 0:
            print("peak at the LOW end -- focus is below the span; re-centre lower.")
        else:
            fine = axis.sweep(axis.plan(coarse.peak_z_um, args.fine_half, args.fine_step), grab,
                              score=score, settle_s=0.15)
            rec["fine"] = [(p.z_readback_um, p.score, p.diagnostics["mean"],
                            p.diagnostics["max"]) for p in fine.points]
        zf, why = best_z_um(coarse, fine)
        rec["z_focus_um"], rec["why"] = zf, why
        print(f"best focus: {zf} ({why})")
        if zf is not None:
            rec["z_parked_um"] = axis.park_at(zf)
        rec["position"] = positions(core)
        print(json.dumps(rec["position"]))
    finally:
        if lights:
            aura_off(core)
        p = args.out / f"focus100x_{datetime.now():%Y%m%d-%H%M%S}.json"
        p.write_text(json.dumps(rec, indent=1, default=str))
        print(f"record: {p}")


if __name__ == "__main__":
    main()
