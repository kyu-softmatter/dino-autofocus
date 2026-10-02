# T-039 `z_retract` operation (first engine motion on the stand)

- Owner: AF 실행1 (guards owner)
- Prerequisites: T-032b merged (engine/operations/__init__.py imports every op module). If it has not merged when you
  start, branch anyway and add the import line after it lands.
- Branch: `exec1/T-039-z-retract-op`
- Review: AF 검토보조1
- Decision: director (2026-10-02, answer to T-038). Low priority, but before T-032 stage 2 if possible. It becomes
  runbook step 2a in `docs/runbooks/first-bench-motion.md`: away from the sample, the safest direction, testing the
  lock lift, readback and records before any XY move.

## Owned paths

- `src/dino_autofocus/engine/operations/z_retract.py` (new), one import line in `engine/operations/__init__.py`
- `tests/engine/test_operations_z_retract.py`

## Content

- `start z_retract {}`: moves Z to `z_safe` (`RETRACT_Z_UM` / `Z_SAFE_UM` = 0 µm) through `FocusAxis.retract()` in
  engine/guards.py; no args.
- Refuses only what every motion op refuses: the T-036 lock on mm-real while `BENCH_MOTION` is locked, and rule 12
  (local operator with the control token and an open session). No clearance callback needed (it moves away from
  the sample); no gate beyond the Z drive being present.
- Readback: the read Z after the move, compared within the guards' Z tolerance; a mismatch fails the op with the
  commanded and read values. Recorded like every op (`finished.data.summary` with commanded, readback, verified;
  lights end state per T-011e).
- Already at z_safe: succeeds with no move, records the readback.
- Tests (mock and FakeBackend with bench=True): moves to 0 and verifies; already at 0 is a no-op success; refused
  while locked (mm-real lock stand-in) and without control or session; a readback mismatch fails.

## Done when

- Common criteria, your own test files plus ruff (sessions.md run rule). Trailer `Session: AF 실행1`.
  Send `[검토요청 T-039]` to AF 검토보조1. When it merges, tell AF 실행11 (T-038 runbook step 2a).
