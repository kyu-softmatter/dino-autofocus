"""Software objective change, by SAFETY.md section 2's software sequence.

    python scripts/change_objective.py --to 0            # read state, then change to 4x
    python scripts/change_objective.py --status          # read-only

Sequence: PFS servo off -> ZDrive -> 0 (smaller Z is retracted, KH 2026-09-05) ->
refuse unless `PFS in Range` reads out of range -> Nosepiece State -> ZDrive -> 2800
(near edge of SAMPLE_Z_WINDOW_UM). Every Z move goes through agentic_microscope's
guarded FocusAxis and is verified by readback. No light is switched on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r"C:\agentic_microscope")
from mm_grab import open_core  # noqa: E402

RETRACT_Z_UM, RETURN_Z_UM = 0.0, 2800.0


def state(core) -> dict:
    s = {"nosepiece_state": core.getProperty("Nosepiece", "State"),
         "nosepiece_label": core.getProperty("Nosepiece", "Label"),
         "z_um": round(core.getPosition("ZDrive"), 3)}
    for key, fn in (("pfs_enabled", "isContinuousFocusEnabled"),
                    ("pfs_locked", "isContinuousFocusLocked")):
        try:
            s[key] = bool(getattr(core, fn)())
        except Exception as exc:  # noqa: BLE001
            s[key] = f"unreadable: {exc}"
    try:
        s["pfs_in_range"] = core.getProperty("PFS", "PFS in Range")
    except Exception as exc:  # noqa: BLE001
        s["pfs_in_range"] = f"unreadable: {exc}"
    print(json.dumps(s))
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", type=int, default=None, help="Nosepiece State (0 = 4x)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--park", action="store_true",
                    help="leave ZDrive retracted at 0 after the rotation (e.g. to oil the lens)")
    ap.add_argument("--return-only", action="store_true",
                    help="no rotation: from retracted, ZDrive -> 2800 on the current objective")
    args = ap.parse_args()

    core, _ = open_core(30.0, 0)
    s0 = state(core)
    if args.status or (args.to is None and not args.return_only):
        return
    from hardware.focus import FocusAxis, registry_key

    if args.return_only:
        axis = FocusAxis(core, registry_key(s0["nosepiece_label"]), allow_motion=True)
        axis.require_pfs_quiet(disable=True)
        if s0["z_um"] > 1.0:
            raise SystemExit(f"--return-only expects ZDrive retracted, reads {s0['z_um']}")
        print(f"return: ZDrive {s0['z_um']} -> {RETURN_Z_UM}")
        axis.move_to(RETURN_Z_UM, allow_ascent_um=RETURN_Z_UM - s0["z_um"] + 0.5)
        state(core)
        return
    if int(s0["nosepiece_state"]) == args.to:
        print("already on that objective; nothing moved")
        return

    axis = FocusAxis(core, registry_key(s0["nosepiece_label"]), allow_motion=True)
    axis.require_pfs_quiet(disable=True)
    print(f"retract: ZDrive {s0['z_um']} -> {RETRACT_Z_UM}")
    axis.move_to(RETRACT_Z_UM)
    s1 = state(core)
    if str(s1["pfs_in_range"]).strip().lower() == "in range":
        raise SystemExit("PFS still reads 'In Range' after retract; refusing to rotate")

    core.setProperty("Nosepiece", "State", args.to)
    core.waitForDevice("Nosepiece")
    s2 = state(core)
    if int(s2["nosepiece_state"]) != args.to:
        raise SystemExit(f"Nosepiece reads {s2['nosepiece_state']}, not {args.to}; "
                         "ZDrive left retracted")

    if args.park:
        print("parked: ZDrive left retracted; run with --return-only when ready")
        return
    axis = FocusAxis(core, registry_key(s2["nosepiece_label"]), allow_motion=True)
    print(f"return: ZDrive {RETRACT_Z_UM} -> {RETURN_Z_UM}")
    axis.move_to(RETURN_Z_UM, allow_ascent_um=RETURN_Z_UM - RETRACT_Z_UM + 0.5)
    state(core)
    print(f"pixel size now {core.getPixelSizeUm()} um")


if __name__ == "__main__":
    main()
