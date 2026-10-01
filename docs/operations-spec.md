# 엔진 작업(operation) 명세 (T-006, 초안)

- 작성: AF 실행4 · 개발 (2026-10-01). 소유: 이 파일 하나 (T-006).
- 목적: 벤치 스크립트가 하는 일을 엔진 작업의 `plan → preflight → run → abort` 로 풀어,
  WP-C 이식을 기계적으로 만든다. T-002 (가드, 백엔드 계약) 와 T-004 (UI 명세) 의 입력이다.
- 근거 코드: `scripts/*.py` (main `6ba1bc1`). 운영 기록: `docs/runs/2026-09-30_substrate-scan.md`
  (이하 "9/30 기록"), 같은 이름의 `.yaml`. 계획: `docs/PLAN.md` v0.2.
- **추론** 표시: `C:\agentic_microscope\hardware\focus.py` (FocusAxis) 는 이 PC 에 없다.
  스크립트의 사용 방식에서 짐작한 동작은 "**추론**" 으로 적고, 확인할 질문은 마지막 절에 모은다.

진행 상태 (작성 순서는 매니저 지시, T-006 "v0.2 조정")

| 절 | 작업 | 상태 |
|---|---|---|
| 1 | `lights_off` | 초안 |
| 2 | `status` | 초안 |
| 3 | `scan_4x` | 초안 |
| 4 | `objective_change` (PLAN 2절 F5 7단계 포함) | 작성 예정 (다음) |
| 5 | `hardware_scan` (F2) | 작성 예정 |
| 6 | `sample_map` (F4) | 작성 예정 |
| 7 | `focus_100x` | 작성 예정 |
| 8 | `edge_trace` | 작성 예정 |
| 9 | 보류와 범위 밖: `find_particle_z`, `focus_servo` | 작성 예정 |
| 10 | 현미경 PC 에서 확인할 질문 | 계속 추가 |

## 0. 공통 약속

### 0.1 호출 이름표

"run" 표의 **엔진 호출** 열은 아래 이름을 쓴다. 출처는 `docs/tasks/T-002-engine-contract.md`
본문과 부록 1·2, 그리고 매니저의 범위 조정 (`approach`, Z 후퇴 조건 XY 가드) 이다. T-002 에서 이름이
확정되면 그쪽을 따른다. "가칭" 은 T-002 본문에 기능만 있고 이름이 없는 것이다.

| 구분 | 이름 | 스크립트 원본 |
|---|---|---|
| 백엔드 수명 | `open()`, `close()` | `mm_grab.open_core` (config 로드, AutoShutter 0, 노출, ROI) |
| 백엔드 정보 | `info()` → config, camera, sensor, roi, exposure_ms, pixel_um, objective, intermediate_mag, bit_depth | `open_core` 의 `info`, `core.getImageBitDepth()` |
| 프레임 | `snap()` → `Frame` | `core.snapImage(); core.getImage()` |
| 설정 | `set_exposure(ms)`, `set_roi(size)` | `core.setExposure`, `core.setROI / clearROI` |
| 위치 | `positions()` → x_um, y_um, z_um (+piezo). 실패는 예외가 아니라 필드 | `mm_grab.positions` |
| 속성 | `read_property(dev, prop)`, `set_property(dev, prop, v)` → readback 기록 | `core.getProperty`, `mm_grab.set_and_read` |
| 조명 | `lamp_on()`, `lamp_off()`, `aura_line_on(line, percent)`, `aura_off()`, `all_off()` | `set_and_read(DiaLamp, State, ·)`, `mm_grab.aura_on / aura_off` |
| XY | `xy_move(x, y)` 가칭. 읽기는 `positions()` | `core.setXYPosition; waitForDevice` |
| 렌즈 | `nosepiece_read()` 가칭 → state, label. `nosepiece_set(state)` 가칭 | `getProperty / setProperty("Nosepiece", ...)` |
| PFS | `pfs_read()` 가칭 → enabled, locked, in_range | `isContinuousFocusEnabled / Locked`, `PFS in Range` |
| 가드 Z 축 | `axis = <guard Z axis>(backend, key, allow_motion=, dry_run=)` | `FocusAxis(core, key, allow_motion=, dry_run=)` |
| | `axis.plan(c, half, step)`, `.describe()` | 같음 |
| | `axis.sweep(plan, grab, score=, settle_s=)` → `.points[i].{z_um, z_readback_um, score, diagnostics}`, `.argmax_index`, `.peak_z_um`, `.peak_interior` | 같음 |
| | `axis.move_to(z, allow_ascent_um=)`, `axis.park_at(z)` → 착지 z, `axis.position_um()` | 같음 |
| | `axis.require_pfs_quiet(disable=True)` | 같음 |
| | `axis.approach(target_um, step_um)` | 새 이름 (F5 7단계). 원본에 없음 |
| | `best_z_um(coarse, fine)` → `(z \| None, why)`, `registry_key(label)` | 같음 |
| 가드 XY | XY 박스 검사 (박스 + 1 mm) | `scan_4x.goto_xy` 안의 `box` 검사 |
| | 큰 XY 이동은 Z 후퇴가 readback 으로 확인될 때만 | 새 가드 (F4 클릭 이동, F5 이탈·복귀). 원본에 없음 |
| 순수 함수 | `vollath4`, `parabola_peak`, 4×4 peak, `block_scores` | `mm_grab.vollath4`, `scan_4x.*`, `focus_100x.peak` |

