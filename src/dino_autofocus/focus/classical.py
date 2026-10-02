"""Classical focus metrics for live frames and the sweep-curve tools built on them.

Pure numpy, no hardware. Inputs are mono camera frames (uint16; the Kinetix reads out
12-bit, ceiling 4095, or 16-bit, ceiling 65535). Every metric peaks at best focus.

The metrics come from the scripts that ran on the bench on 2026-09-30 and keep their
formulas exactly, so values in old scan records stay comparable:

* ``vollath4`` and ``brenner`` -- ``scripts/mm_grab.py``. The frame is median-subtracted
  and divided by its mean absolute deviation, so a brighter exposure does not read as
  sharper. Vollath F4 (lag-1 minus lag-2 autocorrelation, both axes) cancels uncorrelated
  noise; Brenner (lag-2 squared differences) rises on dim, noisy frames.
* ``peak_brightness`` -- ``scripts/focus_100x.py --metric peak``: brightest 4 x 4-binned
  spot minus the binned median. For sparse particle fields at 100x, where a whole-frame
  sharpness barely moves.
* ``tenengrad`` -- Sobel gradient energy, one of the ``RELIABLE`` metrics of the vendored
  ``dino_autofocus.synth.sim.metrics``, here on the valid interior only and with the same
  normalisation as the two above.

``vollath4`` here sums both axes, while ``synth.sim.metrics.vollath4`` uses the x axis
only: both peak at the same plane, but their values differ.

Saturation: the metrics use the pixels as read and do **not** mask clipped pixels. A
clipped core flattens the gradient at the top of a particle, so a saturated frame
under-reads its own sharpness and can move the peak. Keep ``saturated_fraction`` next to
the score (``frame_stats`` does) and treat frames above ``MAX_SATURATED_FRACTION`` as not
readable; ``analyse_sweep`` drops them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

#: Camera clip levels. The Kinetix_red ran 12-bit on 2026-09-30.
CEILING_12BIT = 4095
CEILING_16BIT = 65535

#: A frame with a larger clipped fraction is not used for focus. Same limit as the tile
#: picker in ``dino_autofocus.live.select_tiles``.
MAX_SATURATED_FRACTION = 0.001

#: A sweep frame whose mean is more than this fraction off the sweep's median is a light
#: dropout, not a focus change (``scripts/scan_4x.py``; on 2026-09-30 one Aura frame at
#: -23 % read 2.7x sharper than the rest and became the "peak").
DROPOUT_TOLERANCE = 0.02

PEAK_BIN = 4  # focus_100x.py: 4 x 4 binning, so one hot pixel cannot win

Edge = Literal["interior", "top", "bottom"]


def ceiling_for_bits(bits: int) -> int:
    """Clip level of a camera read out at `bits` bits (``2**bits - 1``)."""
    if not 1 <= bits <= 16:
        raise ValueError(f"bit depth {bits} outside 1..16 for a uint16 frame")
    return (1 << bits) - 1


def saturated_fraction(img: np.ndarray, ceiling: int) -> float:
    """Fraction of pixels at or above the camera's clip level."""
    return float(np.mean(np.asarray(img) >= ceiling))


def _normalise(img: np.ndarray) -> np.ndarray:
    """Median-subtracted, divided by the mean absolute deviation (mm_grab.py, float32)."""
    a = np.asarray(img).astype(np.float32)
    a = a - np.median(a)
    a /= max(float(np.abs(a).mean()), 1e-6)
    return a


def vollath4(img: np.ndarray) -> float:
    """Scale-invariant Vollath F4 over both axes (``scripts/mm_grab.py``)."""
    a = _normalise(img)
    f = (a[:, :-1] * a[:, 1:]).mean() - (a[:, :-2] * a[:, 2:]).mean()
    g = (a[:-1] * a[1:]).mean() - (a[:-2] * a[2:]).mean()
    return float(f + g)


def brenner(img: np.ndarray) -> float:
    """Scale-invariant Brenner sharpness, lag 2 on both axes (``scripts/mm_grab.py``)."""
    a = _normalise(img)
    return float(((a[:, 2:] - a[:, :-2]) ** 2).mean() + ((a[2:] - a[:-2]) ** 2).mean())


