"""Bring the focus score to 0 with the piezo z, in small checked steps.

1. probe: +0.5 um, and measure how the score answers (DoF per um, and its sign) -- the
   head's scale on real data and the piezo's direction are both unverified, so neither is
   assumed;
2. step: dz = -score / slope, at most 0.5 um, inside +-5 um of where it started and the
   stage's 0..600 um;
3. done when |score| < 0.3 DoF twice running; stops after 15 steps, on Esc/f, or when a
   step would leave the window.

Each decision uses the median of 5 readings taken from frames after the move settled.
"""

from __future__ import annotations

import time

import numpy as np


class AutoFocusZ:
    """'w': find best focus with the piezo near where it is, by the Vollath F4 peak.

    1. fine: +-1 um at 0.25 um; a clear peak inside -> parabola vertex, move there, done;
    2. peak on an edge: extend that way in 0.5 um steps (to +-5 um of the start), then fine
       again around the new maximum;
    3. Vollath flat (far out of focus): DINO's unsigned score at -2/+2 um says which side is
       less blurred; step there and retry.
    Every plane: the median of `n` frames taken after the move settled. Esc returns to the
    start. The result (z before / after) is the focus-drift record.
    """

    def __init__(self, move_z, read_z, log, out, window_um: float = 5.0, n: int = 5,
                 settle_s: float = 0.35):
        self.move_z, self.read_z, self.log, self.out = move_z, read_z, log, out
        self.z0 = read_z()
        self.window = (max(self.z0 - window_um, 0.0), min(self.z0 + window_um, 600.0))
        self.n, self.settle = n, settle_s
        self.planes: dict[float, dict] = {}
        self.done, self.status = False, "starting"
        self._frames, self._dino, self._since = [], [], 0.0
        self._gen = self._run()
        self._want = next(self._gen)  # first plane to measure
        self._goto(self._want)
        log({"event": "af_start", "z0_um": self.z0, "window_um": list(self.window)})

    # -- plumbing (same contract as ZSweep: feed_frame / feed_dino / stop)
    def _goto(self, z: float) -> None:
        z = float(np.clip(z, *self.window))
        self.cur_z = self.move_z(z, self.window)
        self.cur_target = round(z, 3)
        self._frames, self._dino = [], []
        self._since = time.monotonic() + self.settle

    def stop(self, why: str, back: bool = True) -> None:
        if self.done:
            return
        self.done, self.status = True, f"stopped: {why}"
        if back:
            try:
                self.move_z(self.z0, self.window)
            except Exception as exc:  # noqa: BLE001
                self.status += f" (return failed: {exc})"
        self._save(why)
        self.log({"event": "af_stop", "why": why, "z_um": self.read_z()})

    def feed_frame(self, t: float, metrics: dict) -> None:
        if not self.done and t >= self._since:
            self._frames.append(metrics)
            self._maybe()

    def feed_dino(self, t: float, score: float | None) -> None:
        if not self.done and t >= self._since and score is not None:
            self._dino.append(score)
            self._maybe()

    def _maybe(self) -> None:
        if len(self._frames) < self.n:
            return
        vol = [f["vollath"] for f in self._frames]
        rec = {"z_um": self.cur_z, "vollath": float(np.median(vol)),
               "vollath_sd": float(np.std(vol)),
               "dino": float(np.median(self._dino)) if self._dino else None}
        self.planes[self.cur_target] = rec
        try:
            nxt = self._gen.send(rec)
        except StopIteration:
            return
        except Exception as exc:  # noqa: BLE001
            self.stop(f"error: {exc}")
            return
        self._goto(nxt)

    def _save(self, why: str) -> None:
        import json

        rows = [dict(target_um=k, **v) for k, v in sorted(self.planes.items())]
        self.out.write_text(json.dumps({"why": why, "z0_um": self.z0, "rows": rows,
                                        "result": getattr(self, "result", None)}, indent=1))

    # -- the search
    def _scan(self, zs):
        """Measure each plane (cached), yield-driven; returns sorted (z, rec) list."""
        for z in zs:
            z = round(float(np.clip(z, *self.window)), 3)
            if z not in self.planes:
                yield z
        pts = sorted((k, v) for k, v in self.planes.items())
        return pts

    def _peak(self, pts):
        z = np.array([p[0] for p in pts])
        v = np.array([p[1]["vollath"] for p in pts])
        sd = np.median([p[1]["vollath_sd"] for p in pts]) / np.sqrt(self.n)
        i = int(np.argmax(v))
        prominent = v[i] - np.median(v) > max(6 * sd, 1e-4)
        return z, v, i, prominent

    def _run(self):
        centre = self.z0
        for attempt in range(6):
            self.status = f"fine scan around {centre:.2f} um"
            pts = yield from self._scan(centre + np.arange(-1.0, 1.0001, 0.25))
            local = [p for p in pts if abs(p[0] - centre) <= 1.0001]
            z, v, i, prominent = self._peak(local)
            if prominent and 0 < i < len(z) - 1:
                lo, hi = max(0, i - 2), min(len(z), i + 3)
                p = np.polyfit(z[lo:hi], v[lo:hi], 2)
                zf = float(-p[1] / (2 * p[0])) if p[0] < 0 else float(z[i])
                zf = float(np.clip(zf, z[lo], z[hi - 1]))
                z_now = self.move_z(zf, self.window)
                self.result = {"z_before_um": self.z0, "z_focus_um": zf, "moved_um": zf - self.z0}
                self.done, self.status = True, (f"in focus at {z_now:.2f} um "
                                                f"({zf - self.z0:+.2f} um from start)")
                self._save("complete")
                self.log({"event": "af_done", **self.result})
                return
            if prominent:  # maximum on an edge of the fine scan: walk that way
                step = 0.5 if i == len(z) - 1 else -0.5
                self.status = "peak beyond the scan: extending"
                zc = float(z[i])
                best = v[i]
                while True:
                    zc += step
                    if not self.window[0] <= zc <= self.window[1]:
                        self.stop("focus is beyond the +-5 um window")
                        return
                    rec = yield round(zc, 3)
                    if rec["vollath"] < best:  # passed the peak
                        break
                    best = rec["vollath"]
                centre = zc - step
                continue
            # flat: far from focus; ask DINO which side is less blurred
            self.status = "Vollath flat: probing with DINO at -2 / +2 um"
            a = yield round(float(np.clip(centre - 2, *self.window)), 3)
            b = yield round(float(np.clip(centre + 2, *self.window)), 3)
            if a["dino"] is None or b["dino"] is None or abs(a["dino"] - b["dino"]) < 0.5:
                self.stop("no focus signal within reach (Vollath flat, DINO undecided)")
                return
            centre = centre - 2 if a["dino"] < b["dino"] else centre + 2
        self.stop("no clear peak after 6 attempts")