순수 함수(초점 지표, 포물선)는 `focus/` (WP-E, T-003) 소유로 보고, 작업은 import 만 한다.

### 0.2 이벤트와 기록

- 이벤트 종류는 T-002 `events.py` 목록을 쓴다: `planned`, `preflight_ok / preflight_failed`,
  `started`, `progress`, `frame_ready`, `reading`, `finished`, `aborted`, `error`, `position`,
  `light_changed`, `property_set`, `confirm_required`, `log`.
- 기록 폴더는 T-002 대로 `<sample_dir>/<op>_<stamp>/log.jsonl` + `summary.json`.
  샘플이 없는 작업(`status`, `lights_off`)은 T-002 의 기본 기록 위치를 따른다
  (런처의 `outputs/launcher_logs` 에 해당).
- 각 절의 "기록" 항목은 (a) 지금 스크립트가 쓰는 파일과 필드, (b) 엔진 기록에서 어디로 가는지를 적는다.

### 0.3 모든 작업에 공통인 것

| 항목 | 지금 스크립트 | 엔진에서 |
|---|---|---|
| 코어 열기 | 스크립트마다 `open_core()` 로 config 를 다시 로드한다. 로드 시 System/Startup 프리셋 (`LappMainBranch1 State 1`, `mm_grab.py` 머리말) 이 적용되고 노출과 ROI 가 바뀐다 | 엔진이 백엔드를 한 번만 연다 (코어 단일 소유). 작업은 `open()` 을 부르지 않는다 |
| 다른 프로그램 점유 | 런처의 `hardware_users()` 가 프로세스 명령줄로 확인하고 경고만 한다 | 같은 검사를 엔진 시작 시 한 번. 작업 단위가 아니라 엔진 단위 |
| stdout 로그 | 런처가 `run_logged.py` 로 `launcher_<label>_<stamp>.log` 에 복사 | `log` 이벤트로. 파일은 `log.jsonl` 에 함께 |
| Ctrl+C | `KeyboardInterrupt` → 각 스크립트의 `finally` | `abort` 명령. 작업은 프레임과 이동 사이에서 멈추고 가드의 종료 경로를 탄다 |
| 소등 | 스크립트마다 다르다 (각 절의 abort 항목) | 가드의 종료 컨텍스트가 모든 경로에서 `all_off()` + readback (T-002) |

## 1. `lights_off`

원본: `scripts/lights_off.py`. 런처 버튼 "Lights off (Aura + DiaLamp)" (`hw=True`).

**1) 입력 인자**: 없음. 원본은 코어를 `open_core(10.0, 0)` 으로 연다 (노출 10 ms, 전체 센서). 엔진 인자 없음.

**2) plan**: 계산할 것 없음. 보여 줄 문구: "Aura State → 0, DiaLamp State → 0. Nothing moves."

**3) preflight**: 원본에는 없다. 엔진에서는 현재 조명 상태를 읽어 `reading` 으로 남긴다
(`read_property(Aura, State)`, `read_property(DiaLamp, State)`). 읽기가 실패해도 막지 않는다. 소등은 항상 시도한다.

**4) run**

