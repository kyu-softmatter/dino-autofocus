# T-009 WP-D1 서버 골격 (FastAPI)

- 담당: AF 실행7 · 개발
- 묶음: WP-D1 (PLAN.md v0.3 9절)
- 선행: main 1f131fc (PLAN v0.3, `web` 그룹). 엔진 실행기 T-011 은 기다리지 않는다 (가짜 엔진으로 테스트)
- 배정: 2026-10-01, 총괄 지시
- 브랜치: `exec7/T-009-server-skeleton`
- **의존성 변경 권한**: 이 과제만 `pyproject.toml`, `uv.lock` 을 고친다 (아래 의존성 절)

## 목표

엔진의 유일한 소유자인 FastAPI 서버의 골격. 서버는 판단하지 않는다. 요청을 엔진 명령으로
옮기고 엔진 이벤트와 프레임을 WebSocket 으로 내보낸다. 영역별 라우터 (`server/api/<영역>.py`)
는 각 영역 묶음이 채운다. 이 과제는 구조, 공통 스키마, 접속 범위, 정적 파일 제공까지다.

## 소유 경로

- `src/dino_autofocus/server/__init__.py`, `__main__.py`, `app.py`, `ws.py`, `static.py`
- `src/dino_autofocus/server/schemas/` (공통 스키마)
- `src/dino_autofocus/server/api/__init__.py` (라우터 등록 장치만. 영역 파일은 만들지 않는다)
- `tests/server/` (파일 이름 `test_server_*.py`)
- `pyproject.toml`, `uv.lock` (의존성 절의 변경만)

## 결정 사항 (실행7 질문에 대한 매니저 답)

1. **엔진 실행기는 엔진 쪽 소유다.** `engine/runner.py` 를 T-011 (실행1, T-002 다음) 이 만든다.
   서버는 아래 인터페이스만 가정하고, 테스트는 `tests/server/` 안의 가짜 엔진으로 한다.
   ```python
   class EngineAPI(Protocol):
       def submit(self, cmd: Command) -> str: ...            # op_id. abort/confirm/lights_off 도 Command
       def subscribe(self, sink: Callable[[Event], None]) -> Callable[[], None]: ...  # 반환값 = 구독 해제
       def snapshot(self) -> dict: ...                         # 현재 상태 (위치, 조명, 실행 중 작업), JSON 가능
   ```
   서버 안에서는 이 Protocol 을 서버 쪽 타입으로 두고, T-011 이 병합되면 엔진 쪽 정의로 바꾼다.
2. **계약은 pydantic 이 엔진 dataclass 를 감싼다.** `server/schemas/` 의 pydantic 모델이 엔진
   `Command` / `Event` 를 감싸고, `kind` 는 엔진의 kind 목록에서 만든 `Literal` 이며 `data` 는 dict.
   엔진 kind 목록과 어긋나면 실패하는 테스트를 둔다. 영역별 `data` 의 타입은 각 영역 묶음이 정한다.
   T-002 가 아직 main 에 없으면 kind 목록을 임시 상수로 두고 `[이슈]` 로 알린다.
3. **원격은 읽기 전용.** 기본 바인딩 `127.0.0.1`. 원격 보기는 명령행 `--remote-view` 또는 환경변수
   `DINO_AF_REMOTE_VIEW=1` 로 켜고, 켜면 `0.0.0.0` 에 바인딩한다. 어느 경우든 **명령 경로**
   (POST 와 WebSocket 명령 메시지) 는 `request.client.host` 가 루프백일 때만 받고 나머지는 403.
   GET 과 이벤트 구독은 원격에서도 된다. `configs/*.yaml` 은 광학 설정 전용이라 쓰지 않는다.
