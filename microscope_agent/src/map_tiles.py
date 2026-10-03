"""4x tile layout and the focus plane through the tiles, pure (no hardware, no guards).

Tile order is serpentine (rows alternate direction), as on 2026-09-30 (scripts/scan_4x.py).
The scan square is centred on the hole fit with half side ``diameter_mm * 500 + margin_um``;
the allowed XY box around it is the engine guards' business (``XYBox.around``), not this
file's.

``fit_plane`` / ``plane_z``: z = a + b (x - x0) + c (y - y0) through the tiles' measured
focus z; slopes in um per mm. Grade "computed" (from measured tile z; never a model value).

Flat file in the soft-matter-agents layout (docs/integration-sma.md section 9): stdlib +
numpy only. ``dino_autofocus.engine.operations.scan_4x`` re-exports these names.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

GRADE_COMPUTED = "computed"  # dino_autofocus.engine.records.GRADE_COMPUTED
DEFAULT_UM_PER_PX = 1.625
#: 2026-09-30 4x calibration (docs/runs/2026-09-30_substrate-scan.yaml); d_px = M @ d_stage
DEFAULT_M_PX_PER_UM = ((0.61602, 0.00236), (0.00126, -0.61456))


def grid(centre: tuple[float, float], half_side_um: float, fov_um: float,
         overlap: float) -> tuple[list[tuple[float, float, int, int]], float, int]:
    """Serpentine tile centres covering a square of half-side `half_side_um` (scan_4x.py)."""
    pitch = fov_um * (1 - overlap)
    n = max(1, math.ceil((2 * half_side_um - fov_um) / pitch) + 1)
    offs = (np.arange(n) - (n - 1) / 2) * pitch
    pts: list[tuple[float, float, int, int]] = []
    for r, dy in enumerate(offs):
        row = [(float(centre[0] + dx), float(centre[1] + dy), r, c) for c, dx in enumerate(offs)]
        pts += row if r % 2 == 0 else row[::-1]
    return pts, float(pitch), n


def tile_name(row: int, col: int) -> str:
    """`tile_r<r>c<c>`: the .npy name in a scan folder (plot_scan.py reads it)."""
    return f"tile_r{row}c{col}"


def tile_list(pts: Sequence[tuple[float, float, int, int]]) -> list[dict]:
    """grid() points as the plan's tile dicts {name, row, col, x_um, y_um}, in scan order."""
    return [{"name": tile_name(r, c), "row": r, "col": c, "x_um": x, "y_um": y}
            for x, y, r, c in pts]


def half_side_um(diameter_mm: Any, margin_um: float) -> float:
    """Half side of the scan square around a hole of `diameter_mm`."""
    return float(diameter_mm) * 500 + margin_um


def square_box_um(centre: Sequence[float], half: float) -> list[float]:
    """[x0, x1, y0, y1] of the square of half side `half` around `centre`."""
    return [centre[0] - half, centre[0] + half, centre[1] - half, centre[1] + half]


def camera_calibration(cal: dict | None) -> tuple[float, list[list[float]], str]:
    """(um_per_px, M_px_per_um, source) from a sample's stage_camera_calibration dict."""
    cal = cal or {}
    um_px = float(cal.get("um_per_px", DEFAULT_UM_PER_PX))
    m = cal.get("M_px_per_um")
    if m is None:
        return um_px, [list(r) for r in DEFAULT_M_PX_PER_UM], "2026-09-30 4x calibration"
    return um_px, [[float(v) for v in r] for r in m], "sample stage_camera_calibration"


def fit_plane(points: list[tuple[float, float, float]]) -> dict | None:
    """z = a + b (x - x0) + c (y - y0) through (x, y, z) points; flat with fewer than 3 or
    collinear points. Slopes in um per mm. Grade "computed"."""
    if not points:
        return None
    p = np.asarray(points, dtype=np.float64)
    x0, y0 = float(p[:, 0].mean()), float(p[:, 1].mean())
    a_mat = np.c_[np.ones(len(p)), p[:, 0] - x0, p[:, 1] - y0]
    if len(p) >= 3 and np.linalg.matrix_rank(a_mat) == 3:
        coef, *_ = np.linalg.lstsq(a_mat, p[:, 2], rcond=None)
        kind = "plane"
    else:
        coef, kind = np.array([p[:, 2].mean(), 0.0, 0.0]), "flat (fewer than 3 independent tiles)"
    rms = float(np.sqrt(np.mean((a_mat @ coef - p[:, 2]) ** 2)))
    return {"kind": kind, "x0_um": x0, "y0_um": y0, "z0_um": float(coef[0]),
            "slope_x_um_per_mm": float(coef[1]) * 1000, "slope_y_um_per_mm": float(coef[2]) * 1000,
            "rms_um": rms, "n_points": len(p), "grade": GRADE_COMPUTED}


def plane_z(plane: dict, x_um: float, y_um: float) -> float:
    return (plane["z0_um"] + plane["slope_x_um_per_mm"] / 1000 * (x_um - plane["x0_um"])
            + plane["slope_y_um_per_mm"] / 1000 * (y_um - plane["y0_um"]))