| # | 스크립트 호출 | 엔진 호출 | 비고 |
|---|---|---|---|
| 1 | `open_core(10.0, 0)` | (엔진이 이미 연 백엔드) | 원본은 config 재로드와 노출 변경이 따라온다 |
| 2 | `aura_off(core)` = `set_and_read("Aura", "State", 0)` | `aura_off()` | 마스터 State 만 끈다. 라인(`GREEN 1`)과 세기(`GREEN_Intensity 10`)는 그대로 남는다 |
| 3 | `set_and_read("DiaLamp", "State", 0)` | `lamp_off()` | |
| 4 | `verified` 가 거짓인 항목을 `WARNING` 으로 출력 | 거짓이면 `error` 이벤트, 결과 `finished(ok=False)` | 원본은 그래도 종료 코드 0 |

엔진에서는 2–3 을 `all_off()` 하나로 묶는다. 가드의 종료 경로가 부르는 함수와 같은 것이어야 한다.

**5) abort / finally**: 원본에 `finally` 없음. 엔진의 `lights_off` 는 그 자체가 종료 경로다.

제안: `lights_off` 는 **다른 작업이 실행 중이어도 받는다.** 받으면 실행 중 작업에 `abort` 를 보내고,
그 작업의 종료 경로가 끝난 뒤 `all_off()` 를 한 번 더 확인한다. 지금 런처는 하드웨어 작업이 돌고 있으면
`lights_off` 도 거부한다. 그런데 불이 켜진 채 멈춘 작업이 있을 때가 이 버튼이 가장 필요한 순간이다.

**6) 기록**

| 지금 | 엔진 |
|---|---|
| stdout: `set_and_read` 의 JSON 두 줄 (`device, property, wanted, read, verified`) + 요약 한 줄 | `property_set` 이벤트 두 개 (같은 필드), `light_changed`, `summary.json`: `{aura_state, dialamp_state, verified}` |

**7) 확인 지점**: 없음 (안전한 방향).

**8) 9/30 기록 대응**: 종료 상태 "Aura OFF, DiaLamp OFF (both read back)". 알려진 문제 4번
(`live_focus.py` 가 창을 닫을 때 DiaLamp 를 끄지 않음) 때문에 이 버튼이 생겼다. 엔진에서는
`edge_trace` 와 라이브 뷰의 종료 경로가 소등을 하므로, 이 버튼은 확인과 비상용이 된다.

## 2. `status`

원본: `scripts/change_objective.py --status` (`state()` 함수). 런처 Step 0 "Show objective / Z / PFS".

**1) 입력 인자**: `--status` 하나. 원본은 코어를 `open_core(30.0, 0)` 으로 연다. 엔진 인자 없음.

**2) plan**: 없음. 읽기만 한다.

**3) preflight**: 없음.

**4) run**

| # | 스크립트 호출 | 엔진 호출 | 읽는 값 |
|---|---|---|---|
| 1 | `open_core(30.0, 0)` → `info` 출력 | `info()`, `positions()` | config, camera, autoshutter, exposure_ms, sensor, roi, pixel_um, objective, intermediate_mag, position (x_um, y_um, z_um) |
| 2 | `getProperty("Nosepiece", "State")`, `getProperty("Nosepiece", "Label")` | `nosepiece_read()` | `nosepiece_state`, `nosepiece_label` |
| 3 | `getPosition("ZDrive")` | `positions().z_um` | `z_um` (소수 3자리) |
| 4 | `isContinuousFocusEnabled()`, `isContinuousFocusLocked()` | `pfs_read()` | `pfs_enabled`, `pfs_locked`. 실패하면 `"unreadable: <exc>"` 문자열 |
| 5 | `getProperty("PFS", "PFS in Range")` | `pfs_read()` | `pfs_in_range` (`"In Range"` 또는 `"Out of Range"`). 실패하면 같은 문자열 |
| 6 | (없음) | `read_property(Aura, State)`, `read_property(DiaLamp, State)` | **추가 제안**: 조명 상태. 종료 상태 확인과 상태 표시줄에 필요하다 |
| 7 | (없음) | `info().bit_depth` | **추가 제안**: 카메라 천장. scan_4x 첫 시도의 실패 원인이었다 (3절 8항) |

- Nosepiece 번호: `State` 는 0 부터, `Label` 앞 숫자는 1 부터다. 4x 는 State 0 / `1-Plan Apo LmbdD20 4x`,
  100x Oil 은 State 5 / `6-Plan Apo LmbdD0.13 100x Oil`. UI 는 Label 을 보여 주고 명령은 State 로 보낸다.
