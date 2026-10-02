# T-036 SAFETY: lock bench motion on mm-real until the clearance guards land (TOP PRIORITY)

- Owner: AF 실행12 (wrote mm_real.py). Pause T-034 and do this first.
- Prerequisite: T-033 merged (569693a)
- Branch: `exec12/T-036-mm-real-motion-lock` (from a hash)
- Review: AF 검토보조2, then AF 검토. Both take it ahead of other traffic.
- Director's SAFETY direction (PLAN rule 2: safety is decided by code).

## Owned paths

- `src/dino_autofocus/engine/backends/mm_real.py`, `tests/engine/test_backends_mm_real*.py`

## Content

- A module constant `BENCH_MOTION = "LOCKED"` that ships locked. While locked, every motion method on mm-real
  (move_z / z moves, move_xy, move_xy_rel, set_nosepiece, PFS on, and any path that guards' approach/sweep reaches)
  raises with the named reason "bench motion locked until clearance guards land (T-027, T-011)".
- Allowed while locked: status reads, positions, frames and streams, describe/config reads, D15 light on/off, PFS off.
- The lock can be lifted only by a reviewed commit that changes the constant. No runtime argument, environment
  variable, config or setting may lift it; a test asserts the constant is read nowhere else.
- Tests: every motion method refuses on mm-real while LOCKED (demo adapter config, skip without it); mock and mm-demo
  are unaffected.

## Lifting

- After T-027 (guards: approach refuses without clearance on bench) and the T-011 bench check are both on main, one
  commit flips the constant, with the manager's and the director's confirmation. The director then removes the
  checklist warning.

## Done when

- Common criteria, trailer `Session: AF 실행12`. Send `[검토요청 T-036] SAFETY top priority` to AF 검토보조2.

## T-036b follow-up (from the T-036 pre-review): startup preset must not move the stand

- `open()` loads the bench config, and Micro-Manager applies its System/Startup preset (and any preset run at load)
  automatically. Before loading, parse the `.cfg` text and refuse with a named reason if any preset applied at load
  sets a property of a MOTION_DEVICES device (ZDrive / XYStage position, Nosepiece State, PFS on/offset).
  Light-path and shutter settings stay allowed. Record what the preset sets in `config_record()`.
- Tests with small synthetic `.cfg` files (one clean, one with a motion property in Startup).
- Owner AF 실행12, review AF 검토보조2, priority right after T-036 merges.
