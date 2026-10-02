# T-027 WP-H: sample operations and geometry (engine side)

- Owner: AF 실행1 (wrote `sample.py` in T-002-3)
- Prerequisites: T-002 stages 2 and 3 merged, and T-019 merged (records/events.py fold, session.sample_event). T-011 (runner) not required: implement the ops against the
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
- `sample_new` only reserves the id (`YYYYMMDD_HHMM_n`) and the legacy folder, and returns the id in
  `finished.data.summary.sample_id`. It writes no event. When an experiment session opens for a sample
  that has no events yet (engine sees it through `set_experiment_session`), the engine writes
  `sample_created` as the first event in that session's `sample_events.jsonl` (manager decision, option (b)).

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

## Session and sample (manager decision, answers 실행1)

- One sample per experiment session, as T-019 is written. `sample_open` and `sample_new` run with no session
  open (they choose the sample for the next session; nothing moves) and refuse with `preflight_failed` when a
  session is open for a different sample. `sample_geometry_set`, `loading_confirm_person` and
  `loading_check_image` need the open session of that sample.
- Build on the T-019 API. `geometry_set` and `loading_step` are new sample-event kinds written through
  `session.sample_event()`. Do not edit `records/*`.

## Boundary ops (added)

- `boundary_mark`, `boundary_undo`, `boundary_reset` are sample events too (no hardware), so they live here.
  They are record-only ops that run beside a hardware op (T-011). They need an open session.

## One fold, one projection (manager decision, from T-106)

- `records.events.fold()` (T-019) is the only fold. It stays generic and keeps unknown kinds in `.other`.
- `engine/sample.py` calls it and projects the result into one named view (geometry, loading steps, boundary,
  flags, candidates, awaiting_return, last session). The sample, map and sessions screens all read that view
  through the server. `records/*` is not edited for engine kinds.

## guards.py follow-up (from T-002-4 pre-review)

- In `operation()`'s error branch, `rec.sink(ev)` runs outside the try, so a failing record writer (disk full)
  still replaces the original exception. Move it inside, keep the original, test it.
- Same fix in the `finally` loop (reviewer, 5006a4a merge).
- SAFETY (reviewer, before M3/M4): `approach()` refuses on a non-mock backend when `clearance` is None. This is
  defence in depth next to the T-011 runner check. Test with a bench-flagged FakeBackend.
- guards table (PLAN v1.3, fbc1e08): add the F5 step-out as data, `escape_dy_um = +15000` (sign +Y, 15 mm), marked
  "unmeasured provisional", plus a check that refuses a step-out beyond the stage Y limit read from the backend.
- Reader: expose whether the current hole fit came from a closed loop (`trace_stop`, `arc_deg`), next to
  `fitted_at`, so the re-trace rule and scan_4x can tell a partial arc from a full fit.
- `hole_loop()` prefers `hole["closed_loop"]` when present (T-032 adds it); the text match and the
  FULL_LOOP_ARC_DEG = 330 (unmeasured provisional) rule stay only for older fits.