- 원본은 "Read only" 라고 하지만, `open_core` 가 config 를 다시 로드하면서 Startup 프리셋, 노출 30 ms,
  ROI 해제를 적용한다. 엔진의 `status` 는 이미 열린 백엔드에서 읽기만 하므로 이 부작용이 없다.

**5) abort / finally**: 없음. 아무것도 켜거나 움직이지 않는다.

**6) 기록**

| 지금 | 엔진 |
|---|---|
| stdout 에 `info` JSON 한 줄과 `state` JSON 한 줄. 파일은 런처 로그뿐 | `reading` 이벤트 하나 (위 표의 필드 전부). 사용자가 명시적으로 실행했을 때만 `status_<stamp>/summary.json` |

제안: 상태 표시줄의 주기적 갱신은 `status` 작업이 아니라 `position` 이벤트로 한다. 그래야 몇 초마다
기록 폴더가 생기지 않는다. 결정은 T-002, T-004 에 맡긴다.

**7) 확인 지점**: 없음.

**8) 9/30 기록 대응**: Step 0. 결과 `Nosepiece 0 = 1-Plan Apo LmbdD20 4x`, ZDrive 62.9 µm,
PFS off / "Out of Range". 실패 사례 없음. ZDrive 62.9 µm 는 Z 창(2800–3200) 밖이다.
이 값을 scan_4x 의 `z_guess` 규칙이 어떻게 다루는지는 3절 3항에 있다.

## 3. `scan_4x`

원본: `scripts/scan_4x.py`. 런처 Step 2 "Start 4x scan" (확인 대화상자 뒤 실행), "Dry run" 체크.

**1) 입력 인자**

| 명령행 | 기본값 | 엔진 인자 이름 | 비고 |
|---|---|---|---|
| `--sample` | (필수) | `sample_id` | `sample.json` 의 `hole` 이 있어야 한다 |
| `--margin` | 500.0 µm | `margin_um` | 구멍 둘레에 더하는 여유 |
| `--overlap` | 0.15 | `overlap` | 타일 겹침 비율 |
| `--exposure` | None (자동) | `exposure_ms` (None = 자동) | 자동 노출은 run 10번 |
| `--aura LINE PERCENT` | GREEN 1 | `aura_line`, `aura_percent` | 퍼밀 변환(`GREEN_Intensity = 10`)은 백엔드 몫 |
| `--z-guess` | None | `z_guess_um` | None 이면 현재 Z 가 2800–3200 안일 때 현재 Z, 밖이면 2960 |
| `--first-half-range` | 160.0 µm | `first_half_um` | 첫 타일 거친 스윕 반폭 |
| `--tile-half-range` | 50.0 µm | `tile_half_um` | 이후 타일 거친 스윕 반폭 |
| `--dry-run` | False | `dry_run` | 계획만 출력. 원본은 첫 스윕 계획 하나만 보여 준다 |
| `--no-preview` | False | (없음) | 미리보기는 UI 몫. 엔진은 항상 `frame_ready` 를 낸다 |

코드 안의 고정값 (엔진에서는 이름 붙은 상수 또는 숨은 인자로 둔다):

| 값 | 원본 위치 | 이름 제안 |
|---|---|---|
| 거친 스텝 10 µm (첫 타일), 6 µm (이후) | `sweep_pair(z_ref, hr, 10.0 if first else 6.0, 12.0, 2.0)` | `coarse_step_first_um`, `coarse_step_um` |
| 고운 스윕 ±12 µm, 2 µm 간격 | 같음 | `fine_half_um`, `fine_step_um` |
| settle 0.1 s (거친), 0.2 s (고운) | `sweep_pair` | `settle_coarse_s`, `settle_fine_s` |
| 블록 6 × 6 | `BLOCKS` | `blocks_per_side` |
| 드롭아웃 판정 ±2 % (스윕 중앙값 밝기 대비) | 타일 루프 | `dropout_frac` |
| 자동 노출: p99.9 를 천장의 50 % 로. 배율은 0.25–4 로 자르고 0.7–1.4 면 멈춤. 최대 6 회, 노출 1–2000 ms, 시작 30 ms | 자동 노출 루프, `open_core(args.exposure or 30.0, 0)` | `auto_exposure_*` |
| XY 이동 후 0.2 s 대기 | `goto_xy` | `xy_settle_s` |
| XY 박스 여유 1000 µm | `box` | 가드 상수 |
| 주차 상한 3200 µm | `axis.park_at(min(z_img, 3200.0))` | Z 창 상한 (가드) |
| 렌즈 라벨 `1-Plan Apo LmbdD20 4x`, 레지스트리 키 `"4x"` | `OBJECTIVE_4X`, `FocusAxis(core, "4x", ...)` | 렌즈 표 (T-002 또는 F2 구성 파일) |

