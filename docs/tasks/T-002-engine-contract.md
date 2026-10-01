# T-002 WP-A 엔진 계약

- 담당: AF 실행1 · 개발
- 묶음: WP-A (PLAN.md 8절). **가장 먼저**: WP-B·C·D·E 가 이 인터페이스를 기다린다
- 선행: 없음 (T-001 과 독립)
- 배정: 2026-10-01, 총괄 승인 (제안 디렉터리 그대로, D1–D3 는 추후 조정)
- 브랜치: `exec1/T-002-engine-contract`

## 목표

UI 없이 import 되고 하드웨어 없이 테스트되는 엔진의 **계약(골격)** 을 만든다. 구현의 양보다
인터페이스의 명확성이 중요하다. 백엔드 구현(WP-B), 작업 이식(WP-C)은 이 과제에 넣지 않는다.
목표 분량은 테스트 포함 600줄 안팎. 작게 끝내고 빨리 병합한다.

## 소유 경로

- `src/dino_autofocus/engine/__init__.py`, `backend.py`, `events.py`, `records.py`, `guards.py`, `sample.py`
- `tests/engine/conftest.py`, `tests/engine/test_contract*.py`

다른 경로는 수정하지 않는다. `scripts/*` 는 읽기만 한다.

## 총괄 조건 (그대로 지킨다)

1. 엔진 API 는 Qt, tkinter, 다른 UI 툴킷을 import 하지 않는다. 이벤트는 순수 Python 콜백
   (`Callable[[Event], None]`) 또는 `queue.Queue` 로 낸다.
2. 같은 프로세스 실행(D3 권고안)을 전제로 하되, 명령과 이벤트는 **직렬화 가능한 dataclass**
   (`dataclasses.asdict` → `json.dumps` 가 그대로 되는 것)로 만든다. 나중에 프로세스를 나눌 수
   있어야 한다.
3. `import dino_autofocus.engine` 시점에 torch, pymmcore, tkinter 가 import 되지 않는다
   (PLAN.md 5절 7항). 테스트로 확인한다.

## 모듈별 내용

### `backend.py` — Backend 프로토콜

현재 스크립트가 하드웨어에 하는 일을 전부 덮는 `typing.Protocol` (또는 ABC). 근거 코드:
`scripts/mm_grab.py` (`open_core`, `set_and_read`, `aura_on/off`, `positions`, `PiezoReader.move_z`),
`scripts/change_objective.py` (`state`, Nosepiece/PFS 읽기), `scripts/scan_4x.py` (XY 이동, 조명).
부록의 "WP-C 가 백엔드에서 필요로 하는 것" 목록을 모두 덮는다.

- 수명: open / close. close 는 모든 종료 경로에서 소등을 보장하는 자리와 연결된다 (guards 참조).
- 정보: `info()` → config, camera, sensor, roi, exposure_ms, pixel_um, objective, intermediate_mag,
  image bit depth (Kinetix 는 12-bit, 천장 4095).
- 프레임: `snap()` → `Frame` (mono uint16 ndarray + 메타: 시각, z_um, x_um, y_um, exposure_ms).
  autofocus-jev 의 교훈대로 프레임의 z 는 노출 시점이 아닐 수 있으니 메타에 읽은 시각을 둔다.
- 설정: `set_exposure(ms)`, `set_roi(size)`.
- 위치: `positions()` → x_um, y_um, z_um, 선택적으로 piezo, 읽기 실패는 예외가 아니라 필드로.
- 속성: `read_property(device, prop)`, `set_property(device, prop, value)` → **읽어서 확인한 기록**
  (`set_and_read` 의 `verified` 패턴). 쓰기는 모두 readback 기록을 돌려준다.
- 조명: Aura 라인 켜기(퍼밀 단위 주의), Aura 끄기, DiaLamp 켜기/끄기, **전체 소등**.
- 모션: Z 이동, XY 이동, Nosepiece 읽기/설정, PFS 상태 읽기/끄기. 모션 메서드는 **가드를 거친
  경로로만** 호출될 수 있게 설계한다 (아래 guards). 백엔드가 직접 안전을 판단하지 않는다.

### `events.py` — 명령과 이벤트

- `Command`: 작업 시작(이름 + 인자 dict), 중단(abort), 사용자 확인 응답(confirm: 예 — 100x 상향
  연장 승인, 오일 확인).
- `Event`: 작업 생애주기 (planned, preflight_ok / preflight_failed, started, progress, frame_ready,
  reading, finished, aborted, error), 하드웨어 (position, light_changed, property_set 기록),
  confirm_required (UI 가 대화상자를 띄울 지점), log.
- 모두 `kind`, `t` (시각), `op_id` 를 가진 dataclass. JSON 왕복 테스트.
- `EventSink` = 콜백 또는 큐. 엔진은 sink 가 UI 인지 모른다.

