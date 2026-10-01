# dino-autofocus 개발 계획서 (초안 v0.2, 2026-10-01)

작성: 총괄 세션 (사용자와의 대화로 방향 결정). 이 파일은 총괄 세션만 수정한다.
코드, 주석, 로그, UI 문구는 영어로 쓰고, 계획 문서는 한국어로 쓴다.

변경 이력
- v0.1: 목표, 구조, 설계 규칙, 결정 D1–D5, 작업 묶음 WP-A–E.
- v0.2: 사용자 요구사항 F1–F5 추가 (2026-10-01). **모든 기능을 mock 으로 먼저 구축**.
  Python 환경 방침 추가. 작업 묶음 WP-F–J 추가. D1 권고 갱신. D5 결정 (통합 시 공개).
- v0.3: **D1 결정: 로컬 웹 앱 (FastAPI + React)**. D3 확정. 서버/웹 구조, API 규칙, 작업 묶음 WP-D 분할. Node 는 uv 그룹 `web`.
- v0.4: F6 시뮬레이션 현황 상세, 공통 요구 X1 (모든 화면에 프롬프트 칸), X2 (Claude 연동).
  Claude 연동 설계 (5절), 결정 D6–D8, 작업 묶음 WP-K, WP-L.

## 1. 목적과 범위

- **최종 목표**: 이 저장소의 측정 기능을 soft-matter-agents 의 하드웨어 엔진
  (`microscope_agent/src/orchestrator.py` + `devices/*`)에 붙여 실험 측정을 자동화한다.
  저장소 이름은 autofocus 지만 범위는 초점에 한정되지 않는다.
- **현재 단계의 목표**: 사람이 쓰는 **유저 인터페이스**를 만든다. 범위는 두 가지다.
  - 에이전트 콘솔: 질문을 넣고, 이전 질문과 시뮬레이션·실험의 현황/계획/결과를 본다.
  - 현미경 조작: 하드웨어 파악, 샘플 로딩 확인, 샘플 맵, 배율 전환과 액침액 로딩.
- **mock 우선**: 모든 기능을 mock 하드웨어와 mock 에이전트 저장소로 먼저 끝까지 만든다.
  실제 하드웨어 연결은 mock 에서 동작이 확인된 뒤 현미경 PC 에서 한다.
- 통합 자체는 이번 단계에 하지 않지만, 통합을 막는 설계는 지금 피한다 (6절).

## 2. 기능 요구사항 (사용자, 2026-10-01)

번호는 우선순위가 아니다. 생각난 순서다. 비어 있는 항목은 추후 채운다.

### F1. 유저 인터페이스

기술: **로컬 웹 앱, FastAPI 백엔드 + React 프런트** (D1, 사용자 결정 2026-10-01). 구조는 5절.

| | 기능 | 데이터 출처 |
|---|---|---|
| F1.1 | 질문을 할 수 있는 곳 | 에이전트 저장소에 질문을 넣는다. mock 에서는 로컬 저장소 |
| F1.2 | 이전 질문 확인 | `*/questions/<qid>/` 의 goal, axis, plan 카드 |
| F1.3 | 시뮬레이션 현황 / 계획 / 결과 | `simulation_agent/questions/`, `simulation_agent/runs/` |
| F1.4 | 실험 현황 / 계획 / 결과 | `microscope_agent/questions/`, `microscope_agent/runs/`, 이 저장소의 샘플 기록 |

- 에이전트 저장소는 **읽기 전용**으로 연다. soft-matter-agents 원칙상 파일이 진실이고,
  카드는 정해진 세션과 게이트만 쓴다. UI 가 카드를 직접 고치지 않는다.
- 질문 넣기(F1.1)가 실제로 어디에 무엇을 쓰는지는 soft-matter-agents 의 설계 범위다.
  지금은 어댑터 인터페이스 뒤에 mock 저장소로 구현하고, 실제 경로는 통합 단계에서
  그쪽 architecture 세션과 정한다 (10절 미해결).
- 시뮬레이션은 WSL 에서 돈다. UI 는 시뮬레이션 코드를 import 하지 않고 파일만 읽는다.

### F2. 연결된 하드웨어 파악과 상태

| | 기능 |
|---|---|
| F2.1 | 연결된 하드웨어를 탐지해 **하드웨어 구성 파일**을 만든다 |
| F2.2 | 구성 파일을 바탕으로 **활성화할 게이트**가 정해진다 |

