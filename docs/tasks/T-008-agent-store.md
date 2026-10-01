# T-008 WP-F: AgentStore 어댑터와 mock 저장소 (F1 의 데이터 층)

- 담당: 미정. **먼저 비는 실행 세션**에 배정한다 (총괄 지시)
- 묶음: WP-F (PLAN.md v0.2 9절). 어댑터는 UI 기술과 무관하다
- 선행: 없음
- 배정: 2026-10-01 작성
- 브랜치: `execN/T-008-agent-store`

## 목표

F1 에이전트 콘솔 (질문 넣기, 이전 질문, 시뮬레이션·실험 현황/계획/결과) 이 읽을 데이터 층을
만든다. soft-matter-agents 저장소는 **읽기 전용**이다 (PLAN.md 6절 9항). 질문 넣기 (F1.1) 는
어댑터 인터페이스 뒤의 mock 저장소에만 쓴다. 실제 쓰기 경로는 통합 단계에서 정한다.

## 소유 경로

- `src/dino_autofocus/agents/__init__.py`, `store.py`, `mock_store.py`, `sma_files.py`
- `src/dino_autofocus/agents/mock_data/` (예제 카드 복사본)
- `tests/agents/` (파일 이름 `test_agents_*.py`)

## 내용

### `store.py` — `AgentStore` 프로토콜과 자료형

- 자료형 (직렬화 가능한 dataclass): `QuestionSummary`, `QuestionDetail` (goal, axis 카드들, plan,
  synthesis, refusal, 버전), `RunSummary`, `RunDetail` (microscope: `commands.json`, `log.json`;
  simulation: `config.json`, `log.json`, `observables.json`, `trajectory_meta.json`),
  `InboxThread`.
- 메서드: `list_questions(agent)`, `get_question(qid)`, `list_runs(agent)`, `get_run(agent, run_id)`,
  `list_inbox()`, `submit_question(text, target, ...)`. agent 는 `"microscope" | "simulation"`.
- 카드 버전: `v2_`, `v3_` 접두 파일이 있으면 최신 버전을 기본으로, 이전 버전 목록도 돌려준다
  (`simulation_agent/questions/sim-20260923-001/` 참조).
- 카드의 원본 dict 는 잃지 않고 그대로 담는다. UI 가 필드를 골라 쓴다. 등급 표시 필드
  (`numbers`, grade) 는 해석하지 않고 보존한다.
- 상태와 시각 (`status`, `created_at`, `finished_at`) 은 목록에서 바로 쓸 수 있게 꺼낸다.

### `sma_files.py` — soft-matter-agents 파일 읽기

- 루트 경로는 인자 (기본 `D:\codes\github\soft-matter-agents`, 환경변수로 바꿀 수 있게).
- 읽기만 한다. `submit_question` 은 `ReadOnlyStoreError` 같은 명시적 예외. 테스트로 쓰기가 없음을
  확인한다 (예: 루트를 읽기 전용 tmp 사본으로 두고 파일 변경이 없는지).
- `contracts/schemas/*.schema.json` 은 참고만 한다. soft-matter-agents 의 코드를 import 하지 않는다.
- 큰 파일 (시뮬레이션 trajectory 등) 은 열지 않는다. 목록과 메타만.

### `mock_store.py` — mock 저장소

- `mock_data/` 의 예제 카드를 읽고, `submit_question` 은 사용자 지정 쓰기 폴더 (기본은 임시 폴더,
  패키지 안은 쓰지 않음) 에 질문 카드 초안을 남긴다. 형식은 `goal.schema.json` 을 흉내 내되
  `"origin": "dino-autofocus mock"` 같은 표시를 넣어 실제 카드와 구분한다.
- 예제 카드: `D:\codes\github\soft-matter-agents` 에서 **읽기만 해서 복사**한다 (총괄 지시).
  microscope 질문 1–2 개, simulation 질문 1 개 (v2/v3 버전 포함), microscope run 1 개,
  simulation run 1 개 (큰 trajectory 제외), inbox 스레드 1 개. 전체 200 KB 이하.
  복사한 출처 커밋 (`git -C D:\codes\github\soft-matter-agents rev-parse HEAD`) 을
  `mock_data/SOURCE.md` 에 적는다.

### 테스트

- mock 저장소로 모든 메서드, 버전 선택, 직렬화 왕복, 쓰기 폴더 밖에 쓰지 않음.
- `sma_files` 는 실제 soft-matter-agents 폴더가 없으면 `pytest.skip`. 있으면 목록이 비지 않고
  쓰기가 없음을 확인. 형식 검증은 `mock_data` 사본으로 한다.
- torch, pymmcore, UI 툴킷 import 없음.

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests`, 소유 밖 diff 없음,
  커밋 메시지 끝 `Session: AF 실행N`)
- `uv run python -c "import sys, dino_autofocus.agents; assert not {'torch','pymmcore','tkinter'} & set(sys.modules)"`
- 끝나면 `[검토요청 T-008]` 를 검토 세션에
