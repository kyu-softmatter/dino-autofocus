# T-029 WP-J: objective change with immersion loading (engine side)

- Owner: unassigned (next free engine seat)
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
- `escape_dy_um` has no default (preflight refuses). `approach_step_um`: see the checklist; until measured,
  use the guards table value marked "unmeasured provisional".
- The F5 Y step-out sign is still open with the user. Take it from the guards table, not a literal.
