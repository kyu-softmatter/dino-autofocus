"""4x mosaic, stage <-> image mapping and classical particle candidates (WP-I, T-032).

Pure numpy / scipy: nothing here talks to a backend. `operations/sample_map.py` calls it on
scan_4x tile outputs; the server renders the saved mosaic for the map screen.

Image convention (PLAN v1.2, the 2026-09-30 run): the camera image is mirrored against the
stage. M is the stage-camera calibration in px per um (`d_pixels = M @ d_stage`, as
edge_trace measures it), and the stage point imaged at pixel p = (col, row) of a tile taken
at stage t is

    stage = t + inv(M) @ (centre - p),      centre = ((w - 1) / 2, (h - 1) / 2)

The mosaic is stored in **stage orientation**: column index grows with stage x, row index
grows with stage y, row 0 is the lowest y (draw it with origin "lower"). Each tile is binned,
then flipped and, if the camera is turned by about 90 degrees, transposed, so that only the
signs and the axis order of inv(M) are used (as scripts/plot_scan.py does). The rotation
left over (about 0.1 degree on the bench) is recorded in `rotation_ignored_deg`.

Mosaic pixel (col, row) covers stage x in [x0 + col * s, x0 + (col + 1) * s) with
s = `um_per_px` of the mosaic; `stage_to_mosaic` / `mosaic_to_stage` use pixel centres.
Overlapping tiles are averaged. Pixels no tile covers are 0 (camera frames never are: the
offset is ~100 ADU).

Candidates are found on the full-resolution tiles (a 9/30 particle is ~4 px wide at 4x, gone
after 8x binning): background removed, a Laplacian-of-Gaussian blob response, local maxima
above `min_snr` times the response's robust noise, line-like maxima (the hole edge) dropped
by the Hessian eigenvalue ratio. They are candidates only (`source: "classical_candidate"`,
`grade: "computed"`); a person confirms them (PLAN F4).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .records import GRADE_COMPUTED

BIN = 8  # plot_scan.py
ORIENTATION = "stage"
CANDIDATE_SOURCE = "classical_candidate"
# 2026-09-30 4x calibration (docs/runs/2026-09-30_substrate-scan.yaml); used when a sample has none
BENCH_M_4X = [[0.61602, 0.00236], [0.00126, -0.61456]]


# ---------------------------------------------------------------- tile geometry
def um_per_px(M: Any) -> float:
    return 1.0 / math.sqrt(abs(float(np.linalg.det(np.asarray(M, float)))))


def tile_pixel_to_stage(M: Any, tile_um: Sequence[float], col: float, row: float,
                        shape: Sequence[int]) -> tuple[float, float]:
    """Stage (x, y) um of pixel (col, row) in a tile of `shape` (rows, cols) taken at `tile_um`."""
    h, w = int(shape[0]), int(shape[1])
    centre = np.array([(w - 1) / 2, (h - 1) / 2])
    xy = np.asarray(tile_um, float) + np.linalg.solve(np.asarray(M, float),
                                                      centre - np.array([col, row], float))
    return float(xy[0]), float(xy[1])


def stage_to_tile_pixel(M: Any, tile_um: Sequence[float], x_um: float, y_um: float,
                        shape: Sequence[int]) -> tuple[float, float]:
    """Pixel (col, row) of stage (x, y) in a tile taken at `tile_um`: centre - M @ (q - t)."""
    h, w = int(shape[0]), int(shape[1])
    centre = np.array([(w - 1) / 2, (h - 1) / 2])
    p = centre - np.asarray(M, float) @ (np.array([x_um, y_um], float) - np.asarray(tile_um))
    return float(p[0]), float(p[1])


@dataclass(frozen=True)
class Orientation:
    """How a camera frame becomes stage-oriented: transpose first, then flip."""

    transpose: bool
    flip_cols: bool
    flip_rows: bool
    rotation_ignored_deg: float

    @classmethod
    def of(cls, M: Any) -> Orientation:
        A = np.linalg.inv(np.asarray(M, float))  # stage um per pixel; stage = t + A (c - p)
        # d stage / d col = -A[:, 0], d stage / d row = -A[:, 1]
        transpose = abs(A[0, 0]) < abs(A[1, 0])  # image columns run mostly along stage y
        if transpose:
            A = A[:, ::-1]  # after the transpose, columns are the old rows
        flip_cols = -A[0, 0] < 0  # mosaic columns must grow with stage x
        flip_rows = -A[1, 1] < 0  # mosaic rows must grow with stage y
        sx = -A[0, 0] * (-1 if flip_cols else 1)
        rot = math.degrees(math.atan2(-A[1, 0] * (-1 if flip_cols else 1), sx))
        return cls(bool(transpose), bool(flip_cols), bool(flip_rows), rot)

    def apply(self, img: np.ndarray) -> np.ndarray:
        if self.transpose:
            img = img.T
        if self.flip_cols:
            img = img[:, ::-1]
        if self.flip_rows:
            img = img[::-1]
        return img


def bin_image(img: np.ndarray, b: int) -> np.ndarray:
    h, w = (img.shape[0] // b) * b, (img.shape[1] // b) * b
    return img[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3), dtype=np.float64)


# ---------------------------------------------------------------- the mosaic
@dataclass
class MosaicMeta:
    x0: float
    x1: float
    y0: float
    y1: float
    um_per_px: float  # of the mosaic (camera um/px x bin)
    bin: int
    M_px_per_um: list[list[float]]
    objective: str
    n_tiles: int
    tile_shape: list[int]  # camera frame (rows, cols)
    orientation: str = ORIENTATION
    transpose: bool = False
    flip_cols: bool = False
    flip_rows: bool = False
    rotation_ignored_deg: float = 0.0
    calibration_source: str = ""
    shape: list[int] = field(default_factory=list)  # mosaic (rows, cols)
    empty_value: float = 0.0
    tiles: list[dict] = field(default_factory=list)  # name, x_um, y_um, col0, row0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> MosaicMeta:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


def stage_to_mosaic(meta: MosaicMeta, x_um: float, y_um: float) -> tuple[float, float]:
    """Mosaic (col, row) of stage (x, y), in pixel-centre coordinates."""
    s = meta.um_per_px
    return (x_um - meta.x0) / s - 0.5, (y_um - meta.y0) / s - 0.5


def mosaic_to_stage(meta: MosaicMeta, col: float, row: float) -> tuple[float, float]:
    s = meta.um_per_px
    return meta.x0 + (col + 0.5) * s, meta.y0 + (row + 0.5) * s


@dataclass
class Tile:
    name: str
    x_um: float  # stage readback at the tile centre
    y_um: float
    image: np.ndarray


def build_mosaic(tiles: Sequence[Tile], M: Any, *, objective: str = "4x", bin: int = BIN,
                 calibration_source: str = "") -> tuple[np.ndarray, MosaicMeta]:
    """Bin, orient and place every tile at its stage centre; overlaps are averaged."""
    if not tiles:
        raise ValueError("no tiles to build a mosaic from")
    M = np.asarray(M, float)
    ori = Orientation.of(M)
    s = um_per_px(M) * bin
    shape = tiles[0].image.shape
    small = [ori.apply(bin_image(np.asarray(t.image, float), bin)) for t in tiles]
    hs, ws = small[0].shape
    half_x, half_y = ws * s / 2, hs * s / 2
    xs = [t.x_um for t in tiles]
    ys = [t.y_um for t in tiles]
    x0, x1 = min(xs) - half_x, max(xs) + half_x
    y0, y1 = min(ys) - half_y, max(ys) + half_y
    W, H = int(math.ceil((x1 - x0) / s)), int(math.ceil((y1 - y0) / s))
    acc = np.zeros((H, W), np.float64)
    cnt = np.zeros((H, W), np.int32)
    placed = []
    for t, img in zip(tiles, small, strict=True):
        if img.shape != (hs, ws):
            raise ValueError(f"tile {t.name} has shape {t.image.shape}, expected {shape}")
        c0 = int(round((t.x_um - x0) / s - ws / 2))
        r0 = int(round((t.y_um - y0) / s - hs / 2))
        cs, rs = max(c0, 0), max(r0, 0)
        ce, re = min(c0 + ws, W), min(r0 + hs, H)
        acc[rs:re, cs:ce] += img[rs - r0:re - r0, cs - c0:ce - c0]
        cnt[rs:re, cs:ce] += 1
        placed.append({"name": t.name, "x_um": t.x_um, "y_um": t.y_um, "col0": c0, "row0": r0})
    mosaic = np.where(cnt > 0, acc / np.maximum(cnt, 1), 0.0).astype(np.float32)
    meta = MosaicMeta(x0=x0, x1=x0 + W * s, y0=y0, y1=y0 + H * s, um_per_px=s, bin=bin,
                      M_px_per_um=M.tolist(), objective=objective, n_tiles=len(tiles),
                      tile_shape=[int(shape[0]), int(shape[1])], transpose=ori.transpose,
                      flip_cols=ori.flip_cols, flip_rows=ori.flip_rows,
                      rotation_ignored_deg=round(ori.rotation_ignored_deg, 3),
                      calibration_source=calibration_source, shape=[H, W], tiles=placed)
    return mosaic, meta


def calibration_for(sample_json: Path | None, objective: str = "4x") -> tuple[list, str]:
    """M from the sample's stage_camera_calibration for this objective, else the bench 4x M."""
    if sample_json is not None and sample_json.exists():
        cal = json.loads(sample_json.read_text(encoding="utf-8")).get("stage_camera_calibration")
        if cal and cal.get("M_px_per_um") and cal.get("objective", objective) == objective:
            return cal["M_px_per_um"], "sample stage_camera_calibration"
    if objective != "4x":
        raise ValueError(f"no calibration for {objective!r} and no bench default")
    return BENCH_M_4X, "2026-09-30 bench 4x (docs/runs/2026-09-30_substrate-scan.yaml)"


