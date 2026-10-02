# 매니저 대기 목록

과제로 아직 배정하지 않은 요구, 공유 파일 변경 순서, 현미경 PC 확인 항목을 모은다. 매니저만 쓴다.

## HANDOVER (freeze, 2026-10-02) — read this first

**Freeze lifted by the user on 2026-10-02** (after the bench results below); new work may be carded again.
Earlier user decision: no new work is assigned. Work already committed or in review finishes (review → merge → push by hash);
then each seat is archived. Development moves to another platform later; this section is the handover list.
Everything below "HANDOVER" is the older working backlog and stays for history.

### State at the end of the freeze (main = origin/main = 3cbe466)

- Nothing is in flight. All 108 local exec* branches are contained in main. Last suite on the merged tree:
  pytest 1488 passed, 11 skipped; vitest 322 passed; build ok; no D:\AutoFocus* folder created by tests.
- Merged after the freeze: T-009g/i/j (server starts the real runner, mock by default, separate mock records root,
  replay start-up, op records into the open session), schema regen 3, T-010-9, T-010-12, T-012-6 (gsd), T-013c,
  T-015e, T-032 stage 2 (sample_map, goto_xy with PFS off first), T-105 login, T-106 sessions.
- Safety locks: `mm_real.BENCH_MOTION = "LOCKED"` (on). `guards.BENCH_APPROACH` was `"UNMEASURED"` at the freeze;
  the user unlocked it to `"MEASURED"` on 2026-10-02 (see below).
- After `git merge main`, run `uv sync` (anthropic and gsd are in the server group).
- All seats are archived except the director, AF 검토 and the manager.

### Carded but not started (unassigned; pick up from the card)

- ~~Schema regen 4~~ (done with the dual-camera live view, 2026-10-02: `WsFrame.camera`; the clashing
  `GateRow` / `HardwareProfileOut` names were split). Left: T-104's screen can swap to generated types.
- T-035d import torch only inside torch tests: tests/test_backbone.py and tests/test_live.py (T-035 card).
- T-106b session.json carries backend kind/bench; T-106c records/librarian_mock.py skips bench:false sessions in the
  real root (T-106 card).
- T-026 stage 3 launcher `-Backend mock|mm-demo|replay|mm-real` (mm-real only with `-Bench`) (T-026 card).
- T-038d runbook step 2c: remove "blocked" once goto_xy (T-032 stage 2) is on main (T-038 card).
- T-101b (contingent) align features/hardware + server/api/hardware.py if T-028 field names change.
- T-107 browser M1 walk-through in web/e2e/ reusing T-035's mock day; needs a headless-browser package decision.
- SECURITY (from T-105 review, 검토보조3): `POST /api/auth/signup` answers 409 `account_exists`, which tells a caller
  (remote viewers can call signup) that an email is registered; and login/unlock have no attempt limit. Before real
  logins or remote viewing: a neutral signup answer and a per-account and per-client attempt limit with lockout.

### 2026-10-02 bench results

First three items done (user approved, freeze lifted 2026-10-02); the rest are open.