### `records.py` — 기록

PLAN.md 5절 4항: 모든 작업은 시작 상태, 보낸 명령, 읽은 값, 종료 상태를 남긴다.
- 작업마다 `<sample_dir>/<op>_<stamp>/` 에 `log.jsonl` (이벤트 그대로) 과 `summary.json`.
- 모델이 낸 숫자는 기록에서 `"grade": "model"` 로 표시된다 (PLAN.md 5절 3항). 필드 이름을
  여기서 정하고 WP-E 가 따른다.
- 종료 상태에는 조명 상태 readback 이 반드시 들어간다.

### `guards.py` — 가드 골격

`C:\agentic_microscope\hardware\focus.py::FocusAxis` 는 이 저장소 밖(현미경 PC)에 있어 읽을 수
없다. 스크립트의 **사용 방식**(부록)과 `docs/runs/2026-09-30_substrate-scan.md` 에서 규칙을
끌어내 순수 함수/클래스로 만든다. WP-C 가 기계적으로 이식할 수 있게 부록의 메서드 이름과
결과 필드 이름을 따른다.

규칙 (하드웨어 없이 테스트):
- Z 창 `SAMPLE_Z_WINDOW_UM = (2800, 3200)`. 밖이면 거부. 예외: 렌즈 교체 시 Z→0 후퇴 경로는
  `change_objective.py` 의 순서(PFS off → Z 0 → PFS out-of-range 확인 → 회전 → Z 2800)로만.
- 스윕은 **상향만** (`plan` 이 오름차순, 내려가는 이동은 `allow_ascent_um` 규칙으로 명시 허용).
- 100x 천장 `min(3200, centre + 0.4 * 130)` (free WD 130 µm). 피크가 스팬 꼭대기면 올라가지 않고
  `confirm_required` 를 낸다.
- readback 검증: 명령값과 읽은 값의 허용 오차, 어긋나면 중단 (운영 기록: 3037 명령 / 3036 읽음에서
  가드가 섰다).
- XY 박스: 스캔 박스 + 1 mm 밖은 거부.
- 종료 시 소등: `with` 컨텍스트(또는 try/finally)로 **모든 종료 경로**에서 Aura·DiaLamp off + readback.
  `live_focus.py` 의 DiaLamp 미소등 버그를 여기서 구조적으로 막는다.
- 코어 단일 소유: 엔진 인스턴스 하나만 백엔드를 연다.
- 모델 출력은 어떤 가드 입력에도 들어가지 않는다.
- `dry_run=` 은 모션을 기록만 하고 보내지 않는다 (scan_4x `--dry-run`).

### `sample.py` — 샘플 폴더 모델

`scripts/live_focus.py` 의 `Sample` 에서 tkinter 캔버스 결합을 떼어낸 순수 모델.
- id 규칙 `YYYYMMDD_HHMM_n`, 폴더 배치 (`sample.json`, `map.json`, `track_*.jsonl`,
  `scan4x_*/`, `focus100x_*.json`), `sample.json` 읽기/쓰기 왕복.
- 루트는 기본 `D:\AutoFocus\samples` 이되 인자로 바꿀 수 있다 (이 데스크톱에는 없다).
- 지도 그리기(XYMap 의 draw)는 UI 몫이다. 경계점·방문 필드 데이터만 여기서 다룬다.

### `tests/engine/`

- `conftest.py`: 프로토콜을 메모리에서 구현하는 `FakeBackend` (고정 프레임, 위치는 명령대로
  움직이고 readback 은 설정 가능하게 어긋낼 수 있음). WP-B 의 인메모리 replay 와 WP-C 테스트가
  이 fixture 를 가져다 쓴다.
