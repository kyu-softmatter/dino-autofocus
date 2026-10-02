# T-011 WP-A 엔진 실행기

- 담당: AF 실행15 · 개발 (실행1 은 T-002 2·3단계를 계속한다)
- 묶음: WP-A
- 선행: **T-002-1 병합** (backend, events). 2·3단계는 기다리지 않는다. 가드와 기록은 주입받는 자리로 둔다
- 배정: 2026-10-01 작성 (실행7 의 T-009 질문에서 나옴)
- 브랜치: `exec15/T-011-engine-runner`

## 목표

명령을 받아 작업을 실행하는 엔진 본체. 서버 (T-009) 는 판단하지 않으므로 dispatch, 작업 스레드,
op_id 발급, abort / confirm 전달, 선점 소등은 엔진에 있어야 한다.

## 소유 경로

- `src/dino_autofocus/engine/runner.py`
- `tests/engine/test_contract_runner.py`

## 내용

- T-009 가 가정한 인터페이스를 그대로 구현한다:
  `submit(cmd) -> op_id`, `subscribe(sink) -> unsubscribe`, `snapshot() -> dict`.
  `EngineAPI` Protocol 을 이 파일에 정의해 서버가 import 하게 한다 (T-009 병합 뒤 서버 쪽 사본을
  이것으로 바꾸는 일은 서버 소유 세션에 배정한다).
- 작업 등록표: 이름 → 작업 클래스 (`plan → preflight → run → abort`). 작업 구현은 WP-C 몫이고
  여기서는 등록 장치와 테스트용 가짜 작업만.
- 한 번에 작업 하나 (코어 단일 소유). 실행 중 새 작업 명령은 거부 이벤트.
- **`lights_off` 는 선점**: 실행 중 작업을 abort 하고 전체 소등을 readback 으로 확인 (T-002 부록 3).
- `confirm_required` 이벤트와 `confirm` 명령을 op_id 로 짝짓는다. 시간 제한 없이 기다리되 abort 는 받는다.
- 모든 종료 경로에서 소등 기록과 `finished` / `aborted` / `error` 이벤트.
- 주기 `position` 이벤트 (간격 설정 가능, 기록 폴더 없음).
- 스레드 안전한 sink 호출. 엔진은 sink 가 서버인지 모른다. UI 툴킷 import 금지.

## 완료 조건

- 공통 조건 (커밋 메시지 끝 `Session: AF 실행1`)
- `FakeBackend` 와 가짜 작업으로: 정상 종료, abort, 선점 소등, confirm 짝짓기, 동시 제출 거부,
  예외 경로의 소등 기록 테스트
- 끝나면 `[검토요청 T-011]`

## v0.4 조정 (PLAN.md v0.4, 5f25603)

Claude 연동 (X2, PLAN.md 6절 11항): Claude 는 제안만 한다. 엔진 실행기의 확인 흐름을 Claude 제안에도
쓴다.

- 동작 명령에 상태를 둔다: `proposed → confirmed → running → finished | aborted | error`, 그리고
  `proposed → rejected`. 사람이 확인하기 전에는 하드웨어 호출이 없다. 확인 뒤에도 게이트와 가드를
  그대로 지난다.
- 모든 Command 와 기록에 **출처 필드** `origin: "human" | "assistant"` 를 둔다. assistant 제안이면
  제안 id 와 대화 id 를 함께 남긴다. 확인한 사람의 동작 (확인 / 거부, 시각) 도 기록한다.
- 사람이 직접 낸 동작 명령은 지금처럼 바로 `confirmed` 로 들어간다. 확인 대화상자가 필요한
  지점 (100x 상향, 오일) 의 `confirm_required` 와는 별개의 단계다.
- 서버 쪽 제안 카드 API 는 T-013 이 만든다. 엔진은 제안 저장과 상태 전이만 맡는다.

## T-006 명세에서 온 요구 (실행4, 341e344)

T-002-1 병합 뒤 이 과제가 `engine/events.py` 수정도 맡는다 (소유 이전. 실행1 의 2·3단계는 events.py 를 고치지 않는다).

- **실행 중 인자 변경 명령**: `update` (op_id, 바꿀 인자 dict). 예: edge_trace 의 `+` / `-` 속도.
  작업이 바꿀 수 있는 인자를 선언하고, 선언 밖은 거부 이벤트.
- **`confirm_required` 의 종류 `manual_step`**: F5 의 액침액 로딩 "Loading done". 응답을 수동 단계
  기록으로 남긴다.
- **종료 상태 `awaiting_return`**: F5 를 이탈·회전 뒤 중단했을 때. 샘플 기록에 남기고, 그동안 다른
  모션 작업은 preflight 에서 막는다. 복귀 작업만 허용한다.