**2) plan** (모션 없이 계산 가능. `planned` 이벤트로 낸다)

- 입력: `sample.json` 의 `hole.centre_um`, `hole.diameter_mm`, `stage_camera_calibration.um_per_px`
  (없으면 1.625), `info().sensor` (또는 ROI).
- `half = diameter_mm × 500 + margin_um`, `fov = min(w, h) × um_per_px`, `pitch = fov × (1 − overlap)`,
  `n = max(1, ceil((2·half − fov) / pitch) + 1)`. 타일 중심은 `(i − (n−1)/2) × pitch` 격자이고, 행마다
  방향을 뒤집는 serpentine 순서다 (`grid()`).
- XY 박스: `centre ± (half + 1000)`.
- 첫 스윕: `axis.plan(z_guess, first_half_um, 10).describe()`. 원본 dry-run 은 여기까지만 보여 준다.
  엔진의 plan 은 이후 타일의 스윕 폭(±50 @6, 고운 ±12 @2)과 "실패하면 첫 타일 폭으로 한 번 넓힘" 규칙도 적는다.
- 검산 값 (WP-C 테스트 벡터로 쓸 수 있다): 9/30 의 `diameter_mm 6.1438`, margin 500, overlap 0.15,
  2400 px × 1.6252 µm 에서 fov 3901, pitch 3315, n = 2 (2 × 2 타일). 9/30 기록과 일치한다.

**3) preflight**

| 확인 | 원본 | 엔진 제안 |
|---|---|---|
| `sample.json` 존재 | 런처 `sample_id(required=True)` 만 본다. 스크립트는 없으면 예외 | `preflight_failed("no sample.json")` |
| `hole` 피팅 있음 | 없음. `hole` 이 null 이면 `TypeError` | `preflight_failed("hole not fitted: run edge_trace")` |
| 피팅이 이번 세션 것인가 | 런처 대화상자의 질문뿐 ("Hole traced in brightfield this session?") | `sample.json` 에는 피팅 시각이 없고 `updated` 만 있다. T-002 `sample.py` 에 `hole.fitted_at` 을 두고, 엔진 시작 이후가 아니면 `confirm_required` (운영 규칙: 세션마다 재추적) |
| 렌즈 라벨 = 4x | 있음. 단 그리드를 출력한 **뒤**에 확인한다 | 맨 앞으로 옮긴다. 아니면 `preflight_failed` |
| PFS | run 의 `require_pfs_quiet(disable=True)` 가 끈다 | 읽어서 `reading` 으로 남긴다. 끄는 것은 run 7번 |
| 현재 Z | `z_guess` 계산에만 쓴다 | 현재 Z 가 창 밖이면 (9/30 시작 시 62.9 µm) 첫 이동이 2960 µm 까지 약 2.9 mm 상승한다. `confirm_required` 로 묻는 것을 제안. 원본은 묻지 않는다 |
| 카메라 비트 깊이 | run 중 `getImageBitDepth()` | preflight 에서 읽어 천장을 정한다. 4095 (12-bit) 여야 9/30 설정과 같다 |
| 다른 작업 실행 중 | 런처 `hardware_users()` | 엔진 단일 소유 (0.3) |

**4) run**

