"""`light_set{mode, line, percent}`: switch the light by meaning, nothing moves (ui-spec 4.3, D15).

Modes (ui-spec 7.2 "Brightfield on" / "Aura <line> <pct> % on"):

- `brightfield`: Aura off, DiaLamp on (`lamp_on`).
- `aura`: DiaLamp off, the Aura line at `percent` % (per-mille inside the backend), master on.
- `off`: everything off (`all_off`). The pre-emptive stop is the runner's `lights_off` command
  kind; this mode is the same switch-off asked for as a setting.

Allow-list: the four Aura lines and the DiaLamp, through the backend's meaning-level methods
only, never `set_property`. Every switch is read back; a readback that does not verify switches
everything off again and the operation ends in `error`. On success the light stays as set
(the runner's `keep_lights_on_finish`); every other exit path switches off.

Who may run it (D15: M3, operator with the control grant, open session) is the runner's
permission table (`light_set` is a light action there), not this module.

Until T-015 / T-002-4 land: `switch` calls the backend light methods directly. It is the one
place to change when the methods take the control token and the guarded helpers exist.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path

from ..backend import Backend, Readback
from ..events import Event, EventSink, fan_out, null_sink
from ..guards import lights_off, snapshot
from ..records import OpRecord

NAME = "light_set"
MODES = ("brightfield", "aura", "off")
# the Aura lines of the bench light engine; T-015 moves the allow-list next to the protocol
AURA_LINES = ("VIOLET", "CYAN", "GREEN", "RED")
MAX_PERCENT = 100.0


@dataclass(frozen=True)
class LightRequest:
    mode: str
    line: str | None = None
    percent: float | None = None

    def describe(self) -> str:
        if self.mode == "brightfield":
            return "Aura off, DiaLamp on. Nothing moves."
        if self.mode == "aura":
            return f"DiaLamp off, Aura {self.line} at {self.percent:g} %. Nothing moves."
        return "Aura off, DiaLamp off. Nothing moves."


def parse(args: dict) -> LightRequest:
    """Check `args` against the allow-list; ValueError says what is wrong."""
    extra = sorted(set(args) - {"mode", "line", "percent"})
    if extra:
        raise ValueError(f"unknown light_set arguments: {extra}")
    mode = args.get("mode")
    if mode not in MODES:
        raise ValueError(f"mode {mode!r} is not one of {MODES}")
    if mode != "aura":
        if args.get("line") is not None or args.get("percent") is not None:
            raise ValueError(f"mode {mode!r} takes no line or percent")
        return LightRequest(mode)
    line = str(args.get("line") or "").upper()
    if line not in AURA_LINES:
        raise ValueError(f"Aura line {args.get('line')!r} is not one of {AURA_LINES}")
    try:
        pct = float(args.get("percent"))
    except (TypeError, ValueError):
        raise ValueError(f"percent {args.get('percent')!r} is not a number") from None
    if not math.isfinite(pct) or not 0 < pct <= MAX_PERCENT:
        raise ValueError(f"percent {pct} must be in (0, {MAX_PERCENT:g}]")
    return LightRequest("aura", line, pct)


def plan(args: dict) -> dict:
    req = parse(args)
    return {"op": NAME, "text": req.describe(), "request": asdict(req)}


def switch(backend: Backend, req: LightRequest) -> list[Readback]:
    if req.mode == "brightfield":
        return backend.lamp_on()
    if req.mode == "aura":
        return backend.aura_line_on(req.line, req.percent)
    return backend.all_off()


def run_light_set(backend: Backend, parent: Path, args: dict, sink: EventSink = null_sink, *,
                  user_id: str | None = None, session_id: str | None = None) -> dict:
    """Switch, read back, record `<parent>/light_set_<stamp>/`. Returns the result dict.

    Raises ValueError before anything is switched if `args` fail the allow-list."""
    req = parse(args)
    rec = OpRecord(parent, NAME, start_state=snapshot(backend), user_id=user_id,
                   session_id=session_id)
    emit = fan_out(rec.sink, sink)
    emit(Event("started", rec.op_id, {"op": NAME, "args": dict(args), "user_id": user_id,
                                      "session_id": session_id}))
    status, error, result, lights = "error", None, None, None
    try:
        rbs = switch(backend, req)
        emit(Event("light_changed", rec.op_id, {"readbacks": [asdict(r) for r in rbs]}))
        bad = [f"{r.device}.{r.prop} wanted {r.wanted}, read {r.read}" for r in rbs
               if not r.verified]
        if not rbs:
            bad = ["the backend returned no readback"]
        if bad:
            error = "light not verified: " + "; ".join(bad)
            emit(Event("error", rec.op_id, {"error": error}))
        else:
            status = "finished"
            result = {"mode": req.mode, "line": req.line, "percent": req.percent,
                      "readbacks": [asdict(r) for r in rbs], "verified": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        emit(Event("error", rec.op_id, {"error": error}))
        raise
    finally:
        if status == "finished":
            lights = {"switched_off": False, "why": "light_set leaves the light as set",
                      "state": backend.light_state(), "verified": None}
        else:
            lights = {"switched_off": True, **lights_off(backend)}
        emit(Event("light_changed", rec.op_id, lights))
        if status == "finished":
            emit(Event("finished", rec.op_id, {"error": None}))
        rec.finish(status, lights=lights, end_state=snapshot(backend), result=result,
                   error=error)
    return {"status": status, "error": error, "result": result, "record": str(rec.dir)}