def tenengrad(img: np.ndarray) -> float:
    """Scale-invariant Sobel gradient energy on the valid interior (no border padding)."""
    a = _normalise(img)
    if a.shape[0] < 3 or a.shape[1] < 3:
        raise ValueError(f"tenengrad needs at least 3 x 3 pixels, got {a.shape}")
    # Sobel = [1, 2, 1] smoothing across the derivative axis, [-1, 0, 1] along it
    sy = a[:-2] + 2 * a[1:-1] + a[2:]
    gx = sy[:, 2:] - sy[:, :-2]
    sx = a[:, :-2] + 2 * a[:, 1:-1] + a[:, 2:]
    gy = sx[2:] - sx[:-2]
    return float((gx**2 + gy**2).mean())


def peak_brightness(img: np.ndarray, bin_px: int = PEAK_BIN) -> float:
    """Brightest `bin_px` x `bin_px`-binned spot minus the binned median, in ADU.

    Not scale invariant on purpose: at 100x on a sparse field it tracks how much light the
    in-focus particle concentrates. A clipped particle caps at the ceiling, so check
    ``saturated_fraction`` (the 2026-09-30 100x runs saturated at 30-50 ms).
    """
    a = np.asarray(img)
    h, w = (a.shape[0] // bin_px) * bin_px, (a.shape[1] // bin_px) * bin_px
    if h == 0 or w == 0:
        raise ValueError(f"frame {a.shape} smaller than one {bin_px} x {bin_px} bin")
    b = a[:h, :w].reshape(h // bin_px, bin_px, w // bin_px, bin_px).mean(
        axis=(1, 3), dtype=np.float32)
    return float(b.max() - np.median(b))


METRICS: dict[str, Callable[[np.ndarray], float]] = {
    "vollath4": vollath4,
    "brenner": brenner,
    "tenengrad": tenengrad,
    "peak": peak_brightness,
}


def score(img: np.ndarray, metric: str = "vollath4") -> float:
    """Focus score of `img` by name: one of ``METRICS``."""
    try:
        fn = METRICS[metric]
    except KeyError:
        raise KeyError(f"unknown metric {metric!r}; available: {sorted(METRICS)}") from None
    return fn(img)


@dataclass
class FrameStats:
    """Per-frame numbers a sweep keeps next to its score (the scripts' ``diagnostics``)."""

    score: float
    metric: str
    mean: float
    median: float
    p999: float
    max: int
    saturated_fraction: float


def frame_stats(img: np.ndarray, metric: str = "vollath4",
                ceiling: int = CEILING_16BIT) -> FrameStats:
    """Score `img` and record the brightness numbers the sweep checks need."""
    a = np.asarray(img)
    return FrameStats(score=score(a, metric), metric=metric, mean=float(a.mean()),
                      median=float(np.median(a)), p999=float(np.percentile(a, 99.9)),
                      max=int(a.max()), saturated_fraction=saturated_fraction(a, ceiling))


# -- sweep curves ---------------------------------------------------------------------------

def dropout_mask(means: Sequence[float], tolerance: float = DROPOUT_TOLERANCE) -> np.ndarray:
    """True for frames whose mean is within `tolerance` of the sweep's median mean.

    The others are light dropouts (``scripts/scan_4x.py``) and must not pick the peak.
    """
    m = np.asarray(means, dtype=np.float64)
    if m.size == 0:
        return np.zeros(0, dtype=bool)
    med = float(np.median(m))
    return np.abs(m - med) <= tolerance * abs(med)


def _sorted_curve(z: Sequence[float], s: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    zz, ss = np.asarray(z, dtype=np.float64), np.asarray(s, dtype=np.float64)
    if zz.ndim != 1 or zz.shape != ss.shape or zz.size == 0:
        raise ValueError(f"z and score must be non-empty 1-D and the same length "
                         f"({zz.shape} vs {ss.shape})")
    o = np.argsort(zz, kind="stable")
    return zz[o], ss[o]


def parabola_vertex(z: Sequence[float], s: Sequence[float]) -> float:
    """Sub-step peak: the vertex of the parabola through the argmax and its neighbours.

    Same formula as ``synth.sim.metrics.argmax_parabolic`` (used by
    ``scripts/eval_synthetic.py``), after sorting by z. At either end of the span it returns
    that end's z: the curve says nothing about how far beyond the span the peak is (see
    ``peak_edge``). The vertex is clipped to the two neighbours.
    """
    zz, ss = _sorted_curve(z, s)
    j = int(np.argmax(ss))
    if j == 0 or j == len(zz) - 1:
        return float(zz[j])
    x0, x1, x2 = zz[j - 1:j + 2]
    y0, y1, y2 = ss[j - 1:j + 2]
    den = (x0 - x1) * (x0 - x2) * (x1 - x2)
    if abs(den) < 1e-30:
        return float(x1)
    a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / den
    b = (x2**2 * (y0 - y1) + x1**2 * (y2 - y0) + x0**2 * (y1 - y2)) / den
    if abs(a) < 1e-30:
        return float(x1)
    return float(np.clip(-b / (2 * a), x0, x2))


def peak_edge(z: Sequence[float], s: Sequence[float]) -> Edge:
    """Where the score maximum sits in the span: ``"top"`` (highest z), ``"bottom"`` or
    ``"interior"``. A span of one or two frames has no interior."""
    zz, ss = _sorted_curve(z, s)
    j = int(np.argmax(ss))
    if j == len(zz) - 1:
        return "top"
    if j == 0:
        return "bottom"
    return "interior"


@dataclass
class SweepAnalysis:
    """What the classical curve says, before it is turned into a verdict.

    Indices refer to the frames in the order passed in. ``z_um`` must be the encoder
    readback of each frame, not the commanded z.
    """

    z_um: list[float]
    scores: list[float]
    kept: list[bool]                 # False: light dropout or saturated
    dropped_z_um: list[float]        # light dropouts
    saturated_z_um: list[float]
    edge: Edge | None                # None when no frame is kept
    argmax_index: int | None         # best kept frame, original index
    z_vertex_um: float | None        # parabola vertex: computed, not any frame's z
    nearest_index: int | None        # kept frame closest to the vertex
    prominence: float | None         # (max - higher end) / |max| over kept frames
    notes: list[str] = field(default_factory=list)

    @property
    def n_kept(self) -> int:
        return sum(self.kept)


def analyse_sweep(z_um: Sequence[float], scores: Sequence[float],
                  means: Sequence[float] | None = None,
                  saturated: Sequence[float] | None = None,
                  dropout_tolerance: float = DROPOUT_TOLERANCE,
                  max_saturated: float = MAX_SATURATED_FRACTION) -> SweepAnalysis:
    """Drop light-dropout and saturated frames, then locate the peak of what is left.

    `means` (frame means) enables the dropout filter, `saturated` (clipped fractions) the
    saturation filter; both are per frame, in the order of `z_um`.
    """
    z = [float(v) for v in z_um]
    s = [float(v) for v in scores]
    n = len(z)
    if len(s) != n:
        raise ValueError(f"{n} z values but {len(s)} scores")
    keep = np.ones(n, dtype=bool)
    notes: list[str] = []
    if means is not None:
        if len(means) != n:
            raise ValueError(f"{n} z values but {len(means)} means")
        keep &= dropout_mask(means, dropout_tolerance)
    dropped = [z[i] for i in range(n) if not keep[i]]
    if dropped:
        notes.append(f"light dropout at z {dropped}")
    sat_z: list[float] = []
    if saturated is not None:
        if len(saturated) != n:
            raise ValueError(f"{n} z values but {len(saturated)} saturated fractions")
        sat = np.asarray(saturated, dtype=np.float64) > max_saturated
        sat_z = [z[i] for i in range(n) if sat[i] and keep[i]]
        keep &= ~sat
        if sat_z:
            notes.append(f"saturated (> {max_saturated:g} clipped) at z {sat_z}")
    out = SweepAnalysis(z_um=z, scores=s, kept=keep.tolist(), dropped_z_um=dropped,
                        saturated_z_um=sat_z, edge=None, argmax_index=None, z_vertex_um=None,
                        nearest_index=None, prominence=None, notes=notes)
    idx = [i for i in range(n) if keep[i]]
    if not idx:
        return out
    kz = np.array([z[i] for i in idx])
    ks = np.array([s[i] for i in idx])
    out.edge = peak_edge(kz, ks)
    out.argmax_index = idx[int(np.argmax(ks))]
    out.z_vertex_um = parabola_vertex(kz, ks)
    out.nearest_index = idx[int(np.argmin(np.abs(kz - out.z_vertex_um)))]
    o = np.argsort(kz, kind="stable")
    smax, ends = float(ks.max()), max(float(ks[o][0]), float(ks[o][-1]))
    out.prominence = (smax - ends) / max(abs(smax), 1e-12)
    return out