- 탐지: Micro-Manager 에 로드된 장치, 각 장치의 속성, 읽기 확인 가능 여부, 대물렌즈 목록,
  카메라 비트 깊이, 피에조 연결 여부. mock 에서는 mock 장치 목록에서 같은 형식을 만든다.
- 구성 파일: `hardware_profile.json` (가칭). 탐지 시각, 장치별 상태, 사람이 확인한 항목을 담는다.
- 게이트: 기능마다 필요한 장치와 조건을 선언한다. 예를 들어 F4 샘플 맵은 XYStage, ZDrive,
  DiaLamp, 4x 대물렌즈, 카메라가 있고 읽기 확인이 될 때만 켜진다.
  UI 는 꺼진 기능을 숨기지 않고 **꺼진 이유**와 함께 비활성으로 보여 준다.
- 게이트는 코드가 판정한다. 모델이나 UI 대화상자가 게이트를 열지 않는다.

### F3. 샘플 로딩 확인

| | 기능 |
|---|---|
| F3.1 | 샘플 지오메트리 선택 창: 샘플 두께, 커버슬립 두께, 샘플 형태 (뒤집힘 여부 등) |
| F3.2 | (추후 작성) |

- 지오메트리는 이후 단계의 안전 한계에 들어간다. 커버슬립 두께는 대물렌즈 작동 거리와
  보정 링 조건, 뒤집힘은 초점 탐색 범위를 바꾼다.
- 후보 필드 (사용자 확인 필요): 샘플 크기 (보통 24 mm × 50 mm), 챔버 형태와 구멍 지름
  (9월 30일 시료는 약 6 mm), 커버슬립 두께 (기본 170 µm), 샘플 두께, 방향 (정상 / 뒤집힘).
- 로딩 확인은 사람의 확인과 이미지 확인을 함께 쓴다. 선택값 읽기는 상태 확인이 아니다.

### F4. 샘플 맵핑 (투과광 권장)

| | 기능 |
|---|---|
| F4.1 | 입자가 있던 대략적인 위치를 기록 |
| F4.2 | 쓰던 입자를 잃어버렸을 때 찾기, 좋은 샘플 영역 추천에 활용 |
| F4.3 | 맵에서 원하는 지역을 클릭하면 그 위치로 이동 |
| F4.4 | 주요 지역을 flag 하는 기능 |

- 투과광(DiaLamp) 4x 타일 스캔으로 모자이크를 만든다. 9월 30일 엣지 추적과 4x 스캔을 재사용한다.
- 입자 위치는 고전 이미지 처리로 찾은 **후보**로 기록하고, 사람이 확인한 것과 구분한다.
- 클릭 이동은 이동 게이트를 거친다. 스캔 박스 밖이면 거부하고, Z 가 안전 높이가 아니면 먼저 후퇴한다.
- flag 는 이름, 메모, 시각, 대물렌즈, 좌표를 샘플 기록에 남긴다.

### F5. 배율 전환과 액침액(오일/물) 로딩

| | 기능 |
|---|---|
| F5.1 | 재물대 특성상 샘플이 올라간 뒤에는 배율 전환 시 액체를 로딩하기 어렵다 |
| F5.2 | 배율 전환과 함께 y 방향으로 약 15–20 mm 벗어나 용액을 로딩하기 좋게 한다. 방향은 추후 결정 |
| F5.3 | 로딩 후 사용자가 클릭하면 원래 위치로 돌아온다 |

순서 (기존 `change_objective.py` 절차에 XY 이탈과 복귀를 더함):

```
1. 현재 XY, Z, 대물렌즈를 기록
2. PFS off -> Z 후퇴 (0 µm) -> PFS Out of Range 확인
3. Y 를 이탈 위치로 이동 (Z 가 후퇴 상태일 때만 허용)
4. 대물렌즈 회전, 읽기 확인
5. 사용자: 오일/물 로딩 -> "로딩 완료" 클릭      <- 수동 단계, 기록에 남김
6. XY 를 1 의 위치로 복귀 (Z 는 여전히 후퇴)
7. Z 는 목표값으로 점프하지 않고 후퇴 위치에서 단계적으로 접근
```

