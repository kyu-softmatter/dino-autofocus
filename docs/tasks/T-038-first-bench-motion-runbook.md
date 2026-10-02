# T-038 Runbook: first motion on the stand (after the T-036 unlock)

- Owner: AF 실행11
- Prerequisites: none to write it. It is used after the T-036 unlock commit merges.
- Branch: `exec11/T-038-first-bench-motion-runbook`
- Review: AF 검토보조1 (guards and bench rules), then AF 검토. The director confirms the content.
- Decision: director, in reply to the manager's lift plan (2026-10-02). First motion on the stand is gated by this
  runbook, not by code. The code already fails safe on steps 4 and 5.

## Owned paths

- `docs/runbooks/first-bench-motion.md` (new). No code, no tests.

## Content, in this order

1. On the microscope PC, run the cfg checks from `docs/microscope-pc-checklist.md`. `mm-real` `open()` must succeed with
   no `UnsafeConfig` (T-036b/T-036d). Write down whether System/Shutdown is applied at unload.
2. 4x only: retract Z to 0, then small XY moves well inside the stage, with the user watching and the abort
   reachable (the console stop and the local abort route). Name the exact moves and the expected readbacks.
3. No 100x Oil approach until Q13 (`approach_step_um`) and Q20 (XY move needing a Z retract, `z_safe`) in
   `docs/operations-spec.md` 10 are answered on the microscope PC.
4. No F5 objective change on the stand until the stage limits and the +Y 15 mm step-out are measured. mm-real
   already refuses F5 when the limits are unknown; keep it that way.
5. Lenses without a `FREE_WD_UM` entry stay refused as rotation targets, as now.

For each step: who does it (the user), what the screen shows, which readback confirms it, and how to stop. Link to
the cards that enforce each rule (T-027b, T-029c, T-036b/d), and say "unmeasured provisional" wherever a value is.

## Done when

- The file exists with steps 1-5 and links. Plain English, short steps, no window-opening commands.
  Send `[검토요청 T-038]` to AF 검토보조1. Trailer `Session: AF 실행11`.

## Step 2 route (manager, from 실행11)

- No registered op moves XY or retracts Z on request on main today. The Z retract and the turn to 4x are done by hand
  at the stand (the 9/30 run ended on 100x Oil at Z 498 µm). Engine XY moves use `goto_xy` from T-032 stage 2
  (실행10), marked "blocked until T-032 stage 2 merges".
- The runbook says plainly: never use `scripts/*` to move the stand; they bypass the guards and the T-036 lock.
- Step 1 relies on mm-real `open()`; the checklist command skips the role-mismatch check (passed to the director).
