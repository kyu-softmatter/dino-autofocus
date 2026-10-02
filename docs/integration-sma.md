# soft-matter-agents 통합 준비 (M6, 초안 2026-10-02)

PLAN.md 8절 M6 "soft-matter-agents 어댑터 설계" 의 출발점. 근거는 soft-matter-agents `baf6f1e`
(2026-09-29) 를 읽기 전용으로 읽은 결과와 이 저장소 main `d239448`. 그쪽 경로는 그 저장소 기준이다.
이 문서는 설계 초안이고, 결정은 7절의 사람 결정을 거친다.

## 1. 지금 상태 요약

| | dino-autofocus | soft-matter-agents |
|---|---|---|
| 초점 | `focus/` 고전 지표 + 판정 (`in_focus \| step_up \| step_down \| no_sample_here \| unsure`), DINO 는 보조 | 초점 코드 없음. 과제 026 (2단계 첫 초점) **미배정**. 판정 어휘는 `plan.md` §13.2 Trial 2 에 있다 |
| Z 이동 | 엔진 가드 안에서만, 실제 장비는 두 겹 잠금 (`BENCH_MOTION`, `BENCH_APPROACH`) | ZDrive 는 네 곳에서 거부 (`SOFTWARE_MAY_COMMAND` 에 없음, `NAMED_REFUSALS`, `REFUSED_CALLS`, 과제 033) |
| 한계값 | `guards.py` 의 표, 모두 `unmeasured provisional` (40x WI 0.17 mm 는 사용자 값) | `envelope/safety.json` (사람만 씀). **ZDrive 위치·스텝·속도, XY 이동 범위, 초점 탐색 범위 키가 없다.** 스키마가 `additionalProperties:false` |
| 기록 | 실험 세션 폴더, 작업별 기록, 수치에 grade (`measured \| computed \| model`) | `runs/<run_id>/log.json` (run_log 스키마), 등급 E1–E6, 모델 숫자는 E6 이고 카드에 들어가지 않는다 |
| 의존성 | core 에 torch, pymmcore-plus 0.18.1, sklearn, matplotlib 등 | pixi `mic`: pymmcore-plus 0.18.1 / pymmcore 12.5.0.75.0 (같은 고정값). torch, sklearn, skimage, pydantic, pyyaml **없음** |
| 공개 | 비공개 (D5: 통합 때 공개) | 공개 |

## 2. 통합의 기본 방향 (권고)

**soft-matter-agents 의 orchestrator 가 장비를 움직이는 유일한 경로로 남는다.** 이 저장소의 엔진·가드를
그쪽에 두 번째 모션 경로로 들여가지 않는다. 그쪽 규칙상 `devices/` 는 orchestrator 만 부르고, 안전 비교는
결정론적 Python 이며, 모든 이동은 plan 필드에서 `from` 을 달고 나온다.

그래서 넘겨줄 것은 세 가지로 나뉜다.

1. **판정 제공자 (verdict provider)**: 프레임에서 나온 결정론적 지표와 엔코더 Z 를 받아 판정 하나,
   가리킨 프레임, 근거를 돌려주는 순수 함수. Z 를 돌려주지 않고, 무엇도 허용하지 않는다 (거부만 가능).
   `focus/verdict.py` 의 `from_sweep` 이 이미 이 모양이다 (numpy 만, scipy 는 함수 안 import).
2. **화면 (UI)**: 이 저장소의 웹 앱은 그쪽 파일을 읽기만 한다 (`agents/sma_files.py`). 통합 뒤에도
   장비 쪽은 그쪽 run 과 approval 을 보여 주고, 동작은 그쪽 plan 승인 흐름으로 넘긴다.
3. **측정값과 운영 규칙**: 9월 30일·10월 2일 벤치 결과, 렌즈 작동 거리, 방향 규칙은 코드가 아니라
   라이브러리언 항목(최대 E3)과 사람이 쓰는 envelope 로 건너간다. 이 저장소의 숫자를 그쪽 코드에 직접 넣지 않는다.

