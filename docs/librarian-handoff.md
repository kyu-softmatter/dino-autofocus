# librarian 인계 목록: dino-autofocus 의 벤치 숫자와 사실 (질문 카드)

## 1. 목적과 기준

- 목적: dino-autofocus 가 soft-matter-agents 의 `microscope_agent` 로 합쳐질 때 (약 3주 뒤) librarian 이 받아야 할
  모든 물리·벤치 숫자와 사실을 한곳에 모은다. 각 줄은 사용자에게 묻는 카드 하나다: **사람이 쓰거나 잰 값인가, 언제 어떻게.**
- soft-matter-agents 규칙 (plan.md §10.3): 다른 저장소의 숫자는 librarian 을 거쳐 항목으로만, 최대 E3. 안전 한계는 숫자로 건너가지 않는다
  (사람이 `envelope/safety.json` 에 직접 쓴다). 모델이 낸 숫자는 E6 이고 카드에 들어가지 않는다.
- 작성일: 2026-10-02. 읽기 전용 조사. 두 저장소 모두 아무것도 바꾸지 않았다.
- 기준 커밋:
  - dino-autofocus `025080f86baadb5b76c44ddcf47ca798454a6519` (main HEAD). 작업 트리에 커밋 안 된 변경이 있다
    (`engine/backend.py` 등, Frame 에 camera 라벨 추가; 숫자는 바뀌지 않음). **아래의 file:line 은 모두 HEAD `025080f` 기준**이다
    (`git show HEAD:<path>`). backend.py 는 130행 뒤로, mm_real.py 는 383행 뒤로 작업 트리에서 1–3행 밀려 있다.
  - soft-matter-agents `baf6f1e5b7e2012ab6c6d1e1d13d643f7b98d083` (HEAD, 작업 트리 깨끗함). librarian 저장소는
    `librarian_agent/kb/entries/*.json` 291개. microscope_agent 의 사본 `envelope/snapshot.json` 은 109개 항목
    (`kb_version kbv-4b981dc870d3`, built_from_commit `9f92387`). 아래 "있음" 칸의 `(S)` 는 snapshot 에도 있음, `(KB)` 는 저장소에만 있음.
