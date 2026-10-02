# Console screen contract (T-100 stage A)

Area `console` (PLAN.md 2절 F1, 9절 WP-F). This is the contract between the screen, the server router
`server/api/console.py` and the AgentStore. The panels themselves are in `docs/ui-spec.md` 7.1, which is
not repeated here (on main since T-004 merged).

Sources read: AgentStore `agents/store.py` (T-008, `exec6/T-008-agent-store` 28eaec8), server skeleton
`server/app.py` and `server/api/__init__.py` (T-009, `exec7/T-009-server-skeleton` a4e3671), roles and
control `auth/roles.py`, `auth/control.py` (T-018, in progress in exec13), web shell `web/README.md`
and `src/app/route.ts` (T-010 a5fb986, in review).

## Endpoints

All are mounted at `/api/console` by T-009's area-router mechanism. Bodies are the store dataclasses'
`to_dict()` output wrapped in pydantic models, so the OpenAPI types reach `web/src/api/`. Card contents
(`Card.data`, `RunDetail.records`, `InboxThread.status`) stay `Any` and pass through untouched; grades and
`numbers` are never re-computed (PLAN 6절 3항, ui-spec 7.1 "숫자 표").

| Method, path | Query / body | Response | AgentStore |
|---|---|---|---|
| `GET /store` | | `{store, writable}`: `"mock"` / `"soft-matter-agents"` (see "Rules") | store kind, `store.writable` |
| `GET /questions` | `agent=microscope\|simulation`, optional. Omitted: both, merged newest first | `QuestionSummary[]` | `list_questions(agent)`, once per agent |
| `GET /questions/{qid}` | `version=N`, optional. Omitted: latest | `QuestionDetail` (`summary.versions` lists the others) | `get_question(qid, version)` |
| `GET /runs` | `agent=`, optional, as for questions | `RunSummary[]` | `list_runs(agent)` |
| `GET /runs/{agent}/{run_id}` | | `RunDetail` (`not_opened` lists big or unreadable records) | `get_run(agent, run_id)` |
| `GET /inbox` | | `InboxThread[]` with messages | `list_inbox()` |
| `POST /questions` | `{text, target, purpose?, observable?}` | `201`, `QuestionSummary` | `submit_question(text, target, purpose=, observable=)` |

Error mapping (all T-009b refusals: `detail = {code, message}` and the `X-DinoAF-Refusal` header):
`NotFoundError` → 404 `not_found`; empty text or an unknown `purpose` (`ValueError`) → 422 `invalid`
(a bad `agent` / `target` is FastAPI's own 422); a read-only store → 409 `read_only_store` with
`"Submitting to soft-matter-agents is not connected yet (read-only)"`; other `StoreError` → 500
`store_error`.

Versions: the picker lists every entry of `summary.versions` as the store returns it (1 for unprefixed
files, N for any `vN_` prefix; v4_, v5_ exist). The screen assumes no upper bound and no fixed set, unlike
the `r1`/`v2_`/`v3_` example in ui-spec 7.1.

The status and date filters and the two-version diff (ui-spec 7.1) run in the browser over these
responses: the list is small, and the diff fetches `?version=` twice. No server diff endpoint.

Refresh: when the area opens and on the `"Refresh"` button. No polling, no file watching (ui-spec 7.1).
After a successful submit the screen re-reads `GET /questions`.

## Rules: remote, role, read-only

Reads (`GET`) are open to every logged-in user, local or remote, any role (ui-spec 7.0 remote table).

Submit is refused in this order; the first reason is the one shown (ui-spec 7.0 "비활성 이유"):

Before anyone clicks, the screen asks the shared `GET /api/permissions?ops=submit_question` (T-009b, backed
by T-011's check and T-018's `SUBMIT_QUESTION` plus loopback) and shows its `reason` as written. The console
router computes no role, control, session or remote rule itself; it adds only its own rule, the read-only
store, through `GET /api/console/store`. Reason order on screen: the shell's read-only flag (`useReadOnly`,
`"Read-only: remote view"`), then the permission reason (`"Checking permissions…"` while loading,
`"Permission check unavailable"` on error or a missing op), then the store's. Reads go through the shell's
client (`useClient().get`); the screen re-reads when the event socket reconnects after a drop.

