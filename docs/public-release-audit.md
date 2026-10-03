# 공개 전 점검 (P5): 개인 정보, 비밀, 라이선스, 큰 파일, 보안, 내부 문서

Read-only audit for `docs/integration-sma.md` P5 (repo goes public by 2026-10-23, D5 / Q7).
Nothing was changed except adding this file. No history was rewritten.

- Tree audited: `int/P5-public-audit` at `1302694` (every tracked file at HEAD, 492 files).
- History audited: every object reachable from `--all` (755 commits, 1594 blobs, 120 local branches,
  remote has only `origin/main`, no tags), commit messages, and `git log --all --format='%an %ae'`.
  Blobs were scanned one by one (so merge resolutions and deleted files are covered), not only `log -p`.
- Patterns: e-mail addresses, `X:\Users\<name>`, `/home/<name>`, IPv4, phone numbers, host names,
  `sk-ant-` / `sk-` / `ghp_` / `github_pat_` / `AKIA` / `xox*` / `AIza` / `hf_` / private-key headers,
  `password|secret|token|api_key = "..."`, serial numbers, COM ports, `.env`/key/cookie/DB/log file names.
- This document is itself public once the repo is: it names no real address, serial or user name;
  findings cite `file:line` or a commit instead.

Severity: **high** = blocks publishing; **med** = fix (or decide) before publishing or before remote
view is used; **low** = tidy-up, acceptable as is; **info** = checked, nothing to do.
"Decision" = needs the user (y) or can be done by a work card (n).

## 1. 개인 정보