- `test_contract_*.py`: import 시 torch/pymmcore/tkinter 없음, 이벤트 JSON 왕복, 가드 거부 사례
  (창 밖, 하향, readback 어긋남, XY 박스 밖, 100x 천장), 예외 경로에서도 소등 기록이 남음,
  sample.json 왕복 (`tmp_path`).

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests`, 소유 밖 diff 없음,
  커밋 메시지 끝 `Session: AF 실행1`)
- `uv run python -c "import sys, dino_autofocus.engine; assert not {'torch','pymmcore','tkinter'} & set(sys.modules)"`
- 위 모듈과 테스트가 있고, `FakeBackend` 로 가짜 작업 하나가 기록 폴더를 남기는 테스트가 통과
- 끝나면 `[검토요청 T-002]` 를 검토 세션에. 인터페이스 결정 중 애매한 것은 `[이슈]` 로 매니저에게

## 참고

- `docs/PLAN.md` 4·5절, `docs/integration-notes.md` (autofocus-jev, soft-matter-agents 절)
- `docs/runs/2026-09-30_substrate-scan.md` 2·3절 (운영 규칙, 설정값)
- 실행5 가 쓰는 `docs/ui-spec.md` (T-004) 초안이 오면 매니저가 전달한다. 이벤트 목록의 입력이
  되지만 기다리지는 않는다.

## 부록: 스크립트가 쓰는 FocusAxis API (실행4 조사, 2026-10-01)

WP-C 는 이 이름들이 `guards.py` 의 가드 Z 축에 있다고 기대한다. 인터페이스 소유는 WP-A 한 곳이다.

- `plan(centre_um, half_um, step_um)` → 상향 스윕 계획, `.describe()` 있음
- `sweep(plan, grab, score=fn, settle_s=)` → 결과: `.points[i].z_um / .z_readback_um / .score /
  .diagnostics (dict)`, `.argmax_index`, `.peak_z_um`, `.peak_interior`
  (원본의 `.verdict()` 는 WP-E 어휘를 쓰므로 T-002 에서는 `peak_interior` 등 원자료만 두고
  판정 매핑은 T-003 에 맡긴다)
- `move_to(z_um, allow_ascent_um=)`, `park_at(z_um)` → 착지 z 반환, `position_um()`
- `require_pfs_quiet(disable=True)`; 생성자 `allow_motion=`, `dry_run=`
- 모듈 함수 `best_z_um(coarse, fine) -> (z | None, why: str)`, `registry_key(nosepiece_label)`
  (렌즈별 설정 키; 4x, 100x-Oil)

WP-C 가 백엔드에서 필요로 하는 것: `snap()` → uint16 frame, property get/set + readback 기록,
`aura_on(line, pct)` / `aura_off()`, DiaLamp on/off, XY goto/read, Z read, Nosepiece label 읽기,
exposure get/set, image bit depth.

## 부록 2: Micro-Manager 데모 장치 실측 (실행3 조사, 2026-10-01)

Backend 프로토콜이 mm-demo 와 mm-real 을 둘 다 덮으려면 아래를 고려한다.

- 데모 Z (DStage) 범위가 −300~+300 µm 이고 원점 이동이 안 된다. mm-demo 는 백엔드 안에서
  오프셋을 둔다 (demo_z = z_um − 오프셋). **가드와 기록은 벤치 좌표 2800–3200 을 그대로 쓴다.**
  즉 프로토콜의 z 는 항상 벤치 좌표다.
- 데모 카메라 "Fluorescent Beads" 모드는 z 에 따라 결정적인 초점 곡선을 준다 (vollath4 기준 0 µm
  17.5, ±5 µm 3.1, ±20 µm 0.04). 데스크톱에서 초점 작업 테스트가 가능하다.
- 데모 XY 는 기본 속도에서 약 25 mm 넘는 이동이 코어 타임아웃 5 s 에 걸린다. 프로토콜의 XY
  이동은 타임아웃을 인자 또는 백엔드 설정으로 둔다.
- 광원 대응: DiaLamp 는 데모의 "White Light Shutter", Aura 는 LED 라벨과 LED Shutter. LED Shutter
  에는 State 속성이 없어 셔터 API 로만 다룬다. 그래서 프로토콜의 조명 메서드는 "속성 쓰기" 가
  아니라 **의미 단위** (`lamp_on/off`, `aura_line_on(line, percent)`, `aura_off`, `all_off`) 로 두고,
  각 메서드가 readback 기록을 돌려준다.

## v0.2 조정 (PLAN.md v0.2, 6ba1bc1)

PLAN.md 9절에서 WP-A 소유에 `gates.py` 가 추가됐다. 골격만 만들고 규칙 내용은 WP-G 가 채운다.
분량 목표는 그대로 작게 유지한다.

- 소유 경로 추가: `src/dino_autofocus/engine/gates.py`, 테스트는 `tests/engine/test_contract_gates.py`.
- `gates.py` 골격: 작업마다 필요한 장치와 조건을 선언하는 자료형 (`GateRequirement`), 하드웨어
  구성 파일 (`hardware_profile.json`, 가칭) 의 최소 자료형 (탐지 시각, 장치별 상태, 사람이 확인한
  항목), `evaluate(profile, requirements) -> {op: (enabled, reasons)}`. 꺼진 작업은 **이유 목록**과
  함께 돌려준다 (UI 가 숨기지 않고 이유를 보여 준다). 게이트는 코드가 판정하고, 모델이나 UI
  대화상자가 열지 않는다.
- 가드 규칙 추가 (PLAN.md 2절 F4·F5, 5절):
  - **큰 XY 이동은 Z 후퇴 상태가 읽기로 확인될 때만** 허용한다. "큰 이동" 기준과 후퇴 높이는 상수로
    두고 값이 미정이면 docstring 에 "추후 측정" 으로 적는다 (F5 이탈은 Y 약 15–20 mm).
  - **복귀 후 Z 는 목표로 점프하지 않고** 후퇴 위치에서 단계적으로 접근한다. 가드 Z 축에
    단계 접근 메서드를 둔다 (이름 예: `approach(target_um, step_um)`), 매 단계 readback.
- 이벤트와 기록: 수동 단계 (예: 액침액 로딩 후 "로딩 완료" 클릭) 를 명령 (`confirm`) 과 기록
  항목으로 남긴다 (PLAN.md 6절 4항).
- Backend 의 기본 구현은 이제 `mock` 시뮬레이터다 (T-007, 실행3). 프로토콜의 `info()` 에
  대물렌즈 세트 (라벨, 배율, 픽셀 크기, 작동 거리) 와 재물대 한계를 담을 자리를 둔다.

## 부록 3: T-006 초안에서 온 요구 (실행4, 042726b, 2026-10-01)

`docs/operations-spec.md` 0.1절에 "스크립트 호출 → 엔진 호출" 이름표가 있다. T-002 에 이름이 없던
것은 가칭으로 적혀 있다: `xy_move`, `nosepiece_read` / `nosepiece_set`, `pfs_read`. 이름을 다르게
정하면 매니저에게 알린다 (실행4 가 명세를 맞춘다).

원본 스크립트의 빈틈 (엔진에서 구조로 막는다):
1. 조명을 켜는 도중 예외가 나면 `finally` 가 소등하지 않는다. **조명을 켜기 전에 종료 컨텍스트에
   들어간다.**
2. 조명 readback `verified=False` 를 아무도 확인하지 않는다. 엔진은 어긋나면 작업을 멈춘다.
3. XY 이동 후 readback 을 명령값과 비교하지 않는다 (9월 30일 사람이 재물대를 움직인 사례).
   XY 에도 Z 와 같은 readback 가드를 둔다.

매니저 결정 (2026-10-01):
- **`lights_off` 는 선점 명령이다.** 다른 작업이 실행 중이어도 받고, 그 작업을 abort 한 뒤 전체
  소등을 readback 으로 확인한다. 이 명령만 단일 소유 규칙의 예외다.
- **상태 표시는 `position` 이벤트로** 갱신한다. `status` 작업은 사용자가 요청할 때만 돌고
  기록 폴더를 만든다. 주기 갱신은 기록 폴더를 만들지 않는다.
- `sample.py` 의 hole 에 **`fitted_at`** 를 둔다. "세션마다 재추적" 규칙의 입력이다.
- 기록 폴더 이름은 기존 도구가 찾는 접두를 유지한다: `scan4x_<stamp>/`. 그 안에 엔진 공통
  `log.jsonl`, `summary.json` 과 함께 기존 형식의 `scan.json` 도 쓴다 (런처와 `plot_scan.py` 호환).
  records 는 작업이 폴더 접두를 지정할 수 있게 한다.

## 단계별 병합 (총괄 지시, 2026-10-01)

T-002 는 열 개가 넘는 과제의 선행이다. 한 번에 끝내지 말고 세 번에 나눠 `[검토요청 T-002-1]`,
`-2`, `-3` 으로 낸다. 같은 브랜치에 이어서 커밋하고, 단계마다 검토요청에 그 단계의 커밋 범위를 적는다.

1. **T-002-1**: `backend.py` (프로토콜), `events.py` (명령·이벤트 자료형, kind 목록 상수), `__init__.py`,
   `tests/engine/conftest.py` 의 `FakeBackend`, 해당 테스트. 이것이 들어가면 T-015, T-017, T-013, T-009 의
   상당 부분이 풀린다.
2. **T-002-2**: `guards.py`, `gates.py` 골격과 테스트.
3. **T-002-3**: `records.py`, `sample.py` 와 테스트.

각 단계는 그 자체로 공통 완료 조건을 통과해야 한다.

## 규칙 12와 임시 값 표시 (PLAN.md v0.7, 총괄 승인)

- **모든 명령과 기록에 `user_id` 와 `session_id` (실험 세션 id) 필드**를 둔다 (1단계 `Command`, 3단계
  records). 값이 없으면 null 로 기록한다. 거부 규칙 (operator 로그인과 열린 세션이 없으면 동작 명령 거부,
  정지는 항상 받음) 은 T-011 이 구현한다.
- 측정 전 임시 상수 (큰 XY 이동 문턱, z_safe, F5 이탈 거리 등) 는 코드에서 **"unmeasured provisional"**
  로 표시하고, 그 값이 가드 판단에 쓰인 기록에도 같은 표시를 남겨 실측값과 구분한다.