4. **의존성**: `pydantic` 을 명시하고 (지금은 간접 의존성), `fastapi`, `uvicorn[standard]` 를 의존성
   그룹 `server` 로 넣어 `default-groups` 에 추가한다. `httpx` 는 `dev` 그룹에. 1f131fc 위에서 고쳐
   `uv lock` 으로 lock 을 다시 만든다. 다른 세션은 main 을 받은 뒤 `uv sync`.
   패키지 배포용 선택 의존성 (`ui`, `hw`, `ml`) 분리는 D2 결정 때 한다.

## 내용

- `app.py`: `create_app(engine: EngineAPI, *, remote_view: bool) -> FastAPI`. 전역 싱글턴 없이
  주입. 공통 엔드포인트: `GET /api/health`, `GET /api/state` (`snapshot`), `POST /api/commands`
  (Command 제출, op_id 반환). 영역 라우터는 `server/api/` 의 등록 장치로 붙는다.
- `ws.py`: `/ws/events` (엔진 이벤트 JSON 스트림, 구독 해제 정리), `/ws/frames` (라이브 프레임
  브리지: 엔진 `frame_ready` 를 서버에서 비닝해 약 800 px JPEG 로, 목표 10 fps, 느린 클라이언트는
  최신 프레임만 받게 버린다). JPEG 인코딩 라이브러리가 필요하면 의존성 절에 함께 넣는다.
- `static.py`: `web/dist` 가 있으면 `/` 에서 제공, 없으면 안내 페이지. Node 는 실행에 필요 없다.
- `__main__.py`: `uv run python -m dino_autofocus.server [--remote-view] [--port N] [--backend mock]`
  과 `--dump-openapi PATH` (서버를 띄우지 않고 OpenAPI JSON 을 쓴다. T-010 이 TS 타입 생성에 쓴다).
  실제 엔진이 아직 없으면 `--backend` 는 가짜 엔진만 지원하고 그렇게 표시한다.
- 서버 import 시 torch, pymmcore, UI 툴킷 없음.

## 테스트 (`tests/server/test_server_*.py`)