def load_scan_tiles(scan_dir: Path) -> tuple[dict, list[Tile]]:
    """scan.json and the tile .npy files of a scan_4x / sample_map record folder."""
    rec = json.loads((scan_dir / "scan.json").read_text(encoding="utf-8"))
    tiles = [Tile(t["name"], float(t["x_um"]), float(t["y_um"]),
                  np.load(scan_dir / f"{t['name']}.npy")) for t in rec["tiles"]]
    return rec, tiles


def mosaic_from_scan(scan_dir: Path, M: Any | None = None, *, bin: int = BIN,
                     save: bool = True) -> tuple[np.ndarray, MosaicMeta]:
    """Build (and by default save) the mosaic of one scan folder. M defaults to the sample's
    calibration (`<scan_dir>/../sample.json`), else the 2026-09-30 bench 4x M."""
    rec, tiles = load_scan_tiles(scan_dir)
    source = "given"
    if M is None:
        M, source = calibration_for(scan_dir.parent / "sample.json")
    from .guards import GuardError, registry_key

    try:
        objective = registry_key(str(rec.get("objective", "4x")))
    except GuardError:
        objective = str(rec.get("objective", "4x"))
    mosaic, meta = build_mosaic(tiles, M, objective=objective, bin=bin,
                                calibration_source=source)
    if save:
        save_mosaic(scan_dir, mosaic, meta)
    return mosaic, meta


