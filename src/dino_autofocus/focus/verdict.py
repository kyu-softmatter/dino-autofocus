"""Focus verdicts in the soft-matter-agents focus-seat vocabulary (task 026).

A verdict is **for display and for the record only**. It never sets a motion limit, never
opens a gate and never takes part in a safety decision: those are decided by the engine's
guards from encoder readbacks and fixed limits (docs/PLAN.md, design rules 2 and 3).

Vocabulary: ``in_focus | step_up | step_down | no_sample_here | unsure``.

* ``step_up`` means best focus lies *above* the current stage z: the focus drive should
  move up (larger ZDrive um). ``step_down`` the opposite. At 100x a step up is the
  operator's call (2026-09-30 rule); the verdict only reports it.
* The z of a verdict is the **encoder readback of a real frame** that was taken. It is never
  a model output and never an interpolated z. Computed numbers (a parabola vertex) and model
  numbers (DINO dz, sigma) are kept as evidence with their grade.

Two mappings:

``from_sweep`` -- a classical z sweep (scores of frames at known encoder z):
  no frame with more than dark-level dynamic range -> ``no_sample_here``;
  too few readable frames or a flat curve -> ``unsure``;
  peak at the top of the span -> ``step_up``; at the bottom -> ``step_down``;
  peak inside -> ``in_focus`` at the real frame nearest the parabola vertex.

``from_reading`` -- one frame's signed DINO reading (``dino_autofocus.live.FocusReading``),
  in DoF units with dz = stage - best focus (positive: the stage is above focus):
  no tile with sample signal -> ``no_sample_here``; tiles but none readable, or sigma above
  ``MAX_SIGMA_DOF`` -> ``unsure``; ``|dz| <= IN_FOCUS_DOF`` -> ``in_focus``; sign known
  (``|dz| > sigma``) -> ``step_down`` for dz > 0, ``step_up`` for dz < 0; else ``unsure``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol

from .classical import (
    DROPOUT_TOLERANCE,
    MAX_SATURATED_FRACTION,
    FrameStats,
    analyse_sweep,
)

#: Frames whose 99.9th percentile is less than this many ADU above their median hold no
#: sample: 2026-09-30, a 30 ms 100x Vollath run read only the dark offset (~102 ADU) and
#: gave no focus. Provisional; set from dark frames on the microscope PC.
MIN_DYNAMIC_RANGE_ADU = 20.0

#: A curve whose (max - min) / max(|max|, |min|) is below this is flat: no peak to trust.
MIN_CURVE_CONTRAST = 0.05

#: Fewer readable sweep frames than this cannot place a peak.
MIN_SWEEP_FRAMES = 3

#: |dz| at or under this many DoF reads as in focus (the live view's green band).
IN_FOCUS_DOF = 1.0

#: A model reading with a larger sigma (DoF) is ``unsure``. Provisional.
MAX_SIGMA_DOF = 3.0

#: Grade of a number in a verdict record. "measured": read from the hardware (encoder z,
#: pixel statistics); "computed": deterministic from measured values (a classical metric,
#: a parabola vertex); "model": produced by a learned model -- grade E6 in soft-matter-agents,
#: kept out of any decision. Field name to be aligned with engine.records (T-002).
Grade = Literal["measured", "computed", "model"]


class Verdict(StrEnum):
    IN_FOCUS = "in_focus"
    STEP_UP = "step_up"
    STEP_DOWN = "step_down"
    NO_SAMPLE_HERE = "no_sample_here"
    UNSURE = "unsure"


@dataclass
class Evidence:
    name: str
    value: float | int | str | None
    grade: Grade
    unit: str = ""


@dataclass
class FocusVerdict:
    verdict: Verdict
    source: Literal["sweep", "dino"]
    reason: str
    frame_index: int | None = None   # the real frame the verdict points at
    z_um: float | None = None        # that frame's encoder readback, never a model value
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def has_model_numbers(self) -> bool:
        return any(e.grade == "model" for e in self.evidence)

    def as_record(self) -> dict[str, Any]:
        """JSON-ready dict (``json.dumps`` works on it as is)."""
        d = asdict(self)
        d["verdict"] = str(self.verdict)
        d["z_grade"] = None if self.z_um is None else "measured"
        return d


def _num(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else float(x)


# -- mapping 1: classical sweep -------------------------------------------------------------

def from_sweep(z_um: Sequence[float], stats: Sequence[FrameStats], *,
               min_dynamic_range_adu: float = MIN_DYNAMIC_RANGE_ADU,
               min_contrast: float = MIN_CURVE_CONTRAST,
               min_frames: int = MIN_SWEEP_FRAMES,
               dropout_tolerance: float = DROPOUT_TOLERANCE,
               max_saturated: float = MAX_SATURATED_FRACTION) -> FocusVerdict:
    """Verdict from a classical sweep.

    `z_um` is the encoder readback of each frame (not the commanded z), `stats` the
    ``classical.frame_stats`` of the same frames, in the same order.
    """
    if len(z_um) != len(stats):
        raise ValueError(f"{len(z_um)} z values but {len(stats)} frame stats")
    if not stats:
        return FocusVerdict(Verdict.UNSURE, "sweep", "empty sweep")
    metric = stats[0].metric
    ev = [Evidence("metric", metric, "computed"), Evidence("n_frames", len(stats), "measured")]
    dyn = max(s.p999 - s.median for s in stats)
    ev.append(Evidence("max_dynamic_range", dyn, "measured", "ADU"))
    if dyn < min_dynamic_range_adu:
        return FocusVerdict(Verdict.NO_SAMPLE_HERE, "sweep",
                            f"no frame has more than {dyn:.1f} ADU above its median "
                            f"(dark level < {min_dynamic_range_adu:g} ADU)", evidence=ev)

    a = analyse_sweep(z_um, [s.score for s in stats], means=[s.mean for s in stats],
                      saturated=[s.saturated_fraction for s in stats],
                      dropout_tolerance=dropout_tolerance, max_saturated=max_saturated)
    ev += [Evidence("n_kept", a.n_kept, "computed"),
           Evidence("dropout_z_um", str(a.dropped_z_um), "measured", "um"),
           Evidence("saturated_z_um", str(a.saturated_z_um), "measured", "um")]
    notes = "; ".join(a.notes)
    if a.n_kept < min_frames:
        return FocusVerdict(Verdict.UNSURE, "sweep",
                            f"only {a.n_kept} readable frames of {len(stats)}"
                            + (f" ({notes})" if notes else ""), evidence=ev)
    kept = [s.score for s, k in zip(stats, a.kept, strict=True) if k]
    hi, lo = max(kept), min(kept)
    contrast = (hi - lo) / max(abs(hi), abs(lo), 1e-12)
    ev += [Evidence("curve_contrast", contrast, "computed"),
           Evidence("peak_edge", a.edge, "computed"),
           Evidence("z_vertex_um", _num(a.z_vertex_um), "computed", "um")]
    if contrast < min_contrast:
        return FocusVerdict(Verdict.UNSURE, "sweep",
                            f"flat curve: contrast {contrast:.3f} < {min_contrast:g}", evidence=ev)

    i = a.argmax_index
    assert i is not None  # n_kept >= min_frames >= 1
    if a.edge == "top":
        return FocusVerdict(Verdict.STEP_UP, "sweep",
                            "peak at the top of the span: focus may be higher",
                            frame_index=i, z_um=float(z_um[i]), evidence=ev)
    if a.edge == "bottom":
        return FocusVerdict(Verdict.STEP_DOWN, "sweep",
                            "peak at the bottom of the span: focus may be lower",
                            frame_index=i, z_um=float(z_um[i]), evidence=ev)
    j = a.nearest_index
    assert j is not None
    ev.append(Evidence("score_at_frame", stats[j].score, "computed"))
    return FocusVerdict(Verdict.IN_FOCUS, "sweep",
                        f"peak inside the span; nearest real frame to the vertex "
                        f"{a.z_vertex_um:.2f} um" + (f" ({notes})" if notes else ""),
                        frame_index=j, z_um=float(z_um[j]), evidence=ev)


# -- mapping 2: one signed model reading ----------------------------------------------------

class ReadingLike(Protocol):
    """What ``dino_autofocus.live.FocusReading`` provides (no import of live here)."""

    score: float | None
    sigma: float | None
    n_used: int
    tiles: list[Any]

    @property
    def sign_known(self) -> bool: ...


def from_reading(reading: ReadingLike, z_um: float | None, frame_index: int | None = None, *,
                 in_focus_dof: float = IN_FOCUS_DOF,
                 max_sigma_dof: float = MAX_SIGMA_DOF) -> FocusVerdict:
    """Verdict from one frame's signed reading; `z_um` is that frame's encoder readback.

    dz (``reading.score``) is in DoF, dz = stage - best focus: dz > 0 means the stage is
    above focus, so the drive should step down.
    """
    dz, sigma = reading.score, reading.sigma
    ev = [Evidence("dz", _num(dz), "model", "DoF"),
          Evidence("sigma", _num(sigma), "model", "DoF"),
          Evidence("n_tiles", len(reading.tiles), "computed"),
          Evidence("n_used", reading.n_used, "model")]

    def v(verdict: Verdict, reason: str) -> FocusVerdict:
        return FocusVerdict(verdict, "dino", reason, frame_index=frame_index,
                            z_um=None if z_um is None else float(z_um), evidence=ev)

    if not reading.tiles:
        return v(Verdict.NO_SAMPLE_HERE, "no tile with sample signal in the frame")
    if dz is None or not math.isfinite(dz):
        return v(Verdict.UNSURE, f"{len(reading.tiles)} tiles, none readable")
    if sigma is None or not math.isfinite(sigma) or sigma > max_sigma_dof:
        return v(Verdict.UNSURE, f"model sigma {sigma} DoF above {max_sigma_dof:g}")
    if abs(dz) <= in_focus_dof:
        return v(Verdict.IN_FOCUS, f"|dz| {abs(dz):.2f} <= {in_focus_dof:g} DoF (model)")
    if reading.sign_known:
        if dz > 0:
            return v(Verdict.STEP_DOWN, f"dz {dz:+.2f} DoF: stage above focus (model)")
        return v(Verdict.STEP_UP, f"dz {dz:+.2f} DoF: stage below focus (model)")
    return v(Verdict.UNSURE, f"dz {dz:+.2f} DoF but |dz| <= sigma {sigma:.2f}: sign unknown")