- health / state / commands 왕복 (httpx `TestClient`), 이벤트 WebSocket 수신, 원격 주소에서 명령
  403 과 GET 허용, 스키마 kind 목록 일치, `--dump-openapi` 결과에 공통 스키마 포함, import 시
  무거운 모듈 없음, 프레임 브리지의 크기와 속도 제한 (가짜 프레임).

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests`, 소유 밖 diff 없음,
  커밋 메시지 끝 `Session: AF 실행7`)
- `uv run python -m dino_autofocus.server --dump-openapi out.json` 이 동작
- 끝나면 `[검토요청 T-009]` 를 검토 세션에. 의존성 변경이 있다는 것을 첫 줄에 적는다

## Graceful shutdown route (from the T-016 merge review)

- `POST /api/shutdown`, loopback only (refused for remote viewers, including under D13). It asks the engine to
  stop: abort the running operation, lights off with readback, finish records, then the server exits.
  The launcher (T-026) calls it before any hard kill. Test with the fake engine.

## Shutdown safety (director)

- Hardware must not depend on the graceful route alone. The server's own exit hooks (signal handlers and
  `atexit`) call the engine's all-off as well, so Ctrl+C or a normal process exit still turns lights off.

## From the screen contracts (T-100/101/102 stage A, 업무분배보조)

- `create_app(engine, *, agent_store=..., remote_view=...)` keeps the AgentStore on `app.state`, with an
  `AgentStoreDep` in `server/api/__init__.py`. The dev default is `MockStore`.
- An auth dependency that yields `(login token or None, is_local)` from the cookie plus loopback. The T-018
  control object lives on `app.state` (a stub until T-018 merges).
- `/api/commands` consults the engine's permission table (T-011, op -> action, needs control, needs session).
  The server does not keep its own copy.
- `/api/commands` refuses `map_flag`, `map_flag_retire`, `candidate_confirm`, `candidate_reject`. Those go only
  through `server/api/map.py`, which checks `WRITE_MAP_FLAG` (D16). The common endpoint must not bypass it.
- D13: remote POSTs stay refused except `abort`.

## From the login screen contract (T-105 stage A, db0a4d1)

- Remote viewers must be able to log in (PLAN 5). Exempt exactly `POST /api/auth/{login, logout, unlock,
  activity, signup}` from the loopback-only write rule. None of them reaches the engine.
- Export the loopback rule as a dependency (e.g. `IsLocal`) so `server/api/auth.py` reuses it.
- A cookie check on `/ws/*` and every other `/api/*` router. Abort and the stop path stay open (D13/D2).
- The control token never reaches the browser. The server attaches the operator's grant to the engine
  Command, and the browser sees only `has_control`.

## Split (manager, 2026-10-01): T-009 now, T-009b after T-011 and T-018

- T-009 (review now): everything independent of unmerged work, plus AgentStoreDep, IsLocal, the auth POST
  exemptions and the D16 refusal on `/api/commands`.
- T-009b (same branch or `exec7/T-009b`, after T-011 and T-018 merge): cookie check on `/ws/*` and `/api/*`,
  attaching the control grant to the engine Command, and reading the T-011 permission table.
- Dependencies: `pillow` for JPEG. `httpx2` instead of `httpx`, only if it is the package Starlette's own docs
  name for TestClient. State the source and the package's maintainer in the review request.

## Shared permissions endpoint (T-009b, from T-103)

- `GET /api/permissions?ops=a,b,c` -> `{op: {allowed, reason}}`: engine `check()` (T-011) plus remote, role and
  login state. Every screen uses it for pre-click disabled reasons (ui-spec 7.0). Area routers add only
  area-specific items (e.g. `can_open_folder`). Feature gates stay in `/api/hardware/gates`.
- `/api/permissions` also answers non-engine actions, from the T-018 named permissions plus loopback:
  `session_open`, `session_close`, `session_continue`, `submit_question`. Engine ops (including `map_flag`,
  `map_flag_retire`, `candidate_confirm`, `candidate_reject`) come from the engine's `check()`. Area-only rules
  stay in the area routers as 403/409.

## Typed snapshot (T-009b, from T-010)

- A pydantic `Snapshot` model for `GET /api/state` (lights, positions, running op, sample, hardware,
  last_shutdown_lights, unclean_shutdown), so the web side gets generated types instead of an untyped dict.
- T-009b test (director): a request from another loopback origin without a session cookie gets nothing beyond the
  login routes (no state, no events, no commands except loopback abort and lights_off; PLAN rule 12 and D13 as of
  85440a5/5be7028: remote abort needs a login, remote lights_off stays refused).

## Mark remote refusals (T-009b, from the screen manager)

- The remote middleware's 403 carries `detail.code = "remote_view"` (and a header `X-DinoAF-Refusal: remote_view`).
  Every other 403 (D16, session owner, role) uses its own code. Test both.

## Sample seat wiring (T-009b, from T-027 9e192b0)

- At app start: `import dino_autofocus.engine.operations.sample_ops` (registers the ops) and
  `install_sample_seat(runner, SampleSeat(store, samples_root, session_for))`, where `session_for(session_id)` returns the
  server's open ExperimentSession object, so every writer shares one seq counter.
- The sessions router (T-106) calls `ensure_sample_created(session, store)` on session open.

## From the T-009 merge (9901bbc)

- T-009b: parametrize the 422 test over SERVER_STAMPED so any future server-stamped field is covered.
- Until T-009b lands, user_id and control_grant are always None, so a real Runner refuses every non-stop command;
  T-009b fixes that by stamping them from the login cookie and the control object.

## T-009b contract for T-105 / T-106 (실행7, accepted by the manager; read on resume)

- Cookie `dinoaf_session` (SESSION_COOKIE in server/api/__init__.py) holds the T-018 login token; T-105's login route
  sets it HttpOnly, SameSite=Strict, Path=/.
- `app.state.auth = AuthSeat(accounts, logins, control, audit)`; control routes call `seat.acquire(token, local=...)`
  and `seat.release(token)`, never `control.*`; the browser sees only `has_control`.
- Without a login: GET /api/health, the six POST /api/auth/* routes, POST /api/shutdown (loopback), and on
  /api/commands: `abort` and `lights_off` from loopback. A remote `abort` needs a logged-in viewer (D13). Everything
  else: 401 `login_required`; a locked login: 423 `locked` except stops and auth routes. GET /api/auth/me without a
  cookie is 401. T-105 asks 실행7 if it needs another open GET.
- Refusal shape: `detail = {code, message}` plus header `X-DinoAF-Refusal`. Codes: remote_view, foreign_origin,
  map_route, role, local_only (403), login_required (401), locked (423).
- Stamping: user_id from the login, control_grant from the seat; session_id stays None (the runner uses the session the
  server set); T-106 calls `runner.set_experiment_session`. Role from `engine.runner.permission(op)`.
- `/api/permissions`: engine check() plus login, lock, remote, role; session_open/close/continue = local operator,
  logged in, unlocked; submit_question = allows(role, SUBMIT_QUESTION, local).
- D14: loopback /ws/events connections reported through `engine.set_local_viewers(count)`.
- Sample seat wiring waits for T-027 (a single wiring function as the seam).

## T-009c (AF 실행7, after T-009b merges; review AF 검토보조1)

- (a) WebSocket handshake runs the same `origin_refusal` as HTTP (a cross-site page can open a WebSocket to
  127.0.0.1). Test a foreign Origin refused on `/ws/events` and `/ws/frames`.
- (b) Waits for the director (D14/X3): whether a locked loopback login keeps a viewer socket that counts for D14.
  Options under decision: a count-only socket (lock state only) or the full read-only streams for the same login.
  Do not implement until the decision is recorded here.
- (c) SAFETY (실행7, corrected): SameSite ignores ports, so a page served on another loopback port of the same host
  carries the `dinoaf_session` cookie and passes today's loopback origin check. If the operator holds control, it
  can send commands stamped with that grant (hardware moves). Fix: on REST and the WS handshake accept only the
  server's own origin (Origin netloc == Host) plus dev origins named explicitly (`--dev-origin`, default none; the
  T-010 Vite proxy sets it). Tests for a foreign port, localhost vs 127.0.0.1, and a listed dev origin.
- Status: the whole card is held until the director replies (D14 question pending); (a) and (c) do not depend on it.

## T-009d (AF 실행7, from T-105; review AF 검토보조3; T-105 waits for it)

1. First-run setup must be reachable without a login: add `/api/auth/setup` to OPEN_READS and `setup/admin` to
   AUTH_OPEN_PATHS. The handler (T-105) stays loopback-only (403 `remote_view` from a remote PC) and returns 409
   once an admin exists.
   SAFETY: this is the only write that works with no login, so the middleware also requires the request's
   Origin to be the server's own on this path, independent of T-009c: scheme, host and port compared exactly
   with the server's own origin. "Is loopback" is not enough (`origin_refusal` accepts any loopback port). No dev
   exception until T-009c adds explicit `--dev-origin` values; first-run setup in dev goes to the server's port.
   Tests: no Origin, a foreign loopback port, localhost vs 127.0.0.1, http vs https, and the own origin.
2. `tests/server/test_server_login.py`: replace `post("/api/auth/login", json={}) == 404  # T-105` with a check
   that does not break when T-105's router exists (e.g. `!= 401`, the path is open).
3. `GET /api/auth/me` answers a locked login (`locked_ok=True` in `_http_refusal`), so the lock screen knows whose
   password to ask for and can tell locked from logged out. No login still gives 401. Every other read stays 423
   while locked.
4. (from the screen manager; blocks all seven screen routers) Replace
   `test_server_rest.py::test_no_area_routers_yet` (`include_area_routers(FastAPI()) == []`) with a test that does
   not name areas: every module under `server/api/` not starting with "_" exposes a module-level `router` and is
   mounted at `/api/<name>`; a module without `router` raises TypeError (use a temporary test package).
