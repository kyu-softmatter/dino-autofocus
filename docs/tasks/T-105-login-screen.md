# T-105 WP-M login: server router and login screen (X3)

- Owner: AF 실행13 (after T-018; T-014 comes after this task)
- Package: WP-M follow-up (PLAN.md 5절 "사용자와 로그인", 7절 D9, D12). Assigned by AF 업무분배보조
- Prerequisites: stage A starts once `[검토요청 T-018]` is sent. Stage B: T-018 merged, T-009 (server
  skeleton) and T-010 (web shell) first skeleton merged
- Branch: `exec13/T-105-login-screen`
- Review: `[검토요청 T-105]` to AF 검토보조4 (AF 검토보조3 if 4 has more than three queued)

## Owned paths

- Stage A: `docs/screens/login.md` (new)
- Stage B: `src/dino_autofocus/server/api/auth.py`, `tests/server/test_api_auth.py`, `web/src/app/login/`

Not yours: `auth/` (T-018; small fixes allowed only if listed in the review request), the rest of `server/`
(T-009), `web/` outside `app/login/` (T-010; the shell's route guard and status bar are the shell's),
`tools/launcher/` (T-016), `web/package*.json`, `pyproject.toml`.

## Content

Stage A, contract (short, English):
- Endpoints: login, logout, sign-up (name, email, password only), current user (`/me`: id, name, role,
  locked, has control), admin list of pending accounts, admin approve with role, control acquire / release /
  admin force-release, unlock.
- Cookie: HttpOnly, SameSite=Strict, server-side session token from T-018. Remote view also needs login.
- What the shell must provide (route guard that sends unauthenticated users to the login screen, user and
  control in the status bar). Anything T-010 or T-009 lacks becomes a request to AF 업무분배보조, who
  forwards it to the manager.

Stage B, implementation:
- `auth.py`: router through T-009's mechanism over the T-018 modules. Pending accounts cannot log in and get
  the pending notice. Role is set only by an admin on approval. Every login, logout, sign-up, approval and
  control change goes to `audit.jsonl` through T-018.
- Abort and lights-off never need login state or control (PLAN 5절); this router must not add a check that
  blocks them.
- `app/login/`: login form, sign-up form, pending notice, lock screen (work and guards keep running while
  locked; abort stays available), admin approval list with role picker. UI text in English.
- The admin email is never in code, tests or fixtures; tests use `example.test` addresses only.

## Tests

- pytest with `TestClient`: login success and failure, case-insensitive email, pending account refused,
  cookie flags, logout, admin approve sets role and writes audit lines, non-admin approve refused, control
  single holder and admin force-release, abort allowed while locked and without control.
- vitest: forms, pending notice, lock screen keeps abort, approval list hidden for non-admins.
- Tests never open browser or desktop windows, and stop any server they start.

## Done when

- Common criteria (`uv run pytest`, `uv run ruff check src tests`, owned paths only in
  `git diff --stat main...HEAD`), T-010's npm checks (`ci`, `build`, `test`, type check)
- Commit with `git commit -- <paths>`; no `git add -A`, no `--amend`, no push. Trailer `Session: AF 실행13`
- `[검토요청 T-105]` to the review assistant above, with branch, hash, changed files and test counts