## 3. 접점 (그쪽 구조에 맞춘 위치)

| 접점 | 그쪽 위치 | 이 저장소에서 오는 것 | 그쪽 규칙 |
|---|---|---|---|
| A 판정 제공자 | `microscope_agent/src/` 의 평평한 파일 하나 (예: `focus_verdict.py`). `operator.run` 의 `observe` 훅 (`operator.py:1186`) 또는 Trial 2 탐색 루프가 부른다 | `focus/classical.py` + `verdict.py` 의 순수 부분 | check 13 (평평한 src), check 16 (devices 를 import 하지 않음), check 82 (외부 import 선언). 기록은 `log.json` 의 이벤트 (`focus_verdict` 또는 §13.1 의 `watcher_flag`) |
| B 프레임 출처 | `devices/micromanager.py` 의 `snap` / `sequence` (이미 가드됨) | 없음. 이 저장소의 `Backend.snap` 을 들여가지 않는다 | 프레임 Z 는 장치 읽기 |
| C Z 구동 | `devices/micromanager.py` 확장 또는 새 `devices/<driver>.py` | 동작 규칙만: 상향 스윕, 매 스텝 읽기 확인, PFS 를 먼저 끔, 후퇴 0 µm, 큰 XY 이동 전 후퇴 | 허용 목록을 푸는 **별도 과제 카드** (`_operation_gate` 방식의 예외), envelope 에 새 Z 한계, 매 스텝 간격 비교 |
| D plan 모양 | `plan.schema` 의 새 절 (focus search: step, range, 이동 횟수 상한, 분기 목록, 성공 기준), `operator.derive_*`, check 86 또는 새 check | `focus_100x` 의 단계 정의와 상한 | manager-microscope 가 스키마와 검사를 고친다 |
| E 작동 거리 | `operator.RESOLVERS["working_distance"]` | 40x WI 0.17 mm (d239448) 는 **그쪽에 숫자로 넣지 않는다**. 측정 → 라이브러리언 항목 → 그쪽 갭 `objective_40x_wd_at_170um` 해소 | 범위면 가까운 끝 (0.16 mm). 첫 대상은 100x Oil 이 권고 |
| F 세션 ↔ run | `runs/<run_id>/` | `session.json` 의 세션 id, 사용자, 백엔드, `bench` | 라이브러리언은 `bench: false` 세션을 건너뛴다 (T-106b, BACKLOG M6) |
| G 도구 노출 | 그쪽 Claude Code 세션 | 어시스턴트의 읽기 도구를 MCP 로 (PLAN 5절 X2) | 과제 026 §9: 외부 서비스 호출은 "사람의 결정, 미승인" |

## 4. 이 저장소에서 지금 할 수 있는 준비 (그쪽을 건드리지 않음)

| # | 일 | 이유 | 소유 |
|---|---|---|---|
| P1 (완료, 802284e) | `pyproject.toml` 을 가벼운 core (numpy, scipy) + 선택 의존성 `ml` (torch, torchvision, sklearn, skimage), `hw` (pymmcore-plus), `server`, `plot` 으로 나눈다 | check 82 와 pixi `mic` 에 선언할 것을 최소로. PLAN 4절 방침과 같다 | pyproject 권한 순서 (BACKLOG) |
| P2 | 판정 제공자 공개 표면 고정: `focus.verdict` 의 입력·출력을 JSON 계약으로 적고, numpy 만으로 import 되는지 계약 테스트 | 접점 A. 그쪽은 파일 하나로 복사하거나 의존성으로 받는다 | WP-E |
| P3 | `FocusVerdict.as_record()` 를 그쪽 run_log 이벤트 모양으로 바꾸는 변환기와, 그쪽 `contracts/schemas/run_log.schema.json` 을 (읽기만) 써서 검증하는 테스트 (그 저장소가 없으면 skip) | 기록 형식을 미리 맞춘다. `model` grade 는 E6 로 대응, 카드에는 안 들어감 | WP-E |
| P4 | `guards.py` 의 모든 숫자 표 (FREE_WD_UM, BENCH_FREE_WD_UM, 큰 XY 문턱, Y 이탈 15 mm 등) 의 출처·등급 목록 | 라이브러리언과 envelope 로 넘길 목록. 그쪽에서는 사람이 값을 쓴다 | 가드 소유자 |
| P5 | 공개 전 점검: 기록에 실제 이메일 없음 (git 전체 이력 검색 결과 0 건, 2026-10-02), 9/30 기록의 operator 이름 (유지 결정), `models/heads/*.joblib` (피클이라 공개 저장소에서 내려받아 여는 쪽이 위험; 형식 또는 해시 고정 검토), 보안 두 항목 (가입 409, 시도 제한) | D5 공개 | 총괄 |
| P6 | T-106b (`session.json` 에 backend kind, bench) | 접점 F | 카드 있음 |

