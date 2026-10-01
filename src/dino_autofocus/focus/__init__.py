"""Focus metrics and verdicts. Classical metrics are the default and the final judge; the
DINO reading is an aid (docs/PLAN.md). Importing this package does not import torch:
``focus.dino`` loads the model only in ``DinoVerdict.from_head``.
"""

from .classical import (
    CEILING_12BIT,
    CEILING_16BIT,
    METRICS,
    FrameStats,
    SweepAnalysis,
    analyse_sweep,
    brenner,
    ceiling_for_bits,
    dropout_mask,
    frame_stats,
    parabola_vertex,
    peak_brightness,
    peak_edge,
    saturated_fraction,
    score,
    tenengrad,
    vollath4,
)
from .dino import DinoVerdict
from .verdict import Evidence, FocusVerdict, Verdict, from_reading, from_sweep

__all__ = [
    "CEILING_12BIT",
    "CEILING_16BIT",
    "METRICS",
    "DinoVerdict",
    "Evidence",
    "FocusVerdict",
    "FrameStats",
    "SweepAnalysis",
    "Verdict",
    "analyse_sweep",
    "brenner",
    "ceiling_for_bits",
    "dropout_mask",
    "frame_stats",
    "from_reading",
    "from_sweep",
    "parabola_vertex",
    "peak_brightness",
    "peak_edge",
    "saturated_fraction",
    "score",
    "tenengrad",
    "vollath4",
]
