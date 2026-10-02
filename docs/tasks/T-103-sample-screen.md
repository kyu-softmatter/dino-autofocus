# T-103 WP-H sample screen (F3): server router and web area

- Owner: AF 실행14
- Package: WP-H screen part (PLAN.md 2절 F3, 9절). Assigned by AF 업무분배보조 (screen areas)
- Prerequisites: stage A none. Stage B: T-009 (server skeleton) and T-010 (web shell) first skeleton merged.
  The engine side (`sample_open`, `sample_new`, proposed `sample_geometry_set`, `loading_confirm_person`,
  `loading_check_image`, geometry in `engine/sample.py`) is the manager's WP-H work; until it merges, tests
  use a fake engine with the same command names and a fixture sample root
- Branch: `exec14/T-103-sample-screen`
- Review: `[검토요청 T-103]` to AF 검토보조4 (AF 검토보조3 if 4 has more than three queued)

## Owned paths

- Stage A: `docs/screens/sample.md` (new)
- Stage B: `src/dino_autofocus/server/api/sample.py`, `tests/server/test_api_sample.py`,
  `tests/server/fixtures/sample/` (small fixture sample root), `web/src/features/sample/`

Not yours: `engine/` (including `sample.py`), the rest of `server/` (T-009), `web/` outside
`features/sample/` (T-010), `web/src/app/assistant/` (T-014), `web/package*.json`, `pyproject.toml`.

## Content

Spec: `docs/ui-spec.md` 7.0 and 7.3 (branch `exec5/T-004-ui-spec`, 6fcd8a8, until it merges); PLAN 2절 F3.
Cite them; do not restate them.

Stage A, contract (short, English):
- Endpoints: sample list (ID, created, `fitted_at`, objectives used, last experiment session,
  `awaiting_return`), opened sample summary, geometry with the source of each value
  (`"entered by <user> <t>"`, `"default"`, `"not set"`), loading-check state. Commands through T-009's
  `POST /api/commands`: `sample_open`, `sample_new`, `sample_geometry_set`, `loading_confirm_person`,
  `loading_check_image`. Events read: `sample_opened`, `map_changed`, `finished`.
- The geometry field list is provisional (PLAN 10절: the user still has to confirm F3.1). Keep the fields in
  one place on each side so they change in one edit; mark the fields that feed safety limits (coverslip
  thickness, sample thickness, orientation).
- Gaps (op names, event fields, where geometry lives in the sample record) become requests to
  AF 업무분배보조, who forwards them to the manager.
- Remote and role rules: reads for everyone. Open, new, geometry save and the person confirmation need the
  local operator. `loading_check_image` turns on brightfield and takes a frame, so it needs the operator with
  control and an open experiment session (D15, like motion).

Stage B, implementation (mock first):
- `sample.py`: read endpoints only; commands use the common command endpoint. Pydantic response models.
- `"Open folder"`: shown only on the local screen; on a remote screen show the path only. The server action
  that opens Explorer must be injectable, and tests replace it with a recorder: tests never open Explorer or
  any window (docs/sessions.md).
- `features/sample/index.tsx` by the T-010 registration rule: list, opened sample, geometry form, three-step
  loading check (geometry, person, image). "Loading confirmed (person + image)" only when all three are
  recorded by the engine; reading a selected value is not a state check (PLAN F3).
- UI text in English. Generated types from `web/src/api/` only.

## Tests

- pytest with `TestClient`, a fake engine and the fixture sample root: list, opened sample, geometry with
  sources, loading state, remote/role refusals, `"Open folder"` calls the recorder and is refused remotely.
- vitest: geometry form shows sources and safety marks, loading check needs all three steps, read-only mode.
- Tests never open browser, Explorer or desktop windows, and stop any server they start. No hardware scripts.

## Done when

- Common criteria (`uv run pytest`, `uv run ruff check src tests`, owned paths only in
  `git diff --stat main...HEAD`), T-010's npm checks (`ci`, `build`, `test`, type check)
- Commit with `git commit -- <paths>`; no `git add -A`, no `--amend`, no push. Trailer `Session: AF 실행14`
- `[검토요청 T-103]` to the review assistant above, with branch, hash, changed files and test counts
