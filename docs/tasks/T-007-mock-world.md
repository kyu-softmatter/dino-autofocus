# T-007 WP-B: mock 시뮬레이터의 가상 세계 (M1 기본 백엔드의 핵심)

- 담당: AF 실행3 · 개발 (T-005 다음 과제)
- 묶음: WP-B (PLAN.md v0.2 9절, "mock 시뮬레이터 우선")
- 선행: T-005 의 `[검토요청]` 을 보낸 뒤 같은 worktree 에서 `main` 을 받아 새 브랜치로 시작.
  T-002 는 기다리지 않는다
- 배정: 2026-10-01, 총괄 지시 (PLAN.md v0.2)
- 브랜치: `exec3/T-007-mock-world`

## 목표

PLAN.md v0.2 5절의 `mock` 백엔드는 M1 의 기본 백엔드다. 그 핵심인 **가상 세계**
(샘플, 광학, 재물대, 광원, 영상 생성)를 Backend 프로토콜과 독립된 순수 모듈로 먼저 만든다.
프로토콜을 구현하는 얇은 `MockBackend` (`engine/backends/mock.py`) 는 T-002 병합 뒤 다음 과제로
배정한다. 이 세계 하나로 F1–F5 의 현미경 기능이 데스크톱에서 끝까지 돌아야 한다.

## 소유 경로

- `src/dino_autofocus/engine/backends/mock_world.py` (커지면 `mock_world/` 패키지로 나눠도 된다)
- `tests/engine/test_backends_mock_world.py`

`configs/*.yaml` 은 읽기만 한다. `src/dino_autofocus/synth/*` 는 수정하지 않는다.

## 내용

- **가상 샘플** (seed 로 결정적): 샘플 크기 (보통 24 mm × 50 mm), 챔버 구멍 (중심, 지름 약 6 mm),
  커버슬립 두께 (기본 170 µm), 방향 (정상 / 뒤집힘), 입자 (지름 약 5–6.7 µm, 바닥층과 그 위
  15–25 µm 에 몇 개). 초점면은 기울어진 평면: 9월 30일 실측 4x 초점 3048.7 µm, 기울기 x −1.66,
  y −3.62 µm/mm (`docs/runs/2026-09-30_substrate-scan.md` 1절).
- **대물렌즈 세트**: `configs/ti2_*.yaml` 의 4x, 10x, 20x, 40x, 60x, 100x (NA, 배율, 침지 굴절률,
  작동 거리, 픽셀 6.5 µm / 배율). DoF 는 NA 와 파장에서 계산한다 (`synth/optics` 를 참고만 하거나
  import). 동초점 오프셋: 100x 초점 ≈ 4x 초점 − 60 µm. Nosepiece 위치 번호와 라벨은 운영 기록의
  라벨을 따른다 (0 = 4x, 5 = 100x Oil).
- **재물대**: XY 범위와 Z 범위 (현재값 미측정이면 상수로 두고 "추후 측정"), 이동 속도, readback
  오차 주입 옵션 (가드 테스트용, 예: 3037 명령 / 3036 읽음).
- **광원**: DiaLamp (투과광: 구멍 가장자리와 입자 그림자가 보임), Aura 라인 (형광: 입자만 밝음,
  퍼밀 단위 강도), 둘 다 off 면 어두운 offset (~102 ADU). 광 드롭아웃 주입 옵션 (−23 % 프레임).
- **PFS**: 상태 (off, Out of Range) 만 흉내. 소프트웨어가 켜지 않는다.
- **영상 생성** `render(x_um, y_um, z_um, objective, light, exposure_ms, roi, binning) -> uint16`:
  시야 안의 구멍 가장자리와 입자를 그리고, |z − 초점면| / DoF 에 따라 흐리게 하고, 노출에 비례한
  신호와 포아송 + 읽기 노이즈, 12-bit 천장 4095 포화. 같은 입력이면 같은 출력 (seed).
  100x 에서는 희소 입자라 Vollath 가 실패하고 peak 지표가 동작하는 9월 30일 현상이 재현되면 좋다.
- **성능**: 512² 프레임 한 장 50 ms 안 (numpy + scipy 만, GPU 없음). 2400² 전체 센서는
  ROI 와 binning 으로 줄여서 쓴다는 것을 docstring 에 적는다.
- **상태 직렬화**: 세계 상태 (위치, 렌즈, 광원) 를 dict 로 내고 다시 받는다 (기록과 재현용).
- torch, pymmcore, UI 툴킷 import 금지.

## 테스트

- 결정성 (같은 seed 같은 프레임), 초점에서 vollath4 최대이고 |dz| 에 따라 단조 감소 (4x),
  100x 희소 입자에서 peak 지표가 초점을 찾음, 광원 off 면 offset 수준, 포화 처리, 드롭아웃과
  readback 오차 주입, 성능 (느슨한 상한, CI 에서 흔들리지 않게).
- 초점 지표는 T-003 (실행2) 의 `focus/classical.py` 가 아직 main 에 없으면 테스트 파일 안에
  최소 구현을 두고 주석으로 표시한다. T-003 병합 뒤 정리는 다음 과제에서 한다.

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests`, 소유 밖 diff 없음,
  커밋 메시지 끝 `Session: AF 실행3`)
- 끝나면 `[검토요청 T-007]` 를 검토 세션에

## T-007b (AF 실행3, after T-029c; review AF 검토보조2) — timing test that survives a loaded machine

- `tests/engine/test_backends_mock_world.py::test_512_frame_renders_under_50_ms` (best of 5 under 50 ms) failed under
  parallel load (검토보조2, `tests/engine tests/e2e`). Keep the strict bound only when `DINOAF_PERF=1` is set
  (skip with a reason otherwise), and keep an always-on loose check (e.g. median of 5 under 500 ms) so a real
  regression still fails.