## 규칙 12 (PLAN.md v0.7)

- 모든 Command, 이벤트, 기록에 `user_id` 와 `session_id` (실험 세션 id).
- **로그인한 operator 의 제어권 토큰 (T-018 `auth/control.py`) 과 열린 실험 세션 (T-019) 이 없으면
  장비를 움직이는 명령은 거부**한다. 정지 (`abort`, `lights_off`) 는 예외로 항상, 잠긴 상태에서도 받는다.
- T-018, T-019 가 아직 main 에 없으면 확인 함수를 주입받는 자리로 두고 테스트는 가짜로 한다.

## T-004 명세에서 온 결정 (실행5, 0f37167 4.4절. 매니저 결정 2026-10-01)

- **연속 획득은 작업이 아니라 엔진 소유 "획득 스트림"** 이다. 단일 소유 규칙에 세지 않는다. 라이브 뷰가
  켜진 동안에도 edge_trace (`t`) 같은 작업을 받는다.
- 스냅을 직접 하는 작업 (scan_4x, focus_100x) 은 시작할 때 스트림을 멈추고 끝나면 (모든 종료 경로에서)
  원래 상태로 되돌린다.
- **하드웨어를 움직이지 않는 기록 작업** (경계점 표시 `b`, 되돌리기 `u`, tare `z`, 샘플 열기) 은 단일 소유
  규칙에서 뺀다. 실행 중인 작업과 동시에 받는다. 기록에는 그대로 남긴다.
- 원격 abort 허용 여부, 로컬 탭이 모두 끊겼을 때 자동 abort 여부는 사용자 결정 대기다 (총괄에 올림).
  설정 값으로 두고 기본은 "원격 abort 허용", "자동 abort 끔" 으로 시작한다. 결정되면 기본값만 바꾼다.

## v1.0 decisions (PLAN.md 3494688, D13 and D14). Supersedes the defaults in the T-004 section above

