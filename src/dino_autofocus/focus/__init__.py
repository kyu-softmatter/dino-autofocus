"""Focus metrics and verdicts. Classical metrics are the default and the final judge; the
DINO reading is an aid (docs/PLAN.md). Importing this package does not import torch:
``focus.dino`` loads the model only in ``DinoVerdict.from_head``.

``classical``, ``verdict`` and ``sma_event`` live in ``microscope_agent/src/`` as the flat
files ``focus_classical``, ``focus_verdict`` and ``focus_run_log`` (the soft-matter-agents
layout, docs/integration-sma.md section 9); they are registered here under their old names.
"""

from .._flat import load

classical = load("focus_classical", f"{__name__}.classical")
verdict = load("focus_verdict", f"{__name__}.verdict")
sma_event = load("focus_run_log", f"{__name__}.sma_event")

from .classical import (  # noqa: E402
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
from .dino import DinoVerdict  # noqa: E402
from .verdict import Evidence, FocusVerdict, Verdict, from_reading, from_sweep  # noqa: E402

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
