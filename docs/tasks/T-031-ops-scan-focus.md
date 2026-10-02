# T-031 WP-C part 2: scan_4x and focus_100x operations, focus helpers

- Owner: AF 실행11 (after T-023)
- Prerequisites: T-002 merged (done), T-015, T-021 (MockBackend). Register with the T-011 runner when it lands.
- Branch: `exec11/T-031-ops-scan-focus`
- Review: AF 검토보조2
- Spec: `docs/operations-spec.md` (scan_4x, focus_100x). PLAN v1.2 conventions.

## Owned paths

- `src/dino_autofocus/engine/operations/scan_4x.py`, `focus_100x.py`
- `src/dino_autofocus/focus/classical.py` (additions only: the three helpers below)
- `tests/engine/test_operations_scan*.py`, `test_operations_focus*.py`, `tests/focus/test_focus_helpers*.py`

## Content

- `scan_4x`: tiles serpentine; XY tile moves allowed at sample Z by the per-objective table (4x); sweeps ascend;
  2 % light-dropout filter; writes `scan4x_<stamp>/` with engine `log.jsonl`, `summary.json`, legacy `scan.json`,
  plus `mosaic.npy` and `mosaic.json` (orientation "stage", `M_px_per_um`, objective, `n_tiles`) and
  `scan_box_um` / `allowed_box_um` in the summary.
- `focus_100x`: peak metric; refuses to climb when the peak is at the top of the span and raises
  `confirm_required` instead; ceiling from guards. Args per `docs/screens/objective.md`.
- Focus helpers in `focus/classical.py` (from 실행2's memo): `block_scores(img, n=6)`, a parabola wrapper
  that returns None at the ends, double-peak detection ("check immersion oil").
- A helper that gives the 4x focus plane at the current XY (default centre for focus_100x), from the last scan.
- Grades: z values are "measured"; vertices and metrics "computed"; nothing "model" goes into a guard.

## Done when

- Common criteria, trailer `Session: AF 실행11`. Send `[검토요청 T-031]` to AF 검토보조2.

## mm_demo_core follow-up (T-023 merge review, 0b25f78)

- `DemoDevices.set_and_read` is public and writes any property with no allow-list. Make it private again
  (`_set_and_read`) or run `check_set_property` inside it, so no later caller can bypass the guards. Small fix,
  allowed in this task (owned path addition: `engine/backends/mm_demo_core.py`, this change only).