| # | 스크립트 호출 | 엔진 호출 | 비고 |
|---|---|---|---|
| 1 | `open_core(args.exposure or 30.0, 0)` | `set_exposure(exposure_ms or 30)`, `set_roi(0)`, `info()` | |
| 2 | `getProperty("Nosepiece", "Label")` | `nosepiece_read()` | preflight 로 옮긴다 |
| 3 | `FocusAxis(core, "4x", allow_motion=True, dry_run=)` | 가드 Z 축 생성. 원본은 `registry_key` 대신 `"4x"` 고정 | |
| 4 | `axis.position_um()` | 같음 | `z_guess` 계산 |
| 5 | dry-run 이면 `axis.plan(...).describe()` 출력 후 종료 | plan 단계에서 끝. `finished(dry_run=True)` | 기록 폴더를 만들지 않는다 |
| 6 | `out.mkdir`, `getImageBitDepth()` | 기록 폴더 생성, `info().bit_depth` | |
| 7 | `axis.require_pfs_quiet(disable=True)` | 같음 | **추론**: PFS 서보를 끄고 꺼졌는지 읽는다 |
| 8 | `aura_on(core, line, pct)` = DiaLamp State 0 → `{LINE}_Intensity` (퍼밀) → `{LINE} 1` → Aura State 1, 각각 readback | `aura_line_on(line, percent)` | 원본은 `verified=False` 여도 계속한다. 엔진은 멈추는 것을 제안 |
| 9 | `goto_xy(x0, y0)`: 박스 검사 → `setXYPosition` → `waitForDevice` → 0.2 s → `getXYPosition` | XY 박스 가드 → `xy_move(x, y)` → `positions()` | 원본은 XY readback 을 명령값과 비교하지 않는다 |
| 10 | 자동 노출이면 `axis.move_to(min(z_guess, 3200), allow_ascent_um=max(0, z_guess − z) + 0.5)` 후 최대 6 회 `snap` → p99.9 → `setExposure` | `axis.move_to(...)`, `snap()`, `set_exposure()` | 원본은 p99.9 를 출력만 한다 |
| 11 | 타일마다 `goto_xy(x, y)` | 9번과 같음 | `progress(tile k/n)` |
| 12 | `sweep_pair`: `axis.sweep(axis.plan(z_ref, hr, step), grab, score=, settle_s=0.1)`. `coarse.peak_interior` 이면 `axis.sweep(axis.plan(coarse.peak_z_um, 12, 2), grab, score=, settle_s=0.2)` | 같음 | `grab` = `snap()`. 원본은 미리보기용으로 `axis.position_um()`, `vollath4` 도 부른다. 엔진은 점마다 `frame_ready` + `progress` |
| 13 | `best_z_um(coarse, fine)` | 같음 | 결과 `(zf, why)` |
| 14 | 첫 타일이 아니고 `zf` 가 None 이면 첫 타일 폭(±160 @10)으로 `sweep_pair` 한 번 더 | 같음 | |
| 15 | 드롭아웃 필터: 거친+고운 점의 `diagnostics.mean` 중앙값에서 2 % 넘게 벗어난 점을 뺀다. 빠진 점이 있고 고운 스윕이 있으면 남은 고운 점(3개 이상)으로 `parabola_peak` 다시 | 순수 함수 (`focus/`) | `why` 가 `"fine pass without light-dropout frames at [...]"` 로 바뀐다 |
| 16 | 블록 36 개마다 `parabola_peak(zs, blocks[b])` | 순수 함수 | `block_z_um` |
| 17 | `axis.park_at(min(zf or z_ref, 3200))` | 같음 | 착지 z 가 `z_image_um` |
| 18 | `grab()` → `tile_rXcY.npy` 저장, `scan.json` 저장 | `snap()`, 기록 | 타일마다 저장한다. 중단돼도 앞 타일은 남는다 |
| 19 | `zf` 가 있으면 `z_ref = zf`, `first = False` | 같음 | 실패한 타일은 다음 타일의 기준을 바꾸지 않는다 |
| 20 | `rec["finished"]` | `finished` | |

`score` 함수 (거친·고운 공통): `sharp = vollath4`, `blocks = block_scores` (6×6 vollath4), `mean`, `p999`,
`saturated_frac = mean(frame ≥ ceiling)`. 판정 지표는 Vollath F4 하나다.

**5) abort / finally**

| 순서 | 원본 `finally` | 엔진 제안 |
|---|---|---|
| 1 | `lights` 가 비어 있지 않으면 `aura_off()` (Aura State 0 만) | 가드 종료 경로의 `all_off()` (Aura + DiaLamp, readback) |
| 2 | `rec["z_end_um"] = axis.position_um()` | `positions()` 전부를 종료 상태로 |
| 3 | `scan.json` 저장 | `summary.json` + `aborted` 또는 `finished` |
| Z | 그 자리에 둔다 (후퇴하지 않음) | 같게 둔다. 4x 는 작동 거리 20 mm 라서 후퇴가 안전에 필요하지 않다 |
| XY | 그 자리 | 그 자리 |

