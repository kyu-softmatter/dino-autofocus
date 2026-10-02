"""The 100x focus search as steps, pure: what to sweep, not whether a move is allowed.

The search (``dino_autofocus.engine.operations.focus_100x``, port of scripts/focus_100x.py):
a coarse sweep around a centre; a peak inside it gets a fine sweep around the coarse peak; a
peak on the top end is **not** climbed: Z goes back to the low end and the operator is asked
whether to extend upward, one span higher from the old top, at most ``MAX_EXTENSIONS`` times
and never past the ceiling; a peak on the low end is reported ("re-centre lower").

This file only yields the spans and the Z points. The limits (floor, ceiling) are
arguments: in this repository the engine's guards (``FocusAxis.plan``) compute them, check
every move and read it back; in soft-matter-agents the envelope gives them. Nothing here
moves anything, and no model value takes part.

The span helpers return ``(centre_um, half_um, step_um)``, the arguments of
``FocusAxis.plan`` and of ``sweep_z``; ``sweep_z`` gives the same Z list as the guards' plan
for the same floor and ceiling.

Flat file in the soft-matter-agents layout (docs/integration-sma.md section 9): stdlib +
numpy only, siblings loaded by path.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name: str, filename: str):
    """A sibling file by path, the soft-matter-agents idiom (no package, no relative import).
    A name already loaded is reused, so every importer shares one module object."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_classical = _load("_mic_focus_classical", "focus_classical.py")
MAX_SATURATED_FRACTION = _classical.MAX_SATURATED_FRACTION

GRADE_COMPUTED = "computed"  # dino_autofocus.engine.records.GRADE_COMPUTED
PROVISIONAL = "unmeasured provisional"  # dino_autofocus.engine.backend.PROVISIONAL
DEFAULT_CENTRE_UM = 2930.0
PARFOCAL_4X_TO_100X_UM = -60.0  # 2026-09-30, one sample; unmeasured provisional
DARK_OFFSET_ADU = 102.0  # Kinetix_red dark offset on 2026-09-30
SIGNAL_MIN_ADU = 50.0  # a first frame whose max is within this of the dark offset: no signal
DEFAULT_EXPOSURE_MS = 20.0  # provisional (2026-09-30, one run)
MAX_EXTENSIONS = 3
METRICS = ("peak", "vollath")
REDUCE_EXPOSURE = "reduce exposure"
DARK_SIGNAL = "signal at dark level"
TOP_END, LOW_END, INTERIOR = "top_end", "low_end", "interior"


@dataclass(frozen=True)
class FocusArgs:
    centre_um: float | None = None  # None: 4x plane + parfocal offset, else 2930
    half_um: float = 40.0
    step_um: float = 2.0
    fine_half_um: float = 3.0
    fine_step_um: float = 0.2
    # provisional (2026-09-30, one run): 20 ms gave a clean peak without saturation; the
    # script's default was 30
    exposure_ms: float = DEFAULT_EXPOSURE_MS
    aura_line: str = "GREEN"
    aura_percent: float = 1.0
    metric: str = "peak"
    oil_loaded: bool | None = None  # True when this session recorded load_immersion


def parse(args: dict) -> FocusArgs:
    known = set(FocusArgs.__dataclass_fields__)
    extra = sorted(set(args) - known - {"sample_id"})
    if extra:
        raise ValueError(f"unknown focus_100x arguments: {extra}")
    a = FocusArgs(**{k: v for k, v in args.items() if k in known})
    if a.metric not in METRICS:
        raise ValueError(f"metric {a.metric!r} is not one of {METRICS}")
    for name in ("half_um", "step_um", "fine_half_um", "fine_step_um", "exposure_ms"):
        v = float(getattr(a, name))
        if not math.isfinite(v) or v <= 0:
            raise ValueError(f"{name} {v} must be a finite number > 0")
    return a


# ---------------------------------------------------------------- where to start
def centre_from_plane(plane: dict | None) -> dict:
    """The suggested sweep centre and where it came from (computed, not model): the 4x focus
    plane at this XY ({z_um, scan}, scan_4x.focus_plane_4x) plus the parfocal offset, else
    the script default."""
    if plane is not None:
        return {"centre_um": plane["z_um"] + PARFOCAL_4X_TO_100X_UM, "z_4x_um": plane["z_um"],
                "source": f"4x plane of {plane['scan']} + parfocal "
                          f"{PARFOCAL_4X_TO_100X_UM:g} um ({PROVISIONAL})",
                "grade": GRADE_COMPUTED}
    return {"centre_um": DEFAULT_CENTRE_UM, "z_4x_um": None,
            "source": "script default (no 4x scan)", "grade": None}


def centre_grade(pl: dict) -> str | None:
    return GRADE_COMPUTED if pl.get("z_4x_um") is not None else None


# ---------------------------------------------------------------- the spans
def coarse_span(centre_um: float, a: FocusArgs) -> tuple[float, float, float]:
    return centre_um, a.half_um, a.step_um


def fine_span(peak_z_um: float, a: FocusArgs) -> tuple[float, float, float]:
    """Around an interior coarse peak (the readback of the best plane)."""
    return peak_z_um, a.fine_half_um, a.fine_step_um


def extension_span(lo_um: float, hi_um: float, step_um: float) -> tuple[float, float, float]:
    """After a peak on the top end of lo..hi: one span higher, swept up from the low end
    (centre at the old top, half the old span), so Z never jumps upward."""
    return hi_um, hi_um - lo_um, step_um


def room_above(new_top_um: float, hi_um: float) -> bool:
    """False when the ceiling leaves nothing above the old top (the extension stops)."""
    return not new_top_um <= hi_um + 1e-6


def sweep_z(centre_um: float, half_um: float, step_um: float, *, floor_um: float,
            ceiling_um: float) -> list[float]:
    """Ascending Z points centre +- half at `step`, clipped to floor..ceiling (the same
    arithmetic as the guards' FocusAxis.plan, with the limits as arguments)."""
    c, h, s = float(centre_um), float(half_um), float(step_um)
    if not all(math.isfinite(v) for v in (c, h, s)):
        raise ValueError(f"centre {c}, half {h} and step {s} must be finite numbers")
    if s <= 0 or h < 0:
        raise ValueError(f"step {s} must be > 0 and half range {h} >= 0")
    lo, hi = max(float(floor_um), c - h), min(float(ceiling_um), c + h)
    if lo > hi:
        raise ValueError(f"sweep {c - h:.2f}..{c + h:.2f} um is outside "
                         f"{float(floor_um):.0f}..{float(ceiling_um):.2f} um")
    n = int(math.floor((hi - lo) / s + 1e-9)) + 1
    return [round(lo + i * s, 4) for i in range(n)]


# ---------------------------------------------------------------- reading a sweep
def peak_at(at_top: bool, argmax_index: int | None) -> str:
    """Where the coarse peak lies: TOP_END (extend upward or stop, no fine pass), LOW_END
    (re-centre lower, no fine pass) or INTERIOR (a fine pass follows)."""
    if at_top:
        return TOP_END
    if argmax_index == 0:
        return LOW_END
    return INTERIOR


def at_dark_level(first_max_adu: float) -> bool:
    """The first frame's max within SIGNAL_MIN_ADU of the dark offset: no signal."""
    return float(first_max_adu) <= DARK_OFFSET_ADU + SIGNAL_MIN_ADU


def too_bright(saturated_fractions: Iterable[Any],
               limit: float = MAX_SATURATED_FRACTION) -> bool:
    """Any plane with more clipped pixels than `limit` (None counts as 0): reduce exposure."""
    return any((s or 0) > limit for s in saturated_fractions)