class ZSweep:
    """Step the piezo z through [z0, z0 + span] and record the focus measures at each plane.

    At every plane, after the move settles, it keeps `n` frames' classical metrics and the
    DINO readings computed from frames taken after the settle; then it moves on. At the end
    it fits a parabola to the top of the Vollath curve and, if the peak lies inside the swept
    range, moves there; otherwise it returns to z0. Results go to `out` (JSON).
    """

    def __init__(self, move_z, read_z, log, out, span_um: float = 10.0, step_um: float = 0.25,
                 n: int = 5, settle_s: float = 0.35):
        self.move_z, self.read_z, self.log, self.out = move_z, read_z, log, out
        self.z0 = read_z()
        lo = max(self.z0 - span_um / 2, 0.0)  # centred on where it is (from 0 if near it)
        hi = min(lo + span_um, 600.0)
        self.window = (lo, hi + 0.01)
        self.targets = list(np.arange(lo, hi + 1e-6, step_um))
        self.n, self.settle = n, settle_s
        self.rows: list[dict] = []
        self.done, self.status = False, "starting"
        self.i = -1
        self._frames: list[dict] = []
        self._dino: list[float] = []
        self._since = 0.0
        log({"event": "zsweep_start", "z0_um": self.z0, "targets": [self.targets[0],
             self.targets[-1], step_um]})
        self._next()

    def stop(self, why: str) -> None:
        if self.done:
            return
        self.done, self.status = True, f"stopped: {why}"
        self._save(why)
        try:
            self.move_z(self.z0, self.window)
        except Exception as exc:  # noqa: BLE001
            self.status += f" (return to z0 failed: {exc})"
        self.log({"event": "zsweep_stop", "why": why, "z_um": self.read_z()})

    def _next(self) -> None:
        self.i += 1
        if self.i >= len(self.targets):
            self._finish()
            return
        z = self.move_z(float(self.targets[self.i]), self.window)
        self.current = {"target_um": round(float(self.targets[self.i]), 4), "z_um": round(z, 4)}
        self._frames, self._dino = [], []
        self._since = time.monotonic() + self.settle
        self.status = f"plane {self.i + 1}/{len(self.targets)} at {z:.2f} um"

    def feed_frame(self, t: float, metrics: dict) -> None:
        if self.done or t < self._since:
            return
        self._frames.append(metrics)
        self._maybe_advance()

    def feed_dino(self, t: float, score: float | None) -> None:
        if self.done or t < self._since or score is None:
            return
        self._dino.append(score)
        self._maybe_advance()

    def _maybe_advance(self) -> None:
        if len(self._frames) < self.n or len(self._dino) < min(self.n, 3):
            return
        row = dict(self.current)
        for k in self._frames[0]:
            row[k] = float(np.median([f[k] for f in self._frames]))
        row["dino"] = float(np.median(self._dino))
        row["dino_abs"] = abs(row["dino"])
        row["dino_all"] = [round(s, 3) for s in self._dino]
        self.rows.append(row)
        try:
            self._next()
        except Exception as exc:  # noqa: BLE001
            self.stop(f"error: {exc}")

    def _peak(self, key: str, sign: float = 1.0):
        z = np.array([r["z_um"] for r in self.rows])
        v = sign * np.array([r[key] for r in self.rows])
        i = int(np.argmax(v))
        if i == 0 or i == len(v) - 1:
            return None, i  # maximum on the edge of the sweep: no peak inside it
        lo, hi = max(0, i - 3), min(len(v), i + 4)
        p = np.polyfit(z[lo:hi], v[lo:hi], 2)
        if p[0] >= 0:
            return None, i
        return float(-p[1] / (2 * p[0])), i

    def _finish(self) -> None:
        zv, _ = self._peak("vollath")
        zd, _ = self._peak("dino_abs", -1.0) if self.rows else (None, 0)
        self.result = {"vollath_peak_um": zv, "dino_min_abs_um": zd}
        target = zv if zv is not None and self.window[0] <= zv <= self.window[1] else self.z0
        self.done = True
        self._save("complete")
        z = self.move_z(float(target), self.window)
        self.status = (f"done: Vollath peak at {zv:.2f} um, moved there (z {z:.2f})"
                       if zv is not None else f"done: no Vollath peak inside; back at {z:.2f}")
        self.log({"event": "zsweep_done", **self.result, "moved_to_um": z})

    def _save(self, why: str) -> None:
        import json

        self.out.write_text(json.dumps({"why": why, "z0_um": self.z0, "rows": self.rows,
                                        "result": getattr(self, "result", None)}, indent=1))


