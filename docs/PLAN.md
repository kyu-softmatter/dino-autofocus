# dino-autofocus 개발 계획서 (초안 v0.1, 2026-10-01)

작성: 총괄 세션 (사용자와의 대화로 방향 결정). 이 파일은 총괄 세션만 수정한다.
코드, 주석, 로그, UI 문구는 영어로 쓰고, 계획 문서는 한국어로 쓴다.

## 1. 목적과 범위

- **최종 목표**: 이 저장소의 측정 기능을 soft-matter-agents 의 하드웨어 엔진
  (`microscope_agent/src/orchestrator.py` + `devices/*`)에 붙여 실험 측정을 자동화한다.
  저장소 이름은 autofocus 지만 범위는 초점에 한정되지 않는다.
- **현재 단계의 목표**: 사람이 현미경을 조작하는 **유저 인터페이스**를 만든다.
  통합 자체는 이번 단계에 하지 않지만, 통합을 막는 설계는 지금 피한다 (5절).

## 2. 현재 상태 (2026-10-01 기준)

| 구성 | 위치 | 상태 |
|---|---|---|
| 런처 | `scripts/launcher.py` (tkinter) + `tools/launcher` exe | 스크립트를 콘솔 창으로 띄우기만 함. 하드웨어 로직 없음 |
| 라이브 뷰 | `scripts/live_focus.py` (912줄, tkinter 단일 파일) | 화면, 맵, 엣지 추적, 서보, 기록이 한 파일에 섞여 있음 |
| 하드웨어 접근 | `scripts/mm_grab.py` (`open_core`, 광원, 피에조) | 스크립트마다 직접 import |
| 모션 가드 | `C:\agentic_microscope` 의 `FocusAxis` | 현미경 PC 에만 있음, 이 저장소 밖 |
| 작업 스크립트 | `scan_4x`, `focus_100x`, `change_objective`, `find_particle_z`, `lights_off` | 2026-09-30 벤치에서 사용. `find_particle_z` 는 사용 불가 판정 |
| 초점 점수 | `src/dino_autofocus/live.py`, `backbone.py` | DINO 헤드는 합성 100x 데이터로만 학습 |
| 기록 | `D:\AutoFocus\samples\<sample_id>\` | sample.json, map.json, scan, log |

## 3. 컴퓨터별 역할

| 컴퓨터 | 하는 일 | 하지 않는 일 |
|---|---|---|
| 현미경 PC (RTX A4000) | 하드웨어 실행, **이미지 합성, DINO 학습**, 실시간 점수, 지연 측정 | — |
| 개발 데스크톱 (GTX 1650 SUPER) | UI/엔진 개발, demo/replay 백엔드로 테스트 | 하드웨어 실행, 데이터셋 생성, 헤드 학습 |

개발 세션은 하드웨어 명령을 실행하지 않는다. 벤치 확인은 사용자가 현미경 PC 에서 한다.

## 4. 아키텍처

```
  UI (화면, 확인 대화상자)          <- 하드웨어 로직 없음
     | commands          ^ events / frames
     v                   |
  Engine (operations + guards + records)   <- UI 없이 import 가능, 통합 대상
     |
  Backend:  mm-real | mm-demo | replay(저장된 스택)