| id | sev | where | finding | recommended fix | decision |
|---|---|---|---|---|---|
| P1 | med | commits `5a994a7`, `0a27658`, `7c394a8` (2026-10-01, all on `origin/main`) | Three commits are authored and committed under a **second person's identity** (a first name and a university address, not the repo owner's). They are the microscope-PC commits (PSF simulator vendoring, live scoring + bench scripts, launcher + focus head). The address appears only in commit metadata, in no file and no message. Likely the microscope PC's global git config belongs to someone else. | Ask that person whether their name/address may be public. If yes: accept. If no: rewrite before publishing (`git filter-repo --mailmap`); this changes 749 of 750 commit hashes on `main` and breaks the commit hashes cited throughout `docs/` (see §7). A `.mailmap` does **not** hide it (it must contain the old address). Either way set a repo-local `user.name`/`user.email` on the microscope PC so new commits use the owner's identity. | y |
| P2 | info | all other 747 commits | The owner's own commit identity (name + university address). Expected for a public repo. | none | n |
| P3 | info | `docs/runs/2026-09-30_substrate-scan.md:6`, `.yaml:8`; `docs/PLAN.md:232`; `docs/tasks/BACKLOG.md:85` | Operator user name in the 9/30 run record. **Decided: keep** (user, 2026-10-02). | none; the stale question at `BACKLOG.md:85` can be marked decided. | n |
| P4 | low | `docs/microscope-pc-checklist.md:121,136,137`; `docs/runs/2026-10-02_bench-properties.json:18` | The microscope PC's Windows user name (a lab name, contains a space) and its host name, inside install paths. Not a person, but a machine identifier. | Replace with `%USERPROFILE%` / "the microscope PC" in HEAD. History: accept. | n |
| P5 | low | history only: `docs/runbooks/train-focus-head.md`, added `33db72d`, removed `7b27eba` (both on `origin/main`) | The dev desktop's `C:\Users\<owner's name>\.cache\...` path. Owner's own name, already removed at HEAD. | Accept (no rewrite). | n |
| P6 | low | `src/dino_autofocus/agents/mock_data/**` (e.g. `.../sim-20260923-001/v2_goal.json:95`, `.../mic-20260925-002/plan_microscope_mic-20260925-002.json:17`); `web/src/features/console/testData.ts:133` | `authorised_by` / `source` ids built from the owner's first name + date. Copied byte for byte from soft-matter-agents (already public there, `mock_data/SOURCE.md`). | Accept. | n |
| P7 | low | e.g. `docs/runs/2026-09-30_substrate-scan.md:6`, `src/dino_autofocus/engine/backends/stacks.py`, `docs/PLAN.md:242,245` | Lab drive layout (`D:\AutoFocus\...`, `C:\agentic_microscope`). Functional defaults, no personal data. | Accept. | n |
| P8 | info | tests, docs, server | IPv4: only `127.0.0.1`, `0.0.0.0` and private example addresses in tests (`192.168.1.20`, `192.168.0.20`, `10.0.0.5`). The other regex hits are version numbers in `uv.lock`/`pyproject.toml`. No real lab IP anywhere in history. | none | n |
| P9 | info | all blobs and messages | E-mail: no address other than `@example.test` (plus case variants used by normalisation tests, `tests/auth/test_auth_accounts.py:29-33,142`) and `noreply@anthropic.com` in commit trailers. **The configured admin address is in no blob, message or path in the whole history.** (Confirms the P5 row's "0 건".) | none | n |
| P10 | info | all blobs | No phone numbers. No real host names besides P4 (the `*.local` hits are JS identifiers such as `me.local`). | none | n |

## 2. 비밀 (키, 토큰, 비밀번호)

| id | sev | where | finding | recommended fix | decision |
|---|---|---|---|---|---|
| K1 | info | all blobs (HEAD + history) and commit messages | No API key, token, private key, cookie, `.env`, credential or account/audit file was ever committed. `.env` is ignored (`.gitignore:7`). The only paths with "accounts"/"audit" are source and tests. The deleted `CLAUDE.md` (`6d0a129` → `c13a736`) holds only commands and rules. | none | n |
| K2 | low | `tests/assistant/test_assistant_runner.py:362,366` | Dummy `ANTHROPIC_API_KEY` value starting with `sk-ant-` (a test that the key never reaches the status payload). Not a real key, but secret scanners (GitHub push protection, SMA's CI) may flag it. | Change the value to something without the `sk-ant-` prefix, e.g. `"test-key-not-real"`. | n |
| K3 | info | `tests/auth/conftest.py:11`, `tests/server/test_server_origin.py:16`, `tests/e2e/*`, `web/src/app/login/login.test.tsx`, `web/src/features/accounts/accounts.test.tsx:121` | Test-only passwords for fake `example.test` users; no real password. `tests/auth/fixtures/users.json` holds no passwords. | none | n |
| K4 | info | `scripts/mm_grab.py:115,203-215` | The piezo controller's "User" access code is read at run time from the vendor's own `config.ini` and never stored or logged; no code value is in any blob. | none | n |
| K5 | med (**해결 2026-10-02**: `.gitignore` 에 `.agent/`, `.claude/`) | `.gitignore:16` (only `.agent/usage/`); shared folder has untracked `.agent/` and `.claude/` | Session coordination folders (`.agent/tasks`, `.claude/launch.json`, and any future `settings.local.json`) are not ignored. One `git add .` would publish them. | Add `.agent/` and `.claude/` to `.gitignore` (work card). | n |

## 3. 라이선스

| id | sev | where | finding | recommended fix | decision |
|---|---|---|---|---|---|
| L1 | **high** (**해결 2026-10-02**: MIT `LICENSE`, `pyproject` `license = "MIT"`; 사용자 결정. L2 의 psf-autofocus 출처는 여전히 열림) | repo root; `pyproject.toml:1-5` | **No `LICENSE` file**, and `pyproject.toml` has no `license` field. A public repo without a licence is "all rights reserved": soft-matter-agents (MIT) cannot legally take it as a dependency or copy files from it. | Add `LICENSE` = MIT, "Copyright (c) 2026 Kyu Hwan Choi" (same text as soft-matter-agents), and `license = "MIT"` + `license-files = ["LICENSE"]` in `pyproject.toml`. Not added here (user's choice). | y |
| L2 | **high** | `src/dino_autofocus/synth/**` (`synth/__init__.py:3-4`), `tests/synth/**`, `scripts/make_dataset.py`, `scripts/show_system.py`, `scripts/preview_dataset.py` (`pyproject.toml:84-91`); vendored in `5a994a7` | About 6,000 lines **vendored from psf-autofocus** (`afocus` at `dc63189`). The upstream licence and copyright holder are recorded nowhere, the upstream repo is not on this desktop, and the vendoring commit is under the P1 identity. If psf-autofocus is not wholly the owner's work (or its licence is not MIT-compatible), publishing it under MIT is not allowed. | User confirms who owns psf-autofocus and under what licence. Then add a short notice: in `synth/__init__.py` (source repo, commit, copyright, licence) and, if the licence is not MIT, a `NOTICE` / `LICENSES/` file. | y |
| L3 | low | `src/dino_autofocus/backbone.py:1-5,19-20,88`; `scripts/bench_latency.py:56` | DINOv2 (Apache-2.0) is **not vendored**: code comes from a separate local clone pinned to `7764ea0f`, weights are fetched by that clone's `hubconf` at run time. Nothing to redistribute, so no NOTICE duty. | Add one README line crediting DINOv2 (Apache-2.0) and its paper. | n |
| L4 | low | `src/dino_autofocus/live.py:109` (`DinoExtractor(self.head["backbone"], ...)`); `backbone.py:70,88`; the dinov2 clone's `hubconf.py:9` exports `cell_dino_*` | Cell-DINO / X-Ray DINO (FAIR Noncommercial / research licences): nothing vendored, nothing downloaded by default; only discussed in `docs/integration-notes.md:19-25`. But the backbone name comes from the head file, and the pinned clone also exposes Cell-DINO entries, so a head file could load noncommercial weights without anyone choosing to. | Allow-list backbone names (`dinov2_*` only) in `DinoExtractor`. | n |
| L5 | info | `models/heads/head_k100x_dinov2_vits14_L1.{joblib,json}` | Trained by the owner on synthetic data from L2's simulator; features from DINOv2 (Apache-2.0). No licence problem once L2 is settled. Format risk: S9. | none | n |
| L6 | low | `configs/micromanager/single_cam_red_noDMD_nocom10.cfg:25,26,32,34`; `docs/librarian-handoff.md:84,88,105`; `docs/runs/2026-10-02_bench-properties.json:743,1535,1874` | Micro-Manager Configurator output for this bench (user data, no vendor copyright). COM ports and, in comments/JSON, the **serial numbers** of the two cameras and two light sources, plus firmware versions. No host name or IP. Not secret, but they identify the lab's instruments. The `.cfg` files are byte-exact copies whose SHA-256 is checked (`.gitattributes`), so editing the comments changes that hash. | Keep (recommended: serials help vendor support and the `.cfg` hash) or redact in the docs/JSON only. | y |
| L7 | info | `src/dino_autofocus/agents/mock_data/SOURCE.md` | Copied from soft-matter-agents (MIT, same owner). | none | n |
| L8 | info | `tools/launcher/{Launcher.cs,build.ps1,make_icon.py,autofocus.ico}`, `web/` | The icon is drawn by the repo's own `make_icon.py` (PIL shapes, no font or third-party art). No bundled fonts or icon sets in `web/` (system fonts; `scripts/launcher.py:75` names Segoe UI only). Web deps (React, three.js, Vite, ...) come from npm via `web/package-lock.json`, not vendored. | none | n |
| L9 | info | `pyproject.toml:21-24`; `scripts/mm_grab.py:117` | pymmcore(-plus) and the NanoBench vendor DLL are used, not vendored (DLL loaded from the vendor install path at run time). | none | n |

## 4. 큰 파일과 바이너리 (전체 이력)

Packed size 7.2 MiB. Only two binaries were ever committed: the focus head and the launcher icon.
Every path below is still present at HEAD; no large file was added and later deleted.

| # | size (bytes) | path (largest version in history) |
|---|---|---|
| 1 | 4,670,394 | `models/heads/head_k100x_dinov2_vits14_L1.joblib` (binary, pickle) |
| 2 | 207,486 | `uv.lock` |
| 3 | 204,154 | `web/src/api/schema.ts` |
| 4 | 86,528 | `docs/ui-spec.md` |
| 5 | 79,284 | `web/package-lock.json` |
| 6 | 76,277 | `docs/operations-spec.md` |
| 7 | 69,128 | `src/dino_autofocus/engine/runner.py` |
| 8 | 56,570 | `tests/engine/test_contract_runner.py` |
| 9 | 49,589 | `docs/PLAN.md` |
| 10 | 45,554 | `src/dino_autofocus/engine/operations/edge_trace.py` |
| 11 | 44,835 | `scripts/live_focus.py` |
| 12 | 43,589 | `docs/runs/2026-10-02_bench-properties.json` |
| 13 | 40,099 | `src/dino_autofocus/engine/guards.py` |
| 14 | 39,364 | `docs/librarian-handoff.md` |
| 15 | 37,742 | `web/src/features/map/index.tsx` |
| 16 | 36,921 | `src/dino_autofocus/agents/mock_data/.../v3_plan_simulation_sim-20260923-001.json` |
| 17 | 35,723 | `src/dino_autofocus/agents/simulation.py` |
| 18 | 31,848 | `src/dino_autofocus/engine/backends/mm_real.py` |
| 19 | 31,828 | `src/dino_autofocus/assistant/tools.py` |
| 20 | 31,742 | `src/dino_autofocus/agents/mock_data/.../v3_synthesis.json` |

| id | sev | where | finding | recommended fix | decision |
|---|---|---|---|---|---|
| B1 | low | `7c394a8` (`models/heads/*.joblib`, 4.7 MB) | If S9 replaces the pickle with a safe format, the old pickle blob stays in history (still loadable by anyone who checks out an old commit, but nothing in a new commit points to it). Size is no problem. | Accept (no rewrite). | n |

## 5. 보안 (공개 후 의미 있는 것)

Checked and fine: default bind `127.0.0.1` (`server/__main__.py:430`); `proxy_headers=False`, so
the loopback rule uses the socket address and an `X-Forwarded-For` cannot fake it
(`__main__.py:433-434`); Host allow-list against DNS rebinding (`server/app.py:387-388`); exact
Origin check on writes and WebSocket handshakes (`server/api/__init__.py:242-261`); no CORS
middleware (no `allow_origins` anywhere); cookie `HttpOnly`, `SameSite=Strict`, path `/`
(`server/api/auth.py:161-162`); login tokens `secrets.token_urlsafe(32)` kept only as SHA-256
(`auth/logins.py:110,207,211`); passwords scrypt with per-hash salt, `hmac.compare_digest`
(`auth/passwords.py:51-76`); unknown e-mail costs the same as a wrong password (`auth/accounts.py:353-358`);
pending/disabled reported only after the right password (`accounts.py:359-362`); first admin only
from loopback + own page (`api/auth.py:204-213`); no hard-coded secret; the Anthropic key is read
from the environment only (`assistant/providers/anthropic.py:51-53`).

| id | sev | where | finding | recommended fix | decision |
|---|---|---|---|---|---|
| S1 | med | `server/api/auth.py:184-185` (via `signup`, `:228-237`); known, `docs/PLAN.md:224` | Sign-up for an existing e-mail answers `409 account_exists`, so anyone who can reach the page learns which addresses have accounts. | Answer `201 {status: "pending"}` for both cases (do not create or change the existing account; optionally audit-log the attempt). | n |
| S2 | med | `server/api/auth.py:240-249` (login), `:269-275` (unlock); `auth/logins.py:197-213,303-318`; known, `docs/PLAN.md:225` | No attempt limit on login or unlock. Besides guessing, each unauthenticated attempt costs one scrypt (~0.4 s CPU, 16 MiB; `auth/passwords.py:18-21`, `dummy_verify` included), so a loop of requests can load the PC that drives the stage. | Per-account and per-client-address counters with back-off and a temporary lock (e.g. 5 failures → 15 min), checked **before** the scrypt; audit the lock. Same limiter on unlock (per login session). | n |
| S3 | med | `server/app.py:91-93` (`signup` open without login), `auth/accounts.py:216-219` | Sign-up is open to anyone who can reach the server, with no cap on pending accounts; each request also costs a scrypt hash (same CPU point as S2) and a write to `accounts.json`. Harmless on loopback; under `--remote-view` anyone on the LAN can fill the approval list. | Rate-limit sign-up (S2's limiter) and cap pending accounts (e.g. 20); or refuse sign-up from non-loopback clients unless switched on. | y |
| S4 | med | `server/__main__.py:369-371,430`; `server/api/auth.py:162` | `--remote-view` listens on `0.0.0.0` over **plain HTTP**: passwords and the session cookie cross the LAN in clear text; the cookie has no `Secure` flag (cannot have one over HTTP). | Before real remote viewing: decide how viewers reach it (VPN / Tailscale on the LAN, or TLS in uvicorn with a lab certificate). Do **not** put a reverse proxy or tunnel on the microscope PC (S5). Add `secure=True` when served over HTTPS. Firewall the port to the lab subnet. | y |
| S5 | med | `server/api/__init__.py:217-218` (`is_local` = socket is loopback), `:293-294` (stops without login), `server/app.py:131-135,146-149` (shutdown and first-admin setup from loopback) | "Loopback" means "the microscope PC, trusted". Any local port forwarder (`ssh -L/-R`, ngrok, cloudflared, Tailscale serve, RDP/VS Code port forwarding, a local reverse proxy) makes remote traffic arrive from `127.0.0.1` and get microscope-PC rights: commands (with a login), stops and shutdown without a login, and first-run admin setup. | Document in `docs/runbooks/launcher.md` and the README: never forward or proxy the server port. Optional hardening: refuse requests carrying `X-Forwarded-For`/`Forwarded`/`Via` headers from loopback. | n |
| S6 | low | `server/app.py:363,380-384` | FastAPI's `/docs`, `/redoc` and `/openapi.json` are outside `/api/`, so the access middleware does not cover them: under remote view the full API schema is readable without login. The code will be public anyway, so this only adds convenience for a LAN visitor. | `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` unless `--dev`, or put them behind the login check. | n |
| S7 | low | `auth/logins.py:303-311` | `unlock` runs the scrypt check while holding the login-sessions lock, which every request takes (`login_state` → `logins.get`). A burst of unlock attempts from one locked session stalls all requests for ~0.4 s each. | Verify the password outside `_guard()`, then re-take the lock to flip `locked`. S2's limiter also caps it. | n |
| S8 | low | `server/static.py:41-46`, `server/app.py` | No security headers (`Content-Security-Policy`, `X-Frame-Options`/`frame-ancestors`, `X-Content-Type-Options`). `SameSite=Strict` already stops cookie use in cross-site frames, so clickjacking risk is small. | Add a small middleware with `frame-ancestors 'none'`, `nosniff`, a basic CSP. | n |
| S9 | med | `src/dino_autofocus/live.py:17,104` (`joblib.load(head_path)`), reached from `focus/dino.py:36-42`, `scripts/live_focus.py:444`, `scripts/check_scorer.py:32`; file `models/heads/head_k100x_dinov2_vits14_L1.joblib` | The head is a pickle: loading it runs whatever code it contains. In a public repo a swapped file (a PR, a fork, a tampered clone) is code execution on the microscope PC. Today only the CLI scripts load it, with an explicit `--head`; the server does not. The head is only `StandardScaler` + `MLPRegressor` / `RidgeCV` / `LogisticRegression` (`scripts/train_head.py:44,101,116`): all plain arrays. | Preferred: export the fitted arrays (scaler mean/scale, MLP `coefs_`/`intercepts_`, ridge/logistic `coef_`/`intercept_`) to `.npz` + the existing `.json`, and score with numpy (`np.load(..., allow_pickle=False)`); no sklearn at run time either. Minimum: SHA-256 of the `.joblib` in the `.json`, checked before `joblib.load`, and refuse paths outside `models/heads/`. | y |
| S10 | low | `scripts/train_head.py:33`, `scripts/eval_synthetic.py:44`, `scripts/learning_curve_p5.py:41`, `scripts/plot_pred.py:33`, `scripts/check_scorer.py:29`, `synth/sim/dataset.py:447,543` | `np.load(..., allow_pickle=True)` on generated dataset shards (`scene_params` is an object array). The shards are made locally and never in git, so this is only a risk if someone loads shards from elsewhere. The engine/server side already uses `allow_pickle=False` (`engine/backends/stacks.py:232-350`). | Note it in the dataset runbook; longer term store `scene_params` as JSON. | n |
| S11 | low | `auth/passwords.py:19` | scrypt `N=2**14, r=8, p=1` is below current OWASP guidance (`N=2**17`). The hash format carries its parameters, so it can be raised later. | Raise when S2 lands (cost per attempt matters less once attempts are limited). | n |

## 6. 공개하지 않거나 줄일 내부 문서

Nothing here is secret; the question is what a public reader should see. Recommendations:

| id | sev | where | finding | recommended fix | decision |
|---|---|---|---|---|---|
| D1 | med | `docs/sessions.md`; `docs/tasks/*.md` (49 cards incl. `BACKLOG.md`) | Multi-session coordination (seat names, review/merge rules, per-session worktrees) and task cards. `BACKLOG.md:92-93,224-232` has dev-desktop memory / commit-charge details and the user's personal to-do items; cards cite many internal commit hashes. Useful history, noise for a public reader. | Before publishing: move `docs/sessions.md` and `docs/tasks/` out of the public tree (keep them in the shared folder or a private notes repo), or keep them under a clearly labelled `docs/dev-history/`. History keeps them either way (accept). | y |
| D2 | low | `docs/librarian-handoff.md` | Hand-over question cards for the SMA librarian; holds instrument serials (L6) and HEAD-relative `file:line` notes that go stale. | Keep until the librarian hand-over is done, then delete or move with D1. | n |
| D3 | low | `docs/microscope-pc-checklist.md` | Bench check list; contains P4 paths and host name. | Keep; fix P4. | n |
| D4 | info | `docs/PLAN.md` (Korean; §3 "사용자가 할 것", machine specs), `docs/integration-sma.md`, `docs/integration-notes.md`, `docs/setup-new-pc.md`, `docs/runbooks/*`, `docs/screens/*`, `docs/ui-spec.md`, `docs/operations-spec.md`, `docs/runs/*` | Design and operation docs; fine to publish. `PLAN.md` mentions GPU models and the "user to-do" list, both harmless. | Keep. | n |

## 7. 이력: 다시 쓸지, 그대로 둘지

Only `origin/main` exists on the remote, so making the GitHub repo public publishes `main`'s history
(750 commits) and nothing from the 120 local branches unless they are pushed. Findings that exist
**only in history** or in commit metadata:

| finding | in HEAD? | recommendation |
|---|---|---|
| P1 second author identity (3 commits) | metadata only | **Accept if that person agrees.** A rewrite changes 749 of 750 hashes on `main` (the first of the three commits is the 2nd commit), invalidates every local branch/worktree and every commit hash cited in `docs/` (task cards, `librarian-handoff.md`, `microscope-pc-checklist.md`), and must happen before anything else is merged. Only rewrite if they say no. |
| P5 owner's dev-desktop user path | no (removed in `7b27eba`) | Accept. |
| B1 old pickle blob | yes today | Accept. |
| old versions of docs (P4 paths, P3 operator) | yes | Accept (same content as HEAD). |
| deleted `CLAUDE.md` | no | Accept (harmless). |

No secret was ever committed, so no finding forces a rewrite. Recommended overall: **accept the history**,
settle P1 with the person concerned, and before publishing make sure only `main` is pushed
(do not `git push --all`).

## 8. 사용자가 정할 것 (요약)

1. **L1** `LICENSE` 추가: MIT, "Copyright (c) 2026 Kyu Hwan Choi" (soft-matter-agents 와 같게) — 권고: 추가.
2. **L2** psf-autofocus 의 저작권자와 라이선스 확인 (공급된 약 6천 줄의 출처). 본인 것이 아니면 공개 불가 또는 허락 필요.
3. **P1** 현미경 PC 커밋 3개의 다른 사람 이름·주소: 그 사람에게 묻고 그대로 둠 (권고) / 이력 다시 쓰기. 현미경 PC 의 git 사용자 설정도 고친다.
4. **S9** 포커스 헤드 형식: `.npz` + numpy 로 바꾸기 (권고) / joblib 유지 + SHA-256 고정.
5. **S3, S4** 원격 보기 방식: 가입을 원격에서 열어 둘지, 원격 접속을 VPN·TLS 중 무엇으로 할지 (실제 원격 보기 전에).
6. **D1, L6** 내부 문서 (`docs/sessions.md`, `docs/tasks/`) 를 공개 트리에서 뺄지, 장비 일련번호를 둘지 (권고: 문서는 빼고, 일련번호는 둔다).

Work cards that need no decision: S1, S2 (known), S5 runbook note, S6-S8, S10-S11, K2, K5, L3, L4, P4.
