# 매니저 대기 목록

과제로 아직 배정하지 않은 요구, 공유 파일 변경 순서, 현미경 PC 확인 항목을 모은다. 매니저만 쓴다.

## 공유 파일 변경 순서

| 파일 | 지금 권한 | 다음 | 그다음 |
|---|---|---|---|
| `pyproject.toml`, `uv.lock` | T-009 (실행7: fastapi, uvicorn, pydantic, httpx) | T-013 (`anthropic`) | T-012 (`gsd`) |
| `web/package.json`, `package-lock.json` | T-010 (실행4). 열려 있는 동안 요청받은 패키지를 이 과제가 넣는다 | 차트 라이브러리 (T-012 그래프) | `three` (3D 뷰어), 그다음 T-014 요청분 |

권한은 앞 과제가 main 에 병합된 뒤 넘긴다.

요청 접수:
- T-022 (실행16): `dependencies` 에 `three`, `devDependencies` 에 `@types/three`. 래퍼 (@react-three/fiber 등) 없음.
  T-010 1차 골격 병합 뒤 package.json 권한자가 넣는다.

## Review routing (manager, 2026-10-01)

Dev seats send `[검토요청 T-NNN]` to the assistant for their task. One branch, one assistant.

| Assistant | Tasks |
|---|---|
| AF 검토보조1 | T-002 (all stages), T-008 (done), T-011, T-015, T-025, T-027, T-028 |
| AF 검토보조2 | T-007, T-012, T-021, T-023, T-024 |
| AF 검토보조3 | T-004, T-009, T-013, T-018, T-019 |
| AF 검토보조4 | T-010, T-014, T-016, T-020, T-022 |

New tasks get an assistant in their card. Unlisted tasks go to the least loaded assistant.

## Manager to-do on events

- T-009 and T-010 first skeletons merged → tell AF 업무분배보조 (screen stage B starts).
- 실행14 (T-020) or 실행5 (T-004) review cleared → offer the seat to AF 업무분배보조 for T-103 / T-104.
- T-018 merged → 실행13 starts T-105 (screen manager). T-019 merged → 실행2 starts T-106.

## 후속 과제 후보

- **WP-C 초점 이식에 같이 넣을 것** (실행2 메모, 2026-10-01): `focus/classical.py` 에
  `block_scores(img, n=6)` (scan_4x 의 `block_z_um`), 끝에서 None 을 내는 포물선 래퍼 (`parabola_peak`
  호환), 이중 피크 감지 ("check immersion oil" 경고). 담당은 실행2 (T-003 작성자).
- **T-015 백엔드 프로토콜 확장 + MockBackend**: 실행12 에 묶어서 준다 (T-002 병합 뒤).
- **WP-G 하드웨어 파악**: T-002, T-015 뒤.
- **mm_demo.py 본체**: T-017 (실행11) 뒤, T-002 병합 뒤.
- **3D 궤적 뷰어 (Three.js)**: T-012 1단계 (프레임 형식) 병합 뒤, 2D 와 병렬. 소유
  `web/src/features/simulation/viewer3d/`. 시작할 때 `three` 를 package.json 권한자가 넣는다.
- **T-014 공통 프롬프트 칸**: 실행13 예약, T-010 1차 골격 병합 뒤.
- **서버의 EngineAPI 사본 교체**: T-011 병합 뒤, T-009 소유 세션.

- **로그인 서버·화면**: `server/api/auth.py` (쿠키 HttpOnly, SameSite=Strict), `web/src/app/login/`.
  T-018, T-009, T-010 뒤. 담당은 T-018 작성자 (실행13) 가 유력. 런처는 고치지 않는다 (첫 화면 주소만 연다).
- **실험 세션 API·화면**: `server/api/sessions.py`, `web/src/features/sessions/`. T-019, T-009, T-010 뒤.
- **WP-C 이식, WP-G, WP-H, WP-J**: T-002 병합 단계에 맞춰.

- **런북 보강** (검토 세션 제안, T-003 병합 때): `docs/runbooks/train-focus-head.md` 1절에 DINOv2 가중치가
  첫 실행 때 인터넷에서 받아진다는 점, 현미경 PC 가 오프라인이면 `~/.cache/torch/hub/checkpoints` 를
  미리 복사해야 한다는 점을 넣는다.
- **T-019 git 쪽 구현**: 세션별 브랜치/워크트리 대 한 브랜치 폴더별 커밋. 사용자 결정 뒤.

- **From the T-004 spec (실행5, 6fcd8a8), accepted, for future cards:**
  - WP-H: record operations `sample_geometry_set`, `loading_confirm_person`, `loading_check_image` (ui-spec 7.3).
  - WP-I: append-only `map_flag_retire`, `candidate_confirm`, `candidate_reject` (ui-spec 7.4).
  - WP-G: `hardware_confirm` for human-confirmed profile items (ui-spec 7.2).
  - Server/web: first-screen notice of the last shutdown's light readback (ui-spec 5.2).
  - Piezo keys f / w / W stay disabled until M5 (operations-spec 9.2).
- **Waiting on the director/user:** real `light_set`/`lights_off` at M3 instead of M4; whether viewers
  may submit questions to the mock store and write flags (default: local operator only).

## Engine requirements promised to the screens (for WP-C, G, I cards)

- Op names are fixed by the screen contracts (list in T-011). Engine cards must use them.
- **Sample state storage (manager decision):** boundary points, flags and candidates are append-only events
  in the open experiment session's `records/sample_events.jsonl` (PLAN 5, T-019). The engine has one
  reader that folds them into the current state. Legacy `sample.json` / `map.json` are derived views for
  the old tools. Flag and candidate writes need an open session. The engine assigns `flag_id` and
  `candidate_id`, and a reject is a new entry with source `person_rejected`.
- WP-G: HardwareProfile gets host, config, per-device type/library/properties/write_verified, objective rows,
  camera, piezo, positions/pfs/lights (ops-spec 5). Confirmed items are `{value, by, at}`, and profile history
  keeps a diff. This is not added to T-002-2; it goes into the WP-G card.
- WP-C: `light_set{mode, line, percent}` op. WP-C/WP-I: `scan_4x` writes `mosaic.npy` and `mosaic.json`
  (orientation "stage", `M_px_per_um`, objective, `n_tiles`); `goto_xy` event payloads; `scan_box_um`
  and `allowed_box_um` in `summary.json`.
- Lens table: engine data inside guards (fa2bdcd). Q8 only asks where FocusAxis keeps its WD values, so the
  provisional rows can cite their source. Moves to the person-owned envelope at integration.

## 현미경 PC 확인 항목 (총괄에 넘김)

- `docs/operations-spec.md` 10절 Q1–Q21 (실행4, T-006)
- T-003 임시 상수: `MIN_DYNAMIC_RANGE_ADU` 20, `MIN_CURVE_CONTRAST` 0.05, `MAX_SIGMA_DOF` 3.0,
  `IN_FOCUS_DOF` 1.0
- 암전 판정 방식: T-003 은 프레임마다 p99.9 − median < 20 ADU, T-006 명세의 focus_100x preflight 는
  최댓값이 암전 오프셋 (약 102 ADU) 근처. 둘 중 무엇을 쓸지
- 임시 가드 값 (T-015): 큰 XY 이동 문턱 min(렌즈 시야, 1 mm), z_safe 0 µm, F5 이탈 거리 기본값 없음
