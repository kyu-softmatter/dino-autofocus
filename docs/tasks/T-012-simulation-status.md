# T-012 WP-K 시뮬레이션 현황 (F6)

- 담당: 미정
- 묶음: WP-K (PLAN.md v0.4 9절)
- 선행: 데이터 층 (1단계) 은 T-008 병합 뒤. 서버와 화면 (2단계) 은 T-009, T-010 병합 뒤.
  한 세션이 1단계를 먼저 커밋하고 같은 브랜치에서 2단계를 이어 가도 되고, 둘로 나눠 배정해도 된다
- 배정: 2026-10-01 작성
- 브랜치: `execN/T-012-simulation-status`

## 목표

PLAN.md 2절 F6: 진행 중인 시뮬레이션의 진행률, 실행 폴더 zip 내려받기, 궤적 재생 뷰어, 로그와
관측량 그래프. 참고 구조는 공개 저장소 kyu-softmatter/HOOMD_GUI (FastAPI 로컬 러너, 루프백 바인딩,
Host 헤더 허용 목록, 같은 출처에서 웹과 API). 읽기만 한다. 시뮬레이션 코드는 import 하지 않는다.

## 소유 경로

- 1단계 (데이터 층): `src/dino_autofocus/agents/simulation.py`, `src/dino_autofocus/agents/mock_sim.py`,
  `tests/agents/test_agents_simulation*.py`
- 2단계 (화면): `src/dino_autofocus/server/api/simulation.py`, `web/src/features/simulation/`,
  `tests/server/test_server_simulation*.py`

T-008 의 `agents/{store,mock_store,sma_files}.py` 는 고치지 않는다. 필요한 연결점이 있으면 매니저에게
요청한다 (T-008 소유 세션에 작은 후속 과제로 준다).

## 내용

### 1단계 — `agents/simulation.py`, `agents/mock_sim.py`

- 실행 하나의 현황: 현재 step / 전체 step, 경과 시간, 예상 종료. 출처는 `simulation_agent/runs/<id>/`
  의 `config.json`, `log.json`, `trajectory_meta.json`. 진행 상태 파일이 실제로 있는지는 현미경 PC 확인
  사항이므로 (PLAN.md 10절) 출처를 하나의 함수로 모으고, 없으면 "unknown" 으로 돌려준다.
- 로그와 관측량 시계열: `log.json`, `observables.json` 에서 읽은 값 그대로. 다시 계산하지 않는다.
- 궤적: `trajectory_meta.json` 이 가리키는 파일 (GSD, WSL 쪽 `\\wsl$\...`) 의 프레임 수와 프레임 읽기.
  GSD 라이브러리가 필요하면 의존성 요청을 매니저에게 먼저 한다 (지금은 넣지 않는다). mock 에서는
  numpy 로 만든 가짜 궤적.
- zip: 실행 폴더를 스트리밍 zip 으로. 큰 궤적은 선택해서 포함. 원본은 읽기만.
- `mock_sim.py`: 시간에 따라 진행하는 가짜 실행 (step 이 늘고 로그가 길어지고 궤적 프레임이 생김).
  쓰기는 지정한 임시 폴더에만.

### 2단계 — `server/api/simulation.py`, `web/src/features/simulation/`

- 라우터: 목록, 현황, 시계열, 궤적 프레임, zip 내려받기. 진행률은 T-009 의 WebSocket 또는 SSE.
  모든 경로가 GET (읽기 전용) 이라 원격 보기에서도 동작한다.
- 화면: 진행률, 내려받기 버튼, Canvas 2D 궤적 재생 (3D 는 나중에 Three.js 인스턴싱), 그래프.
  공통 프롬프트 칸 (T-014) 에 선택된 run id 를 문맥으로 넘긴다. 프롬프트 칸을 따로 만들지 않는다.

## 완료 조건

- 공통 조건, 웹 쪽은 T-010 의 npm 검사 (build, test, 타입 검사)
- 끝나면 `[검토요청 T-012]`