```

- **Backend**: 카메라 프레임, 위치 읽기, 광원 설정, 가드된 Z/XY 이동. 구현 셋.
  `mm-real` 은 현미경 PC, `mm-demo` 는 Micro-Manager 데모 장치, `replay` 는
  `D:\AutoFocus\samples` 의 저장된 스택을 재생해 z 이동에 반응한다.
- **Engine**: 작업(operation) 단위. 각 작업은 `plan → preflight → run → abort` 를 가지며,
  진행 이벤트를 내보내고 기록 파일을 쓴다. 초기 작업 목록:
  `status`, `live`, `edge_trace`, `scan_4x`, `objective_change`, `focus_100x`, `lights_off`.
- **Guards**: Z 창(2800–3200 µm), 상향 스윕만, 읽기 확인, XY 박스, 종료 시 소등,
  코어 단일 소유. UI 대화상자는 추가 확인일 뿐 가드를 대신하지 않는다.
- **Focus**: 고전 지표(Vollath, Tenengrad, peak)가 기본이고 최종 판정자다.
  DINO 점수는 보조이며 torch 는 쓸 때만 import 한다.
- 기존 `scripts/*` 는 이식이 끝날 때까지 그대로 둔다. 벤치에서 쓰던 경로를 깨지 않는다.

제안 디렉터리 (D1–D3 결정 후 확정):

```
src/dino_autofocus/engine/      backend.py events.py records.py guards.py sample.py
src/dino_autofocus/engine/backends/   mm_real.py mm_demo.py replay.py
src/dino_autofocus/engine/operations/ status.py live.py edge_trace.py scan_4x.py ...
src/dino_autofocus/focus/       classical.py dino.py verdict.py
src/dino_autofocus/ui/          app.py, 화면 구성 요소
tests/engine/  tests/ui/
```

## 5. 지금부터 지킬 설계 규칙 (통합 대비)

1. **UI 는 하드웨어를 직접 부르지 않는다.** 모든 호출은 엔진을 거친다.
2. **안전은 코드가 정한다.** 가드는 엔진에 있고 모델은 안전 판단에 들어가지 않는다.
3. **모델 출력은 판정이지 Z 가 아니다.** 표시 어휘는 soft-matter-agents 초점 과제와
   맞춘다: `in_focus | step_up | step_down | no_sample_here | unsure`. Z 값은 선택된
   프레임의 엔코더 읽기에서 온다. 모델 숫자는 기록에서 "model" 로 표시한다.
4. **모든 작업은 기록을 남긴다.** 시작 상태, 보낸 명령, 읽은 값, 종료 상태.
5. **모든 종료 경로에서 소등한다.** `live_focus.py` 의 DiaLamp 미소등 문제를 엔진에서 고친다.
6. **엔진은 하드웨어 없이 돈다.** demo/replay 로 데스크톱에서 테스트한다.
7. **무거운 import 는 사용 지점에서.** soft-matter-agents 의 규칙과 같다.
8. **2026-09-30 운영 규칙을 코드로 넣는다.** 명시야로 구멍 가장자리 추적 후 입자 조명으로 전환,
   세션마다 재추적, 오일 확인 대기, 100x 에서 상향 연장은 사용자 승인 후.

soft-matter-agents 와의 대응 (통합 단계에서 다룸):

| 이 저장소 | soft-matter-agents |
|---|---|
| Backend 프로토콜 | `devices/*.py` 의 preflight / apply / read / abort |
| Engine operation | 승인된 plan 의 단계, `operator.py` 가 실행 |
| Guards | `GuardedCore` 허용 목록 + orchestrator 인터록. 현재 ZDrive/XYStage 는 거부됨 |
| 기록 파일 | `runs/<run_id>/log.json`, 등급 표시 |

## 6. 결정이 필요한 사항 (사용자)

| # | 질문 | 선택지 | 권고 |
|---|---|---|---|
| D1 | UI 기술 | (a) PySide6 + pymmcore-widgets (b) tkinter 유지 (c) 로컬 웹 (FastAPI + 브라우저) | **(a)**. pymmcore-plus 생태계와 맞고 2400² 라이브 뷰를 한 프로세스에서 처리한다. 엔진이 UI 독립이면 나중에 웹을 얹을 수 있다 |
| D2 | Python 환경 | 시스템 Python + uv 이원화 유지, 또는 uv 하나로 통일 | **통일**. 학습과 점수가 현미경 PC 로 오므로 하나의 uv 환경이 단순하다. pyproject 에 pymmcore-plus 는 이미 있다 |
| D3 | 엔진 프로세스 | UI 와 같은 프로세스(스레드), 또는 별도 프로세스 | **같은 프로세스로 시작**. 명령/이벤트 API 로만 통신해 나중에 분리 가능하게 한다 |
| D4 | 첫 UI 범위 | 2026-09-30 절차의 Step 0–2 만, 또는 대물렌즈 교체와 100x 까지 | **Step 0–2 + 소등 + demo/replay 를 M1**, 렌즈 교체와 100x 는 M3 |
| D5 | 공개/비공개 | soft-matter-agents 는 공개, 이 저장소는 비공개 | **통합 단계에서 결정**. 지금은 엔진을 torch 없이 import 되게만 유지 |

## 7. 마일스톤

| | 내용 | 확인 방법 |
|---|---|---|
| M1 | 엔진 계약 + demo/replay 백엔드 + UI 셸 (샘플 선택, 라이브 뷰, 상태, 소등) | 데스크톱에서 하드웨어 없이 실행, `uv run pytest` |
| M2 | 현미경 PC 읽기 전용: 실제 카메라, 위치, 광원 상태 표시 | 사용자가 현미경 PC 에서 실행 |
| M3 | 동작 작업을 UI 로: 엣지 추적, 4x 스캔, 렌즈 교체, 100x 초점 | 벤치 실행 기록이 2026-09-30 결과와 일치 |
| M4 | 초점 판정 패널: 고전 지표 + DINO 판정, A4000 학습 헤드 | 현미경 PC 에서 학습/지연 측정 기록 |
| M5 | 통합 준비: soft-matter-agents 백엔드 어댑터 설계 문서 | 총괄 세션 검토 |

## 8. 작업 묶음과 파일 소유 (매니저가 배정)

동시에 같은 파일을 만지지 않도록 묶음마다 소유 경로를 정한다.

| 묶음 | 내용 | 소유 경로 | 선행 |
|---|---|---|---|
| WP-A 엔진 계약 | Backend 프로토콜, 이벤트, 기록, 가드 골격 | `engine/{backend,events,records,guards,sample}.py`, `tests/engine/test_contract*.py` | 없음. **가장 먼저** |
| WP-B 백엔드 | mm-real (mm_grab 에서 추출), mm-demo, replay | `engine/backends/`, `tests/engine/test_backends*.py` | WP-A 인터페이스 |
| WP-C 작업 이식 | status, scan_4x, objective_change, focus_100x, lights_off, edge_trace | `engine/operations/`, `tests/engine/test_operations*.py` | WP-A, 테스트는 WP-B demo |
| WP-D UI 셸 | 메인 창, 라이브 뷰, 샘플 패널, 단계 진행, 상태 표시 | `ui/`, `tests/ui/` | D1 결정, WP-A 이벤트 |
| WP-E 초점 + 학습 런북 | 고전 지표/DINO 래퍼, 판정 매핑, 현미경 PC 학습 절차 | `focus/`, `docs/runbooks/`, `tests/focus/` | WP-A |

공유 파일 규칙:
- `pyproject.toml`, `uv.lock`: 실행 세션은 직접 고치지 않고 매니저에게 요청한다.
  매니저가 한 세션에만 의존성 변경을 배정한다.
- `docs/PLAN.md`, `docs/sessions.md`: 총괄 세션만 수정한다.
- `docs/tasks/`: 매니저만 쓴다.
- `scripts/*`: 과제에 명시된 경우만 수정한다.

## 9. 알려진 미해결 사항

- `find_particle_z.py` 의 입자 판별이 신뢰할 수 없다 (실제 입자 약 6.7 µm).
- Aura 깜박임으로 밝기 −23 % 프레임이 한 번 나왔다.
- 4x→100x 동초점 오프셋이 약 −60 µm 로 측정됐고 기준 시료로 재측정이 필요하다.
- A4000 지연 시간과 fp16 헤드의 실측 성능은 아직 측정하지 않았다.
- 현재 헤드는 합성 100x 형광 데이터로만 학습됐다. 명시야 유리/물 계면은 시뮬레이션되지 않는다.
