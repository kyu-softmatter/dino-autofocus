# Console screen contract (T-100 stage A)

Area `console` (PLAN.md 2절 F1, 9절 WP-F). This is the contract between the screen, the server router
`server/api/console.py` and the AgentStore. The panels themselves are in `docs/ui-spec.md` 7.1, which is
not repeated here (branch `exec5/T-004-ui-spec`, 6fcd8a8, until it merges).

Sources read: AgentStore `agents/store.py` (T-008, `exec6/T-008-agent-store` 28eaec8), server skeleton
`server/app.py` and `server/api/__init__.py` (T-009, `exec7/T-009-server-skeleton` a4e3671), roles and
control `auth/roles.py`, `auth/control.py` (T-018, in progress in exec13).

## Endpoints

All are mounted at `/api/console` by T-009's area-router mechanism. Bodies are the store dataclasses'
`to_dict()` output wrapped in pydantic models, so the OpenAPI types reach `web/src/api/`. Card contents
(`Card.data`, `RunDetail.records`, `InboxThread.status`) stay `Any` and pass through untouched; grades and
`numbers` are never re-computed (PLAN 6절 3항, ui-spec 7.1 "숫자 표").

| Method, path | Query / body | Response | AgentStore |
|---|---|---|---|
| `GET /capabilities` | | `{store, can_submit, submit_reason}` (see "Rules") | `store.source`, `writable` (gap 1) |
| `GET /questions` | `agent=microscope\|simulation`, optional. Omitted: both, merged newest first | `QuestionSummary[]` | `list_questions(agent)`, once per agent |
| `GET /questions/{qid}` | `version=N`, optional. Omitted: latest | `QuestionDetail` (`summary.versions` lists the others) | `get_question(qid, version)` |
| `GET /runs` | `agent=`, optional, as for questions | `RunSummary[]` | `list_runs(agent)` |
| `GET /runs/{agent}/{run_id}` | | `RunDetail` (`not_opened` lists big or unreadable records) | `get_run(agent, run_id)` |
| `GET /inbox` | | `InboxThread[]` with messages | `list_inbox()` |
| `POST /questions` | `{text, target, purpose?, observable?}` | `201`, `QuestionSummary` | `submit_question(text, target, purpose=, observable=)` |

Error mapping: `NotFoundError` → 404, bad `agent` / `purpose` / empty text (`ValueError`) → 422,
`ReadOnlyStoreError` → 409 with `"Submitting to soft-matter-agents is not connected yet (read-only)"`,
other `StoreError` → 500 with its message. Bodies are T-009's `ApiError {detail}`.

The status and date filters and the two-version diff (ui-spec 7.1) run in the browser over these
responses: the list is small, and the diff fetches `?version=` twice. No server diff endpoint.

Refresh: when the area opens and on the `"Refresh"` button. No polling, no file watching (ui-spec 7.1).
After a successful submit the screen re-reads `GET /questions`.

## Rules: remote, role, read-only

Reads (`GET`) are open to every logged-in user, local or remote, any role (ui-spec 7.0 remote table).

Submit is refused in this order; the first reason is the one shown (ui-spec 7.0 "비활성 이유"):

The screen shows the ui-spec text below, not the server's `detail` (T-009's middleware detail is
`"commands are accepted only on the microscope PC (...)"`); `GET /capabilities` returns the screen text.

| Check | Where | Status | Screen text |
|---|---|---|---|
| Request is not from the microscope PC | T-009 middleware (non-GET from non-loopback) | 403 | `"Read-only: remote view"` |
| Not logged in, or screen locked | `control.authorize(SUBMIT_QUESTION, ...)` | 403 | the decision's reason |
| Role below operator (viewer) | same, D16 | 403 | `"Needs the operator role"` |
| Store is not the mock store | `ReadOnlyStoreError` | 409 | `"Submitting to soft-matter-agents is not connected yet (read-only)"` |

- D16: the route calls `authorize(Action.SUBMIT_QUESTION, login_token, local=<loopback>)`. Hiding or
  disabling the button is only the display of that result. Device control (the control token) is not
  needed: submitting moves nothing. An open experiment session is not needed either (PLAN 6절 12항 covers
  commands that move hardware); `session_id` is recorded when one is open, else null.
- `GET /capabilities` runs the same checks without writing and returns the first failing reason in
  `submit_reason`, so the form is disabled with its reason before anyone clicks.
- Every submit attempt, accepted or refused, goes to the audit log with `user_id`, `session_id`, `target`
  and the new `qid` (PLAN 5절 "로그 세 가지", gap 4).

## Prompt context (X1)

The area registers with the shared prompt box (T-014): selected `qid`, `version`, selected card `kind`
(`goal`, `axis`, `plan`, `synthesis`, `refusal`, ...), selected `run_id` and its `agent`. Short ids only;
no card bodies and no images (D7).

## Links out

- Simulation run detail → the T-012 simulation area for progress, trajectory and download (gap 6).
- "이 저장소의 실험" panel (samples and experiment sessions) → `sample` and `sessions` areas. Not served
  by AgentStore; stage B shows links only (gap 5).

## Gaps (requests)

1. **T-008, store**: no way to tell a writable store from a read-only one without trying a write. Request
   a `writable: bool` attribute on the protocol (`MockStore` True, `SmaFiles` False) or a store-level
   `source`. Fallback in stage B: `isinstance(store, MockStore)`.
2. **T-009, server**: no AgentStore on the app. Request `create_app(..., agent_store=...)` storing it on
   `app.state` and an `AgentStoreDep` beside `Engine` in `server/api/__init__.py`. Default for the dev
   server: `MockStore()` with a temp write folder.
3. **T-009 / T-018, server**: routes need the current login and the loopback flag. Request a dependency
   that yields `(login_token, local)` from the auth cookie and `_is_loopback(request.client.host)`, and
   the `control` object on `app.state` (server side of T-018: `server/api/auth.py`).
4. **T-018, audit**: `AuditKind` has no kind for a question submit. Request `QUESTION_SUBMITTED` /
   `QUESTION_REFUSED` (or confirm `COMMAND_PROPOSED` / `COMMAND_REJECTED` is meant). Also, `roles.py`
   documents `SUBMIT_QUESTION` as "a question to the assistant from a prompt box"; the console's F1.1
   submit to AgentStore uses the same permission (T-100 card). Please widen the docstring, or name a
   separate action if the two should differ.
5. **T-019 / sample**: the "이 저장소의 실험" list has no read API yet; stage B links out only.
6. **T-010 / T-012, web**: the route form for linking to another area with an id (e.g. a simulation
   `run_id`) is not fixed yet. Request the shell's link helper or URL scheme.
7. **T-014, web**: the prompt-context registration call is not on main yet; stage B registers once it is.