원본의 빈틈 (이식할 때 고칠 것):
- `aura_on()` 이 네 번째 쓰기 전에 예외로 멈추면 `lights` 가 빈 리스트라서 `finally` 가 소등하지 않는다.
  엔진은 조명을 켜기 **전에** 종료 컨텍스트에 들어가야 한다.
- `aura_on` 의 `verified=False` 를 확인하지 않는다.
- XY readback 을 명령값과 비교하지 않는다. 9/30 에 사람이 실행 중 재물대를 움직인 일이 있다 (기록 4절 3항).
  허용 오차는 10절 질문.
- Ctrl+C 가 `axis.sweep` 의 이동 중에 오면 어떻게 되는지 모른다. **추론**: `KeyboardInterrupt` 가 그대로
  올라와 `finally` 로 간다. 엔진은 이동과 이동 사이에서만 abort 를 확인한다.

**6) 기록**

지금: `<sample>/scan4x_<stamp>/`

| 파일 | 내용 |
|---|---|
| `scan.json` | `sample, started, header (=info), objective, um_per_px, fov_um, pitch_um, grid_n, hole, margin_um, coordinates, camera_ceiling_adu, light (aura_on 기록 4개), exposure_ms, tiles[], finished, light_off, z_end_um` |
| `scan.json` 의 `tiles[]` | `name, row, col, x_cmd_um, y_cmd_um, x_um, y_um, z_focus_um, focus_note, z_image_um, block_z_um[36], blocks_per_side, dropout_z_um[], curve[{z, sharp, mean, sat}], frame_mean, frame_max, seconds` |
| `tile_r{r}c{c}.npy` | 초점 위치에서 찍은 uint16 프레임 |
| `launcher_scan4x_<stamp>.log` (샘플 폴더) | stdout |

`scripts/plot_scan.py` 가 읽는 필드: `um_per_px`, `fov_um`, `hole`, `tiles[].{x_um, y_um, name, z_focus_um,
blocks_per_side, block_z_um}`, 그리고 상위 폴더 `sample.json` 의 `stage_camera_calibration`.

엔진 기록으로의 대응:

| 지금 | 엔진 |
|---|---|
| `scan.json` 상위 필드 | `summary.json` 에 같은 이름으로. plot_scan 호환을 위해 이름을 바꾸지 않는다 |
| `tiles[]` | `summary.json` 의 `tiles[]` (같은 필드). 타일마다 `reading` 이벤트로도 낸다 |
| `curve[]` | `log.jsonl` 의 `progress` 이벤트 (점마다 명령 `z_um`, `z_readback_um`, `score`, `diagnostics`). `summary.json` 에는 지금처럼 요약 곡선 |
| `light`, `light_off` | `property_set` 이벤트와 종료 상태 |
| `header` | `started` 이벤트의 시작 상태 (`info()` + `positions()`) |
| `.npy` | 같은 폴더에 그대로 |

결정이 필요한 것 (매니저에게):
- 폴더 이름: 지금은 `scan4x_<stamp>` 이고, T-002 규칙대로면 `scan_4x_<stamp>` 가 된다. 런처 `plot()` 과
  `plot_scan.py` 는 `scan4x_*/scan.json` 을 찾는다. 제안: 작업 이름은 `scan_4x` 로 두되 폴더는 `scan4x_<stamp>`
  를 유지하고, `summary.json` 과 같은 내용의 `scan.json` 을 함께 쓴다. 이식이 끝나면 하나로 합친다.
- `z_focus_um` 은 고전 지표(Vollath)와 엔코더 readback 에서 나온 값이다. 모델 값이 아니므로
  `grade: model` 표시 대상이 아니다.

**7) 확인 지점** (`confirm_required`)

| 지점 | 원본 | 엔진 |
|---|---|---|
| 시작 전 | 런처 대화상자: "moves the XY stage and ZDrive and switches on Aura GREEN 1 %", "Nosepiece on 4x?", "Hole traced in brightfield this session?" | `confirm_required("start scan_4x", plan)` 한 번. 렌즈 확인은 preflight 가 대신한다 |
| 피팅이 이번 세션 것이 아님 | 위 대화상자의 질문 | `confirm_required("hole fit is from <time>; re-trace?")` |
| 첫 이동이 Z 창 밖에서 들어옴 | 없음 | `confirm_required("ZDrive <z> -> <z_guess>")` (제안) |
| 실행 중 | 없음 | 없음 |

