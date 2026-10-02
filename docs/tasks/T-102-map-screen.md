# T-102 WP-I sample map screen (F4): server router and web area

- Owner: AF 실행20
- Package: WP-I screen part (PLAN.md 2절 F4, 9절). Assigned by AF 업무분배보조 (screen areas)
- Prerequisites: stage A none. Stage B: T-009 (server skeleton) and T-010 (web shell) first skeleton merged.
  The engine side (`edge_trace`, `scan_4x`, `sample_map`, `goto_xy`, `map_flag`, boundary operations,
  proposed `map_flag_retire`, `candidate_confirm`, `candidate_reject`) is the manager's WP-C/WP-I work;
  until it merges, tests use a fake engine with the same command names and a fixture sample folder
- Branch: `exec20/T-102-map-screen`
- Review: `[검토요청 T-102]` to AF 검토보조4 (AF 검토보조3 if 4 has more than three queued)

## Owned paths

- Stage A: `docs/screens/map.md` (new)
- Stage B: `src/dino_autofocus/server/api/map.py`, `tests/server/test_api_map.py`,
  `tests/server/fixtures/map/` (small fixture sample), `web/src/features/map/`

Not yours: `engine/` (operations, `sample.py`), the rest of `server/` (T-009), `web/` outside
`features/map/` (T-010; `live` keys `b`/`u`/`t` are the shell's and send the same commands),
`web/src/app/assistant/` (T-014), `web/package*.json`, `pyproject.toml`.

## Content

Spec: `docs/ui-spec.md` 5.1, 5.3, 7.0 and 7.4 (branch `exec5/T-004-ui-spec`, 6fcd8a8, until it merges);
`docs/operations-spec.md` 3, 6 and 8절. Cite them; do not restate them.

Stage A, contract (short, English):
- Endpoints: map state (boundary points, hole fit with `fitted_at`, visited fields, scan boxes), the
  result list (`scan4x_*`, `sample_map_*`), mosaic image for one result (server renders `mosaic.npy` +
  `mosaic.json` to an image and handles the flip from the calibration sign), flags, candidates.
  Commands through T-009's `POST /api/commands` and `update(op_id, …)` for edge-trace speed.
  Events read: `map_changed`, `sample_opened`, `position`, `objective`, `progress`, `confirm_required`,
  `preflight_failed`, `finished`.
- Map layers and their data source (ui-spec 7.4 layer table). Click-to-move flow steps 1–6 mapped to events.
- Missing pieces (e.g. candidate ids, mosaic metadata fields, retire/confirm operations) become requests to
  AF 업무분배보조, who forwards them to the manager.
- Remote and role rules: map and progress for everyone; trace, scan, click-move and boundary only for the
  local operator with control and an open experiment session. PLAN v1.1 D16: flag write, flag retire and
  candidate confirm/reject only for the operator on the microscope PC (loopback); viewers and remote
  operators may not.

Stage B, implementation (mock first):
- `map.py`: read endpoints and the mosaic image endpoint; commands use the common command endpoint.
  Pydantic response models. The server reads sample files; it never moves anything itself.
- D16 on the server: every route in `map.py` that writes flags or candidate decisions checks the named
  permission `WRITE_MAP_FLAG` from T-018 `auth/roles.py` (operator only, local only). If these writes go
  through the common command endpoint instead, say so in stage A and request the same check from the manager.
  Hiding buttons alone does not satisfy D16.
- `features/map/index.tsx` by the T-010 registration rule. Canvas map with toggleable layers, axes drawn in
  joystick direction as ui-spec says, side panels (sequence, hole summary, edge trace, scan, results, flags,
  candidates). The hover target, distance and "outside the scanned area" hint are display only; the engine
  decides. Classical candidates and person-confirmed ones have different marks; confirm/reject and flag edits
  add new entries, never overwrite.
- Click-move never raises Z again on screen; after arrival show the refocus hint only (ui-spec 7.4).
- Mosaic images never go into the prompt context (D7). UI text in English.

## Tests

- pytest with `TestClient`, a fake engine and the fixture sample: map state, results, mosaic image (size,
  content type, flip), flags and candidates lists, remote/role refusals. Each flag write, flag retire and
  candidate confirm/reject route has a test that refuses a viewer and one that refuses a remote operator (D16).
- vitest: layer toggles, candidate marks by source, click-move steps from a scripted event sequence
  (including outside-box refusal and the retract confirm), stale hole fit warning, read-only mode.
- Tests never open browser or desktop windows, and stop any server they start. No hardware scripts.

## Done when

- Common criteria (`uv run pytest`, `uv run ruff check src tests`, owned paths only in
  `git diff --stat main...HEAD`), T-010's npm checks (`ci`, `build`, `test`, type check)
- Commit with `git commit -- <paths>`; no `git add -A`, no `--amend`, no push. Trailer `Session: AF 실행20`
- `[검토요청 T-102]` to the review assistant above, with branch, hash, changed files and test counts