P1–P3 은 서로 독립이라 바로 카드로 만들 수 있다. P5 는 공개 직전에 다시 한 번.

## 5. 의존 방식 선택지 (결정 필요, 7절 Q2)

| 선택지 | 장점 | 문제 |
|---|---|---|
| a. 판정 부분만 그쪽 `src/` 에 파일 하나로 옮긴다 (복사) | 그쪽 detachable 규칙, check 13 에 맞는다. 외부 import 는 numpy 뿐 | 두 사본. 이 저장소가 원본이고 커밋 해시를 그쪽 파일에 적는다 |
| b. 공개된 dino-autofocus 를 git 의존성 (커밋 고정) | 사본 없음 | 아키텍처 좌석이 pixi 를 고친다. 지금 core 가 무거워 P1 이 먼저 |
| c. 경로 의존성 | 쉬움 | `microscope_agent/` + `contracts/` 를 현미경 PC 로 떼어 가는 규칙을 깬다. 비권고 |

결정 (Q2): **a 를 폴더 단위로** (소스를 그쪽 폴더로 옮긴다). 첫 단계는 고전 판정만, DINO 없음. 결정론적 지표 최대값 대체 경로가 먼저라는 과제 026 §9 와 맞는다.
DINO 점수는 그다음에 shadow mode (§13.1) 로, b 방식과 `ml` 선택 의존성으로.

## 6. 바꿀 수 없는 그쪽 규칙 (설계가 지켜야 할 것)

- 모델 숫자는 E6, 카드와 KB 항목에 들어가지 않는다. 판정은 거부만 할 수 있고 허용하지 않는다.
- 찾은 Z 는 엔코더 읽기. 넘겨받은 Z 는 목적지가 아니라 목표 (직접 점프 없음, 매 스텝 간격 비교).
- 안전 비교는 결정론적 Python. 애매하면 멈춘다. `unsure` 는 실패가 아니라 기권.
- 모든 이동은 plan 필드에서 유도되고 `from` 을 단다. Tier 1 위는 승인 (`plan_approval`) 이 먼저.
- 다른 저장소에서 온 숫자는 라이브러리언을 거쳐 최대 E3, 안전 한계는 건너가지 않는다 (`rulings.jsonl`).
- 의존성 파일 (`pyproject.toml`, `uv.lock`, `pixi.lock`) 은 아키텍처 좌석만.
- 이 저장소는 그쪽 저장소에 쓰지 않는다 (PLAN 5절).

## 7. 사람 결정 (사용자, 2026-10-02)