- **D13**: a remote viewer may send `abort` and nothing else. Default **on**. Every other command from a
  non-loopback client is refused (the server's 403 rule in T-009 stays; `abort` is the one exception).
- **D14**: during operator-watched operations (declare this per operation, e.g. `edge_trace`), the engine
  aborts **10 s** after every microscope-PC (loopback) browser connection has dropped. Default **on**,
  timeout 10 s, both kept as settings. A reconnect inside the window cancels the timer.
- Record both in the operation log when they fire: which rule, who or what triggered it, the time, and
  for D14 the moment the last connection dropped. Abort then follows the normal exit path (lights off,
  readback recorded).
- The engine learns about browser connections from the server through one call (for example
  `set_local_viewers(count)`), so the engine still imports no web framework.

## From the T-004 spec (실행5, 6fcd8a8, ui-spec 7.5)

- The return-only operation allowed while `awaiting_return` is `start("objective_change", {"resume": true})`.
  Every other motion operation is refused in preflight until it finishes.

## From the T-002-1 review (7f62722)

- `Command("start")` currently accepts `op=""`. Refuse an empty or unregistered operation name with a
  refusal event (events.py is yours now).

## Last-shutdown light readback (ui-spec 5.2, accepted)

- On every engine stop, the final light readback is already recorded. On start, load the last one and put it
  in `snapshot()` as `last_shutdown_lights` (readback dicts plus the time and whether every light read off).
  The web shell shows it on the first screen (T-010).

## D15 (PLAN v1.1, 6beb85a): lights at M3

- `light_set` and `lights_off` are available from M3, on the microscope PC in read-only mode. Nothing moves.
- Gate light commands exactly like motion: operator logged in with the control token, experiment session open.
  `lights_off` as a stop stays exempt locally (any logged-in user, also when locked). Remote clients may
  send `abort` only (D13, confirmed); remote `lights_off` is refused.
- Allow-list unchanged: Aura lines; DiaLamp `State` and `Intensity` only. Every exit path turns the lights off.

## Graceful shutdown (from the T-016 merge review)

- `shutdown(reason)`: abort the running operation, run the normal exit path (lights off with readback,
  records finished), stop the acquisition stream, and record the reason. The server's `POST /api/shutdown`
  (T-009) calls it.

## Shutdown safety (director)

- `shutdown(reason)` runs `lights_off` FIRST, then aborts and finishes records.
- The engine marks itself running in a small state file at start and clears it on a clean shutdown. On the
  next start, if the mark is still there, record "unclean shutdown", read the lights back, and report it in
  `snapshot()` (next to `last_shutdown_lights`) before accepting any command.

## From the screen contracts (T-100/101/102 stage A)

- Add event kinds `map_changed`, `sample_opened`, `objective`, and command kind `update`, to EVENT_KINDS and
  COMMAND_KINDS.
- `snapshot()["hardware"] = {profile, profile_path, gates, last_status}`.
- One permission table, op -> (action class, needs control token, needs open session). The server reads it
  (T-009). Op names the screens use: `hardware_scan{include_properties, piezo_port}`, `hardware_confirm{items}`,
  `status`, `light_set{mode, line, percent}`, `edge_trace{hole_diameter_mm, ...}`, `boundary_mark`,
  `boundary_undo`, `boundary_reset`, `scan_4x`, `sample_map`, `goto_xy`, `map_flag`, `map_flag_retire`,
  `candidate_confirm`, `candidate_reject`. `lights_off` and `abort` are command kinds, not `start(...)`.
- Correction: under D13 a remote client may send `abort` only. Remote `lights_off` is refused for now
  (abort's exit path turns the lights off). Locally anyone logged in may send `abort` and `lights_off`.
  Confirmed by the director. Tests: a remote abort ends with lights off (readback recorded); a remote
  `lights_off` is refused with a clear reason.

## From the sessions screen contract (T-106 stage A, 85b25ad)

- `set_experiment_session(session_id | None, started_at | None)`: the server calls it on open, close and
  continue. The engine uses it for rule 12 (refuse motion without an open session) and for the "re-trace
  every session" check.
- Event kind `session_changed {session_id, started_at, state}` on the event stream.

## Control grant (from T-105)

- The control grant arrives attached to the Command by the server, never from the browser. The engine checks
  the grant against the control object (T-018) and ignores any token-like field supplied in command args.

## From the objective screen contract (T-104 stage A)

- Event kind `objective` (label, state, readback) in EVENT_KINDS.
- `plan(cmd) -> dict`: run an operation's `plan` step only, with no hardware calls, for the screen's GET plan.
- Session and sample rule (manager decision, answers 실행1): one sample per experiment session (T-019 as
  written). `sample_open` and `sample_new` run with no session open (they pick the sample for the next
  session; nothing moves); with a session open they refuse unless the sample is the session's own.

## Frame hand-over to the server (from T-009)

- Optional `FrameSource.latest_frame() -> (uint16 ndarray, meta) | None`, read by the server on `frame_ready`.
  The engine keeps only the newest frame for it. `EngineAPI.shutdown(reason)` is blocking (lights off first).

## Sample block in the snapshot (from T-106, G9)

- `snapshot()["sample"] = {sample_id, reserved, session_id}`, so the server can open a session for the current
  sample.

## Bench backends need a clearance callback (from T-002-4 pre-review)

- When the backend is a bench backend (mm-real), the runner refuses any op that calls `approach()` without a
  clearance callback. Before M4.

## Permission check for the screens (from T-103)

- `check(ops, context) -> {op: {allowed, reason}}`, computed from the one permission table plus engine state
  (running op, awaiting_return, open session, control holder). The server adds remote and auth state
  (T-009b `GET /api/permissions`). Screens never compute these reasons themselves.

## Light payload shape (from T-010 stage 2; manager decision)

- `light_changed` and the snapshot's lights use one shape: `{dialamp: {state, intensity}, aura: {state, lines:
  {<LINE>: percent}}, verified, records}` (ui-spec 4.4 names plus the readback fields). Drop the generic
  `{state: {device: read}}` form.

## Permission classes (manager, confirms 실행15's table)

| op | class | control | session |
|---|---|---|---|
| hardware_scan, status | read | yes | no |
| hardware_confirm, sample_open, sample_new | record | yes (hardware_confirm: local operator only) | no |
| sample_geometry_set, loading_confirm_person, loading_check_image | record | yes | yes |
| boundary_mark/undo/reset, map_flag, map_flag_retire, candidate_confirm/reject | record (beside a hardware op) | no; local operator (D16) | yes |
| score_tare | record | yes | yes |
| light_set | light | yes | yes |
| edge_trace, scan_4x, sample_map, goto_xy, focus_100x, objective_change | motion | yes | yes |
| unknown op | motion (strictest) | yes | yes |
| abort, lights_off | stop | no (D13: remote abort only) | no |

## Exit-path lights (manager decision, from T-030 review)

- A normal op exit (finished) restores the lights to their state before the op: it turns off what that
  op turned on and leaves a light set by `light_set` alone. `error`, `abort`, `lights_off`, `shutdown`, D14 auto-abort and
  closing the experiment session turn everything off (PLAN rule 5, aa32fcf). Record which rule applied. Test: `light_set` then
  `status` keeps the light on; `light_set` then `abort` turns it off.
