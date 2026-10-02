# T-032 WP-I: sample map operation (engine side)

- Owner: AF 실행10
- Prerequisites: pure parts now; the op itself after T-011, T-027 (events) and T-031 (scan_4x outputs) merge
- Branch: `exec10/T-032-sample-map`
- Review: AF 검토보조2
- Screen contract: `docs/screens/map.md` (T-102). Spec: `docs/operations-spec.md` sample_map. PLAN v1.2 conventions.

## Owned paths

- `src/dino_autofocus/engine/operations/sample_map.py`, `src/dino_autofocus/engine/mosaic.py`
- `tests/engine/test_operations_sample_map*.py`, `tests/engine/test_mosaic*.py`

## Content

1. Now (pure, numpy/scipy only): build a mosaic from scan_4x tile outputs (`mosaic.npy`/`mosaic.json`:
   orientation "stage", `M_px_per_um`, objective, `n_tiles`); stage-to-mosaic pixel mapping with the mirrored
   image convention; classical particle-candidate detection (marked as candidates, grade "computed").
2. After the prerequisites: `sample_map` op (brightfield 4x mosaic using scan_4x), `goto_xy` click-move through the
   guards (large moves only with Z retracted, box check), candidates and flags written as sample events through
   T-027 (`map_flag`, `map_flag_retire`, `candidate_confirm`, `candidate_reject`; engine assigns ids; reject is a
   new entry with source "person_rejected"). `goto_xy` event payloads and `scan_box_um`/`allowed_box_um` in summary.
- Tests on MockBackend (T-021) when merged.

## Done when

- Common criteria, trailer `Session: AF 실행10`. Send `[검토요청 T-032]` to AF 검토보조2.

## edge_trace follow-up (owned path addition: `engine/operations/edge_trace.py`, this change only)

- edge_trace writes a stable `hole["closed_loop"] = True | False` at finish, so `sample.hole_loop()` (T-027) need
  not match the stop text. Keep `trace_stop` and `arc_deg` as they are.

## From T-027c (b602da5)

- The fold now keeps retired flags and per-id history. Stage 2 uses `active_flags()` / `open_candidates()` for what
  is in play; never treat every entry in `flags` as active.

## T-032b (AF 실행10, before T-026 stage 2; review AF 검토보조2) — every op registers in the running server

- `server/app.py` imports only `engine.operations.sample_ops`, so status, light_set, edge_trace, scan_4x,
  focus_100x and objective_change never register in the server (the registry fills on import). Add
  `engine/operations/__init__.py` that imports every op module (manager decision, option b). Because importing
  `engine.operations.sample_ops` runs the package `__init__`, `app.py` needs no change. Hardware ops register through
  `register_hardware` (T-028/T-009g); importing their module must stay side-effect-free. Test: a server built by
  `create_app` lists every op name from the operations spec in its runner registry.

## Stage 2 note (manager): edge_trace writes sample events

- Use the fold's existing kinds: `boundary_clear` on replace, `boundary_point` per point, and `hole_fit` for the fit
  (`records.events.fold` already sets `state.hole` from it). No new kind needed. Stop writing map.json / sample.json
  directly; they are derived views.