| Check | Where | Status on submit | Screen text |
|---|---|---|---|
| Request is not from the microscope PC | the shell's read-only flag; the access middleware on the POST | 403 `remote_view` | `"Read-only: remote view"` |
| Not logged in, screen locked | `/api/permissions`; the access middleware | 401 `login_required`, 423 `locked` | the permission reason |
| Role below operator (viewer), D16 | `/api/permissions`; `server_action_why(me, "submit_question")` in the route | 403 `role` | the permission reason, shown next to the form |
| Store is not the mock store | `/api/console/store`; `store.writable` in the route | 409 `read_only_store` | `"Submitting to soft-matter-agents is not connected yet (read-only)"` |

- "Mock store only" is enforced through `AgentStore.writable`, not `isinstance(store, MockStore)`. This is
  deliberate: T-025 added `writable` (gap 1) so routes need not test the class. Today `MockStore` is the
  only writable store and `SmaFiles` is False. A real soft-matter-agents writer, if one is ever added
  (integration, PLAN 10절 F1.1), must also change the 409 rule here and the ui-spec 7.1 text.

- D16: the POST route calls `server_action_why` (T-018 `SUBMIT_QUESTION` plus loopback) on the server.
  Disabling the button is only the display of the permission answer. Device control (the control token)
  is not needed: submitting moves nothing. An open experiment session is not needed either (PLAN 6절 12항
  covers commands that move hardware).
- The web submit goes through the shell's `client.post`: only a 403 `remote_view` switches the app to
  read-only; every other refusal is shown next to the form and changes no global state.
- An accepted submit goes to the audit log as `question_submitted` with `user_id`, `session_id` (the open
  experiment session, else null), `origin: "console"`, `target` and the new `qid` (PLAN 5절 "로그 세 가지").
  Refusals are not logged by this route: the audit kinds have none for a refused question.

## Prompt context (X1)

The screen calls the shell's `useScreenContext(details)` (`src/app/screenContext`, T-010 `web/README.md`);
the prompt box (T-014) only reads it. Details: selected `qid`, `version`, selected card `kind`
(`goal`, `axis`, `plan`, `synthesis`, `refusal`, ...), selected `run_id` and its `agent`. Short ids only;
no card bodies and no images (D7).

## Links out

- Simulation run detail → the T-012 simulation area for progress, trajectory and download (gap 6).
- "이 저장소의 실험" panel (samples and experiment sessions) → `sample` and `sessions` areas. Not served
  by AgentStore; stage B shows links only (gap 5).

## Gaps (requests)

1. ~~T-008~~: closed, `AgentStore.writable` (T-025).
2. ~~T-009~~: closed, `create_app(agent_store=...)` and `AgentStoreDep`.
3. ~~T-009 / T-018~~: closed, `Login`, `IsLocal`, `server_action_why` (T-009b).
4. ~~T-018~~: closed, `AuditKind.QUESTION_SUBMITTED` covers the console submit and prompt boxes. There is
   no kind for a refused question, so refusals are not logged here.
5. **T-019 / sample**: the "이 저장소의 실험" list has no read API yet; stage B links out only.
6. ~~T-010 / T-012~~: closed. The link is `#/simulation/runs/<run_id>`; the shell passes `#/<area>/<rest>`
   through (no link helper) and T-012 stage 2 reads the suffix.
7. ~~T-014~~: resolved by the shell's `useScreenContext` (T-010); nothing waits on T-014.
8. **T-008 / T-025, store**: ui-spec 7.1 list columns that the summaries do not carry: `purpose`, `intent`,
   `observable.name` of the latest goal (`QuestionSummary`), and `approval.kind` of the log (`RunSummary`).
   Closed: T-025 sends `purpose`, `intent`, `observable_name`, `approval_kind`; the lists show them ("—"
   when a card has none).

Web types: the router's models and `PermissionOut` are not in the committed `web/src/api/schema.ts` yet, so
`features/console/api.ts` keeps hand copies until T-010 regenerates it after this router merges.