| # | 질문 | 결정 |
|---|---|---|
| Q1 | 초점을 누가 맡나 | **그쪽 하드웨어 엔진이 맡는다.** 하드웨어 오케스트레이션의 일부 (microscope_agent) |
| Q2 | 의존 방식 | **지금은 따로 개발하고, 합칠 것을 생각해 폴더 구조를 미리 고친다.** 개발이 끝나면 소스를 그쪽 해당 폴더로 옮긴다. 그래서 5절의 b (의존성) 는 쓰지 않고, a (옮겨 넣기) 를 폴더 단위로 한다. 대응표와 단계는 9절 |
| Q3 | 이 저장소의 값을 그쪽 출처로 인정할지 | **합칠 때 정한다.** 사람이 쓰거나 잰 값인지는 사용자가 직접 확인한다. 이 저장소는 값마다 카드로 묻는다 (대부분 이미 공유되어 있을 것). 라이브러리언에게 줄 정보는 `docs/librarian-handoff.md` 에 따로 모은다 |
| Q4 | Z 한계 | **액침액이 필요한 대물렌즈 (40x WI, 60x Oil, 100x Oil) 만 한계를 두고, 나머지 (건식) 는 푼다.** soft-matter-agents 규칙을 따른다 (`objective_clearance_min` 이 렌즈 위치별 작동 거리에서 풀리는 방식). 이 저장소의 가드 변경은 별도 카드로 |
| Q5 | 기권 문턱 | 아래 설명 뒤 다시 묻는다 |
| Q6 | Claude 연동의 위치 | **이 저장소는 인터페이스 (프론트엔드 일부) 와 자동 초점 (백엔드) 을 맡는다. 에이전트 자체는 모두 백엔드가 된다.** 화면의 Claude 연동은 통합 뒤 그쪽 에이전트 쪽으로 간다 |
| Q7 | 공개 시점 | **3주 안 (2026-10-23 까지).** P5 를 그 전에 끝낸다 |

Q5 설명: 판정기는 확신이 낮으면 `step_up` / `step_down` 대신 `unsure` (기권) 를 낸다. "얼마나 낮으면 기권하나" 가
기권 문턱이다. 지금 이 저장소의 값은 `focus/verdict.py` 의 `MAX_SIGMA_DOF = 3.0` (모델 불확실도가 피사계 심도의
3 배를 넘으면 기권), `MIN_CURVE_CONTRAST = 0.05`, `MIN_DYNAMIC_RANGE_ADU = 20` 이고 모두 임시값이다. 그쪽 과제 026
§9 는 이 문턱을 "미정" 으로 둔다. 권고: 임시값으로 시작하고, 벤치에서 사람이 맞춘 초점과 비교한 기록으로 정한다.

## 8. 측정이 먼저인 것 (현미경 PC)

과제 018 §6 과 이 저장소 BACKLOG 의 벤치 항목이 겹친다. 한 번의 벤치 방문으로 양쪽을 채운다:
픽셀 크기, 방식별 through-focus 곡선, 계면 오프셋, PFS 오프셋 부호, 동초점 잔차 (4x→100x 약 −60 µm, 재측정 필요),
40x WI 0.17 mm 칼라에서의 작동 거리, Q13 (접근 스텝), Q20 (Z 후퇴가 필요한 XY 이동), 재물대 한계, 무명령 Z 표류
(485.16 → 483.62 µm). 결과는 이 저장소 `docs/runs/` 와 그쪽 라이브러리언에 각각 들어간다.

## 9. 폴더 구조 (Q2, 초안 2026-10-02)

그쪽 규칙에서 나오는 제약 (soft-matter-agents `baf6f1e`, `contracts/validate.py`):
- check 13: 에이전트 `src/` 는 평평한 파일 또는 `src/devices/<file>` 만. `tests/` 는 평평한 `*.py` 만 (fixture 폴더 없음).
- 그쪽 모듈은 패키지 import 가 아니라 **경로로 형제 파일을 불러온다** (`spec_from_file_location`, 예 `axis_a1_snr.py:44`).
  테스트는 `unittest`, conftest 없음.
- check 82: 함수 안 import 까지 본다. `scipy` 는 `sim` 기능에만 있어 검사는 통과하지만 현미경 PC 의 `mic` 환경에는 없다.
  `focus/classical.py` 의 `separated_peaks` (`scipy.signal.find_peaks`) 는 그 환경에서 실행 중 실패한다.
- 그쪽에는 UI·서버 폴더가 없다. 새 최상위 폴더는 architecture (ALLOWED_PATHS, pixi) 와 manager (AGENT_OF_PATH) 승인이 먼저다.

