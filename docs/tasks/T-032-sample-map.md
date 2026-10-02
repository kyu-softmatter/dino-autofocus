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
