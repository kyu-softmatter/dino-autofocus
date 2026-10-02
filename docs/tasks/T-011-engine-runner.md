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
  `lights_off` as a stop stays exempt (always accepted, also when locked or remote under D13).
- Allow-list unchanged: Aura lines; DiaLamp `State` and `Intensity` only. Every exit path turns the lights off.

## Graceful shutdown (from the T-016 merge review)

- `shutdown(reason)`: abort the running operation, run the normal exit path (lights off with readback,
  records finished), stop the acquisition stream, and record the reason. The server's `POST /api/shutdown`
  (T-009) calls it.