class FocusServo:
    def __init__(self, move_z, read_z, log, step_um: float = 0.5, window_um: float = 5.0,
                 tol_dof: float = 0.3, n_avg: int = 5, settle_s: float = 0.35,
                 max_steps: int = 15):
        self.move_z, self.read_z, self.log = move_z, read_z, log
        self.step, self.tol, self.n, self.settle = step_um, tol_dof, n_avg, settle_s
        self.max_steps = max_steps
        self.z0 = read_z()
        # +-window around the start, inside the stage's own 0..600 um travel
        self.window = (max(self.z0 - window_um, 0.0), min(self.z0 + window_um, 600.0))
        self.slope = None  # DoF per um of piezo z
        self.done, self.status = False, "measuring the score here"
        self._buf: list[float] = []
        self._since = time.monotonic()
        self._gen = self._run()
        next(self._gen)
        log({"event": "servo_start", "z0_um": self.z0, "window_um": list(self.window)})

    def stop(self, why: str) -> None:
        if not self.done:
            self.done, self.status = True, f"stopped: {why}"
            self.log({"event": "servo_stop", "why": why, "z_um": self.read_z(),
                      "slope_dof_per_um": self.slope})

    def feed(self, t_read: float, score: float | None) -> None:
        """A score reading (offset already applied) computed at monotonic time t_read."""
        if self.done or score is None or t_read < self._since:
            return
        self._buf.append(score)
        if len(self._buf) < self.n:
            return
        med = float(np.median(self._buf))
        self._buf = []
        try:
            self._gen.send(med)
        except StopIteration:
            self.done = True
        except Exception as exc:  # noqa: BLE001 - any failure stops motion, says why
            self.stop(f"error: {exc}")

    def _go(self, target: float) -> float:
        if not self.window[0] <= target <= self.window[1]:
            raise ValueError(f"target {target:.3f} um is outside the +-5 um window")
        z = self.move_z(target, self.window)
        self._since = time.monotonic() + self.settle
        self.log({"event": "servo_move", "target_um": round(target, 4), "z_um": round(z, 4)})
        return z

    def _run(self):
        s0 = yield
        z = self.read_z()
        self.log({"event": "servo_score", "z_um": z, "score": s0})
        if abs(s0) < self.tol:
            self.stop(f"already in focus (score {s0:+.2f})")
            return
        # 1. probe
        self.status = "probing +0.5 um"
        z1 = self._go(z + self.step)
        s1 = yield
        self.slope = (s1 - s0) / (z1 - z)
        self.log({"event": "servo_probe", "dz_um": z1 - z, "score_before": s0,
                  "score_after": s1, "slope_dof_per_um": self.slope})
        if abs(s1 - s0) < 0.3:
            self.stop(f"score barely moved over the probe ({s0:+.2f} -> {s1:+.2f}); "
                      "cannot steer by it here")
            return
        z, s, good = z1, s1, 0
        # 2. step towards 0
        for i in range(self.max_steps):
            if abs(s) < self.tol:
                good += 1
                if good >= 2:
                    self.stop(f"in focus: score {s:+.2f} at z {z:.3f} um "
                              f"({z - self.z0:+.3f} um from start)")
                    return
            else:
                good = 0
            dz = float(np.clip(-s / self.slope, -self.step, self.step))
            if abs(s) < self.tol:
                dz *= 0.5  # inside tolerance: confirm with a half step, don't chase noise
            target = z + dz
            if not self.window[0] <= target <= self.window[1]:
                lim = ("the piezo's lower limit (0 um)" if target < 0.0
                       else "the +-5 um window")
                self.stop(f"next step to {target:.3f} um would pass {lim}; "
                          + ("raise the piezo and refocus with ZDrive first"
                             if target < 0 else "score may be off-scale here"))
                return
            self.status = f"step {i + 1}: score {s:+.2f} -> moving {dz:+.3f} um"
            z = self._go(target)
            s = yield
            self.log({"event": "servo_score", "z_um": z, "score": s})
        self.stop(f"not converged in {self.max_steps} steps (score {s:+.2f})")
