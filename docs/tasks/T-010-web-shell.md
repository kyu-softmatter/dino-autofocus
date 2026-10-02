# T-010 WP-D2 웹 셸 (Vite + React + TypeScript)

- 담당: AF 실행4 · 개발 (T-006 다음)
- 묶음: WP-D2 (PLAN.md v0.3 9절)
- 선행: main 1f131fc (`web` 그룹의 Node 22). 생성 타입 연결은 T-009 의 `--dump-openapi` 가 main 에
  들어온 뒤. 그 전에는 골격, 레이아웃, 내비게이션부터 한다
- 배정: 2026-10-01 작성
- 브랜치: `execN/T-010-web-shell`
- **`web/package.json`, `web/package-lock.json` 변경 권한**: 이 과제만 고친다

## 목표

브라우저 앱의 셸. 영역별 화면 (`web/src/features/<영역>/`) 은 각 영역 묶음이 채운다. 이 과제는
프로젝트 골격, 레이아웃, 내비게이션, 상태 표시줄, API 클라이언트, 생성 타입, 라이브 뷰까지다.

## 소유 경로

- `web/` 전체 중 `web/src/features/` 제외
- 예외로 `web/src/features/live/` 는 이 과제 소유 (PLAN.md 9절 WP-D2 내용에 라이브 뷰가 있다.
  서버 쪽 프레임 브리지는 T-009 `ws.py`)
- `web/.gitignore` (`node_modules/`, `dist/`). 루트 `.gitignore` 는 고치지 않는다
- **제외 (v0.4)**: `web/src/app/assistant/` 는 T-014 (공통 프롬프트 칸) 소유다. 셸은 레이아웃에
  프롬프트 칸이 들어갈 자리와 화면 문맥을 넘기는 훅의 이름만 정하고, 컴포넌트는 만들지 않는다

## 내용

- 툴체인: Node 는 `uv run node`, `uv run npm` 으로만 쓴다 (시스템 설치 금지). `npm ci` 가 되도록
  lock 을 커밋한다.
- 영역 6개 (console, hardware, sample, map, objective, live) 의 내비게이션. 영역 화면은
  `web/src/app/` 의 등록표에서 지연 로딩하고, 아직 없는 영역은 셸이 "not implemented yet"
  자리표시를 보여 준다. 영역 묶음은 자기 `features/<영역>/index.tsx` 하나만 만들면 붙도록 등록
  규칙을 정하고 `web/README.md` 에 적는다.
- 상태 표시줄: `/ws/events` 의 `position`, `light_changed` 이벤트와 `GET /api/state`. 조명 상태와
  실행 중 작업을 항상 보이게 한다. 원격 보기 (명령이 403) 일 때는 읽기 전용 표시를 띄우고 명령
  버튼을 끈다.
- 생성 타입: `npm run gen:api` 가 `uv run python -m dino_autofocus.server --dump-openapi` 결과로
  `web/src/api/` 를 생성한다 (예: openapi-typescript). 생성물은 커밋하되 손으로 고치지 않는다.
  T-009 병합 전에는 이 스크립트와 빈 자리만 두고 연결은 병합 뒤 같은 과제에서 한다.
- 라이브 뷰 (`features/live/`): `/ws/frames` 의 JPEG 를 그리고, 프레임 시각과 fps 를 표시.
- 모델 판정은 5개 어휘 (`in_focus | step_up | step_down | no_sample_here | unsure`) 로만, Z 는 엔코더
  값만 표시하는 공통 컴포넌트를 `web/src/app/` 에 둔다 (영역들이 쓴다).
- UI 문구는 영어.

## 테스트

- vitest: 등록표와 자리표시, 상태 표시줄 이벤트 반영, 읽기 전용 모드, 판정 컴포넌트.
- 타입 검사 `tsc --noEmit`.

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests`, 소유 밖 diff 없음,
  커밋 메시지 끝 `Session: AF 실행N`)
- `uv run npm --prefix web ci`, `uv run npm --prefix web run build`, `uv run npm --prefix web test`,
  타입 검사가 모두 통과. `web/dist` 와 `node_modules` 는 커밋하지 않는다
- 끝나면 `[검토요청 T-010]` 를 검토 세션에. package.json 변경이 있다는 것을 첫 줄에 적는다

## v0.6 조정 (PLAN.md 4652b4b, D7)

- 상태 표시줄에 **Claude 데이터 단계** (`prompt_only` | `text` | `images`) 와 공급자 (`fake` | `anthropic`)
  를 항상 보이게 한다. 값은 T-013 의 `GET /api/assistant/status`. 아직 없으면 "assistant: unavailable".
- v0.5 (047048c): 시뮬레이션 화면 (T-012) 이 3D 궤적 뷰어에 Three.js 를 쓴다. `web/package.json` 은 이
  과제 소유이므로, T-012 가 요청하면 매니저를 거쳐 `three` 를 이 과제에서 추가한다 (BACKLOG 참조).

## First-screen notice (ui-spec 5.2, accepted)

- On the first screen, show the last shutdown's light readback from `GET /api/state` → `last_shutdown_lights`
  (T-011 fills it). Warn clearly if any light did not read back off. Second-stage commit; show nothing when
  the field is absent.

## From the screen contracts

- A cross-area link helper (URL scheme), for example console run -> `#/simulation?run_id=...`, so areas link
  without importing each other.

## From the login screen contract (T-105 stage A, db0a4d1)

- Route guard: call `GET /api/auth/me`. On 401 or locked, render `app/login`'s `LoginGate`; any later 401
  returns to it. No `#/login` route.
- Status bar: user name and role, a "remote · read only" badge, the control holder with Take / Release, and a
  user menu (Log out, Lock, Approve accounts for admins).
- Activity hook for the idle lock: `POST /api/auth/activity` on input, throttled to once per 30 s.

## Verdict source (from T-104)

- `FocusVerdict` gets a `source` prop: "model" | "computed". The 100x focus result is "computed", not "model".
  The shell owns the label words; use "computed" everywhere (matches the grade vocabulary
  measured / computed / model).

## Stale readings after a disconnect (safety, from the stage 2 merge review)

- When the event socket drops, the status bar must not keep showing the last lights and XY/Z readings as current.
  Mark them stale/unknown (greyed, "last known at <time>"), especially an old "lights off". Restore on reconnect
  from `GET /api/state`. Test with a fake socket drop.

## vitest under load (from T-100)

- Set vitest `pool: "threads"` and a small `maxWorkers` (e.g. 2) in the web test config; forks workers time out when
  the machine is loaded by other seats.