def save_mosaic(folder: Path, mosaic: np.ndarray, meta: MosaicMeta) -> tuple[Path, Path]:
    np.save(folder / "mosaic.npy", mosaic)
    (folder / "mosaic.json").write_text(json.dumps(meta.to_dict(), indent=1), encoding="utf-8")
    return folder / "mosaic.npy", folder / "mosaic.json"


def load_mosaic(folder: Path) -> tuple[np.ndarray, MosaicMeta]:
    meta = MosaicMeta.from_dict(json.loads((folder / "mosaic.json").read_text(encoding="utf-8")))
    return np.load(folder / "mosaic.npy"), meta


# ---------------------------------------------------------------- candidates
@dataclass(frozen=True)
class CandidateParams:
    polarity: str = "dark"  # "dark": shadows in brightfield; "bright": Aura fluorescence
    sigma_px: float = 1.5  # ~ particle radius / sqrt(2) at 4x (9/30: ~4 px FWHM)
    background_sigma_px: float = 25.0
    min_snr: float = 6.0
    min_blob_ratio: float = 0.3  # |smaller| / |larger| Hessian eigenvalue; a line is ~0
    border_px: int = 8
    max_per_tile: int = 500
    merge_um: float = 10.0  # the same particle seen in two overlapping tiles


DEFAULT_CANDIDATES = CandidateParams()


