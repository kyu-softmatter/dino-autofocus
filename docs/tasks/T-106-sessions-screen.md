# T-106 WP-N experiment sessions: server router and sessions screen (F7)

- Owner: AF 실행2 (after T-019)
- Package: WP-N follow-up (PLAN.md 2절 F7, 5절 "실험 세션과 기록 저장소", D10, D11). Assigned by
  AF 업무분배보조
- Prerequisites: stage A starts once `[검토요청 T-019]` is sent. Stage B: T-019 merged, T-009 (server
  skeleton) and T-010 (web shell) first skeleton merged. The logged-in user id comes from T-105; until it
  merges, tests use a fake user
- Branch: `exec2/T-106-sessions-screen`
- Review: `[검토요청 T-106]` to AF 검토보조4 (AF 검토보조3 if 4 has more than three queued)

## Owned paths

- Stage A: `docs/screens/sessions.md` (new)
- Stage B: `src/dino_autofocus/server/api/sessions.py`, `tests/server/test_api_sessions.py`,
  `web/src/features/sessions/`

Not yours: `records/` (T-019; small fixes allowed only if listed in the review request), the rest of
`server/` (T-009), `web/` outside `features/sessions/` (T-010; the current session in the status bar is the
shell's), `web/package*.json`, `pyproject.toml`.

## Content

Stage A, contract (short, English):
- Endpoints: list sessions (filter by user, sample, status), session detail (`session.json` fields, log
  tail, records list, manifest summary, librarian reflected or not), open (sample id), close, continue with
  the same sample (F7.4), current session.
- Which T-019 function backs each endpoint, and what the shell must show (current session, "Open an
  experiment session first" reason from ui-spec 7.0). Gaps become requests to AF 업무분배보조, who forwards
  them to the manager.

Stage B, implementation:
- `sessions.py`: router through T-009's mechanism over T-019. Open and close only for a local operator;
  reads for everyone. Closed sessions are read-only. Commits run in T-019's worker; the router never blocks
  on git.
- `features/sessions/index.tsx` by the T-010 registration rule: list, detail, open, close, continue.
  Show the code commit hash and dirty flag and the hardware profile hash as recorded, not recomputed.
  UI text in English.

## Tests

- pytest with `TestClient` and a temporary records repo: open, close, list filters, detail, continue,
  closed session refuses writes, remote/role refusals.
- vitest: list and detail render, open/close disabled with the reason in read-only mode.
- Tests never open browser or desktop windows, and stop any server they start. Temporary git repos only.

## Done when

- Common criteria (`uv run pytest`, `uv run ruff check src tests`, owned paths only in
  `git diff --stat main...HEAD`), T-010's npm checks (`ci`, `build`, `test`, type check)
- Commit with `git commit -- <paths>`; no `git add -A`, no `--amend`, no push. Trailer `Session: AF 실행2`
- `[검토요청 T-106]` to the review assistant above, with branch, hash, changed files and test counts

## T-106b (AF 실행2, after T-106 and T-009i merge; review AF 검토보조3) — sessions carry the backend kind

- Director: every experiment session record (session.json) carries the backend `kind` and `bench` (from
  `snapshot()["backend_info"]` / `is_bench`), written at open and on continue, so a downstream librarian can skip
  non-bench sessions. `records/session.py` gets the optional field (this task may edit it; 실행2 owns records).
  Tests: a mock session records kind "mock", bench False; an mm-real-flagged FakeBackend records bench True.
- Integration item (BACKLOG, M6): the soft-matter-agents librarian skips non-bench sessions found in the real root.
- T-106c (AF 실행2, after T-106b; review AF 검토보조3; director): our own `records/librarian_mock.py` skips sessions
  with `bench: false` found in the real records root, so the rule is tested here and the M6 item is a port. Tests: a
  non-bench session in the real root is skipped (and logged); a bench session is ingested; the mock root is unaffected.