Source: docs/microscope-pc-checklist.md "2026-10-02 현미경 PC 결과", docs/runs/2026-10-02_bench-properties.json,
configs/micromanager/*.cfg (byte-exact; `.gitattributes` keeps them `-text`).

- DONE AURA lines: the Aura is "Aura III 5-NII-WA" with UV, CYAN, GREEN, RED, NIR. `engine/backend.py`
  `AURA_LINES = ("VIOLET", "CYAN", "GREEN", "RED")` is wrong (no VIOLET; UV and NIR missing). Touches
  LIGHT_PROPERTIES, mm_real/mm_demo provisional flags, the demo label map (mm_demo_core has no UV/NIR LED),
  tests/engine/test_contract_runner.py:1041. Keep `MEASURED_AURA_LINES = ("GREEN",)`: only the names were read.
- DONE Camera allow-list: readout property is `ReadoutRate`, but its allowed values depend on `Port` (today
  `Port=Dynamic Range` → only `100MHz 16bit`). Add `Port` and `ReadoutRate` together or neither; 9/30's
  `100MHz 12bit` came from another Port (unconfirmed).
- DONE FREE_WD (T-027b): catalog values from the librarian (E3): 10x 4 mm, 20x 0.8 mm, 40x WI 0.17 mm (user, 2026-10-02;
  catalog range 0.16–0.20, the 0.17-collar value is not in the catalog), 60x Oil 0.15 mm. Candidates for `guards.FREE_WD_UM` and
  `BENCH_FREE_WD_UM` (states 1–4). Effect: 10x and 20x may now approach above 2800 µm (WD ≥ the 400 µm window),
  40x-WI/60x-Oil get sweep ceilings and become F5 targets. On the bench, `BENCH_APPROACH` blocked it until the user unlocked it the same day.
- Stage Y limit is at least 20498.8 µm (one +Y 15 mm step-out, readback within 5 µm, < 30 s at 25 mm/s).
  X/Y limits are not readable as properties; mm-real still reports "unknown".
- Core.Focus is empty in the bench cfg (`getFocusDevice()` = ""). mm-real names `ZDrive`, so fine; anything using
  the default focus device fails.
- Light path: the single-cam cfg has no CSU-W1 device, so `CSUW1-Port` keeps its previous value. If it was left at
  State 0 (blue_only), Kinetix_red gets no light with no error. Candidate hardware_scan warning.
  Port states (cfg labels + user): 0 blue_only (100/0 mirror), 1 blue_red (561 nm dichroic), 2 red_only (no mirror).
  Tell the librarian session: this fills `csuw1_port_slots` state numbers; Lapp mirror is 50/50 (new).
- Unexplained drift: between the first property read and the step-out, Z 485.16 → 483.62 µm and Y ~0.7 µm with no
  software command. Hand contact unconfirmed. Check before trusting z readback across idle periods.
- PFS: off from the start; `enableContinuousFocus(False)` reads off. Turning it off from on is still unchecked.

### Blocked on the user

- T-036 unlock: the one-line `BENCH_MOTION = "UNLOCKED"` in engine/backends/mm_real.py was refused by the seat's
  permission check, so it is the user's (branch exec12/T-036-unlock parked at ebfff88). All eleven code prerequisites
  are on main (b1d5a1d). Director: do it when the user is at the microscope PC for runbook step 1.
- PARTIAL (user, 2026-10-02, "2800 제한 해제", before the measurements): `guards.BENCH_APPROACH = "MEASURED"`.
  On the bench, `bench_ascent_refusal` now refuses every upward move (approach, sweeps, move_to) above the lens's
  `approach_ceiling_um`: 3200 for 4x/10x/20x, 2800 for 40x-WI/60x-Oil/100x-Oil/unknown. focus_100x stays refused
  on the bench. Full unlock of the high-mag lenses waits for Q13/Q20 (a sweep's first move has no clearance check).
- Microscope PC measurements and checks (see "현미경 PC" items below and docs/microscope-pc-checklist.md):
  ~~cfg passes `check_load_settings` with BENCH_DEVICES~~ (OK, 2026-10-02); ~~whether System/Shutdown applies at
  unload~~ (the bench cfg has no Shutdown preset); stage limits (Y ≥ 20498.8 µm; the +Y 15 mm step-out ran once
  on 2026-10-02); Q13 (approach step) and Q20 (XY move needing a Z retract); FREE_WD for 10x/20x/40x WI/60x
  (catalog values in, bench check and the 40x 0.17-collar value open); T-029d per-step read latency.
- trajectory.txt samples (three layouts) and the WSL source path, for the T-012 txt reader (now "unverified").
- Copy the old Desktop "DINO Autofocus.exe" aside before `build.ps1 -Force`.
- Operator name in docs/runs/2026-09-30_* ("kyuchoi"): keep or replace before the repo goes public.
- M1 check: log in on the dev desktop and run F1–F7 end to end on the mock (after T-009i, T-105, T-106 merge).

### Process notes for whoever continues

- Rules live in docs/sessions.md (branch from a hash, `git merge main`, commit by path, push by hash only by the
  reviewer, full suites limited to 3 at once with `OPENBLAS/OMP/MKL_NUM_THREADS=1`).
- This desktop's limit is Windows commit charge, not RAM: about 30 open sessions left 10 GB free; full runs crash
  with 0xc000070a / 0x8007000e below ~20 GB free. Those codes mean rerun, not a test failure. Check for orphaned
  pytest processes too: one full run from exec4 hung for ~16 h (2026-10-01 18:44 to 10-02) holding memory unseen.
- Safety cards to read before any stand motion: T-036 (lock), T-029d (BENCH_APPROACH), T-027b (per-lens ceiling),
  T-015b/c (is_bench fail-safe), T-036b/d (preset check), T-029c (step-out intent), T-038 (runbook).
- Ownership after archiving: guards/sample.py/gates had 실행1/17, runner 실행15; any new owner reads those cards.

## 공유 파일 변경 순서

| 파일 | 지금 권한 | 다음 | 그다음 |
|---|---|---|---|
| `pyproject.toml`, `uv.lock` | T-012 (실행9: `gsd`), since T-013b (anthropic) merged 2026-10-02 | 다음 요청자 (매니저 경유) | |
| `web/package.json`, `package-lock.json` | T-010 (실행4). 열려 있는 동안 요청받은 패키지를 이 과제가 넣는다 | 차트 라이브러리 (T-012 그래프) | `three` (3D 뷰어), 그다음 T-014 요청분 |

권한은 앞 과제가 main 에 병합된 뒤 넘긴다.

`web/src/api/schema.ts` (generated): only T-010 (실행4) commits it. Screen-router branches keep their wire types in
their own `api.ts`; after each router merges, 실행4 reruns `gen:api` and the area swaps to the generated types in a
small follow-up (screen manager rule, 2026-10-02).

요청 접수:
- T-022 (실행16): `dependencies` 에 `three`, `devDependencies` 에 `@types/three`. 래퍼 (@react-three/fiber 등) 없음.
  T-010 1차 골격 병합 뒤 package.json 권한자가 넣는다.

## Review routing (manager, 2026-10-01)

Dev seats send `[검토요청 T-NNN]` to the assistant for their task. One branch, one assistant.

| Assistant | Tasks |
|---|---|
| AF 검토보조1 | T-002 (all stages), T-008 (done), T-011, T-015, T-025, T-027, T-028, T-035 |
| AF 검토보조2 | T-007, T-012, T-021, T-023, T-024, T-030, T-031, T-032, T-033, T-034 |
| AF 검토보조3 | T-004, T-009, T-013, T-018, T-019 |
| AF 검토보조4 | T-010, T-014, T-016, T-020, T-022 |

New tasks get an assistant in their card. Unlisted tasks go to the least loaded assistant.

## Manager to-do on events

- Done (de89198): T-038b sent to 실행11. T-032 stage 2 merged → 실행10 unblocks runbook step 2c (T-038d; 실행11 archived).

- **Quota pause (director, after the 19:20 outage):** active 실행1, 3, 4, 6, 7, 10, 11, 12, 15, 17 + AF 검토,
  검토보조1, 2. Paused: 실행2, 5, 8, 9, 13, 14, 16 (after T-037 commit), 18, 19, 20, 검토보조3, 4, 업무분배보조.
  Resume all when T-009b and T-010 stage 4 merge, then tell the director. No broadcasts.
  **Done 2026-10-02 (T-009b bb9935f):** resumed 업무분배보조 (resumes its own screen seats), 실행8, 9, 16, 검토보조3, 4.
- T-009 reviews go to 검토보조1 while 검토보조3 is paused.
- T-009 and T-010 first skeletons merged → tell AF 업무분배보조 (screen stage B starts).
- 실행14 (T-020) or 실행5 (T-004) review cleared → offer the seat to AF 업무분배보조 for T-103 / T-104.
- T-018 merged → 실행13 starts T-105 (screen manager). T-019 merged → 실행2 starts T-106.

- T-009 merged → T-010 reruns gen:api (schema.ts from T-009 b9fb6cc); T-026 stage 2 (실행10); screen routers start;
  T-009b starts (실행7).
- T-009 + T-105 merged → user browser check of the live view and login (via the director).

- Merge order: T-009b (remote_view mark) and T-010 stage 4 (client rule) before any screen router (T-100..T-106 stage B).

- SAFETY: mm-real stays read-only (no motion ops on the stand) until T-027's bench-clearance guard, T-011b's bench check (f70f8d2), T-015b's fail-safe bench flag, T-027b's per-lens approach ceiling (37f5c6c), the two is_bench follow-ups (guards: T-027b item 3; runner: 실행15), T-015c (is_bench never raises), T-029c (step-out intent written first), T-029d (no bench approach until measured) and T-036d (preset check on configured device labels) are all on main. Tell the director when they are.

- On resume of the screen routers: T-106 (실행2) calls `ensure_sample_created(session, store)` on session open (T-027 seam).
- T-015b merged → one bench rule: 실행1 switches `FocusAxis._simulated` and the guards to `is_bench(info)` (T-027b item 3,
  review 검토보조1); 실행15 switches `runner._on_bench` (runner.py ~1144) to it. Review 검토보조2.
  Done when `git grep` finds no direct `BackendInfo.bench` read outside `is_bench()` (today guards.py ~353
  `getattr(info, "bench", None)` and runner.py ~1151 `info.bench`). The lift plan to the director carries the three
  merge hashes (T-015b, guards, runner) and that grep output (director, d960ffd).

## 후속 과제 후보

- **WP-C 초점 이식에 같이 넣을 것** (실행2 메모, 2026-10-01): `focus/classical.py` 에
  `block_scores(img, n=6)` (scan_4x 의 `block_z_um`), 끝에서 None 을 내는 포물선 래퍼 (`parabola_peak`
  호환), 이중 피크 감지 ("check immersion oil" 경고). 담당은 실행2 (T-003 작성자).
- **T-015 백엔드 프로토콜 확장 + MockBackend**: 실행12 에 묶어서 준다 (T-002 병합 뒤).
- **WP-G 하드웨어 파악**: T-002, T-015 뒤.
- **mm_demo.py 본체**: T-017 (실행11) 뒤, T-002 병합 뒤.
- **3D 궤적 뷰어 (Three.js)**: T-012 1단계 (프레임 형식) 병합 뒤, 2D 와 병렬. 소유
  `web/src/features/simulation/viewer3d/`. 시작할 때 `three` 를 package.json 권한자가 넣는다.
- **T-014 공통 프롬프트 칸**: 실행13 예약, T-010 1차 골격 병합 뒤.
- **서버의 EngineAPI 사본 교체**: T-011 병합 뒤, T-009 소유 세션.

- **로그인 서버·화면**: `server/api/auth.py` (쿠키 HttpOnly, SameSite=Strict), `web/src/app/login/`.
  T-018, T-009, T-010 뒤. 담당은 T-018 작성자 (실행13) 가 유력. 런처는 고치지 않는다 (첫 화면 주소만 연다).
- **실험 세션 API·화면**: `server/api/sessions.py`, `web/src/features/sessions/`. T-019, T-009, T-010 뒤.
- **WP-C 이식, WP-G, WP-H, WP-J**: T-002 병합 단계에 맞춰.

- **런북 보강** (검토 세션 제안, T-003 병합 때): `docs/runbooks/train-focus-head.md` 1절에 DINOv2 가중치가
  첫 실행 때 인터넷에서 받아진다는 점, 현미경 PC 가 오프라인이면 `~/.cache/torch/hub/checkpoints` 를
  미리 복사해야 한다는 점을 넣는다.
- **T-019 git 쪽 구현**: 세션별 브랜치/워크트리 대 한 브랜치 폴더별 커밋. 사용자 결정 뒤.

- **From the T-004 spec (실행5, 6fcd8a8), accepted, for future cards:**
  - WP-H: record operations `sample_geometry_set`, `loading_confirm_person`, `loading_check_image` (ui-spec 7.3).
  - WP-I: append-only `map_flag_retire`, `candidate_confirm`, `candidate_reject` (ui-spec 7.4).
  - WP-G: `hardware_confirm` for human-confirmed profile items (ui-spec 7.2).
  - Server/web: first-screen notice of the last shutdown's light readback (ui-spec 5.2).
  - Piezo keys f / w / W stay disabled until M5 (operations-spec 9.2).
- **ops-spec nit (next touch of docs/operations-spec.md):** escape_dy_um direction is decided: +Y, 15 mm, unmeasured provisional (PLAN v1.3, fbc1e08).
- **ui-spec nit (next touch of docs/ui-spec.md):** image check grade is "computed", not "classical". 4.0 transport row still calls abort open; D13 decided it. `update` stays in the command table (T-011 adds it to COMMAND_KINDS).
- **Waiting on the director/user:** real `light_set`/`lights_off` at M3 instead of M4; whether viewers
  may submit questions to the mock store and write flags (default: local operator only).

## Engine requirements promised to the screens (for WP-C, G, I cards)

- Op names are fixed by the screen contracts (list in T-011). Engine cards must use them.
- **Sample state storage (manager decision):** boundary points, flags and candidates are append-only events
  in the open experiment session's `records/sample_events.jsonl` (PLAN 5, T-019). The engine has one
  reader that folds them into the current state. Legacy `sample.json` / `map.json` are derived views for
  the old tools. Flag and candidate writes need an open session. The engine assigns `flag_id` and
  `candidate_id`, and a reject is a new entry with source `person_rejected`.
- WP-G: HardwareProfile gets host, config, per-device type/library/properties/write_verified, objective rows,
  camera, piezo, positions/pfs/lights (ops-spec 5). Confirmed items are `{value, by, at}`, and profile history
  keeps a diff. This is not added to T-002-2; it goes into the WP-G card.
- WP-C: `light_set{mode, line, percent}` op. WP-C/WP-I: `scan_4x` writes `mosaic.npy` and `mosaic.json`
  (orientation "stage", `M_px_per_um`, objective, `n_tiles`); `goto_xy` event payloads; `scan_box_um`
  and `allowed_box_um` in `summary.json`.
- 4x focus plane at the current XY (default centre for focus_100x, T-104 gap 6): owner WP-C focus port.
- Lens table: engine data inside guards (fa2bdcd). Q8 only asks where FocusAxis keeps its WD values, so the
  provisional rows can cite their source. Moves to the person-owned envelope at integration.

- **T-107 (screen manager, later):** browser M1 walk-through in `web/e2e/` (not tests/e2e/, which is T-035). Needs a
  headless browser package decision (downloads binaries) with the director, then T-010's package.json order.
- **Free seat:** 실행16 after T-022b.

## 현미경 PC 확인 항목 (총괄에 넘김)

- `docs/operations-spec.md` 10절 Q1–Q21 (실행4, T-006)
- T-003 임시 상수: `MIN_DYNAMIC_RANGE_ADU` 20, `MIN_CURVE_CONTRAST` 0.05, `MAX_SIGMA_DOF` 3.0,
  `IN_FOCUS_DOF` 1.0
- 암전 판정 방식: T-003 은 프레임마다 p99.9 − median < 20 ADU, T-006 명세의 focus_100x preflight 는
  최댓값이 암전 오프셋 (약 102 ADU) 근처. 둘 중 무엇을 쓸지
- 임시 가드 값 (T-015): 큰 XY 이동 문턱 min(렌즈 시야, 1 mm), z_safe 0 µm, F5 이탈 거리 기본값 없음
- Microscope PC: free working distance (`FREE_WD_UM`) for 10x, 20x, 40x WI, 60x before they become rotation targets (T-029).
- Microscope PC (T-036b, b7c8c98): the bench cfg passes `check_load_settings` (no motion device in System/Startup, System/Shutdown or post-init Property lines), and whether the core applies System/Shutdown at unload.
- Watch (2026-10-02): a native crash / hang in the full pytest run under heavy parallel load, seen three times
  (실행5, 검토보조2 hang at 25%, AF 검토 Windows fatal exception); reruns pass. No test or native frame captured yet.
  Reviewers keep the full pytest log (faulthandler on). When a frame names a module, card a fix.
  Diagnosed (AF 검토, full log on d544ea9 + T-029b): three crashes in one run at unrelated places (platform WMI
  query 0x8007000e, a .pyc read 0xc000070a, pure Python in engine/sample.py 0xc000070a) = machine-wide memory /
  commit-charge exhaustion, not a code bug (same code as docs/integration-notes.md). 0xc000070a / 0x8007000e in a
  test run means "rerun when the machine is quieter", not a failure. Run-limit rule proposed to the director.
  Measured (AF 검토, after T-031b's run): commit charge 9.0 GB free of 81.9 GB, while physical RAM had 25.7 GB free.
  The limit is commit (mostly the ~30 open sessions), so a full suite needs commit headroom; pausing does not free
  it, closing a session or a bigger pagefile does (both are the user's).
  Hangs (two, at 22-25 %): in collection order that band is tests/e2e, then test_backends_mm_demo / mm_demo_core
  (native pymmcore demo adapters). Both hung only while other full suites ran; a lone run with
  faulthandler_timeout=180 passed in 7 min (검토보조2, 13b75b3 + T-037). Unnamed until a dump is captured.
- User (T-012 txt reader, 실행9): three small `trajectory.txt` samples from the WSL run folders, one per layout:
  run-20260924-001-smoke-g2k2 (2D, 98 kB), run-20260923-201-v5-k3-o3 (3D, 134 kB), and the first ~2000 lines of an
  ABP run with theta (e.g. run-20260923-042-small-s2). Put them outside both repos (soft-matter-agents stays
  read-only), e.g. `D:\AutoFocus\sim_samples\<run_id>\trajectory.txt`, and give the WSL source path for
  `DINO_AF_SIM_TRAJECTORY_ROOTS`.
- User (T-026 stage 2, b2f3952): the Desktop "DINO Autofocus.exe" is the user's old tkinter build. Copy it aside before
  running `build.ps1 -Force` (the script also keeps it as `.prev.exe`).
- Microscope PC (T-029d): the bench ascent check reads `info()` and `nosepiece()` on every upward Z step (two core
  reads per step, uncached on purpose so a lens change is never missed). Measure the per-step latency on the stand
  before the BENCH_APPROACH flip.
- T-036 unlock (2026-10-02): every code prerequisite is on main (b1d5a1d). The flip of `BENCH_MOTION` was refused by
  실행12's own permission check, so it is the user's: approve it in 실행12's window or make the one-line edit. Director
  recommends holding it until the user is at the microscope PC for runbook step 1. `exec12/T-036-unlock` is parked
  at ebfff88; no other seat makes the edit.
- Integration (M6, director 2026-10-02): the soft-matter-agents librarian must skip sessions whose session.json has
  `bench: false` (T-106b), as a second guard behind the separate mock records root (T-009i).
- Seats archived (2026-10-02, user via director): 실행1 (guards, sample.py), 15 (runner), 16, 17 (gates, hardware_scan).
  Their files keep their cards; new work in those paths goes to an active seat: guards/sample.py and gates → 실행12
  (bench and lock context), runner.py → 실행7 (server wiring context). 실행3, 11 and 19 archived next; T-101b (only if
  T-028 field names change) and features/hardware + server/api/hardware.py go to 실행14 (screen manager).
