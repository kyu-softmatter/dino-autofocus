# T-003 WP-E 초점 지표·판정 어휘·학습 런북 (WP-A 비의존 부분)

- 담당: AF 실행2 · 개발
- 묶음: WP-E (PLAN.md 8절)
- 선행: T-001 (같은 세션). T-001 의 `[검토요청]` 을 보낸 뒤 같은 worktree 에서 `main` 을 받아
  새 브랜치로 시작한다. T-002 는 기다리지 않는다
- 배정: 2026-10-01, 총괄 승인
- 브랜치: `exec2/T-003-focus-classical`

## 목표

고전 초점 지표와 판정 어휘를 스크립트에서 패키지로 옮기고, 현미경 PC 에서 할 DINO 헤드 학습
절차를 런북으로 쓴다. 엔진(WP-A)에 의존하지 않는 순수 numpy 코드와 문서만 다룬다.
DINO 래퍼는 얇게, torch 는 함수 안에서만 import 한다.

## 소유 경로

- `src/dino_autofocus/focus/__init__.py`, `classical.py`, `verdict.py`, `dino.py`
- `tests/focus/`
- `docs/runbooks/`

`scripts/*`, `src/dino_autofocus/live.py`, `src/dino_autofocus/synth/*` 는 수정하지 않는다
(mm_grab 의 복사본은 WP-C 이식 때 치운다).

## 내용

### `classical.py`

지표를 순수 numpy 함수로. 근거: `scripts/mm_grab.py` (`vollath4`, `brenner`),
`scripts/focus_100x.py` (`--metric peak`: 4×4 비닝 최대 밝기 − 중앙값, 희소 입자용),
`scripts/scan_4x.py` (스윕 중앙값 대비 평균 2 % 이상 어긋난 프레임은 광 드롭아웃으로 제외),
`src/dino_autofocus/synth/sim/metrics.py` (vendored, 수정 금지; 테스트에서 교차 검증 용도로 import 가능).

- `vollath4`, `brenner`, `tenengrad`, `peak_brightness` (그리고 synth 에서 RELIABLE 로 쓰는 것 중
  라이브에 필요한 것), uint16 입력 가정, 포화 픽셀 처리 명시 (12-bit 천장 4095 와 16-bit 모두).
- 스윕 곡선 도구: 광 드롭아웃 필터, 포물선 꼭짓점 보정 (`scripts/eval_synthetic.py` 의
  argmax + parabola 와 같은 식), 피크가 스팬 가장자리에 있는지 판정.

### `verdict.py`

soft-matter-agents 초점 과제(026)의 어휘를 그대로 쓴다 (PLAN.md 5절 3항):
`in_focus | step_up | step_down | no_sample_here | unsure`.

- `Verdict(str, Enum)` 와 `FocusVerdict` dataclass: verdict, 선택된 프레임 index 와 그 프레임의
  **엔코더 z** (모델 값이 아님), 근거 지표값, 모델 점수가 있으면 `grade: "model"` 표시
  (T-002 의 records 가 정하는 필드 이름을 쓴다. T-002 가 먼저 병합되지 않았으면 `grade` 로 두고
  `[이슈]` 로 알린다).
- 매핑 1 — 스윕 곡선에서: 피크가 스팬 안 → `in_focus` (보정된 z 가 아니라 가장 가까운 실제
  프레임의 엔코더 z 를 고른다), 피크가 꼭대기 → `step_up`, 바닥 → `step_down`, 동적 범위가
  암전 수준 (운영 기록: 30 ms Vollath 가 dark offset ~102 ADU 만 읽음) → `no_sample_here`,
  그 밖 → `unsure`.
- 매핑 2 — 단일 프레임 부호 있는 읽기(DINO, `live.FocusReading`)에서: |dz| ≤ 1 DoF →
  `in_focus`; 부호가 알려지면 dz 의 정의 (dz = stage − best focus, 양수면 스테이지가 위) 에 따라
  `step_down` / `step_up`; sigma 가 크면 `unsure`. 단위와 부호를 docstring 에 적는다.
- 판정은 표시용이다. 모션 한계나 안전 판단에 쓰이지 않는다는 문장을 모듈 docstring 에 둔다.

### `dino.py`

`dino_autofocus.live.FocusScorer` 를 감싸 `FocusVerdict` 를 내는 얇은 래퍼. torch 와 live 는
함수/메서드 안에서 import. `import dino_autofocus.focus` 가 torch 를 끌어오지 않는지 테스트.

### `docs/runbooks/train-focus-head.md`

현미경 PC (RTX A4000) 에서 할 절차. 데스크톱에서는 **실행하지 않는다** (PLAN.md 3절).
근거: `docs/setup-new-pc.md`, `docs/synthetic-results.md`, `scripts/make_dataset.py`,
`scripts/train_head.py`, `scripts/eval_synthetic.py`, `scripts/bench_latency.py`,
`scripts/learning_curve*.py` 의 docstring 과 인자.
- 환경 (uv, `DINOV2_REPO` 클론 7764ea0), 데이터셋 생성 인자와 소요 시간/메모리 주의
  (`docs/integration-notes.md` 의 15 workers 크래시), 헤드 학습, 평가, fp16/fp32, 지연 측정,
  결과물 위치 (`models/heads/`), 기록할 것.
- 명령은 코드 블록, 설명은 한국어.

### `tests/focus/`

합성 입력(가우시안 점 + 노이즈, 블러 단계별)으로 각 지표가 초점에서 최대인지, 드롭아웃 필터,
가장자리 판정, 두 매핑의 모든 분기, torch 미import.

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests` — T-001 병합 후이므로 0건,
  소유 밖 diff 없음, 커밋 메시지 끝 `Session: AF 실행2`)
- `uv run python -c "import sys, dino_autofocus.focus; assert 'torch' not in sys.modules"`
- 끝나면 `[검토요청 T-003]` 를 검토 세션에
