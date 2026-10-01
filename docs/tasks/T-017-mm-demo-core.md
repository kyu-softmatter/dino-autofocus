# T-017 WP-B: Micro-Manager 데모 장치 층 (프로토콜 독립 부분)

- 담당: AF 실행11 · 개발
- 묶음: WP-B
- 선행: 없음. Backend 프로토콜 (T-002) 을 구현하는 `mm_demo.py` 본체는 T-002 병합 뒤 다음 과제
- 배정: 2026-10-01
- 브랜치: `exec11/T-017-mm-demo-core`

## 목표

PLAN.md 5절의 `mm-demo` 백엔드에 필요한 장치 다루기를 먼저 만든다. 실행3 의 실측 (T-002 부록 2) 을
코드로 옮긴다. 프로토콜 클래스는 만들지 않고, 그것이 부를 함수들만 만든다.

## 소유 경로

- `src/dino_autofocus/engine/backends/mm_demo_core.py`
- `tests/engine/test_backends_mm_demo_core.py`

`engine/backends/__init__.py` 는 T-005 소유다. 이 과제는 고치지 않는다.

## 내용

- 데모 설정 로드: pymmcore-plus 의 `MMConfig_demo.cfg` (이 PC 에 Micro-Manager 2.0.3 데모 어댑터가
  있다). pymmcore 는 함수 안에서만 import. 어댑터가 없으면 명시적 예외.
- **Z 좌표 변환**: 데모 Z 범위 −300~+300 µm. 벤치 좌표 (2800–3200) 와 데모 좌표 사이 오프셋 변환을
  한 곳에. 엔진과 기록은 항상 벤치 좌표다.
- **XY**: 큰 이동이 코어 타임아웃 5 s 에 걸리므로 속도 설정 또는 타임아웃 인자.
- **광원 대응**: DiaLamp ↔ "White Light Shutter", Aura 라인 ↔ LED 라벨과 LED Shutter (State 속성이
  없어 셔터 API 로만). 의미 단위 함수 (`lamp_on/off`, `aura_line_on(line, percent)`, `aura_off`,
  `all_off`) 가 readback 기록을 돌려준다.
- **카메라**: 2400² 16-bit 흉내 (`scripts/mm_grab.py` 의 `open_core(demo=True)` 와 같은 설정),
  "Fluorescent Beads" 모드에서 z 에 따른 결정적 초점 곡선.
- 대물렌즈 라벨: 데모 Nosepiece 라벨과 실제 Ti2 라벨의 대응표 (실제 라벨은 운영 기록 참조).

## 테스트

- 데모 어댑터가 없으면 `pytest.skip`. 있으면: 좌표 변환 왕복, 범위 밖 거부, 광원 readback, 초점 곡선
  단조성 (실행3 측정: vollath4 0 µm 17.5, ±5 µm 3.1, ±20 µm 0.04), XY 큰 이동이 시간 안에 끝남.
- 코어는 테스트마다 정리한다 (`CMMCorePlus.instance()` 공유 주의). 실행 시간이 길면 표시를 붙인다.

## 완료 조건

- 공통 조건 (커밋 메시지 끝 `Session: AF 실행11`)
- 끝나면 `[검토요청 T-017]`
