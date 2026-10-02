# T-029 WP-J: objective change with immersion loading (engine side)

- Owner: AF 실행3 (after T-007)
- Prerequisites: T-002 stages 2 and 3, T-011, T-021 (MockBackend)
- Branch: `execN/T-029-objective-change`
- Review: AF 검토보조1
- Screen contract: `docs/screens/objective.md` (T-104). Spec: `docs/operations-spec.md` objective_change (F5).

## Owned paths

- `src/dino_autofocus/engine/operations/objective_change.py`, `tests/engine/test_operations_objective*.py`

## Op names and args (fixed by the screen contract)

- Rotate: `start objective_change {target_state, escape, approach_target_um, approach_step_um}`.
- Loading done: `confirm {op_id, args: {key: "load_immersion", ok: true}}` (manual_step, local only).
- Resume after `awaiting_return`: `start objective_change {resume: true}`.
- Re-load immersion without rotating: `start objective_change {reload: true}` (no `target_state`).
- Progress events for steps 2-6: `progress.data = {step, axis, commanded, readback, pfs_in_range, label_read}`.

## Rules

- PLAN 2 F5 seven steps, the guards from T-002 (large XY only with Z retracted, stepwise Z approach),
  `awaiting_return` on interruption after escape or rotation.
- `escape_dy_um` = +15000 µm (guards table, provisional). `approach_step_um` comes from the per-objective guards
  table column (T-002-4, 10 µm, "unmeasured provisional"). Approach: one move 0 → 2800 µm, then steps up
  with the clearance check live at every step.
- F5 step-out (PLAN v1.3, fbc1e08): +Y, 15 mm, both "unmeasured provisional", from the guards table, not a
  literal. Preflight reads the stage Y limit and refuses if the step-out would exceed it. Confirm on the bench
  before M4.

## Clearance callback required (from T-002-4 pre-review)

- `approach(clearance=None)` runs without a clearance check. `objective_change` always passes a real clearance
  callback, and on bench backends (mm-real) the op refuses in preflight without one. Mock/demo may pass a stub.
- Progress key for the step-7 approach: `step_index` (the approach step number; `step` is the F5 step).