대응표 (요약):

| 이 저장소 | 그쪽 위치 | 처리 |
|---|---|---|
| `focus/classical.py`, `verdict.py`, `sma_event.py` | `microscope_agent/src/focus_classical.py`, `focus_verdict.py` | 옮김 (경로 로더, scipy 제거) |
| `focus/dino.py`, `live.py`, `backbone.py` | 나중에 `focus_dino.py` (shadow mode, torch 는 `mic` 에) | 2단계 |
| `guards.py` 의 Z 규칙 (상향 스윕, 읽기 확인, PFS 먼저 끔, 후퇴 0, 큰 XY 전 후퇴) | `focus_step_rules.py` (순수 함수, 한계는 envelope 에서 인자로) | 순수 부분만 |
| `focus_100x.py` 의 단계 생성 | `focus_search.py` (단계마다 `from`) | 나눔 |
| `mosaic.py`, `sample.py`·`scan_4x.py`·`sample_map.py` 의 순수 부분, `edge_trace.py` 검출부 | `map_mosaic.py`, `map_geometry.py`, `map_tiles.py`, `map_edge.py` | 나눔 |
| `runner`, `backend`, `events`, `records`, `gates`, 나머지 가드와 숫자 표, `objective_change`, `z_retract`, `light_set` | orchestrator, operator, envelope, `runs/<run_id>/` | 이 저장소에만 남음 (단독 실행용) |
| `mm_real.py`, `mm_demo*.py` | `devices/micromanager.py` 에 흡수 | 합칠 때 버림 |
| `server/`, `auth/`, `assistant/`, `agents/`, `web/`, `tools/launcher/` | 새 최상위 `console/` (`sma_console` 패키지, `console/web`, `console/launcher`) | 옮김 |
| `synth/`, 학습·평가 스크립트, `models/`, `configs/ti2_*.yaml` | 옮기지 않음 (모델 제작용으로 이 저장소에 남음) | 남음 |

이 저장소 안의 중간 배치 (그쪽을 그대로 닮게):

```
microscope_agent/src/        focus_*.py map_*.py   (평평, __init__.py 없음, stdlib + numpy 만)
microscope_agent/src/devices/
microscope_agent/tests/      test_focus_*.py ...   (평평, unittest, 경로 로더)
console/sma_console/         app ws static hw_port api/ schemas/ auth/ assistant/ store/
console/web/  console/launcher/  console/tests/
src/dino_autofocus/          단독 실행용 나머지 (engine, backends, operations, records, synth, live, backbone)
```

배포는 하나로 유지한다 (`uv sync`, editable 설치, pytest 그대로). `dino_autofocus.focus` 는 평평한 파일을 다시 내보내는
얇은 껍데기로 남겨 기존 import 를 살린다. `tests/test_sma_shape.py` 가 옮길 두 폴더에 check 13·16·82 를 미리 적용한다.

단계 (각 단계 끝에 테스트 통과):
- S0 (P1 완료) 의존성 나누기. S3 (P3 완료) 판정 → run_log 이벤트.
- S1 초점 핵심을 `microscope_agent/src/` 로, scipy 제거, 모양 검사 테스트.
- S2 순수 핵심 파일을 하나씩 (`focus_step_rules`, `focus_search`, `map_*`).
- S4 `console/` 로 서버·웹·런처 옮기기 (import 약 100 곳, gen:api, 런처 경로).
- S5 `hw_port.py`: 화면이 엔진을 직접 부르지 않고 포트 하나로 (그 뒤 console 은 `dino_autofocus` 를 import 하지 않는다).
- S6 합치는 주: 그쪽 승인 순서 (사람: 좌석 → architecture: seats.json, pixi, ALLOWED_PATHS 명세 → manager: validate.py →
  manager-microscope: 과제 카드, plan.schema, envelope 스키마) 를 마친 뒤 복사. 승인 사슬이 길어 **2주차에 시작**한다.
