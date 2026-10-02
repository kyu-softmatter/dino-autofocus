# Login screen and auth API: contract (T-105 stage A)

Design: PLAN.md 5절 "사용자와 로그인", 7절 D9, D12, D13, D16, design rule 12. Core logic:
`src/dino_autofocus/auth/` (T-018). This file fixes the HTTP surface and the screen so that
stage B (`server/api/auth.py`, `web/src/app/login/`) and the shell (T-010) can be built against it.

## 1. Endpoints

All under `/api/auth` (T-009 mounts `server/api/auth.py` there). JSON in and out. Errors are
T-009's `ApiError` (`{"detail": "..."}`). "Local" means the request comes from the microscope PC
(T-009's loopback check); "remote" means any other PC under remote view.

| Method, path | Who | From | Body → reply |
|---|---|---|---|
| `GET /setup` | anyone | any | → `{state: "needs_admin_email" \| "needs_admin" \| "ready"}`. No email in the reply |
| `POST /setup/admin` | anyone, only while state ≠ ready | local | `{name, password, email?}` → `Me` + cookie. `email` only when none is configured |
| `POST /signup` | anyone | any | `{name, email, password}` → `201 {status: "pending"}`. Nothing else is accepted (no role field; extra fields → 422) |
| `POST /login` | anyone | any | `{email, password}` → `Me` + cookie; `401 {detail, outcome}` with `outcome` `bad_credentials` \| `pending_approval` \| `disabled` |
| `POST /logout` | logged in | any | → `204`, cookie cleared, control released |
| `POST /lock` | logged in | any | → `204`. "Lock" in the user menu |
| `POST /unlock` | logged in, locked | any | `{password}` → `Me`; `401` on a wrong password |
| `POST /activity` | logged in | any | → `204`. The screen calls it on user input (throttled, at most every 30 s) so the idle lock does not fire while someone is working |
| `GET /me` | logged in | any | → `Me`; `401` without a valid cookie |
| `GET /accounts?status=pending` | admin | local | → `[Account]` (no hashes) |
| `POST /accounts/{email}/approve` | admin | local | `{role}` → `Account`. Role is set only here (D12) |
| `POST /accounts/{email}/role` | admin | local | `{role}` → `Account` |
| `POST /accounts/{email}/disable` | admin | local | → `Account` |
| `GET /control` | logged in | any | → `{holder: {user_id, name, since} \| null}` |
| `POST /control/acquire` | operator, admin | local | → `{holder}`; `409 {detail, holder}` when someone else holds it |
| `POST /control/release` | the holder | local | → `204` |
| `POST /control/revoke` | admin | local | `{reason}` → `{previous_holder}` |

```
Me      = {user_id, name, role, locked, has_control, local, expires_at}
Account = {email, name, role, status, created_at, approved_by, approved_at}
```

`local` in `Me` tells the screen whether write controls can work at all (D16: questions, map
flags and commands are local only). The server decides each request again; hiding a button is
not the check.

## 2. Cookie and session

- Cookie `dino_af_session`: the T-018 login token. `HttpOnly`, `SameSite=Strict`, `Path=/`, no
  `Max-Age` (dies with the browser) and no `Secure` (plain HTTP on the lab network; revisit if
  remote view ever leaves it). The token never appears in a reply body, a URL or a log.
- Idle lock after 15 min without `/activity`; the session ends 12 h after login (T-018
  defaults, `LoginSessions(idle_lock_s, max_age_s)`).
- The **device-control token never leaves the server.** When a logged-in holder sends a
  command, the server attaches its grant to the engine `Command`; the engine checks it with
  `DeviceControl.check` (T-011). The browser only knows `has_control`.
- Every login, failed login, logout, lock, unlock, sign-up, approval, role change and control
  change goes to `audit.jsonl` through T-018. The router adds no second log.

## 3. Requests without a login

- Abort (and lights-off from the microscope PC) **never** needs a login, an unlocked screen or
  device control (rule 12). The auth router puts no dependency on `/api/commands` or
  `/ws/events`, and the dependency it offers to other routers (`CurrentUser`, below) is not used
  on the stop path.
- Every other `/api/*` route and `/ws/*` needs a valid cookie, remote view included. The one
  exception is the group needed to get in: `GET /setup`, `POST /signup`, `POST /login`.

For other routers, `auth.py` exports FastAPI dependencies: `CurrentUser` (401 without login,
423 when locked) and `require(Action)` (403 with the reason from `DeviceControl.authorize`,
given T-009's local flag).

## 4. Screen (`web/src/app/login/`)

One component tree, shown by the shell instead of the areas when `GET /me` is 401 or `locked`.

| State | Shows |
|---|---|
| setup needed (`/setup` ≠ ready) | "First run: create the administrator account". Name, password (twice), and an email field only for `needs_admin_email`. Local only; remote shows "Set up on the microscope PC" |
| logged out | Login form (email, password). Link to sign-up |
| sign-up | Name, email, password (twice). After submit: "Account created. An administrator must approve it before you can log in." |
| pending (login returned `pending_approval`) | "Your account is waiting for an administrator's approval." No retry loop |
| disabled | "This account is disabled. Ask an administrator." |
| locked | "Locked: enter your password to continue" over a dimmed app. **Running work and guards keep going, and the Abort button stays live on the lock screen.** The status bar stays visible |
| admin approval list | Under the user menu, admin only and local only: pending accounts with name, email, created time, a role picker (viewer / operator / admin, no default chosen) and Approve. Hidden for everyone else |

UI text in English. No email is prefilled, remembered or shown before login.

## 5. What the shell (T-010) and server (T-009) must provide

Requests to AF 업무분배보조, who forwards them to the manager:

1. **T-009: login over remote view.** `writes_from_this_pc_only` refuses every non-GET from a
   remote PC, so a remote viewer cannot `POST /api/auth/login`, `/logout`, `/lock`, `/unlock`,
   `/activity` or `/signup`. Proposal: an exempt list for exactly these paths. They never reach
   the engine.
2. **T-009: the local flag as a dependency** (for example `IsLocal`), so `auth.py` and other
   routers use T-009's loopback rule instead of copying it.
3. **T-009: auth on `/ws/*` and `/api/*`.** A cookie check on the WebSocket handshake and on
   routers other than the open group in 3. The stop path stays open.
4. **T-010: a route guard.** Before rendering an area, call `GET /api/auth/me`. On 401 or
   `locked`, render `app/login/` (exported `LoginGate`) instead. Any 401 from another call sends
   the app back to it. Hash routing stays as is; no `#/login` route is needed.
5. **T-010: status bar items:** user name and role, a "remote · read only" badge when
   `local` is false, the control holder (`GET /control`) with Take / Release for the local
   operator, and a user menu (Log out, Lock, and Approve accounts for an admin).
6. **T-010: an activity hook** that calls `POST /api/auth/activity` on user input, throttled.
