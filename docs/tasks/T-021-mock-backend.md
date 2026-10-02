# T-021 WP-B MockBackend (M1 기본 백엔드)

- 담당: AF 실행12 · 개발 (새 세션). T-015 와 같은 브랜치에서 이어서
- 선행: T-002-1 병합, T-007 (mock 세계, 실행3) 병합. T-007 이 늦으면 T-015 를 먼저 한다
- 브랜치: `exec12/T-015-backend-protocol-v2` 에 이어서 커밋해도 되고 새 브랜치 `exec12/T-021-mock-backend`

## 소유 경로

- `src/dino_autofocus/engine/backends/mock.py`
- `tests/engine/test_backends_mock.py`

## 내용

- T-002 의 Backend 프로토콜과 T-015 확장 메서드 전부를 `mock_world` (T-007) 위에 구현한다.
- 모든 모션 메서드는 처음에 제어권 토큰 확인 자리를 거친다 (T-002 의 토큰 자리). z 는 벤치 좌표.
- `describe_devices()` 는 mock 장치 목록으로 hardware_profile 과 같은 형식을 만든다 (F2 mock).
- 연속 취득은 mock_world 의 render 로 일정 간격 프레임을 낸다.
- readback 오차와 광 드롭아웃 주입 옵션을 그대로 노출한다 (가드 테스트용).
- torch, pymmcore, UI 툴킷 import 금지.

## 완료 조건

- 공통 조건, 커밋 메시지 끝 `Session: AF 실행12`
- T-002 의 계약 테스트를 `FakeBackend` 대신 MockBackend 로도 돌려 통과 (매개변수화)
- 끝나면 `[검토요청 T-021]`
