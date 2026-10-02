# T-030 WP-C part 1: status, light_set and edge_trace operations

- Owner: AF 실행10
- Prerequisites: T-002 merged (done). T-015 for the token light methods. Register with the T-011 runner when it
  lands; until then implement against the T-002 operation lifecycle.
- Branch: `exec10/T-030-ops-status-light-edge`
- Review: AF 검토보조2
- Spec: `docs/operations-spec.md` (status, lights_off, edge_trace). Screen contracts: `docs/screens/hardware.md`,
  `docs/screens/map.md`. PLAN v1.2 conventions (mirrored image, serpentine, Z up toward sample).

## Owned paths

- `src/dino_autofocus/engine/operations/status.py`, `light_set.py`, `edge_trace.py`
- `tests/engine/test_operations_status*.py`, `test_operations_light*.py`, `test_operations_edge*.py`

## Content

- `status`: read-only snapshot op; writes a record folder only when the user asks (periodic status comes from
  `position` events).
- `light_set{mode, line, percent}`: D15 (M3, operator + control + open session), allow-list, through the guarded
  light helpers (T-002-4). `lights_off` is a runner command kind, not this op.
- `edge_trace{hole_diameter_mm, ...}`: port of `scripts/edge_track.py` and the `t` tracking in live_focus.
  Uses the acquisition stream (T-011), XY relative moves (T-015 `xy_move_rel`) through the guards, the image to
  stage mapping `stage + inv(M) @ (centre - p)` with the 2026-09-30 4x M as initial calibration, and the `update`
  command for `+`/`-` speed. Operator-watched (D14). Boundary points are written via T-027's boundary ops.
- Tests on MockBackend (T-021) when merged, FakeBackend before.

## Done when

- Common criteria, trailer `Session: AF 실행10`. Send `[검토요청 T-030]` to AF 검토보조2.