- "이미 있는가" 칸: `있음` 같은 값, `일부` 일부만 있음, `충돌` 값이나 출처가 다름, `없음`. 항목 id 와 등급을 적었다.
- `[envelope]` 표시: 안전 한계·가드 값. librarian 에 숫자로 보내지 않는다 (3절). 카드는 "누가 정했나" 를 묻기 위해 남긴다.
- 출처 약어: `guards` = src/dino_autofocus/engine/guards.py, `backend` = engine/backend.py, `mm_real`/`mm_demo`/`mm_demo_core`/`mock`/`mock_world` = engine/backends/*.py,
  `ops/*` = engine/operations/*.py, `chk` = docs/microscope-pc-checklist.md, `run930y` = docs/runs/2026-09-30_substrate-scan.yaml,
  `run930m` = docs/runs/2026-09-30_substrate-scan.md, `bp1002` = docs/runs/2026-10-02_bench-properties.json,
  `cfg1` = configs/micromanager/single_cam_red_noDMD_nocom10.cfg, `cfg2` = configs/micromanager/DMD_dualcam_LUNF.cfg,
  `BL` = BACKLOG.md (2026-10-02 부터 내부 노트 `dino-autofocus-internal/tasks/BACKLOG.md`). SMA 쪽: `safety` = microscope_agent/envelope/safety.json, `devices.v0` = librarian_agent/kb/staging/devices.v0.json,
  `rulings` = microscope_agent/rulings.jsonl.

## 2. 질문 카드

### 2.1 대물렌즈와 작동 거리

| id | 항목 | 값 + 단위 | dino-autofocus 위치 | 기록된 출처 | soft-matter-agents 에 있나 | 사용자에게 물을 것 |
|---|---|---|---|---|---|---|
| L-001 | Nosepiece State → Label (벤치에서 읽은 6개) | 0 `1-Plan Apo LmbdD20 4x`, 1 `2-Plan Apo LmbdD4 10x`, 2 `3-Plan Apo LmbdD0.8 20x`, 3 `4-Apo LmbdS 40x WI`, 4 `5-Plan Apo LmbdD0.15 60x Oil`, 5 `6-Plan Apo LmbdD0.13 100x Oil` | bp1002:179; cfg1:178-183 | 장치 읽기 2026-10-02 (라벨 문자열은 cfg 가 정함) | 일부: `nosepiece_objective_assignment` E3 (S, 부품 번호로), `stand_state_read_20260924_20x_in_place` E1 (KB, 위치 2 라벨만) | 6개 라벨이 각 위치의 실제 렌즈와 맞는지 사람이 렌즈를 보고 확인했나요? (9/17 부품 번호 확인과 같은 것인가요?) |
| L-002 | 4x 자유 작동 거리 | 20000 um | guards:67; mm_real:98; configs/ti2_4x.yaml:23; run930y:22 | 카탈로그 (guards:63 은 "2026-09-30 run" 이라고 적음) | 있음: `objective_mrd70040` E3 (S), 20 mm | 9/30 기록의 20 mm 는 카탈로그를 옮긴 것인가요, 벤치에서 잰 것인가요? |
| L-003 | 10x 자유 작동 거리 | 4000 um | guards:67; mm_real:98; ti2_10x.yaml:23; chk:155 | 카탈로그, librarian E3 를 2026-10-02 파일로 직접 읽음 (chk:149-150) | 있음: `objective_mrd70170` E3 (S) | 벤치에서 잰 적이 없으면 새로 넘길 것 없음. 맞나요? |
| L-004 | 20x 자유 작동 거리 | 800 um | guards:67; mm_real:98; ti2_20x.yaml:23; chk:156 | 카탈로그 (위와 같음) | 있음: `objective_mrd70270` E3 (S) | 위와 같음 |
| L-005 | 40x WI 자유 작동 거리 | 170 um (0.17 mm) | guards:64-67; mm_real:97-98; mm_demo:80; chk:157; 커밋 d239448 "(user)" | 사용자 값 2026-10-02. 근거로 적힌 것: "collar at 0.17; catalog range 0.16-0.20 mm, value at that collar not in the catalog" | **충돌**: `objective_mrd77400` E3 (S) 은 0.16–0.2 mm 범위, `devices.v0` 의 wd_mm 은 null, gap `objective_40x_wd_at_170um` 열림. `safety:49-65` `objective_clearance_min` 은 범위면 가까운 끝 0.16 mm 를 쓴다 | 0.17 mm 는 작동 거리를 잰 값인가요, 아니면 칼라 눈금 0.17 mm (커버슬립 두께 170 um) 를 작동 거리로 옮긴 것인가요? 쟀다면 날짜와 방법 |
| L-006 | 60x Oil 자유 작동 거리 | 150 um | guards:67; mm_real:98; ti2_60x.yaml:23; chk:158 | 카탈로그 | 있음: `objective_mrd71670` E3 (S) | 벤치 측정 없음이 맞나요? |
| L-007 | 100x Oil 자유 작동 거리 | 130 um | guards:67; mm_real:98; ti2_100x.yaml:23; run930y:22; run930m:134 | 카탈로그 (9/30 기록에도 설정값으로) | 있음: `objective_mrd71970` E3 (S). 같은 숫자가 `safety:66-77` `objective_clearance_absolute_min` 130 um, confirmation physical "Approach test on the stage" (2026-09-20) | 9/30 기록의 130 um 는 카탈로그인가요? safety.json 의 접근 시험과 같은 측정인가요? |
| L-008 | 렌즈별 NA, 배율, 침지 | 4x 0.2 air, 10x 0.45 air, 20x 0.8 air, 40x 1.25 water, 60x 1.42 oil, 100x 1.45 oil | configs/ti2_*.yaml:1,19-21 | 카탈로그 (yaml 머리말이 librarian 항목을 출처로 적음) | 있음: `objective_mrd70040`, `_mrd70170`, `_mrd70270`, `_mrd77400`, `_mrd71670`, `_mrd71970` E3 (S) | 새로 넘길 것 없음. 확인만 |
| L-009 | 커버슬립 두께 | 170 um (#1.5) | ti2_*.yaml:3,45; mock_world:239 | 실험실 관행 | 있음: `coverslip_thickness_in_use` E3 (S) | 같은 값. 확인만 |
| L-010 | 40x WI 보정 링 재확인 | 0.17 mm 에 그대로 | chk:178-181 | 사용자 확인 2026-10-02 | 있음: `objective_40x_collar_setting` E3 (S, 2026-09-22 읽기) | 2026-10-02 재확인을 새 관찰 (같은 사람, 다른 날) 로 librarian 에 넣을까요? 눈으로 본 것인가요? |
| L-011 | 침지 매질 굴절률 | 오일 1.518, 물 1.333, 유리 1.515, 시료 1.33 | ti2_*.yaml:21,40-44 | 설계값 (측정 아님) | 일부: `water_refractive_index_*` E3 (S). 오일 항목 없음 | 오일 굴절률은 오일 병의 표기에서 온 값인가요? (병/로트를 알려 주면 spec 항목 후보) |
| L-012 | Nosepiece 위치 → 렌즈 키 | 0 4x, 1 10x, 2 20x, 3 40x-WI, 4 60x-Oil, 5 100x-Oil (0 부터) | ops/objective_change.py:74-76 | configs 머리말에서 | 있음: `nosepiece_position_indexing`, `nosepiece_objective_assignment` E3 (S) | 확인만 |

### 2.2 재물대·Z·XY 한계와 방향

| id | 항목 | 값 + 단위 | dino-autofocus 위치 | 기록된 출처 | soft-matter-agents 에 있나 | 사용자에게 물을 것 |
|---|---|---|---|---|---|---|
| L-013 | ZDrive 방향 | 커질수록 시료 쪽, 0 = 완전 후퇴 | backend:6; run930y:3; run930m:133 ("measured 2026-09-05") | 측정 2026-09-05 (prior project) | 있음: `z_retract_direction_is_measured` E3 (S). plan.md:1506 은 같은 2026-09-05 측정의 두 기록이라 등급을 올리지 않았다고 적음 | 2026-09-05 뒤에 이 방향을 다시 잰 적이 있나요? (있으면 E1 후보) |
| L-014 | [envelope] 시료 Z 창 | 2800–3200 um | guards:60; run930y:21; run930m:134 | 코드 주석은 "measured window of the 2026-09-30 bench", 실제로는 스크립트 상수 `SAMPLE_Z_WINDOW_UM` | 없음 (safety.json 에 ZDrive 위치 키 없음, docs/integration-sma.md:13) | 누가 정한 창인가요? 어떤 시료에서 잰 것인가요, 정책인가요? (envelope 에 사람이 쓸 값) |
| L-015 | [envelope] 후퇴 높이 / 복귀 높이 | z_safe 0 um / 복귀 2800 um | guards:61,71-72; run930y:109 | unmeasured provisional (chk:63, Q20) | 없음 | 0 um 후퇴와 0→2800 한 번 이동은 사람이 정한 절차인가요? |
| L-016 | [envelope] "Z 후퇴됨" 판정 상한 | 1 um (z_safe + 1) | guards:73 | provisional | 없음 | envelope 값으로 정해 줄 수 있나요? |
| L-017 | [envelope] 스윕 천장 비율 | centre + 0.4 × 자유 작동 거리, 최대 3200 | guards:10-11,62; run930m:101-102 | prior project 스크립트 규칙 | 없음 (`rulings:23` 이 prior 의 free_working_distance_um 를 drop) | 0.4 는 누가 정한 비율인가요? |
| L-018 | [envelope] 단계 접근 걸음 | 모든 렌즈 10 um (100x Oil 은 WD 의 약 1/13) | guards:124-133; chk:65 | provisional, Q13 미측정 | 없음 | Q13 을 쟀나요? 아니면 envelope 에 직접 쓸 값인가요? |
| L-019 | [envelope] Z 후퇴가 필요한 XY 이동 길이 | 4x 10000, 10x 1000, 20x 777, 40x-WI 390, 60x-Oil 260, 100x-Oil 156 um; 모르는 렌즈 0 | guards:119-135 | provisional, 시야 (2400 px × 픽셀) 에서 계산, Q20 미측정 | 없음 | Q20 (오일 막) 을 쟀나요? 이 표는 envelope 에 사람이 쓸 값인가요? |
| L-020 | [envelope] XY 상자 여유 | 1000 um | guards:69 | 매니저 임시값 | 없음 | 정책값으로 남길까요? |
| L-021 | [envelope] 읽기 허용 오차 | Z 0.25 um, XY 5.0 um. 장치 설정: ZDrive Tolerance `0.000um`, XYStage Tolerance `0.000um` | guards:107-108; bp1002:59,128 | 임시값 (Q2). 장치 값은 2026-10-02 읽기 | 없음 | 0.25 / 5 um 는 누가 정했나요? 장치 Tolerance 읽기는 librarian 사실 항목으로 넘길까요? |
| L-022 | [envelope] F5 Y 이탈 | +Y, 15000 um | guards:74-75; docs/PLAN.md:22,302-303; docs/operations-spec.md:412 | 사용자 (PLAN v1.3, 15–20 mm 중 짧은 쪽), provisional | 없음 | +Y 15 mm 는 envelope 정책값인가요? 2026-10-02 한 번 실행 (L-026) 은 측정 기록으로 넘길까요? |
| L-023 | 재물대 Y 이동 범위 하한 | ≥ 20498.8 um | chk:173; BL:56-57 | 측정 2026-10-02 (+Y 15 mm 이동 뒤 읽기) | 없음 (chk:145 "librarian 저장소에도 값이 없다") | 이 읽기를 "Y 가 적어도 여기까지 간다" 는 관찰로 넘길까요? 한계로는 쓰지 않음 (`rulings:71`: 이동 범위를 한계로 쓰면 안전 한계) |
| L-024 | 재물대 X/Y 한계를 속성으로 읽을 수 있나 | 읽을 수 없음 (XYStage·ZDrive 에 Speed, Tolerance, Invert/Transpose 만) | chk:145; BL:57; mm_real:111,368 | 장치 읽기 2026-10-02 | 없음 | 사실 항목으로 넘길까요? 실제 한계는 Ti2 Control 이나 손으로 재야 하나요? |
| L-025 | 이동 속도 설정 | XYStage 25.00 mm/sec (허용 0.25–51.00), ZDrive 2.50 mm/sec (허용 0.50–2.50) | bp1002:41,110; chk:174 | 장치 읽기 2026-10-02 | 없음 | 이 속도는 누가 설정했나요 (Ti2 Control, 기본값)? |
| L-026 | F5 이탈 한 번의 결과 | 이전 X −5134.4 Y 5498.9 Z 483.62 → 이후 X −5134.6 Y 20498.8 Z −0.08 um; XY 읽기 5 um 안; 30 s 안 (25 mm/s) | chk:163-175 | 측정 2026-10-02, 일회용 스크립트가 core 직접 호출 | 없음 | 이 이동을 실제로 보셨나요? librarian 관찰 항목 (XY 읽기 오차, Z 0 명령 → −0.08) 으로 넘길까요? |
| L-027 | [envelope] XY 이동 대기 시간 | 30 s | mm_real:99 | provisional | 없음 | 가장 먼 이동 시간을 쟀나요? |
| L-028 | 영상과 재물대의 방향 | 영상이 재물대에 대해 뒤집힘: +x 재물대 → +열, 열은 −x, 행은 +y 쪽. XYStage Invert-X/Y `No`, TransposeMirrorX/Y `0`; 카메라 Transpose 전부 `0` | run930m:54-56; mock_world:14-16; mosaic.py:6-17; bp1002:88,147,1629 | 측정 2026-09-30 (edge tracker 보정) + 장치 읽기 2026-10-02 | 없음 | librarian 사실 항목 후보. 9/30 보정 한 번이 근거라는 것이 맞나요? |
| L-029 | Core 역할 장치 | Core.Focus 비어 있음 (`getFocusDevice()` = ""), Core.AutoFocus `PFS`, Core.XYStage `XYStage` | bp1002:2371-2373; chk:127-128,143; BL:58-59 | 장치 읽기 2026-10-02 | 일부: `mm_label_zdrive_is_the_focus_axis` E3 (S, prior project cfg 에서 ZDrive 가 초점 축) | Core.Focus 가 빈 것은 새 사실. 넘길까요? |
| L-030 | 시료 크기와 24 mm 변 | 보통 24 mm × 50 mm; 24 mm 변의 방향 미측정 | docs/PLAN.md:83,121; mock_world:236 | 사용자 확인 필요로 적힘 | 없음 | 24 × 50 mm 는 사용자가 말한 값인가요? 시료 종류 (슬라이드 부품 번호) 는? |

### 2.3 보정 (픽셀 크기, 4x M, 동초점 오프셋)

| id | 항목 | 값 + 단위 | dino-autofocus 위치 | 기록된 출처 | soft-matter-agents 에 있나 | 사용자에게 물을 것 |
|---|---|---|---|---|---|---|
| L-031 | 렌즈별 픽셀 크기 (1x 중간 배율, 1x1 binning) | 4x 1.625, 10x 0.65, 20x 0.32373, 40x 0.1625, 60x 0.10833, 100x 0.065 um/px | cfg1:274-308; ti2_*.yaml:7; mm_real:96 (0과 5만) | cfg1:294-296 주석: "Only 20x is a measurement. The other five are exactly 6.5/M" | **값은 있음, 출처 충돌**: `pixel_size_*_zoom_1x` E2 (S) 는 여섯 개 모두 "measured by the operator" (calibration `cal-pixel-size-20260919`). `*_computed` E4 (KB) 도 있음 | 2026-09-19 보정에서 여섯 렌즈를 모두 쟀나요, 20x 만 쟀나요? (cfg 주석과 librarian 이 다름) |
| L-032 | 4x 재물대–카메라 보정 | 1.62524 um/px, 0.117 deg, `M_px_per_um = [[0.61602, 0.00236], [0.00126, -0.61456]]` | run930y:51-55; run930m:53; mosaic.py:47-48; ops/scan_4x.py:107-108; ops/edge_trace.py:90-95; mock_world:163-165 | 측정 2026-09-30 (edge tracker, +x/+y 이동과 위상 상관) | 없음 (librarian 에는 1.625 E2 만; 차이 0.015 %) | 이 보정을 9/30 에 직접 돌렸나요? librarian 에 E2 와 별개의 측정으로 넘길까요? |
| L-033 | 동초점 오프셋 4x → 100x Oil | ≈ −60 um (2026-09-30, 시료 하나). 실험실 2026-09-07 메모는 약 −100 um | ops/focus_100x.py:67; run930y:123,155; run930m:21,154; docs/operations-spec.md:790; chk:109 | 측정 1회, provisional | 없음 (`parfocal` 검색 0건) | −60 um 는 9/30 의 두 초점 z 차이 (3048.7 vs 2989.4) 맞나요? 2026-09-07 메모는 누가 쓴 것인가요? |
| L-034 | 중간 배율 | `1.0x` (읽기 전용 속성, 허용 1.0x/1.5x). 픽셀 프리셋은 1x 가정 | bp1002:487; cfg1:281-285 | 장치 읽기 2026-10-02 | 있음: `intermediate_magnification_is_not_a_state_device` E1 (KB); devices.v0 값 1x/1.5x | 확인만 |
| L-035 | 카메라 화소 간격과 센서 | 6.5 um, 2400 × 2400 | mock_world:63; ti2_*.yaml:26; bp1002:1699 | 데이터시트 + 장치 읽기 | 있음: `camera_sensor_geometry` E3 (S) | 확인만 |
| L-036 | 20x 실제 배율 | 20.0785 (= 6.5 / 0.32373) | ti2_20x.yaml:20; mock_world:132 | 계산 (픽셀 크기에서 역산) | 없음, 그리고 devices.v0 는 숫자 배율 칸을 일부러 두지 않음 ("prior project's 20.078x") | 보내지 않는 것을 권고 (3절). 동의하나요? |
| L-037 | 4x 초점 반복성 | 두 번 스캔 사이 0.4–3.4 um, 4x 초점 심도 약 14 um 대비 | run930y:101; run930m:84 | 측정 2026-09-30 | 없음 | librarian 관찰 항목으로 넘길까요? |

### 2.4 광원과 광경로 (Aura 라인, LApp Branch1, CSUW1-Port)

| id | 항목 | 값 + 단위 | dino-autofocus 위치 | 기록된 출처 | soft-matter-agents 에 있나 | 사용자에게 물을 것 |
|---|---|---|---|---|---|---|
| L-038 | Aura 장치와 라인 | `Aura III 5-NII-WA`, COM7, s/n 30859, fw 3.14.7; 라인 UV, CYAN, GREEN, RED, NIR (on/off 0–1, `<LINE>_Intensity` 0–1000). VIOLET 없음 | bp1002:1718-1873; backend:266-269; cfg1:34-36; chk:141 | 장치 읽기 2026-10-02 (cfg 머리말은 2026-09-03) | 있음: `aura_reports_five_named_lines` E1 (KB), `mm_label_aura_is_the_aura_iii` E3 (S), `aura_green_intensity_runs_to_1000` E1 (KB) | 같은 값. 확인만 |
| L-039 | 세기 단위 | per-mille: 1 % → `GREEN_Intensity 10` | backend:11-12; run930y:45-47; mm_real:569 | 9/30 설정 | 있음: `light_engine_line_intensity_is_per_mille` E3 (S) | 확인만 |
| L-040 | 벤치에서 쓴 라인 | GREEN 만 (9/30: GREEN 1 %, DiaLamp 0 → GREEN_Intensity 10 → GREEN 1 → State 1) | mm_real:94; mm_demo:76; mock:61; backend:266-268; run930y:44-49 | 9/30 사용 | 일부: `particles_show_on_the_green_605_path` E2 (S) | 다른 라인 (UV, CYAN, RED, NIR) 을 켜 본 적이 있나요? |
| L-041 | Aura State 0 이면 모든 라인 꺼짐 (Q10) | 예 | chk:183-188 | 사용자 답 2026-10-02 | 있음: `aura_master_state_0_keeps_green_dark` E1 (KB), `light_engine_master_state_gates_every_line` E3 (S) | 눈으로 본 것인가요, 프레임으로 본 것인가요? GREEN 외 라인도 확인했나요? |
| L-042 | LightEngine (다른 Lumencor) | `Spectra III 8-NII-XS`, COM3, s/n 28145, fw 3.5.4; 라인 VIOLET BLUE CYAN TEAL GREEN YELLOW RED NIR. cfg 가 Core.Shutter = LightEngine, AutoShutter 1 로 설정 | bp1002:565-742; cfg1:32-33,170-172; chk:124,142 | 장치 읽기 2026-10-02 | 있음: `mm_label_lightengine_is_the_spectra_iii` E3 (S), `single_cam_red_config_arms_autoshutter_on_the_lightengine` E1 (KB). gap `light_engine_channel_sets` 열림 (라인 이름 목록은 이 읽기가 준다; 파장은 아님) | 장치에서 읽은 8개 이름을 gap `light_engine_channel_sets` 의 일부 답으로 넘길까요? |
| L-043 | LappMainBranch1 | State 1 = `mirror_in` = Aura 경로 켜짐, **50/50 거울**; State 0 = `mirror_out`. cfg Startup 이 State 1 | chk:194-196,203-204; cfg1:212-213,261; bp1002:501-508 | 사용자 메모 2026-10-02 (50/50 은 새 사실) | 일부: `lapp_state_1_brings_the_aura_to_the_sample` E3 (KB), `single_cam_red_config_startup_puts_the_lapp_mirror_in` E1 (KB). gap `lapp_branch_assignment` 열림 | 50/50 거울은 직접 보거나 문서로 확인한 것인가요, 기억인가요? |
| L-044 | CSUW1-Port 상태 번호 | 0 `blue_only` (100/0 거울), 1 `blue_red` (561 nm dichroic, 파장으로 나눔), 2 `red_only` (거울 없음) | chk:197-202,207; BL:60-63; cfg2:204-207,257,263 | 사용자 메모 2026-10-02 + cfg2 Label 줄 (cfg2:257 은 State 1 을 "operator-stated 2026-09-05") | **일부 (gap 을 채움)**: `csuw1_port_slots` E3 (S) 는 세 슬롯 내용만, "which physical slot is at which position number is not known". devices.v0 gap "csuw1_port slot order" 열림, "One acquisition settles it" | 이 번호는 획득 (빛을 켜고 세 상태에서 어느 카메라에 신호가 오는지) 으로 확인했나요, 메모와 cfg 라벨뿐인가요? |
| L-045 | 단일 카메라 cfg 에는 CSU-W1 장치가 없음 | 포트는 이전 세션 값으로 남음; State 0 이면 Kinetix_red 에 빛이 안 감 (오류 없음) | chk:208-209; BL:60-61 | cfg 읽기에서 나온 추론 | 없음 | 사실 항목 (위험 안내) 으로 넘길까요? |
| L-046 | DMD_dualcam_LUNF.cfg | Startup: LappMainBranch1 1, CSUW1-Port 1. 이 설치에서는 `MightexPolygon1000` (장치 API v71) 때문에 불러오지 못함 | chk:205-207; cfg2:8,255,263; cfg1:6-15 | cfg 사본 + 2026-10-02 시도 | 일부: devices.v0 의 dmd 줄 `automatable_condition: core_requirement` | 확인만 |
| L-047 | DiaLamp 세기 | 608 / 2100 (스탠드에서 설정) | bp1002:533-540; run930y:40; run930m:51; mock_world:204; mock:60 | 9/30 사용, 2026-10-02 같은 값 읽음 | 없음 | 608 은 누가 언제 설정했나요? |
| L-048 | 명시야 광경로 | 9/30: CondenserTurret `3-`, LightPath `4-L100`. 2026-10-02 읽기: Condenser `1-ND` (State 0), LightPath `4-L100` (State 3) | run930y:41-42; run930m:135; bp1002:212-219,376-383 | 9/30 기록 + 장치 읽기 | 일부: `stand_state_read_20260924_20x_in_place` E1 (KB, LightPath 4-L100, Condenser 1-ND), `ti2e_optical_path_addresses` E3 (KB) | 명시야에 condenser `3-` 를 쓴다는 것은 사용자 규칙인가요? |
| L-049 | 명시야 4x 노출 | 10 ms → median 2766 ADU (DiaLamp 608), ≥ 30 ms 포화, 12 ms 사용 | run930y:43; run930m:51-52; ops/sample_map.py:60; mock_world:223-225 | 측정 2026-09-30 (12-bit 판독) | 없음 | 넘길까요? (판독 모드가 L-056 에 달려 있음) |
| L-050 | 입자 빛 노출 (Aura GREEN 1 %) | 4x 994 ms (자동, p99.9 2043 ADU); 100x 20 ms (최대 3435 ADU, 포화 없음); 100x 30–50 ms 포화 | run930y:48,87,119-121; run930m:74,105-106; ops/focus_100x.py:70,85-87; mock_world:104-110 | 측정 2026-09-30 | 없음 | 넘길까요? |
| L-051 | Aura 깜빡임 | 4x 타일 한 장에서 두 프레임이 −23 % | run930y:152; run930m:148-149; focus/classical.py:46-49; mock_world:188-194 | 관찰 2026-09-30, 한 번 | 없음 | 관찰 항목으로 넘길까요? |
| L-052 | 형광 방출 "605 nm" | configs 의 방출 중심 0.605 um, 대역 0.040 um | ti2_*.yaml:3,51-52; mock_world:62 | 경로 이름에서 옮긴 값 | **충돌 가능**: `red_path_605_is_the_ff01_595_31_filter` E5 (S): 605 는 이 벤치의 경로 이름이고 필터는 FF01-595/31 | dino 의 0.605 um 는 필터 중심이 아니라 경로 이름에서 온 값이 맞나요? (그러면 넘기지 않음) |
| L-053 | FilterTurret1 | `1-MXR00724 -Empty` (State 0); FilterTurret2 `1-Empty` | bp1002:254-261,315-322 | 장치 읽기 2026-10-02 | 있음: `filter_cube_mxr00724_is_five_band` E3 (S), `stand_state_read_20260924_20x_in_place` E1 (KB) | 확인만 |

### 2.5 카메라

| id | 항목 | 값 + 단위 | dino-autofocus 위치 | 기록된 출처 | soft-matter-agents 에 있나 | 사용자에게 물을 것 |
|---|---|---|---|---|---|---|
| L-054 | Kinetix_red 정체 | s/n A24M723015, chip TMP-Kinetix, fw 30.48, PVCAM 3.10.2, adapter 1.4.5. Kinetix_blue = A23H723003 (이 cfg 에서 불러오지 않음) | bp1002:830-1534; cfg1:24-28,42-49 | 장치 읽기 (cfg 머리말 2026-09-03) | 있음: `kinetix_red_label_opens_serial_a24m723015` E1 (KB), `camera_bodies_are_told_apart_by_serial` E3 (S) | 확인만 |
| L-055 | 2026-10-02 판독 모드 | Port `Dynamic Range` (허용 Dynamic Range, Sensitivity, Speed, Sub-Electron); ReadoutRate `100MHz 16bit` 하나뿐; BitDepth 16; PixelType 16bit; Gain `1-Standard` | bp1002:863,1104,1392,1400,1432; backend:282-287; chk:140; BL:49-51 | 장치 읽기 2026-10-02 | 있음: `kinetix_red_adapter_properties_as_reported_20260924` E1 (KB, 같은 16bit). gap `kinetix_red_bit_depth` 열림 ("closes with a frame that saturates") | 확인만 |
| L-056 | 2026-09-30 판독 모드 | ReadoutRate `100MHz 12bit`, bit depth 12, 천장 4095. 근거: 16-bit 천장을 노린 자동 노출이 실패, 100x 30–50 ms 에서 4095 포화 | run930y:18-19; run930m:131,156-157; backend:115; focus/classical.py:38-40; mock_world:152-155; mm_real:109 | 9/30 기록. 어느 Port 였는지 미확인 (chk:140) | **충돌**: L-055 와 KB E1 는 16bit. `pixeltype_misreports_bit_depth` E3 (S) 는 반대 방향 ("PixelType reports 12bit while the data delivered is 16-bit") | 9/30 에 Port 를 바꿨나요? 4095 에서 포화된 9/30 프레임 (`focus100x_20260930-202226.json`) 을 gap `kinetix_red_bit_depth` 의 증거로 넘길까요? |
| L-057 | 어두운 오프셋 | 9/30 관찰 약 102 ADU; 2026-10-02 속성 `Offset = 100`; configs 는 100 ADU placeholder | ops/focus_100x.py:68; mock_world:156; run930y:19; bp1002:1152; ti2_*.yaml:34 | 관찰 9/30 + 장치 읽기 | 없음 | 102 ADU 는 어두운 프레임으로 잰 것인가요, 신호 없는 프레임에서 본 것인가요? |
| L-058 | Full well | configs 80000 e- (데이터시트, 16-bit DR); 장치 속성 `FullWellCapacity = 15000` (읽기 전용) | ti2_*.yaml:10,31; configs/kinetix_100x_oil.yaml:26; bp1002:1096 | 데이터시트 vs 장치 읽기 2026-10-02 | 없음 (`cameras_both_kinetix22` E3 는 같은 모델이라는 것만) | 두 값이 다릅니다. 어느 쪽을 librarian 에 넘길까요? 둘 다 사실로 (출처 분리) 넘길까요? |
| L-059 | 판독 잡음 | 1.6 e- rms (DR 모드, 데이터시트) | ti2_*.yaml:8,29; mock_world:158 | 데이터시트 | 있음: `camera_read_noise_dynamicrange` E3 (S) | 확인만 |
| L-060 | 양자 효율 | 0.96 (600 nm, 그래프에서 읽음); configs/kinetix_100x_oil.yaml 은 0.80 (690 nm 근처) | ti2_*.yaml:9,28; configs/kinetix_100x_oil.yaml:23 | 데이터시트 그래프 | 있음: `camera_qe_at_600nm_from_the_kinetix_graph` E3 (S) 0.96. 0.80 은 없음 | 0.80 은 어디서 온 값인가요? (모르면 넘기지 않음) |
| L-061 | 판독 시간 | `Timing-ReadoutTimeNs` 9000000 (9 ms, 노출 10 ms 에서), `ScanLineTime` 3750 | bp1002:1503,1610 | 장치 읽기 2026-10-02 | 없음 (gap `camera_exposure_grid` 와 관련) | 사실 항목으로 넘길까요? |

### 2.6 PFS

| id | 항목 | 값 + 단위 | dino-autofocus 위치 | 기록된 출처 | soft-matter-agents 에 있나 | 사용자에게 물을 것 |
|---|---|---|---|---|---|---|
| L-062 | PFS 상태 읽기 | 9/30 내내 꺼짐, `Out of Range`. 2026-10-02 처음부터 꺼짐 (`enabled false, locked false, Out of Range`), `enableContinuousFocus(False)` 뒤에도 꺼짐. 켜진 상태에서 끄기는 미확인 | run930y:24,60; bp1002:2374-2387; chk:144; BL:66 | 장치 읽기 | 없음 (절차 규칙만: `rulings:24` "PFS must not be servoing during a Z sweep" transfer) | 넘길까요? 켜진 PFS 를 끄는 시험은 언제 할 수 있나요? |
| L-063 | PFS 속성 | DichroicMirrorInserted `Yes`, FocusMaintenance `Off`, LEDIntensity 27 (0–4095) | bp1002:412-460 | 장치 읽기 2026-10-02 | 없음 | 사실 항목으로 넘길까요? |
| L-064 | Core AutoFocus 장치 | `PFS` | bp1002:2371; chk:143; mm_real:104 | 장치 읽기 2026-10-02 | 없음 (렌즈 `*_selector_properties` E3 가 "Ti2-E PFS compatible" 만) | 넘길까요? |
| L-065 | PFSOffset 부호 | 값 없음 (양쪽 모두 미측정) | docs/integration-sma.md:95 | 미측정 | gap `pfs_offset_sign_unmeasured` 열림 | 잰 적이 있나요? |
| L-066 | 렌즈 회전 조건 | Z 후퇴, PFS 끔, `Out of Range` 확인 뒤에만 | guards:31,500-521; run930y:109 | 9/30 절차 (prior project SAFETY.md §2) | 일부: `nosepiece_write_runs_no_escape` E3 (S), `rulings:24` | 숫자 아님. 절차로만 넘길까요? |

### 2.7 표류와 벤치 관찰

| id | 항목 | 값 + 단위 | dino-autofocus 위치 | 기록된 출처 | soft-matter-agents 에 있나 | 사용자에게 물을 것 |
|---|---|---|---|---|---|---|
| L-067 | 명령 없는 Z·Y 표류 | Z 485.16 → 483.62 um, Y 약 0.7 um (첫 속성 읽기와 이탈 사이) | chk:176; BL:64-65; bp1002:2362-2370; docs/integration-sma.md:96-97 | 측정 2026-10-02. 손으로 건드렸는지 미확인 | 없음 | 그 사이 스탠드나 초점 손잡이를 만졌나요? |
| L-068 | 9/30 읽기 불일치 | 명령 3037.0, 읽기 3036.0 um → 정지 (그때 재물대를 손으로 움직임) | run930y:132; run930m:120-121; guards:15 | 관찰 2026-09-30 | 없음 | 손으로 움직인 것이 맞나요? 관찰 항목으로 넘길까요? |
| L-069 | 9/30 시료 구멍 | 중심 (8026.0, 571.6) um, 지름 6.1438 mm, fit rms 42.5 um, 49 점, 352 deg; 이전 fit 에서 1.5 mm 이동 | run930y:62-75; run930m:16-17,29-32; mock_world:237-238 | 측정 2026-09-30 (시료 `20260930_1849_1`) | 없음 | 시료 하나의 값입니다. librarian 에 시료 관찰로 넣을까요, 남겨 둘까요? |
| L-070 | 9/30 4x 초점 평면 | 구멍 중심 z 3048.7 um, 기울기 x −1.66, y −3.62 um/mm, rms 7.6 um (73 블록) | run930y:96-100; run930m:18-19; mock_world:242-243 | 측정 2026-09-30 | 없음 | 위와 같음 |
| L-071 | 9/30 100x 초점과 입자 | 바닥층 2988.45 um (8164.7, 523.4), 2989.42 um (7811.0, 1529.0); 사용자가 찾은 입자 (8579.5, 68.3) z 3012.94, 가장 밝은 3010.0, 바닥 위 20.6 um, FWHM 약 6.7 um | run930y:113-139; run930m:20-22; mock_world:244 | 측정 2026-09-30 | 일부/주의: `tracer_diameter_measured` E2 (S) 는 지름 5 um. 6.7 um 는 영상 FWHM 이라 같은 양이 아님 | 6.7 um FWHM 를 입자 지름으로 쓰지 않는다는 것에 동의하나요? 같은 병의 입자인가요? |
| L-072 | 오일 이중 봉우리 | 첫 곡선이 3005 um 근처에서 두 번째 상승, 오일을 더 넣은 뒤 하나 | run930m:107-108; run930y:119-120 | 관찰 2026-09-30 | 없음 | 관찰 항목으로 넘길까요? |
| L-073 | 피에조 읽기 | 9/30 "NanoBench 6000", COM4, 읽기만, z ≈ 9.94 um 하루 내내 | run930y:23; run930m:138; mock:64-65; ops/hardware_scan.py:56 | 읽기 2026-09-30 | 일부: `piezo_controller_identity` E1 (KB, COM4, NPC-6330), `piezo_rest_position_as_found_20260924` E1 (KB, ch3 −0.0017 um, 다른 날) | "NanoBench 6000" 은 프로그램 이름인가요? 9/30 z 9.94 um 를 관찰로 넘길까요? |
| L-074 | 9/30 시작·끝 상태 | 시작: 4x, Z 62.9 um, PFS 꺼짐. 끝: 100x Oil, Z 498.0 um (사용자가 후퇴), XY (6396.0, 177.5), Aura·DiaLamp 꺼짐 읽기 확인 | run930y:58-60,141-147; run930m:23 | 기록 2026-09-30 | 없음 | 넘길 필요가 있나요? (권고: run 기록으로만) |
| L-075 | 벤치 cfg 불러오기 검사 | sha256 `8184073e31e1a7a63731932a20a622131d4dba04cf839bc9e651bf9abcd53120`; 불러올 때 설정: Core.Camera=Kinetix_red, Core.Shutter=LightEngine, Core.AutoShutter=1, System/Startup LappMainBranch1.State=1; System/Shutdown 없음 | bp1002:1-21; chk:118-126 | 읽기 2026-10-02 | 일부: `single_cam_red_config_startup_puts_the_lapp_mirror_in` E1, `single_cam_red_config_arms_autoshutter_on_the_lightengine` E1 (KB). "Shutdown 없음" 은 새 사실 | "Shutdown 프리셋 없음" 을 넘길까요? |
| L-076 | 설치 상태 | Micro-Manager_2.0.3_20260806 (pymmcore-plus 사본), git 2.49.0.windows.1, torch hub 경로 | chk:130-134 | 읽기 2026-10-02 | 있음: `pymmcore_plus_micromanager_copy_loads_single_cam_red_config` E1 (KB) | 물리 값 아님. 넘기지 않아도 되나요? |

### 2.8 초점 판정 문턱값과 작업 인자 (모두 튜닝 값, 물리 값 아님)

| id | 항목 | 값 + 단위 | dino-autofocus 위치 | 기록된 출처 | soft-matter-agents 에 있나 | 사용자에게 물을 것 |
|---|---|---|---|---|---|---|
| L-077 | `MIN_DYNAMIC_RANGE_ADU` (튜닝) | 20 ADU | focus/verdict.py:46-49; chk:53 | provisional; 9/30 100x 30 ms Vollath 가 어두운 오프셋만 읽은 일에서 | 없음 | 어두운 프레임으로 다시 맞출 때까지 넘기지 않는 것에 동의하나요? |
| L-078 | `MIN_CURVE_CONTRAST` (튜닝) | 0.05 | focus/verdict.py:51-52; chk:54 | 임시 | 없음 | 위와 같음 |
| L-079 | `MIN_SWEEP_FRAMES` (튜닝) | 3 | focus/verdict.py:54-55 | 임시 | 없음 | 위와 같음 |
| L-080 | `IN_FOCUS_DOF` (튜닝) | 1.0 DoF | focus/verdict.py:57-58; chk:55 | 임시 | 없음 | 위와 같음 |
| L-081 | `MAX_SIGMA_DOF` (튜닝, 모델 읽기에 씀) | 3.0 DoF | focus/verdict.py:60-61; chk:56 | provisional | 없음 | 모델 sigma 에 거는 문턱이라 3절로 분류. 동의하나요? |
| L-082 | `MAX_SATURATED_FRACTION` (튜닝) | 0.001 | focus/classical.py:42-44; ops/sample_ops.py:66 | 임시 | 없음 | 넘기지 않음 권고 |
| L-083 | `DROPOUT_TOLERANCE` (튜닝) | 0.02 | focus/classical.py:46-49 | 9/30 −23 % 깜빡임에서 정한 규칙 (scripts/scan_4x.py) | 없음 | 넘기지 않음 권고 (근거 관찰은 L-051) |
| L-084 | `PEAK_BIN` (튜닝) | 4 (4 × 4 binning) | focus/classical.py:51 | scripts/focus_100x.py | 없음 | 넘기지 않음 권고 |
| L-085 | 로딩 검사 문턱 (튜닝) | `MIN_RANGE_ADU` 20, `MIN_STRUCTURE_RATIO` 3.0 | ops/sample_ops.py:67-68 | 임시 | 없음 | 넘기지 않음 권고 |
| L-086 | `focus_100x` 인자 (튜닝) | 중심 2930 um, ±40 @ 2 um, 미세 ±3 @ 0.2 um, 노출 20 ms, GREEN 1 %, `SIGNAL_MIN_ADU` 50, settle 0.1/0.15 s, 확장 3번 | ops/focus_100x.py:66-90 | provisional (9/30 한 번) | 없음 (과제 026 미배정, docs/integration-sma.md:11) | 절차 정의로만 넘기고 숫자는 그쪽 plan 에서 다시 정하는 것에 동의하나요? |
| L-087 | `scan_4x` 인자 (튜닝) | z 추정 2960 um; 첫 타일 ±160 @ 10, 다음 ±50 @ 6, 미세 ±12 @ 2 um; 자동 노출 목표 천장의 0.5, 6회, 시작 30 ms, 1–2000 ms; 여유 500 um, 겹침 0.15; settle 0.1/0.2/0.2 s | ops/scan_4x.py:105-126; run930y:82-86 | 9/30 스크립트 값 | 없음 | 위와 같음 |
| L-088 | `edge_trace` 인자 (튜닝, 속도 상한은 [envelope]) | 기본 100 um/s (9/30 사용자는 400 um/s, 걸음 200 um), 속도 10–1000 um/s, 걸음 20–200 um, `MIN_BLOB_UM` 500, `CAL_MIN_PEAK` 8.0, `CAL_SCALE_RANGE` 0.7–1.4, 각도 차 10 deg, 지름 경고 0.2, cal 200 um, 점 간격 250 um, 반경 1000–7000 um, 경로 25000 um, 360 s | ops/edge_trace.py:81-95,286-298; run930y:67 | 임시 / 9/30 사용 | 없음 | 속도 상한 1000 um/s 는 누가 정했나요? (envelope 후보) |
| L-089 | 모자이크·후보 검출 (튜닝) | `BIN` 8, 후보 검출 문턱 (합성 타일로만 맞춤) | engine/mosaic.py:24-28,44; chk:46 | 합성 데이터로 맞춤 | 없음 | 실제 모자이크로 다시 맞출 때까지 넘기지 않음 권고 |

## 3. librarian 에 숫자로 보내면 안 되는 것

| 무엇 | 위치 | 이유 |
|---|---|---|
| DINO 합성 결과 전부 (signed MAE, sign acc, \|dz\| MAE, 17-plane 오차, `models/heads/*` 의 예측) | docs/synthetic-results.md:16-49 | 모델 출력, E6. 합성 데이터라 벤치 사실도 아니다. 고전 지표의 합성 결과도 벤치 값이 아니다 |
| `MAX_SIGMA_DOF` 3.0 과 모델 sigma 에 거는 판정 | focus/verdict.py:60-67 | 모델 숫자에 거는 문턱. 모델 숫자는 카드에 들어가지 않는다 |
| GTX 1650 SUPER 지연 시간 | docs/synthetic-results.md:51-63 | 개발 데스크톱 측정. 현미경 PC (A4000) 값이 아니다 |
| mock_world 추정값: 형광 세기 거듭제곱 보간, 동초점 log M 보간 (10x–60x), GREEN 외 라인 가중치 0.25, DiaLamp 0.9 계수, 챔버 120 um, 입자 밀도 200 /mm², 위층 비율·높이 | mock_world:104-123,215-225,241,245-247 | 코드 안의 "estimate" / "not measured". 측정이 아니다 |
| mock_world 재물대 한계 ±57000, ±37500, Z 0–9000 um, 속도 5000 / 1000 um/s, settle 0.05 s | mock_world:172-181 | "Not measured: placeholders". 그리고 한계라 안전 값 |
| mock_world 렌즈 라벨 위치 1–4 (`2-Plan Apo LmbdD 10x`, `4-Apo LmbdS 40xC WI` 등) | mock_world:126-137 | 벤치에서 읽은 라벨 (L-001) 과 다르다. 지어낸 라벨 |
| mock_world 와 configs/ti2_40x.yaml 의 40x WI 작동 거리 160 um | mock_world:133; configs/ti2_40x.yaml:23 | guards 의 170 um (L-005) 로 바뀌기 전 값이 남아 있다. 저장소 안에서도 서로 다르다 |
| configs 의 placeholder: gain 1.25 e-/ADU, offset 100, dark_current 0.5, prnu 0.005, hot_pixel_rate 2e-5, photons_per_emitter 8000, background 40, bandwidth 0.040 | configs/ti2_*.yaml:11-12,30-36,52-56; mock_world:157 | 파일 스스로 "placeholder" / 미측정이라고 적음 |
| configs/kinetix_100x_oil.yaml 의 qe 0.80, wavelength 0.690 "assumed", t_immersion 100 | configs/kinetix_100x_oil.yaml:23,43,47 | 출처 미상 또는 가정. 다른 configs 와도 다르다 |
| 20x 배율 20.0785 | configs/ti2_20x.yaml:20; mock_world:132 | 픽셀 크기에서 역산한 값. devices.v0 가 숫자 배율 칸을 일부러 두지 않는다 (명목 이름에 역산 값이 붙는 일) |
| mm_demo_core 의 데모 값: Z 오프셋 3000, 데모 Z −300..300, 데모 LED 파장 `385nm/470nm/550nm/635nm` | mm_demo_core:69-78 | Micro-Manager 데모 장치 값. Aura 라인의 실제 파장이 아니다 |
| mock 의 피에조 `PIEZO_UM (0.0, 0.0, 9.94)` | mock:64-65 | mock 상수, provisional. 넘긴다면 9/30 원래 읽기 (L-073) 로만 |
| 모든 가드 한계와 잠금: Z 창 2800–3200, 후퇴 0 / 복귀 2800, 후퇴 판정 1 um, 천장 0.4 × WD, 접근 걸음 10 um, 큰 XY 이동 문턱 표, XY 상자 1000 um, 허용 오차 0.25 / 5 um, Y 이탈 +15000 um, XY 대기 30 s, edge_trace 속도 상한, Aura 퍼센트 (0, 100], `BENCH_APPROACH`, `BENCH_MOTION` | guards:60-135,692-693; mm_real:86-99; ops/edge_trace.py:81-82; ops/light_set.py:40 | 안전 한계. §10.3 rule 4: 숫자로 건너가지 않는다. 사람이 `envelope/safety.json` 에 직접 쓴다 (스키마 키는 그쪽 매니저) |
| guards 의 `FREE_WD_UM` / `BENCH_FREE_WD_UM` 표 그 자체 | guards:63-68; mm_real:97-98; mm_demo:79-80 | 가드 입력 표. 작동 거리 사실은 렌즈 카탈로그 항목으로 이미 있고 (`objective_mrd*`), 이 표를 옮기면 같은 사실의 두 번째 기록이 된다 (`rulings:23` 도 prior 의 같은 표를 drop). 40x WI 170 um 는 측정이 확인될 때만 gap 답으로 |
| 2.8 절의 튜닝 문턱과 작업 인자 (L-077–L-089) | 각 줄 참조 | 물리 값이 아니라 판정·절차 튜닝. 넘기더라도 벤치 사실 항목이 아니다. 대부분 provisional 또는 합성 데이터로 맞춤 |

## 4. 두 저장소 사이의 충돌과 저장소 안의 불일치

두 저장소 사이 (값이나 출처가 다름):

1. **40x WI 작동 거리**: dino 170 um (사용자, 2026-10-02; guards:67, mm_real:98) vs librarian `objective_mrd77400` E3 0.16–0.2 mm, wd null, gap `objective_40x_wd_at_170um` 열림; `safety:49-65` 는 0.16 mm 를 쓴다. 0.17 은 칼라 눈금 (커버슬립 두께) 과 같은 숫자라, 측정인지 옮겨 적은 것인지 먼저 확인 필요.
2. **Kinetix_red 비트 깊이**: dino 9/30 12-bit, `100MHz 12bit`, 천장 4095 (run930y:18-19) vs librarian `kinetix_red_adapter_properties_as_reported_20260924` E1 16bit, 그리고 dino 2026-10-02 읽기도 16bit (bp1002:1432). librarian `pixeltype_misreports_bit_depth` E3 는 반대 방향 (속성 12bit, 데이터 16-bit). gap `kinetix_red_bit_depth` 는 포화 프레임 하나로 닫힌다고 적혀 있고, 9/30 에 4095 포화 프레임이 있다.
3. **4x 픽셀 크기**: dino 9/30 보정 1.62524 um/px (run930y:52) vs librarian `pixel_size_4x_zoom_1x` E2 1.625. 그리고 출처: dino cfg1:294-296 은 "20x 만 측정, 나머지 다섯은 6.5/M" 인데 librarian 은 여섯 모두 "measured by the operator" (E2).
4. **방출 605 nm**: dino configs 의 방출 중심 0.605 um (ti2_*.yaml:51) vs librarian `red_path_605_is_the_ff01_595_31_filter` E5: 605 는 경로 이름이고 필터는 595/31.
5. **입자 크기**: dino 9/30 입자 FWHM 약 6.7 um (run930y:138), mock 은 5.0–6.7 um vs librarian `tracer_diameter_measured` E2 5 um. 같은 양이 아니지만 섞이기 쉽다.
6. 피에조: dino 9/30 z 9.94 um, "NanoBench 6000" vs librarian 9/24 ch3 −0.0017 um, `NPC-6330`. 날짜가 달라 충돌은 아니고, 이름이 다르다.

dino-autofocus 안의 불일치 (통합 전에 정리할 것, 이 조사에서는 고치지 않음):

- 40x WI 작동 거리: guards / mm_real / mm_demo 는 170, configs/ti2_40x.yaml:23 과 mock_world:133 은 160.
- Full well: configs 80000 e- vs 장치 `FullWellCapacity` 15000 (bp1002:1096).
- 양자 효율: ti2_*.yaml 0.96 vs configs/kinetix_100x_oil.yaml:23 0.80.
- 렌즈 라벨: mock_world:131-134 vs 벤치 (bp1002:179, cfg1:178-183).
- backend:115 주석 "4095 for the Kinetix 100 MHz 12-bit readout" vs 2026-10-02 의 16bit (backend:283-285).

값이 같은 것 (확인만): 4x / 10x / 20x / 60x / 100x 작동 거리, 렌즈별 NA, 픽셀 크기 숫자, 커버슬립 170 um, 40x 칼라 0.17 mm, Z 방향, Aura 다섯 라인과 per-mille, Aura State 0, Spectra III 정체, 판독 잡음 1.6 e-, QE 0.96, 센서 2400 × 2400 / 6.5 um, Kinetix_red 일련번호.