**8) 9/30 기록 대응**: Step 2.

| 사례 | 무엇이 있었나 | 명세에 반영된 곳 |
|---|---|---|
| 첫 시도 `scan4x_20260930-194928/` 가 빈 폴더 | 자동 노출이 16-bit 천장을 목표로 해 12-bit 카메라에서 멈췄다. `getImageBitDepth` 로 고쳤다 | preflight 의 비트 깊이 읽기. mock 테스트는 12-bit 로 |
| 광 드롭아웃 | 두 번째 실행 r1c1 의 고운 스윕에서 −23 % 프레임 두 장이 2.7 배 선명하게 읽혀 피크가 됐다. 3053.99 → 3051.2 µm | run 15번 드롭아웃 필터, `dropout_z_um` |
| 사람이 실행 중 재물대를 움직임 | 기록 사이 XY 가 바뀌었다 | XY readback 비교 (5항 빈틈), 시작 위치는 `started` 이벤트 |
| 노출 | 자동으로 994 ms (p99.9 2043 ADU) | 자동 노출 고정값 |
| 첫 타일 기준 Z | 명시야로 맞춘 현재 Z 3012 µm 근처에서 ±160 | `z_guess` 규칙 |
| 반복성 | 실행 간 0.4–3.4 µm (4x 피사계 심도 약 14 µm) | mock 테스트 허용 오차의 근거 |

결과 (serpentine 순서): r0c0 (6368.3, −1086.0), r0c1 (9683.7, −1086.0), r1c1 (9683.6, 2229.2),
r1c0 (6368.3, 2229.5). 초점 평면: 구멍 중심 3048.7 µm, 기울기 x −1.66, y −3.62 µm/mm.

## 4–9. (작성 예정)

`objective_change` (F5), `hardware_scan`, `sample_map`, `focus_100x`, `edge_trace`, 보류와 범위 밖.
같은 브랜치에 이어서 커밋한다.

## 10. 현미경 PC 에서 확인할 질문

FocusAxis (`C:\agentic_microscope\hardware\focus.py`) 를 읽거나 벤치에서 한 번 돌려 보면 답이 나온다.

| # | 질문 | 왜 필요한가 |
|---|---|---|
| Q1 | `sweep(plan, ...)` 은 현재 Z 가 계획 시작점보다 위일 때 어떻게 시작점으로 가는가 (내려간 뒤 올라오는가, 거부하는가) | "상향만" 가드와 `allow_ascent_um` 의 정확한 뜻 |
| Q2 | readback 허용 오차는 얼마인가. 9/30 에 3037.0 명령 / 3036.0 읽음에서 멈췄다 | T-002 가드의 기본값 |
| Q3 | `park_at(z)` 의 접근 방향과 반환값 (착지 readback 인가, 명령값인가) | `z_image_um` 의 뜻 |
| Q4 | `best_z_um(coarse, fine)` 의 규칙과 `why` 문자열 목록 | 이식과 mock 테스트의 기대값 |
| Q5 | `require_pfs_quiet(disable=True)` 가 읽고 쓰는 것 | preflight 와 run 의 경계 |
| Q6 | `dry_run=True` 일 때 `move_to`, `sweep` 은 무엇을 하는가 | 엔진 `dry_run` 의 정의 |
| Q7 | 이동 중 `KeyboardInterrupt` 가 오면 ZDrive 는 멈추는가, 명령한 곳까지 가는가 | abort 시 Z 위치 기록 |
| Q8 | 레지스트리 키(`"4x"`, `"100x-Oil"`)별 상한과 작동 거리 값은 어디에 있는가 | 렌즈 표의 소유 (T-002 또는 F2 구성 파일) |
| Q9 | `open_core` 의 Startup 프리셋 (`LappMainBranch1 State 1`) 은 눈에 보이는 변화가 있는가 | 엔진이 config 를 한 번만 로드해도 되는지 |
| Q10 | Aura 마스터 State 0 만으로 모든 라인이 꺼지는가 | `all_off()` 의 정의 |
| Q11 | XYStage readback 의 정상 오차 범위 | XY readback 비교 허용 오차 |
