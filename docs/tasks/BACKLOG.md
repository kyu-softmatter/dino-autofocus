# 매니저 대기 목록

과제로 아직 배정하지 않은 요구, 공유 파일 변경 순서, 현미경 PC 확인 항목을 모은다. 매니저만 쓴다.

## 공유 파일 변경 순서

| 파일 | 지금 권한 | 다음 | 그다음 |
|---|---|---|---|
| `pyproject.toml`, `uv.lock` | T-009 (실행7: fastapi, uvicorn, pydantic, httpx) | T-013 (`anthropic`) | T-012 (`gsd`) |
| `web/package.json`, `package-lock.json` | T-010 (실행4) | `three` (T-012 요청 시) | T-014 가 요청하는 것 |

권한은 앞 과제가 main 에 병합된 뒤 넘긴다.

## 후속 과제 후보

- **WP-C 초점 이식에 같이 넣을 것** (실행2 메모, 2026-10-01): `focus/classical.py` 에
  `block_scores(img, n=6)` (scan_4x 의 `block_z_um`), 끝에서 None 을 내는 포물선 래퍼 (`parabola_peak`
  호환), 이중 피크 감지 ("check immersion oil" 경고). 담당은 실행2 (T-003 작성자).
- **T-015 백엔드 프로토콜 확장 + MockBackend**: 실행12 에 묶어서 준다 (T-002 병합 뒤).
- **WP-G 하드웨어 파악**: T-002, T-015 뒤.
- **mm_demo.py 본체**: T-017 (실행11) 뒤, T-002 병합 뒤.
- **T-014 공통 프롬프트 칸**: 실행13 예약, T-010 1차 골격 병합 뒤.
- **서버의 EngineAPI 사본 교체**: T-011 병합 뒤, T-009 소유 세션.

## 현미경 PC 확인 항목 (총괄에 넘김)

- `docs/operations-spec.md` 10절 Q1–Q21 (실행4, T-006)
- T-003 임시 상수: `MIN_DYNAMIC_RANGE_ADU` 20, `MIN_CURVE_CONTRAST` 0.05, `MAX_SIGMA_DOF` 3.0,
  `IN_FOCUS_DOF` 1.0
- 암전 판정 방식: T-003 은 프레임마다 p99.9 − median < 20 ADU, T-006 명세의 focus_100x preflight 는
  최댓값이 암전 오프셋 (약 102 ADU) 근처. 둘 중 무엇을 쓸지
- 임시 가드 값 (T-015): 큰 XY 이동 문턱 min(렌즈 시야, 1 mm), z_safe 0 µm, F5 이탈 거리 기본값 없음