- 이탈 방향과 거리는 재물대 한계와 24 mm 쪽 방향을 측정한 뒤 정한다 (10절).
- 3번과 6번의 XY 이동은 Z 후퇴 상태가 확인될 때만 가드가 허용한다.
- 7번은 soft-matter-agents 과제 026 의 "넘겨받은 Z 는 목적지가 아니라 목표" 규칙과 같다.

### F6. 시뮬레이션 현황 상세 (F1.3 확장)

| | 기능 |
|---|---|
| F6.1 | 진행 중인 시뮬레이션의 진행률 (현재 step / 전체 step, 경과 시간, 예상 종료) |
| F6.2 | 데이터를 쉽게 내려받는 버튼 (실행 폴더 단위 묶음) |
| F6.3 | 시뮬레이션 시각화: 입자 궤적 재생 |
| F6.4 | 주요 결과를 그래프로 보기: 로그 값 (에너지, 온도, 압력 등)과 관측량 |

- 참고: [kyu-softmatter/HOOMD_GUI](https://github.com/kyu-softmatter/HOOMD_GUI). 같은 구조를 쓴다.
  FastAPI 로컬 러너, 루프백만 바인딩, Host 헤더 허용 목록, 같은 출처에서 웹과 API 제공.
  뷰포트는 지금 Canvas 2D 이고, 3D 가 필요해지면 Three.js 인스턴싱으로 간다.
  진행률은 WebSocket 또는 server-sent events 로 받는다. 궤적은 GSD, 로그는 HDF5/CSV.
- 데이터 출처: soft-matter-agents `simulation_agent/runs/<run_id>/` 의 `config.json`,
  `log.json`, `observables.json`, `trajectory_meta.json`. 궤적 파일 자체는 저장소에 없고 WSL 쪽에 있다.
  서버는 `\\wsl$\<배포판>\...` 경로로 읽기만 한다. 실제 경로는 현미경 PC 에서 확인한다.
- 진행률 출처: 실행 중인 시뮬레이션이 진행 상태를 파일로 남겨야 한다. 지금 남기는지 확인이
  필요하다 (10절). mock 에서는 시간에 따라 진행하는 가짜 실행을 쓴다.
- 내려받기: 서버가 실행 폴더를 zip 으로 묶어 스트리밍한다. 큰 궤적은 선택해서 포함한다.
- 그래프의 숫자는 기록 파일에서 읽은 값 그대로 그린다. 화면에서 다시 계산하지 않는다.

### 공통 요구사항

| | 기능 |
|---|---|
| X1 | **모든 화면에 프롬프트로 요청할 수 있는 칸**을 둔다 |
| X2 | **모든 프롬프트와 기능을 Claude 와 연동**한다 (설계는 5절 "Claude 연동") |

- 프롬프트 칸은 공통 컴포넌트 하나로 만들고, 화면은 자기 문맥을 붙여 보낸다.
  예: 샘플 맵 화면은 선택된 샘플 id 와 클릭한 영역, 시뮬레이션 화면은 선택된 run id.
- 답변과 제안은 그 화면 안에 보여 주고, 같은 대화 기록을 모든 화면에서 이어 볼 수 있다.

## 3. 현재 상태

| 구성 | 위치 | 상태 |
|---|---|---|
| 런처 | `scripts/launcher.py` (tkinter) + `tools/launcher` exe | 스크립트를 콘솔 창으로 띄우기만 함 |
| 라이브 뷰 | `scripts/live_focus.py` (912줄, tkinter 단일 파일) | 화면, 맵, 엣지 추적, 서보, 기록이 한 파일에 섞여 있음 |
| 하드웨어 접근 | `scripts/mm_grab.py` | 스크립트마다 직접 import |
| 모션 가드 | `C:\agentic_microscope` 의 `FocusAxis` | 현미경 PC 에만 있음 |
| 작업 스크립트 | `scan_4x`, `focus_100x`, `change_objective`, `find_particle_z`, `lights_off` | 9월 30일 벤치에서 사용. `find_particle_z` 는 사용 불가 판정 |
| 초점 점수 | `src/dino_autofocus/live.py`, `backbone.py` | DINO 헤드는 합성 100x 데이터로만 학습 |
| 기록 | `D:\AutoFocus\samples\<sample_id>\` | sample.json, map.json, scan, log |

## 4. 컴퓨터와 Python 환경

| 컴퓨터 / 환경 | 하는 일 | 하지 않는 일 |
|---|---|---|
| 현미경 PC, Windows (RTX A4000) | 하드웨어 제어, UI, **이미지 합성, DINO 학습**, 실시간 점수 | — |
| 현미경 PC, WSL | 시뮬레이션 (이미 동작 중) | 하드웨어 제어 |
| 개발 데스크톱 (GTX 1650 SUPER) | mock 으로 UI/엔진 개발과 테스트 | 하드웨어 실행, 데이터셋 생성, 헤드 학습 |

Python 환경 방침 (권고, **최종 결정은 현미경 PC 에서**):
- Windows 쪽은 **이 저장소의 uv 환경 하나**로 제어, UI, DINO 를 모두 돌린다.
  새 uv 환경을 하나 더 만들기보다, 지금의 시스템 Python 사용을 없애는 쪽이다.
- 무거운 부분은 선택 의존성으로 나눈다. 예: `ui`, `hw` (pymmcore-plus), `ml` (torch).
  개발 데스크톱은 `ml` 없이도 UI 와 mock 테스트가 돈다.
- WSL 시뮬레이션은 지금 환경 그대로 둔다. Windows 와 WSL 은 파일로만 주고받고 서로 import 하지 않는다.
- 통합 단계에서는 제어 코드가 soft-matter-agents 의 pixi `mic` 환경에서 돌게 된다.
  그래서 엔진 의존성을 작게 유지한다.

## 5. 아키텍처

```
  Web (React + TypeScript, 브라우저)                   <- 하드웨어 로직 없음, API 만 부른다
     | REST: commands, queries       ^ WebSocket: events, live frames
     v                               |
  Server (FastAPI, 하나의 Python 프로세스)               <- 엔진을 소유, 요청을 엔진 명령으로 옮김
     |
  Engine  (operations + guards + gates + records)       <- 웹/서버 없이 import 가능, 통합 대상
     |                     |
  Backend                  AgentStore
  mock | mm-demo | mm-real   mock | soft-matter-agents 파일 (읽기 전용)
```

- **Backend**: 카메라 프레임, 위치 읽기, 광원, 가드된 Z/XY 이동, 대물렌즈.
  - `mock`: 가상 샘플(구멍, 입자 위치), 대물렌즈 세트, 광원, 재물대 한계를 가진 시뮬레이터.
    프레임은 |dz| 에 따라 흐려지는 합성 영상. **M1 의 기본 백엔드**.
  - `replay`: 저장된 z-스택 재생. 개발 PC 의 `data/smoke`, 나중에 실제 샘플 폴더.
  - `mm-demo`: Micro-Manager 데모 장치. `mm-real`: 현미경 PC.
- **AgentStore**: 질문, 카드, 실행 기록을 읽고 질문을 넣는 어댑터. mock 은 고정 예제 카드.
- **Engine**: 작업(operation) 단위. 각 작업은 `plan → preflight → run → abort` 를 가지며
  진행 이벤트를 내보내고 기록 파일을 쓴다.
- **Gates**: 하드웨어 구성 파일과 작업별 요구 조건을 비교해 작업을 켜고 끈다 (F2.2).
- **Guards**: Z 창, 상향 스윕만, 읽기 확인, XY 박스, Z 후퇴 상태에서만 큰 XY 이동,
  종료 시 소등, 코어 단일 소유. UI 대화상자는 추가 확인일 뿐 가드를 대신하지 않는다.
- **Focus**: 고전 지표가 기본이고 최종 판정자다. DINO 점수는 보조이며 torch 는 쓸 때만 import 한다.
- 기존 `scripts/*` 는 이식이 끝날 때까지 그대로 둔다.

웹 앱 규칙:
- **Server** 는 엔진의 유일한 소유자다. 프로세스 하나, 코어 하나. 서버는 판단하지 않고
  요청을 엔진 명령으로 옮기고, 엔진 이벤트를 WebSocket 으로 내보낸다.
- **API 계약은 한 곳에서 정한다.** 명령, 이벤트, 응답은 Python 쪽 pydantic 모델로 정의하고,
  FastAPI 가 만드는 OpenAPI 에서 TypeScript 타입을 생성한다. 손으로 쓴 사본을 두지 않는다.
- **라이브 영상**: 서버가 비닝해 약 800 px JPEG 로 WebSocket 에 보낸다. 목표 10 fps.
  원본 프레임은 디스크 기록에만 남는다.
- **접속 범위**: 기본은 `127.0.0.1` 에만 바인딩한다. 다른 PC 에서 보기는 설정으로 켠다.
  원격 접속에서는 읽기만 허용하고, 움직이는 명령은 현미경 PC 의 브라우저에서만 받는다.
- **배포**: React 는 빌드 결과(`web/dist`)를 FastAPI 가 정적 파일로 제공한다.
  실행에는 Node 가 필요 없고 빌드에만 필요하다. `web/dist` 는 git 에 넣지 않는다.
- **런처**: 데스크톱 exe 는 서버를 띄우고 브라우저를 연다. 기존 tkinter 런처는 이식 후 정리한다.
- 툴체인: Node 22 LTS, Vite, React, TypeScript, npm. **Node 는 시스템에 설치하지 않고 uv 의존성 그룹
  `web` (nodejs-wheel) 으로 넣는다.** `uv sync` 만으로 현미경 PC 와 개발 PC 에 같은 버전이 깔린다.
  실행은 `uv run npm ...`, `uv run node ...`.

### Claude 연동 (X2)

권고 구조: **서버 안에서 Claude API 를 부르고, 앱 기능을 Claude 의 도구로 노출한다.**

```
  화면의 프롬프트 칸 --(질문 + 화면 문맥)--> Server /api/assistant
      Server: Anthropic Python SDK, Tool Runner, 모델 claude-opus-5-5
      도구 = 엔진과 저장소 API 를 감싼 함수 (화면이 쓰는 API 와 같은 것)
  <--(스트리밍 답변, 도구 호출 표시, 실행 제안 카드)--
```

- **구현면**: Anthropic Python SDK 의 Messages API + Tool Runner. 도구는 우리가 정의하고,
  서버가 실행한다. Tool Runner 의 턴별 훅에서 승인 게이트와 기록을 건다.
- **도구는 두 종류다.**
  - 읽기 도구: 하드웨어 상태, 샘플 기록, 맵, 질문과 카드, 시뮬레이션 진행률과 결과. 바로 실행한다.
  - 동작 도구: 이동, 광원, 렌즈 전환, 스캔 시작 등. **실행하지 않고 제안 카드만 만든다.**
    사람이 화면에서 확인을 눌러야 엔진으로 간다. 엔진의 게이트와 가드는 그대로 적용된다.
- **같은 도구를 나중에 MCP 서버로도 연다.** 그러면 soft-matter-agents 의 Claude Code 세션도
  같은 기능을 쓴다. 통합 단계의 일이다.
- **다른 선택지와 비교**
  - Claude Agent SDK: Claude Code 의 하네스 전체 (파일, bash 포함). 실험 장비 UI 에는 권한이
    너무 넓다. 개발용 에이전트에 맞는다.
  - Managed Agents: Anthropic 이 루프와 샌드박스를 돌린다. 장비 도구는 어차피 이 PC 에서
    실행해야 하므로 얻는 것이 적다.
- **캐싱**: 시스템 프롬프트와 도구 목록은 고정해 캐시하고, 화면 문맥과 질문은 그 뒤에 붙인다.
  시스템 프롬프트에 시각이나 매번 바뀌는 값을 넣지 않는다.
- **자격 증명**: API 키는 서버에만 둔다 (환경 변수 또는 `ant auth login` 프로필).
  브라우저로 보내지 않는다. 키가 없으면 프롬프트 칸은 "연결 안 됨" 으로 보이고 나머지 기능은 돈다.
- **mock 우선**: 테스트와 개발은 가짜 LLM 공급자로 한다. 네트워크와 비용 없이 도구 호출 흐름을
  검증한다. 실제 호출은 사용자가 켤 때만 한다.
- **기록**: 모든 대화, 도구 호출, 제안, 사람의 확인/거부를 기록 파일에 남긴다.
  Claude 가 낸 숫자는 "model" 로 표시하고 측정값과 섞지 않는다.
- **비용 표시**: 답변마다 사용 토큰을 보여 준다.

디렉터리:

```
src/dino_autofocus/engine/              backend.py events.py records.py guards.py gates.py sample.py
src/dino_autofocus/engine/backends/     mock.py replay.py mm_demo.py mm_real.py
src/dino_autofocus/engine/operations/   status.py hardware_scan.py edge_trace.py scan_4x.py
                                        sample_map.py objective_change.py focus_100x.py lights_off.py
src/dino_autofocus/agents/              store.py mock_store.py sma_files.py
src/dino_autofocus/focus/               classical.py dino.py verdict.py
src/dino_autofocus/server/              app.py api/ (영역별 라우터) ws.py schemas/ static.py
src/dino_autofocus/assistant/           tools.py (읽기/제안 도구) runner.py providers/ (anthropic, fake) records.py
web/                                    package.json vite.config.ts
web/src/app/                            셸: 레이아웃, 내비게이션, 상태 표시줄, API 클라이언트
web/src/api/                            OpenAPI 에서 생성한 타입 (생성물, 손으로 고치지 않음)
web/src/features/<영역>/                console hardware sample map objective live simulation
web/src/app/assistant/                  모든 화면 공통 프롬프트 칸 컴포넌트
tests/engine/  tests/agents/  tests/focus/  tests/server/   web/ 의 테스트는 vitest
```

## 6. 설계 규칙 (통합 대비)

1. **UI 는 하드웨어를 직접 부르지 않는다.** 모든 호출은 엔진을 거친다.
2. **안전은 코드가 정한다.** 가드와 게이트는 엔진에 있고, 모델은 안전 판단에 들어가지 않는다.
3. **모델 출력은 판정이지 Z 가 아니다.** 표시 어휘: `in_focus | step_up | step_down | no_sample_here | unsure`.
   Z 는 선택된 프레임의 엔코더 읽기에서 온다. 모델 숫자는 기록에서 "model" 로 표시한다.
4. **모든 작업은 기록을 남긴다.** 시작 상태, 보낸 명령, 읽은 값, 종료 상태, 수동 단계.
5. **모든 종료 경로에서 소등한다.**
6. **엔진은 하드웨어 없이 돈다.** 모든 기능은 mock 에서 먼저 끝까지 동작해야 한다.
7. **명령과 이벤트는 직렬화 가능한 데이터다.** 나중에 UI 와 엔진을 다른 프로세스로 나눌 수 있다.
8. **엔진은 UI 툴킷과 torch 를 import 하지 않는다.** 무거운 import 는 사용 지점에서.
9. **에이전트 저장소는 읽기 전용이다.** 카드는 UI 가 쓰지 않는다.
10. **9월 30일 운영 규칙을 코드로 넣는다.** 명시야로 가장자리 추적 후 입자 조명으로 전환,
    세션마다 재추적, 액침액 로딩 확인 대기, 100x 상향 연장은 사용자 승인 후.
11. **Claude 는 제안만 한다.** 동작 도구는 사람이 확인해야 실행되고, 확인 뒤에도 엔진의 게이트와
    가드를 그대로 지난다. Claude 는 안전 판단과 모션 한계에 들어가지 않는다.

soft-matter-agents 와의 대응 (통합 단계에서 다룸):

| 이 저장소 | soft-matter-agents |
|---|---|
| Backend | `devices/*.py` 의 preflight / apply / read / abort |
| Engine operation | 승인된 plan 의 단계, `operator.py` 가 실행 |
| Gates, 하드웨어 구성 파일 | 장치 레지스트리와 `envelope/` |
| Guards | `GuardedCore` 허용 목록 + orchestrator 인터록. **현재 ZDrive, XYStage, Nosepiece 는 거부됨** |
| 기록 | `runs/<run_id>/log.json`, 등급 표시 |
| AgentStore | `*/questions/`, `*/runs/`, `inbox/` |

## 7. 결정이 필요한 사항

| # | 질문 | 상태 / 권고 |
|---|---|---|
| D1 | UI 기술 | **결정: 로컬 웹 앱, FastAPI + React** (사용자, 2026-10-01). 이유는 아래 |
| D2 | Python 환경 | 4절 방침. **현미경 PC 에서 최종 결정** (사용자, 2026-10-01) |
| D3 | 엔진 프로세스 | **결정: 엔진은 FastAPI 서버 프로세스 안에서 돈다** (D1 에 따름). 엔진은 서버 없이도 import 된다 |
| D4 | 첫 범위 | **결정: 모든 기능을 mock 으로 먼저** (사용자, 2026-10-01) |
| D5 | 공개/비공개 | **결정: 통합할 때 이 저장소를 공개한다** (사용자, 2026-10-01). 그때까지 비공개 |
| D6 | Claude 연동 방식 | **권고: 서버의 Messages API + Tool Runner, 동작은 제안 카드**. MCP 노출은 통합 단계 |
| D7 | Claude 에 보낼 수 있는 데이터 | 사용자 결정 필요. 텍스트 기록만, 또는 카메라 프레임과 맵 이미지까지. 이미지도 외부로 나간다 |
| D8 | 비용 한도 | 사용자 결정 필요. 하루 또는 월 한도와 사용 모델. 기본 모델은 `claude-opus-5-5` |

D1 을 웹으로 정한 이유: v0.1 에서는 현미경 화면만 범위여서 PySide6 를 권했다. F1 로 범위가
에이전트 콘솔까지 넓어졌다. 질문 입력, 카드와 실행 기록 열람, 샘플 맵 클릭, 상태 대시보드는
웹이 만들기 쉽다. 같은 화면을 WSL 이나 다른 PC 의 브라우저에서도 열 수 있다. 엔진이 HTTP API
뒤에 있으면 나중에 에이전트가 같은 API 를 쓰기도 쉽다. 대가는 두 언어(Python, TypeScript)와
라이브 영상 스트리밍이다. 라이브 영상은 서버에서 비닝해 약 800 px JPEG 로 보내면 10 fps 가 가능하다.

## 8. 마일스톤

| | 내용 | 확인 방법 |
|---|---|---|
| M1 | **전 기능 mock**: 엔진 계약, mock 백엔드, mock 에이전트 저장소, F1–F6 화면, 모든 화면의 프롬프트 칸 (가짜 LLM) | 개발 데스크톱에서 하드웨어 없이 F1–F5 를 끝까지 실행. `uv run pytest` |
| M2 | 실제 데이터 읽기: soft-matter-agents 파일 읽기, replay 로 실제 샘플 스택 | 사용자 확인 |
| M3 | 현미경 PC 읽기 전용: 하드웨어 탐지, 구성 파일, 게이트, 상태 표시 | 사용자가 현미경 PC 에서 실행 |
| M4 | 동작: 샘플 맵, 클릭 이동, 배율 전환과 액침액 로딩, 100x 초점 | 벤치 기록이 9월 30일 결과와 일치 |
| M5 | 초점 판정: 고전 지표 + DINO, 현미경 PC 학습 헤드 | 현미경 PC 학습/지연 측정 기록 |
| M6 | 통합 준비: soft-matter-agents 어댑터 설계 | 총괄 검토 |

## 9. 작업 묶음과 파일 소유 (매니저가 배정)

| 묶음 | 내용 | 소유 경로 | 선행 |
|---|---|---|---|
| WP-A 엔진 계약 | Backend 프로토콜, 이벤트, 기록, 가드/게이트 골격 | `engine/{backend,events,records,guards,gates,sample}.py` | 없음. 가장 먼저 |
| WP-B 백엔드 | **mock 시뮬레이터 우선**, replay, mm-demo, mm-real | `engine/backends/` | WP-A |
| WP-C 기존 작업 이식 | status, lights_off, edge_trace, scan_4x, focus_100x | `engine/operations/` 의 해당 파일 | WP-A, WP-B mock |
| WP-D1 서버 골격 | FastAPI 앱, 라우터 구조, WebSocket 이벤트/프레임 브리지, 정적 파일 제공, 접속 범위 설정 | `server/{app,ws,static}.py`, `server/schemas/` 공통, `tests/server/` | WP-A 이벤트 형식 |
| WP-D2 웹 셸 | Vite + React + TS 프로젝트, 레이아웃, 내비게이션, 상태 표시줄, 생성 타입 클라이언트, 라이브 뷰 | `web/` 전체 중 `web/src/features/` 제외 | Node 설치, WP-D1 OpenAPI |
| WP-E 초점 + 학습 런북 | 고전 지표, DINO 래퍼, 판정 매핑, 현미경 PC 학습 절차 | `focus/`, `docs/runbooks/` | 없음 |
| WP-F 에이전트 콘솔 (F1) | AgentStore 어댑터, mock 저장소, 질문/이전 질문/시뮬레이션/실험 화면 | `agents/`, `server/api/console.py`, `web/src/features/console/` | 어댑터는 없음, 화면은 WP-D1·D2 |
| WP-G 하드웨어 파악 (F2) | 탐지, 구성 파일 형식, 게이트 판정 | `engine/operations/hardware_scan.py`, `engine/gates.py` 의 규칙, `server/api/hardware.py`, `web/src/features/hardware/` | WP-A |
| WP-H 샘플 로딩 (F3) | 지오메트리 데이터 모델, 입력 창, 로딩 확인 | `engine/sample.py` 의 지오메트리 부분, `server/api/sample.py`, `web/src/features/sample/` | WP-A |
| WP-I 샘플 맵 (F4) | 투과광 모자이크, 입자 후보, flag, 클릭 이동 | `engine/operations/sample_map.py`, `server/api/map.py`, `web/src/features/map/` | WP-B mock, WP-C scan_4x |
| WP-J 배율 전환 (F5) | 2절 F5 순서, XY 이탈/복귀, 수동 단계 | `engine/operations/objective_change.py`, `server/api/objective.py`, `web/src/features/objective/` | WP-A, WP-B mock |

| WP-K 시뮬레이션 현황 (F6) | 진행률, 내려받기, 궤적 뷰어, 결과 그래프. mock 실행 생성기 | `server/api/simulation.py`, `web/src/features/simulation/`, AgentStore 의 시뮬레이션 읽기 부분 | WP-F 어댑터, WP-D1·D2 |
| WP-L Claude 연동 (X1, X2) | 도구 정의, Tool Runner, 가짜 공급자, 제안 카드 흐름, 기록, 공통 프롬프트 칸 | `assistant/`, `server/api/assistant.py`, `web/src/app/assistant/` | WP-A, WP-D1·D2. 실제 호출은 D6–D8 결정 후 |

- 기능별 화면은 `server/api/<영역>.py` 와 `web/src/features/<영역>/` 를 한 묶음이 함께 소유한다.
  셸(WP-D2)은 각 영역을 내비게이션에 붙이는 등록 지점 하나만 열어 두고, 영역 묶음은 그 파일을 고치지 않는다.
- `web/package.json`, `web/package-lock.json` 은 `pyproject.toml` 과 같은 규칙이다. 매니저를 통해 한 세션만 고친다.
- `engine/gates.py` 와 `engine/sample.py` 는 WP-A 가 골격을 만들고, 이후 내용은 G 와 H 가
  나눠 맡는다. 동시에 같은 파일을 배정하지 않는다.
- 공유 파일: `pyproject.toml`, `uv.lock` 은 매니저를 통해 한 세션만 고친다.
  `docs/PLAN.md`, `docs/sessions.md` 는 총괄만, `docs/tasks/` 는 매니저만 쓴다.
  `scripts/*` 는 과제에 명시된 경우만 고친다.

## 10. 미해결 사항

추후 결정:
- F1.1 질문을 실제로 어디에 쓰는지. soft-matter-agents 와 정해야 한다.
- F3.2 내용, F3.1 필드 목록 확정.
- F5 이탈 방향과 거리. 재물대 Y 한계와 샘플의 24 mm 변 방향을 측정한 뒤 정한다.
- F5 에서 물 대물렌즈(40x WI)는 작동 거리 값이 없어 보류 (soft-matter-agents 과제 026 5절).
- F6 진행률: WSL 의 시뮬레이션이 진행 상태를 파일로 남기는지, 궤적과 로그가 어디에 있는지 현미경 PC 에서 확인.
- X2 와 soft-matter-agents 규칙: 그쪽 과제 026 은 외부 서비스 호출을 "사람의 결정, 미승인" 으로 둔다.
  이 저장소의 Claude 연동은 사용자가 요청한 것이고, 통합 시 그쪽 기록에도 남겨야 한다.

9월 30일 벤치에서 넘어온 것:
- `find_particle_z.py` 의 입자 판별을 신뢰할 수 없다 (실제 입자 약 6.7 µm).
- Aura 깜박임으로 밝기 −23 % 프레임이 한 번 나왔다.
- 4x→100x 동초점 오프셋이 약 −60 µm 로 측정됐고 기준 시료로 재측정이 필요하다.
- A4000 지연 시간과 fp16 헤드의 실측 성능은 아직 측정하지 않았다.
- 현재 헤드는 합성 100x 형광 데이터로만 학습됐다. 명시야 유리/물 계면은 시뮬레이션되지 않는다.
