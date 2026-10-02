# T-100 WP-F console screen (F1): server router and web area

- Owner: AF 실행18
- Package: WP-F screen part (PLAN.md 2절 F1, 9절). Assigned by AF 업무분배보조 (screen areas)
- Prerequisites: stage A none. Stage B: T-009 (server skeleton) and T-010 (web shell) first skeleton merged,
  T-008 (AgentStore, mock store) merged
- Branch: `exec18/T-100-console-screen`
- Review: `[검토요청 T-100]` to AF 검토보조4 (AF 검토보조3 if 4 has more than three queued)

## Owned paths

- Stage A: `docs/screens/console.md` (new)
- Stage B: `src/dino_autofocus/server/api/console.py`, `tests/server/test_api_console.py`,
  `web/src/features/console/`

Not yours: `agents/` (T-008), `server/api/__init__.py` and the rest of `server/` (T-009), `web/` outside
`features/console/` (T-010), `web/src/app/assistant/` (T-014), `web/package*.json` and `pyproject.toml`
(requests go to the manager through AF 업무분배보조).

## Content

Spec: `docs/ui-spec.md` 7.0 and 7.1 (branch `exec5/T-004-ui-spec`, 6fcd8a8, until it merges). Cite it; do not
restate it.

Stage A, contract (short, English, about one page):
- Endpoints the screen uses: method, path, query, response fields. Start from ui-spec 7.1 "전송과 갱신"
  (`GET /api/console/questions?agent=`, `questions/{qid}?version=`, `runs?agent=`, `runs/{agent}/{run_id}`,
  `inbox`, `POST /api/console/questions` mock only).
- For each endpoint, the AgentStore method behind it (T-008 `store.py`). List any missing method or field as
  a request; send the list to AF 업무분배보조, who forwards engine/store requests to the manager.
- Remote and role rules per ui-spec 7.0 / 7.1 and PLAN v1.1 D16: reads for everyone; question submit only for
  the operator on the microscope PC (loopback). Viewers and remote operators may not submit. The server
  decides; the screen only shows the reason.
- Prompt context the area registers (ui-spec 7.1): selected `qid`, version, card kind, `run_id`.
- Commit stage A on its own and tell AF 업무분배보조 (no review request yet).

Stage B, implementation (mock first):
- `console.py`: a router registered through T-009's `server/api/` mechanism. Read-only over the injected
  AgentStore; `submit_question` only when the store is the mock store, otherwise 409 with the ui-spec text
  `"Submitting to soft-matter-agents is not connected yet (read-only)"`. Response models are pydantic so the
  OpenAPI types reach the web.
- D16 on the server: the submit route checks the named permission `SUBMIT_QUESTION` from T-018
  `auth/roles.py` (operator only, local only). Hiding the button alone does not satisfy D16.
- `features/console/index.tsx` registered by the T-010 rule (`web/README.md`). Panels from ui-spec 7.1:
  question list with filters, question detail with card tabs and version picker, numbers table with grade
  badges taken as-is (no re-grading on screen), assumptions and `degraded` banner, run list and run detail
  (simulation run detail links to the T-012 simulation area), inbox, submit form.
- Use the generated types in `web/src/api/`; no hand-written copies of the API.
- No polling except the `"Refresh"` button (ui-spec 7.1). UI text in English.

## Tests

- pytest with FastAPI `TestClient` and the T-008 mock store: every endpoint, the read-only store refusing
  submit, remote/role refusals (403) as T-009 defines them. The submit route has a test that refuses a viewer
  and one that refuses a remote operator (D16).
- vitest: list filters, card tabs, grade badges unchanged from the data, submit disabled with its reason in
  read-only mode.
- Tests never open browser or desktop windows, and stop any server they start.

## Done when

- Common criteria (`uv run pytest`, `uv run ruff check src tests`, owned paths only in
  `git diff --stat main...HEAD`), T-010's npm checks (`ci`, `build`, `test`, type check)
- Commit with `git commit -- <paths>`; no `git add -A`, no `--amend`, no push. Trailer `Session: AF 실행18`
- `[검토요청 T-100]` to the review assistant above, with branch, hash, changed files and test counts
