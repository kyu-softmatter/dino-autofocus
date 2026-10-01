# T-005 WP-B 준비: replay 용 z-스택 소스

- 담당: AF 실행3 · 개발
- 묶음: WP-B 의 첫 부분 (Backend 프로토콜에 의존하지 않는 데이터 층)
- 선행: 없음. T-002 와 파일이 겹치지 않는다
- 배정: 2026-10-01
- 브랜치: `exec3/T-005-replay-stacks`

## 목표

replay 백엔드가 "현재 z 에 해당하는 프레임" 을 내려면 z-스택 데이터 층이 필요하다. 이 층은
Backend 프로토콜(T-002)과 무관하므로 먼저 만든다. replay 백엔드 자체는 T-002 병합 뒤 별도
과제로 배정한다.

## 소유 경로

- `src/dino_autofocus/engine/backends/__init__.py` (빈 파일 또는 이 모듈의 공개 이름만)
- `src/dino_autofocus/engine/backends/stacks.py`
- `tests/engine/test_backends_stacks.py`

`src/dino_autofocus/engine/__init__.py` 와 `tests/engine/conftest.py` 는 T-002 (실행1) 소유이므로
**만들지 않는다**. 이 과제의 테스트는 자기 파일 안에서 fixture 를 정의한다.

## 내용

총괄 지시: replay 는 세 가지 입력을 받는다. 테스트는 (a) 만으로 통과해야 한다.

- `ZStack` dataclass: frames `(N, H, W)` uint16, `z_um` `(N,)` 오름차순, 메타 dict (출처, 픽셀 크기,
  best focus 가 알려지면 그 값과 `dz` 정의). `frame_at(z_um)` 은 가장 가까운 평면 (보간 없음,
  선택 규칙과 범위 밖 처리를 docstring 에 명시). 범위 밖 요청은 예외가 아니라 결정된 동작
  (가장자리 평면 + 플래그) 으로 한다. 가드는 엔진의 몫이다.
- (a) 인메모리: `ZStack.from_arrays(...)`. 테스트 안에서 작은 합성 스택(가우시안 점 블러 단계)을
  numpy 로 만드는 것은 허용된다. **데이터셋 생성 스크립트 실행은 금지**.
- (b) `dino_autofocus.synth` 샤드: `data/smoke/shard_00000.npz` 형식 (`image` (N,H,W) uint16,
  `dz_um`, `dz_dof`, `valid`, `cond`, `scene_id`, `family`). `scene_id` 별로 한 스택씩 꺼낸다.
  읽기 형식은 `src/dino_autofocus/synth/sim/dataset.py` (`ShardedArrays`) 를 읽고 맞춘다
  (synth 는 수정 금지). 절대 z 가 없으면 `z_um = dz_um` 으로 두고 메타에 적는다.
  data/ 는 gitignore 대상이다. 이 경로를 쓰는 테스트는 파일이 없으면 `pytest.skip`.
  가능하면 테스트 안에서 같은 키를 가진 작은 npz 를 `tmp_path` 에 써서 로더를 검증한다.
- (c) `D:\AutoFocus\samples` 의 스캔/스택: `scripts/scan_4x.py` 가 쓰는 `scan.json` 과 타일별
  `.npy`, `scripts/focus_100x.py` 의 `focus100x_*.json` 형식을 코드에서 읽어 로더를 만든다. 이 PC
  에는 실제 폴더가 없으므로 테스트는 형식을 흉내 낸 작은 폴더를 `tmp_path` 에 만든다.
  실제 폴더 복사는 총괄이 사용자에게 요청해 두었다.
- 한 함수로 모으기: `load_stacks(source) -> list[ZStack]` (경로 종류로 분기).
- numpy 만 쓴다. torch, pymmcore, UI 툴킷 import 금지.

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests`, 소유 밖 diff 없음,
  커밋 메시지 끝 `Session: AF 실행3`)
- `data/` 가 없는 상태에서도 `uv run pytest tests/engine/test_backends_stacks.py` 가 통과
  (skip 은 허용, 실패는 불가)
- 끝나면 `[검토요청 T-005]` 를 검토 세션에
