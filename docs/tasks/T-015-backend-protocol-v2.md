# T-015 WP-A 백엔드 프로토콜 확장 (T-006 명세의 읽기와 상대 이동)

- 담당: AF 실행12 · 개발 (새 세션). MockBackend 과제 T-021 과 이어서
- 묶음: WP-A
- 선행: T-002-1 병합. MockBackend 과제와 WP-G (hardware_scan) 가 이것을 쓴다
- 배정: 2026-10-01 작성
- 브랜치: `execN/T-015-backend-protocol-v2`

## 소유 경로

- `src/dino_autofocus/engine/backend.py` (T-002 병합 뒤 소유 이전)
- `tests/engine/conftest.py` 의 `FakeBackend` 확장 (T-002-1 병합 뒤 소유 이전. 실행1 의 2·3단계가 conftest 를
  고쳐야 하면 매니저에게 먼저 알린다)
- `tests/engine/test_contract_backend_v2.py`

## 내용 (이름은 `docs/operations-spec.md` 0.1절의 가칭. 다르게 정하면 명세도 고친다)

1. 하드웨어 탐지 읽기 (F2): `describe_devices()` (장치 종류, 라이브러리, 속성, 읽기 전용 여부, 허용 값,
   한계), `nosepiece_labels()` (상태 라벨과 픽셀 크기), `piezo_read()` (쓰기 없음), `config_record()`
   (sha256, 로드 중 변경 여부, AutoShutter readback, 시작 preset 적용 사실).
2. XY 상대 이동 `xy_move_rel(dx_um, dy_um)`: edge_trace 의 보정과 추적 걸음. 가드는 절대 이동과 같다.
3. 연속 취득: `start_stream()` / `next_frame()` / `stop_stream()`. 라이브 뷰와 edge_trace 가 같은
   스트림을 쓴다. 프레임 메타는 `snap()` 과 같다.

## 매니저가 정한 상수 (총괄 승인. 현미경 PC 측정 전 임시값, 코드와 기록에 "unmeasured provisional" 표시)

- **큰 XY 이동 문턱** = min(현재 렌즈 시야 1 배, 1 mm). 4x 에서는 1 mm 라 edge_trace 걸음 200 µm 보다
  크다. 100x 에서는 약 156 µm 라 더 작은 이동도 Z 후퇴를 요구한다. 의도된 보수적 값이다.
- **Z 후퇴 높이 z_safe** = 모든 렌즈 0 µm (`change_objective.py` 의 RETRACT_Z_UM). 렌즈별 값은 측정 뒤.
- **F5 이탈 거리 escape_dy_um** = 기본값 없음. 설정되지 않으면 preflight 가 거부한다.
  이 상수들은 `guards.py` 에 두며, 이 과제가 아니라 T-011 또는 후속 가드 과제가 반영한다.

## 완료 조건

- 공통 조건, `FakeBackend` 가 새 메서드를 모두 구현
- 끝나면 `[검토요청 T-015]`

## Addition (from T-023, 실행11)

- Add an optional `notes: dict[str, str]` (default empty) to `Readback` and `BackendInfo`. Backends use it
  for markings such as `"unmeasured provisional"` and demo substitutions, so they never go into device or
  property names.
