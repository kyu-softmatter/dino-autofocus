# T-027 WP-H: sample operations and geometry (engine side)

- Owner: AF 실행1 (wrote `sample.py` in T-002-3)
- Prerequisites: T-002 stages 2 and 3 merged. T-011 (runner) not required: implement the ops against the
  T-002 operation lifecycle and register them when T-011 lands
- Branch: `exec1/T-027-sample-ops`
- Review: AF 검토보조1
- Screen contract: `docs/screens/sample.md` (T-103, 5ca7f7e). Op names are fixed by it.

## Owned paths

- `src/dino_autofocus/engine/sample.py` (geometry part and the event reader)
- `src/dino_autofocus/engine/operations/sample_ops.py`
- `tests/engine/test_operations_sample*.py`

## Storage (manager decision)

- Source of truth: append-only events in the open experiment session's `records/sample_events.jsonl` (T-019).
  One reader in `sample.py` folds the events into the current sample state. It feeds the sample screen,
  the map screen, `awaiting_return` and the last-session fields.
- `D:\AutoFocus\samples\<sample_id>\` (legacy root, outside git) keeps derived views (`sample.json`,
  `map.json`) and large files, regenerated from the events so the old tools still work.
- `sample_new` writes a `sample_created` event and assigns the id (`YYYYMMDD_HHMM_n`). It returns the id in
  `finished.data.summary.sample_id`.

## Ops

`sample_open{sample_id}`, `sample_new{}`, `sample_geometry_set{sample_id, values}`,
`loading_confirm_person{sample_id}`, `loading_check_image{sample_id}`. "Open folder" is a route, not an op.

- Permissions (rule 12, D15): all five need a local operator with the control token and an open session.
  They use the existing OPERATE action, because geometry feeds safety limits and `sample_open` changes the
  sample that motion ops use. No new named action.
- `loading_check_image` result: `{ok, metric, value, grade: "computed", why, frame_ref}`. Its gate entry
  (camera, DiaLamp, 4x) is in T-028.
- `sample_thickness` and `orientation` have no default. Ops that depend on them refuse while they are
  `not_set`. Validate `orientation` against `ORIENTATIONS`.
- Loading state is per session and sample. It resets on a new session or `sample_open`. Steps 2 and 3 clear
  if a safety field changes after confirmation (screen manager decision G6).

## Notes from the T-002-3 pre-review (검토보조1)

- `SampleGeometry.from_dict` raises TypeError on an unknown key. Keep extras, as `SampleInfo` does.
- Document the 20000-visit cap in `save_map`.
- Use `ORIENTATIONS` in validation (it is unused today).

## Done when

- Common criteria, trailer `Session: AF 실행1`. Tests use `tmp_path` for both the session folder and the
  legacy root. Send `[검토요청 T-027]` to AF 검토보조1.
