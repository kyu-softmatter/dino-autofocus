# T-033 WP-B: mm-real backend (Backend protocol on the real Ti2 / Kinetix / Aura / piezo)

- Owner: AF 실행12
- Prerequisites: T-002, T-015, T-021, T-023 merged (done)
- Branch: `exec12/T-033-mm-real-backend` (create from a hash)
- Review: AF 검토보조2

## Owned paths

- `src/dino_autofocus/engine/backends/mm_real.py`
- `tests/engine/test_backends_mm_real.py`

## Content

- The T-002 + T-015 Backend protocol over pymmcore-plus with the bench config
  (`C:\agentic_microscope\config\micromanager\single_cam_red_noDMD_nocom10.cfg`, path from settings), ported from
  `scripts/mm_grab.py` (`open_core`, `set_and_read`, `aura_on/off`, `positions`, `PiezoReader`). pymmcore imported
  inside functions only. AutoShutter off right after load (as mm_grab does).
- Same allow-lists and token checks as mock/mm-demo (`check_set_property`, MOTION_DEVICES, light allow-list). Pass
  T-015's `BackendContract` parametrised against the demo config (skip without adapters).
- Bench-flagged (`info().bench = True`) so the guards and runner require a clearance callback for `approach()`.
- Piezo: read-only `piezo_read()`; no piezo moves (operations-spec 9.2, M5).
- Readout property candidate `ReadoutRate` stays out of the camera allow-list (checklist).
- No hardware runs on this desktop. Anything that can only be checked on the microscope PC goes into the review
  request as "user check needed" and into the checklist via the manager.

## Done when

- Common criteria, trailer `Session: AF 실행12`. Send `[검토요청 T-033]` to AF 검토보조2.