def detect_blobs(img: np.ndarray, p: CandidateParams = DEFAULT_CANDIDATES) -> list[dict]:
    """Blob maxima in one frame: [{col, row, snr, response}], strongest first."""
    from scipy import ndimage

    if p.polarity not in ("dark", "bright"):
        raise ValueError(f"polarity {p.polarity!r} is not 'dark' or 'bright'")
    a = np.asarray(img, np.float64)
    a = a - ndimage.gaussian_filter(a, p.background_sigma_px, mode="reflect")
    if p.polarity == "dark":
        a = -a
    sm = ndimage.gaussian_filter(a, p.sigma_px, mode="reflect")
    resp = -ndimage.gaussian_laplace(a, p.sigma_px, mode="reflect") * p.sigma_px**2
    noise = 1.4826 * float(np.median(np.abs(resp - np.median(resp))))
    if noise <= 0:
        return []
    size = max(3, int(2 * round(2 * p.sigma_px) + 1))
    peaks = (resp == ndimage.maximum_filter(resp, size=size)) & (resp > p.min_snr * noise)
    b = p.border_px
    peaks[:b], peaks[-b:], peaks[:, :b], peaks[:, -b:] = False, False, False, False
    rows, cols = np.nonzero(peaks)
    if not len(rows):
        return []
    # Hessian of the smoothed image at each peak: a blob curves both ways, a line one way
    gy, gx = np.gradient(sm)
    hyy, hyx = np.gradient(gy)
    hxy, hxx = np.gradient(gx)
    out = []
    for r, c in zip(rows, cols, strict=True):
        H = np.array([[hxx[r, c], hxy[r, c]], [hyx[r, c], hyy[r, c]]])
        ev = np.linalg.eigvalsh(0.5 * (H + H.T))
        big = max(abs(ev[0]), abs(ev[1]))
        ratio = 0.0 if big == 0 else min(abs(ev[0]), abs(ev[1])) / big
        if ratio < p.min_blob_ratio or not (ev < 0).all():
            continue
        out.append({"col": float(c), "row": float(r), "snr": float(resp[r, c] / noise),
                    "response": float(resp[r, c]), "blob_ratio": float(ratio)})
    out.sort(key=lambda d: -d["snr"])
    return out[:p.max_per_tile]


def find_candidates(tiles: Iterable[Tile], M: Any, p: CandidateParams = DEFAULT_CANDIDATES, *,
                    hole: dict | None = None, hole_margin_um: float = 100.0) -> list[dict]:
    """Candidates in stage coordinates over all tiles, merged across overlaps.

    With a `hole` fit ({centre_um, diameter_mm}) only points at least `hole_margin_um`
    inside the hole are kept, so the edge and the spacer give none."""
    found: list[dict] = []
    for t in tiles:
        for b in detect_blobs(t.image, p):
            x, y = tile_pixel_to_stage(M, (t.x_um, t.y_um), b["col"], b["row"], t.image.shape)
            if hole is not None:
                r = float(hole["diameter_mm"]) * 500.0 - hole_margin_um
                if math.hypot(x - hole["centre_um"][0], y - hole["centre_um"][1]) > r:
                    continue
            found.append({"x_um": round(x, 2), "y_um": round(y, 2), "score": round(b["snr"], 2),
                          "tile": t.name, "px": [b["col"], b["row"]],
                          "blob_ratio": round(b["blob_ratio"], 3)})
    found.sort(key=lambda d: -d["score"])
    kept: list[dict] = []
    for f in found:  # strongest first; a weaker twin within merge_um is the same particle
        if all(math.hypot(f["x_um"] - k["x_um"], f["y_um"] - k["y_um"]) > p.merge_um
               for k in kept):
            kept.append(f)
    method = {"detector": "LoG blob, Hessian ratio", **asdict(p)}
    return [{**k, "source": CANDIDATE_SOURCE, "grade": GRADE_COMPUTED, "method": method}
            for k in kept]
