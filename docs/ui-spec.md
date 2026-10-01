# UI 화면·동작 명세 (T-004)

작성: AF 실행5 (2026-10-01). 근거 코드는 `main` 6ba1bc1 의 `scripts/launcher.py`,
`scripts/live_focus.py`, `scripts/edge_track.py`, `scripts/focus_servo.py`, `scripts/scan_4x.py`,
`scripts/mm_grab.py`. 운영 규칙은 `docs/runs/2026-09-30_substrate-scan.md` 2절, 설계 규칙과
기능 요구사항은 `docs/PLAN.md` (v0.2) 2·5·6절.

이 문서는 두 가지 용도로 쓴다.

- D1 결정 뒤 UI 구현 (WP-D 와 F1–F5 화면) 의 명세.
- T-002 (실행1) `engine/events.py` 설계의 입력. 4절이 그 입력이다.

D1 은 로컬 웹 앱 (FastAPI 서버 + React 브라우저 화면) 으로 확정됐다 (매니저 전달, PLAN v0.3 예정).
화면 배치는 툴킷과 무관하게 적고, 엔진 대응표 (4절) 에는 전송 방식 (REST / WebSocket) 을 붙인다.
화면 영역 이름은 v0.3 의 `console`, `hardware`, `sample`, `map`, `objective`, `live` 를 쓴다 (1.0).
작업(operation)별 plan / preflight / run / abort 의 세부는 실행4 의 `docs/operations-spec.md` (T-006)
를 따르고, 여기서는 화면이 그 작업을 어떻게 부르고 무엇을 보여 주는지만 적는다.

표기:

- 코드 이름과 UI 문구는 영어 그대로 인용한다. 예: `"Start live view"`.
- 좌표 `sum` = Ti2 XYStage/ZDrive + 피에조, µm (`live_focus.py::sample_xyz`). 피에조 축 부호는
  아직 검증되지 않았다.
- **(제안)** 은 T-002 과제 파일 목록에 없는 명령/이벤트를 이 문서가 새로 제안하는 것이다.

---

## 1. 화면 목록

### 1.0 화면 영역 (v0.3) 과 현재 화면의 대응

각 영역은 `server/api/<영역>.py` 와 `web/src/features/<영역>/` 으로 구현된다 (매니저 전달).
모든 화면에 공통 상태 줄 (조명, 실행 중 작업, 연결 상태, 원격 여부) 이 붙는다.

| 영역 | 담는 것 | 현재 화면에서 오는 것 | 새 기능 |
|---|---|---|---|
| `live` | 라이브 영상, ROI, 초점 판정, 지표 트레이스, 상태 줄, 프레임 저장 | 1.2 (a) (b) (c) (f), 1.3 스캔 미리보기, 1.4 | — |
| `map` | XY 지도, 경계점과 원 피팅, 엣지 추적, 4x 스캔과 결과 | 1.2 (d) (e) 의 지도·hole 줄, 런처 Step 1 의 추적 설정, Step 2 | F4 모자이크, 입자 후보, flag, 클릭 이동 |
| `sample` | 샘플 선택·새로 만들기·폴더, 샘플 기록 요약 | 런처 Sample, 1.2 (e) 의 샘플 줄, `n` | F3 지오메트리, 로딩 확인 |
| `hardware` | 장치 상태 읽기, 조명 켜고 끄기 | 런처 Step 0, `"Lights off"`, Step 1 의 조명 선택 | F2 탐지, 구성 파일, 게이트 |
| `objective` | 렌즈 교체와 100x 초점 | `change_objective.py`, `focus_100x.py` (런처에 없음, 수동 실행) | F5 7단계, 액침액 로딩 |
| `console` | 에이전트 질문과 기록 열람 | 없음 | F1 |

원격 규칙 (매니저 전달): 서버는 127.0.0.1 에만 바인딩한다. 원격 접속은 읽기 전용이고, 움직이거나
기록을 쓰는 명령은 현미경 PC 의 브라우저에서만 받는다. 영역별로 원격일 때 비활성인 항목은 7절에 적는다.
판정은 서버가 요청 출처로 하고, 화면의 비활성 표시는 추가 안내일 뿐이다 (PLAN 6절 2항과 같은 원칙).

### 1.1–1.4 현재 화면

현재 화면은 네 개의 tkinter 창이다. 런처, 라이브 뷰, 4x 스캔 미리보기, 그리고 거의 쓰지 않는
`mm_grab.py` 의 ROI 라이브 창이다. 라이브 뷰는 한 창 안에 여섯 영역을 둔다.
PLAN v0.2 의 새 화면 (F1–F5) 은 1.5 에 목록만 두고 7절에서 명세한다.

### 1.1 런처 (`scripts/launcher.py`, 창 제목 `"DINO Autofocus"`)

위에서 아래로 따라가는 단계형 창이다. 하드웨어 로직은 없다. 각 작업은 새 콘솔 창에서
`run_logged.py` 로 감싸 실행되고, 출력은 로그 파일에 복사된다.

| 영역 | 보여 주는 것 | 입력 | 갱신 |
|---|---|---|---|
| 머리 | `"DINO Autofocus"`, `"Find the sample, then autofocus-scan it. Work top to bottom."` | — | 고정 |
| Sample | 샘플 ID 콤보박스. `SAMPLES_ROOT` (`D:\AutoFocus\samples`) 의 하위 폴더 이름, 최신순 | 콤보 선택·직접 입력, `"Open folder"`, `"New"` (빈 값 = 라이브 뷰가 시계로 이름을 지음) | 목록은 콤보를 펼칠 때마다 다시 읽음 |
| Step 0 `"Check the microscope"` | `"Read only. The 4x scan needs the 4x objective in place."` | `"Show objective / Z / PFS"` | — |
| Step 1 `"Find the sample: live view + edge trace"` | 조명 라디오, Aura 라인/퍼센트, Exposure, Hole diameter, Trace speed, 키 안내 문구 | 라디오 `"Brightfield (DiaLamp): to find the hole edge"` / `"Aura line"`, 라인 콤보 (`GREEN` 만), `%` (기본 1), Exposure (기본 12 ms), Hole diameter (기본 6 mm), Trace speed (기본 100 µm/s), `"Start live view"` | 조명을 바꾸면 노출 기본값이 12 ms ↔ 500 ms 로 바뀜 (`light_changed`) |
| Step 2 `"Autofocus scan at 4x (Aura GREEN 1 %)"` | Exposure (빈 값 = auto), 안내 문구 | Exposure, 체크 `"Dry run: only print the tile plan"`, `"Start 4x scan"`, `"Show scan result (mosaic + z map)"` | — |
| 기타 | — | `"Lights off (Aura + DiaLamp)"`, `"Try the demo (no hardware)"` | — |
| 상태 줄 | `"Idle."`, `"Checking that the microscope is free ..."`, `"Started <label> (log: <file>)"`, `"Running: <labels>"`, `"Not started."` | — | 1 s 폴링 (`poll`) |

작업 실행 규칙 (`Launcher.run`):

- 하드웨어 작업은 런처가 띄운 다른 하드웨어 작업이 살아 있으면 거부한다.
- 그다음 `hardware_users()` 가 PowerShell 로 프로세스 명령줄을 읽어 현미경 프로그램
  (`HW_MARKERS`: live_focus, scan_4x, Micro-Manager, NIS-Elements 등) 을 찾는다. 찾으면 계속할지 묻는다.
- 로그는 샘플 폴더가 있으면 그 안에, 없으면 `outputs/launcher_logs/` 에
  `launcher_<label>_<stamp>.log` 로 쓴다.
- 중지는 각 콘솔의 Ctrl+C 다. 스크립트 자신의 `finally` 가 소등한다.

### 1.2 라이브 뷰 (`scripts/live_focus.py`, 창 제목 `"Kinetix_red full sensor -- focus score"`)

가로 세 칸과 아래 상태 줄로 된 한 창이다.

```
+----------------------+------------------------------+----------------------+
| (a) 이미지            | (b) 게이지 | (c) 트레이스 2개 | (d) XY 지도           |
|  전체 프레임 + ROI     |            |                 | (e) 위치·샘플 텍스트   |
+----------------------+------------------------------+----------------------+
| (f) 상태 줄                                                                |
+----------------------------------------------------------------------------+
```

| 영역 | 보여 주는 것 | 갱신 |
|---|---|---|
| (a) 이미지 | 2400 × 2400 전체 프레임을 `--display` (800 px) 이하로 평균 비닝하고 0.5–99.8 백분위로 8-bit 늘림 (`bin_for_display`). 가운데 `--score-roi` (518 px) 주황 사각형 = 지표를 읽는 ROI. 헤드가 있으면 DINO 타일 (224 px) 테두리: 유효 (`p_valid ≥ 0.5`) 는 파란 실선과 `+1.3` 같은 dz 숫자, 무효는 회색 점선과 `?` | 보관되는 프레임마다 (`--fps`, 기본 10 fps) |
| (b) 초점 게이지 (`Gauge`) | `"Focus score"`, `"depths of field"`. −10..+10 DoF 세로 눈금, ±1 DoF 초록 띠, 마커와 sigma 막대, 숫자 (`+1.2`), 메모 (`"box: 3/4 tiles, sign unsure, offset +0.5"`, `"no head loaded (--head)"`, `"no readable sample in view"`, 데모에서 `"demo value, not a measurement"`). 값은 최근 5개 읽기의 중앙값 | 점수 스레드의 읽기가 도착할 때 (비동기, 수십 ms) |
| (c) 트레이스 1 (`Trace`) | `"Sharpness, centre 518 px"`: 주황 ROI 의 Brenner. 자동 스케일, 최소/최대/현재값 글자 | 보관되는 프레임마다. 길이 `--history` (30 s) × fps 점 |
| (c) 트레이스 2 | `"z_sum = ZDrive + piezo z (um)"` | 같음 |
| (d) XY 지도 (`XYMap`) | 제목 `"Sample map (stage um)    b: mark edge   u: undo"`. 방문 필드 사각형 (점수로 색: \|s\| ≤ 1 초록, ≤ 3 파랑, 그 밖 회색), 경계점 (빨간 점), 경계점 3개 이상이면 원 피팅 (8개 이상은 이상치 제거, `robust_circle`) 과 중심 ×, 2개면 선, 현재 시야 (주황 사각형 + 십자), 축척 `"<span> um across   +stage x ←  +y ↓"`. 기본으로 x, y 모두 뒤집어 그림 (조이스틱 방향) | 0.5 s |
| (e) 위치·샘플 텍스트 | Ti2 / piezo / sum 의 x, y, z 표. 샘플 ID와 `"(n: new sample)"`, 대물렌즈 라벨, 시야 µm, 지도 필드 수, 경계 범위, hole 중심·지름·rms·점 수, 현재 위치가 중심에서 몇 µm, 가장자리 안쪽 몇 µm, `"(piezo not read)"`. 키 안내와 진행 상태: `"edge track: <status>"`, 헤드가 있으면 tare offset, `"piezo: <status>"` (서보), `"piezo focus: <status>"` (스윕), 읽기 영역 | 0.5 s |
| (f) 상태 줄 | `" shown 9.8 fps (camera 33.1)   mean 812  max 4095  sat 0.02%   x … y … z … um   REC"` | 보관되는 프레임마다 |
| 콘솔 (stdout) | 키 거부 사유, 시작/중지, 경계점 좌표, tare 결과, 추적기 이벤트 JSON 등 25곳의 `print` | 발생 시 |

진행 상태 문자열은 각 루틴의 `.status` 다. 예: 엣지 추적 `"calibrating"`, `"tracking 400 um/s  path 3.20 mm  …"`,
`"coasting on fitted circle (1/3)"`, `"stopped: <why>"`. 서보 `"probing +0.5 um"`,
`"step 3: score +1.20 -> moving -0.240 um"`. 자동 초점 `"fine scan around 9.94 um"`,
`"peak beyond the scan: extending"`, `"Vollath flat: probing with DINO at -2 / +2 um"`.

화면 밖에서 라이브 뷰가 쓰는 기록 (화면 항목은 아니지만 4절 이벤트의 근거):

| 기록 | 내용 | 주기 |
|---|---|---|
| `track_<stamp>.jsonl` | 머리 (`header`, `sample`), 이후 프레임마다 위치, `sample_um`, score, score_raw, score_offset, sharpness, mean, max, sat_pct. 추적기·서보·스윕 이벤트도 같은 파일 | 보관되는 프레임마다 + 이벤트 |
| `map.json` | `visits` (최근 20000), `boundary` | 경계점 변경 시, 그리고 `sample.json` 저장 때 |
| `sample.json` | hole 피팅, 경계 범위, 방문 필드 수, 사용한 대물렌즈, 스테이지-카메라 보정, 렌즈별 tare offset, config, camera | 10 s, 그리고 tare 와 창 닫기 때 |
| `--record` | `video_<stamp>_uint16_<h>x<w>.raw` (11.5 MB/프레임) + `_meta.jsonl` | 보관되는 프레임마다 |
| `autofocus_*.json`, `zsweep_*.json` | 피에조 자동 초점·스윕 결과 | 루틴이 끝날 때 |

### 1.3 4x 스캔 미리보기 (`scripts/scan_4x.py::Preview`, 창 제목 `"scan_4x preview"`)

스캔 루프가 직접 갱신하는 창이다. `--no-preview` 로 끈다. 창을 닫으면 미리보기만 사라지고
스캔은 계속된다.

| 영역 | 보여 주는 것 | 갱신 |
|---|---|---|
| 이미지 | 잡은 프레임, 700 px 이하 비닝 + 백분위 늘림 | 스냅마다 |
| 곡선 | `"<tile>: Vollath F4 vs ZDrive (um)"`: 현재 타일의 선명도 대 ZDrive 산점도 | 스냅마다 |
| 글자 줄 | `"<tile>  (k/n)   ZDrive 3048.70 um   Vollath 0.1234   max 2043/4095   exp 994 ms"` | 스냅마다 |

### 1.4 ROI 라이브 창 (`scripts/mm_grab.py::live`, 창 제목 `"Kinetix_red centre ROI -- 's' saves a frame"`)

518 px 중앙 ROI 와 글자 줄 하나. `s` 가 현재 프레임을 `.npy` 와 위치 `.json` 으로 저장한다.
런처에는 연결되어 있지 않다. 새 UI 에서는 라이브 뷰의 프레임 저장 명령 (2.1, 4.2) 으로 흡수한다.

### 1.5 PLAN v0.2 의 새 화면 (현재 코드 없음)

7절에서 명세한다. UI 셸 (WP-D) 은 이 자리를 내비게이션에 둔다.

| 화면 | 기능 | 작업 묶음 |
|---|---|---|
| 에이전트 콘솔 | 질문 입력, 이전 질문, 시뮬레이션·실험 현황/계획/결과 (F1) | WP-F |
| 하드웨어 | 탐지 결과, `hardware_profile.json`, 게이트별 켜짐/꺼짐과 꺼진 이유 (F2) | WP-G |
| 샘플 로딩 | 지오메트리 입력, 로딩 확인 (F3) | WP-H |
| 샘플 맵 | 투과광 모자이크, 입자 후보, flag, 클릭 이동 (F4). 1.2 (d) 의 확장 | WP-I |
| 배율 전환 | XY 이탈, 렌즈 회전, 액침액 로딩, 복귀 (F5) | WP-J |

### 1.6 갱신 주기 요약

| 주기 | 무엇 | 근거 |
|---|---|---|
| 10 ms | 카메라 버퍼 비우기 (`tick`) | `root.after(10, tick)` |
| 1 / `--fps` (100 ms) | 프레임 보관, 이미지, 트레이스, 상태 줄, track 기록 | 카메라 타임스탬프 `ElapsedTime-ms` 기준. 한 주기 넘게 밀리면 몰아서 내지 않고 다시 맞춤 |
| 비동기 | DINO 읽기와 게이지 | 점수 스레드. 최신 프레임만 넘기고 줄을 세우지 않음 |
| 0.5 s | 위치 읽기, 대물렌즈 라벨과 픽셀 크기 다시 읽기, 지도와 텍스트 다시 그리기 | `pos_t`, `map_t` |
| 1 s | 런처 상태 줄 | `poll` |
| 10 s | `sample.json` 저장 | `save_t` |

새 UI 는 이 주기를 엔진 이벤트 주기로 그대로 옮긴다 (4.1). 화면은 이벤트를 받아 그리기만 한다.

---

## 2. 입력 목록

### 2.1 라이브 뷰 키 바인딩 (`live_focus.py`)

창 전체 (`root.bind`) 에 걸린 키 전부다. 대소문자를 구분한다.

| 키 | 동작 | 조건과 거부 문구 | 하드웨어 | 엔진 명령 (4.2) |
|---|---|---|---|---|
| `b` | 현재 `sum` 위치를 경계점으로 추가하고 `map.json` 저장. 콘솔 `"boundary point N: x … y … um"` | x, y 가 유한할 때만 | 없음 (읽기만) | `start("boundary_mark")` |
| `u` | 마지막 경계점 삭제, 저장 | 경계점이 있을 때 | 없음 | `start("boundary_undo")` |
| `n` | 현재 샘플을 닫고 (`sample.json` 저장) 시계로 새 샘플 ID 를 만듦 | 추적 중이면 거부: `"stop edge tracking before starting a new sample"` | 없음 | `start("sample_new")` |
| `t` | 엣지 추적 시작. 실행 중이면 중지 (`"stopped by key"`) | 데모에서 거부: `"edge tracking needs the real stage"` | **XY 상대 이동** (`setRelativeXYPosition`) | `start("edge_trace", …)` / `abort` |
| `+`, `=`, 숫자패드 `+` | 추적 속도 2배 (상한 1000 µm/s) | — | 실행 중이면 다음 걸음부터 | `update(op_id, {"speed_um_s": v})` (T-011) |
| `-`, 숫자패드 `-` | 추적 속도 ½ (하한 10 µm/s) | — | 같음 | 같음 |
| `Esc` | 엣지 추적, 서보, 스윕을 모두 중지 (`"stopped by Esc"`) | — | 스윕과 자동 초점은 시작 z 로 되돌아감 | `abort` (실행 중인 작업 전부, 4.4 의 2) |
| `f` | 피에조 초점 서보 시작/중지 | 피에조와 헤드가 필요: `"focus servo needs the piezo (COM4) and a focus head (--head)"`. 추적 중이면 `"stop edge tracking first"` | **피에조 Z 이동** | `start("piezo_servo")` / `abort` |
| `w` | 피에조 자동 초점 (Vollath 피크, 멀면 DINO 로 방향) 시작/중지 | 피에조와 헤드가 필요: `"piezo focus needs the piezo (COM4) and a focus head (--head)"`. 추적이나 서보 중이면 `"stop edge tracking / focus servo first"`. 생성 실패는 `"<kind> not started: <exc>"` | **피에조 Z 이동** | `start("piezo_autofocus")` / `abort` |
| `W` | 진단 z 스윕: 현재 위치를 가운데 두고 10 µm, 0.25 µm 간격 | `w` 와 같음 | **피에조 Z 이동** | `start("piezo_zsweep")` / `abort` |
| `z` | tare: 지금이 초점이라고 보고 최근 2 s 의 원 점수 중앙값을 현재 렌즈의 offset 으로 저장 | 읽기가 3개 미만이면 `"tare: fewer than 3 readings in the last 2 s; nothing changed"` | 없음 | `start("score_tare")` |
| `Z` | 현재 렌즈의 tare 삭제 | — | 없음 | `start("score_tare_clear")` |
| `o` | DINO 읽기 영역 전환: 주황 박스 먼저 ↔ 전체 프레임 | — | 없음 | `update(live_op_id, {"read_region": "box_first" | "frame"})` (T-011)\| "frame")` **(제안)** |

`w`, `W` 실행 중에는 매 프레임 위치를 확인한다. ZDrive 가 0.3 µm, XY 가 2 µm 넘게 움직이면
`"ZDrive moved by hand (+0.42 um) during the run"` 으로 중지한다. 이 검사는 엔진 가드로 옮긴다 (4.3).

라이브 뷰에는 프레임 저장 키가 없다. 저장은 `--record` (연속 녹화) 와 `mm_grab.py` 의 `s` 뿐이다.
새 UI 에는 `"Save frame"` 을 라이브 뷰 명령으로 둔다: `start("frame_save")` **(제안)**.

창 닫기 (`finally` 순서): 엣지 추적 중지 → 서보·스윕 중지 → 연속 획득 중지 → 점수 스레드 중지
→ `--aura` 를 썼고 `--leave-light-on` 이 아니면 Aura off → 샘플 닫기 → 피에조 닫기 → 녹화 파일 닫기.
**DiaLamp 는 끄지 않는다** (운영 기록 4절 4항). 웹 UI 에서는 탭 닫기가 엔진을 멈추지 않으므로,
소등은 작업별 `finally` 와 서버 종료 경로가 맡는다 (4.2 끝, 5절).

### 2.2 마우스

| 화면 | 현재 | 새 UI |
|---|---|---|
| 런처 | 버튼, 콤보박스, 라디오, 입력칸, 체크박스 (1.1 표) | 같은 항목을 폼으로 |
| 라이브 뷰 | **마우스 바인딩 없음** (`<Button…>` 바인딩이 코드에 없다). 모든 조작은 키 | 2.1 의 각 키에 버튼을 같이 둔다. 키는 단축키로 유지 |
| 4x 스캔 미리보기 | 창 닫기 = 미리보기만 숨김 (`WM_DELETE_WINDOW`) | 스캔 화면 안의 패널로 |
| XY 지도 | 클릭 없음 | 클릭 이동 (F4.3) 과 flag (F4.4) 는 새 기능 (7절) |

### 2.3 라이브 뷰 명령행 인자 (`live_focus.py`)

"새 UI 에서" 열의 `live.x` 는 `start("live", args)` 의 인자 이름 제안이다. 화면 쪽 표시 설정은 "UI" 로 적었다.

| 인자 | 기본값 | 하는 일 | 새 UI 에서 |
|---|---|---|---|
| `--exposure` | 30 ms | 카메라 노출 | `live.exposure_ms` |
| `--fps` | 10 | 표시·기록 보관 주기 | `live.fps` |
| `--display` | 800 px | 표시 비닝 크기 | UI (화면 크기에 맞춤) |
| `--score-roi` | 518 px | 가운데 지표 ROI 와 주황 박스 | `live.roi_px` |
| `--history` | 30 s | 트레이스 길이 | UI |
| `--record` | 꺼짐 | 보관 프레임을 raw + meta 로 녹화 | `live.record` |
| `--out` | `D:\AutoFocus\frames` | 녹화 폴더 | `live.record_dir` (기본: 샘플 폴더 아래) |
| `--demo` | 꺼짐 | Micro-Manager 데모 장치 | 엔진 백엔드 선택 (`mock` / `mm-demo` / `mm-real`). 작업 인자가 아님 |
| `--screenshot` | 없음 | 3 s 뒤 창을 PNG 로 저장하고 종료 (배치 확인용) | UI 테스트 도구 (`tests/ui/`) |
| `--config` | `single_cam_red_noDMD_nocom10.cfg` | Micro-Manager config | 엔진 백엔드 설정 |
| `--set DEVICE PROPERTY VALUE` | 없음, 반복 가능 | 조명 전에 속성 쓰고 읽기 확인. 런처는 조명 선택에 씀 | **UI 에서 없앤다.** 조명은 `light_set` 의미 명령 (4.3). 임의 속성 쓰기는 노출하지 않음 |
| `--aura LINE PERCENT` | 없음 | Aura 라인 켜기 (퍼밀 = 퍼센트 × 10), 닫을 때 끔 | `start("light_set", {"mode": "aura", "line", "percent"})` |
| `--leave-light-on` | 꺼짐 | 닫을 때 Aura 를 끄지 않음 | **없앤다.** 모든 종료 경로에서 소등 (PLAN 6절 5항) |
| `--piezo` | `COM4` | 피에조 읽기 주소 (`''` = 열지 않음) | 엔진 백엔드 설정 |
| `--sample` | 새 ID | 이어서 쓸 샘플 | `start("sample_open", {"sample_id"})` |
| `--samples-root` | `D:\AutoFocus\samples` | 샘플 루트 | 엔진 설정 (`sample.py` 의 루트 인자) |
| `--head` | 없음 | DINO 헤드 경로 (torch, uv 환경) | 엔진 초점 설정 (WP-E). 없으면 판정 패널이 `"no head loaded"` |
| `--tiles` | 4 | 프레임당 DINO 타일 수 | 엔진 초점 설정 |
| `--score-offset` | 없음 | tare 를 덮어쓰는 DoF offset | **없앤다.** tare 는 `score_tare` 명령과 샘플 기록으로만 |
| `--hole-diameter` | 없음 | 예상 구멍 지름 mm (짧은 호에서 원을 안정시킴) | `edge_trace.expect_diameter_mm`. 기본값은 샘플 지오메트리 (F3) 에서 |
| `--track-speed` | 100 µm/s | 추적 시작 속도 (최대 1000) | `edge_trace.speed_um_s` |

런처 인자는 `--screenshot` (1.5 s 뒤 저장하고 종료) 하나뿐이다.

### 2.4 런처 버튼이 만드는 명령

| 버튼 | 지금 실행하는 명령 | 검증 | 엔진 명령 |
|---|---|---|---|
| `"Open folder"` | `explorer <샘플 폴더 또는 루트>` | — | UI 로컬 동작 (엔진 없음) |
| `"New"` | 샘플 칸 비우기 | — | `start("sample_new")` |
| `"Show objective / Z / PFS"` | `change_objective.py --status` | 하드웨어 점유 검사 | `start("status")` |
| `"Start live view"` (명시야) | `live_focus.py --exposure E --hole-diameter D --track-speed S [--sample ID] --set Aura State 0 --set DiaLamp State 1` | 숫자 검사 | `start("light_set", {"mode": "brightfield"})` 다음 `start("live", {"exposure_ms": E})` |
| `"Start live view"` (Aura) | 같은 앞부분 + `--set DiaLamp State 0 --aura LINE PCT` | 숫자 검사 | `start("light_set", {"mode": "aura", "line": LINE, "percent": PCT})` 다음 `start("live", …)` |
| `"Start 4x scan"` | `scan_4x.py --sample ID [--exposure E] [--dry-run]` | `sample.json` 필수, 숫자 검사, dry run 이 아니면 확인 대화상자 | `start("scan_4x", {"sample_id", "exposure_ms": E 또는 null, "dry_run"})` |
| `"Show scan result (mosaic + z map)"` | uv 환경으로 `plot_scan.py <최신 scan4x_*>` | `sample.json` 필수, 끝난 스캔 필요 | 엔진 명령 아님. UI 가 기록을 읽어 그림 (4.1) |
| `"Lights off (Aura + DiaLamp)"` | `lights_off.py` | 하드웨어 점유 검사 | `start("lights_off")` |
| `"Try the demo (no hardware)"` | `live_focus.py --demo` | — | 백엔드 `mock` 으로 엔진을 열고 `start("live")` |

런처의 오류·확인 문구 (3절에서 대화상자 지점으로 정리한다):

- `"Sample '<id>' has no sample.json yet.\nTrace the hole edge in brightfield live view first (Step 1)."`
- `"<name>: '<value>' is not a number."`
- `"<label> is still running; close it first."`
- `"Another program seems to be using the microscope: … Start anyway?"`
- `"Start 4x scan"` 확인: 4x 렌즈인지, 이번 세션에 명시야로 구멍을 다시 추적했는지
- `"No finished 4x scan in <id> yet."`

---

## 3. 확인 대화상자 지점

(다음 커밋에서 채운다.)

---

## 4. 엔진 대응표

### 4.0 규약

T-002 과제 파일의 명령/이벤트 목록을 그대로 쓰고, 화면에 필요한데 없는 것만 **(제안)** 으로 더한다.
모든 명령과 이벤트는 JSON 직렬화 가능한 dataclass 다 (PLAN 6절 7항). 공통 필드
`kind`, `t`, `op_id` 는 표에서 생략한다.

**전송** (웹 앱 기준). 공통 경로는 T-009 (서버 골격) 가 정한 이름이다. 영역별 `GET` 경로는 제안이다.

| 종류 | 전송 | 경로 | 원격 |
|---|---|---|---|
| 명령 `start` / `abort` / `confirm` / `update` | REST `POST`, 응답은 접수 결과 (`op_id` 또는 거부 사유). 결과는 이벤트로 온다 | `POST /api/commands` (T-009) | **거부** (403). `abort` 만 예외로 허용할지는 4.4 의 5 |
| 이벤트 (아래 표 전부) | WebSocket, JSON 한 줄씩 | `/ws/events` (T-009) | 허용 (구독만) |
| 라이브 영상 | WebSocket, 바이너리 JPEG (약 800 px, 서버에서 비닝, 목표 10 fps) + 그 프레임의 `frame_id` | `/ws/frames` (T-009) | 허용 |
| 현재 상태 한 번에 읽기 (접속 직후, 재접속 후) | REST `GET`, 엔진 `snapshot()` | `/api/state` (T-009) | 허용 |
| 기록 읽기 (샘플 목록, `sample.json`, 스캔 결과, 원본 프레임 한 장) | REST `GET` | `/api/<영역>/...` (제안, `server/api/<영역>.py`) | 허용 |

`/api/state` 는 이벤트를 놓친 화면이 다시 맞추는 자리다. 위치, 렌즈, 조명, 실행 중 작업과 그 마지막
`progress`, 열린 샘플, 대기 중인 `confirm_required` 를 담는다.

**명령**

모든 명령은 `origin` (`"human"` / `"assistant"`) 을 가진다 (T-011 v0.4 조정). 이 문서의 입력은 전부
사람의 입력이므로 `origin="human"` 이고 바로 `confirmed` 로 들어간다. Claude 제안 카드 (`proposed` →
사람 확인) 는 T-013 / T-014 의 화면이다.

| 명령 | 인자 | 쓰임 |
|---|---|---|
| `start` | `op` (작업 이름), `args` (dict) | 모든 작업 시작. 하드웨어를 움직이지 않는 기록 작업 (경계점, tare, 샘플 열기) 도 같은 경로로 보내 기록을 남긴다 (PLAN 6절 4항). `start("lights_off")` 는 **선점**: 실행 중 작업을 abort 하고 소등한다 (T-002 부록 3) |
| `abort` | `op_id` (없으면 실행 중인 전부), `why` | `Esc`, 중지 버튼 |
| `confirm` | `op_id`, `key`, `answer` (`"yes"` / `"no"` 또는 선택값) | `confirm_required` 에 대한 사용자 응답. 종류 `manual_step` (F5 `"Loading done"`) 은 수동 단계 기록으로 남는다 (T-011) |
| `update` (T-011) | `op_id`, `args` (바꿀 인자 dict) | 실행 중 작업의 선언된 인자를 바꿈. 지금 쓰는 곳: 추적 속도 (`+`/`-`), 라이브 읽기 영역 (`o`), 라이브 노출. 선언 밖은 거부 이벤트 |

`update` 가 필요한 이유: 추적 속도는 작업을 멈추지 않고 바꾼다. `abort` + `start` 로 흉내 내면
보정 (`cal_result`) 을 다시 해야 한다.

**작업 이름** (`start.op`)

| 작업 | 하드웨어 | 출처 | 세부 |
|---|---|---|---|
| `status` | 읽기 | `change_objective.py --status` | operations-spec |
| `live` | 카메라 연속 획득, 위치 읽기 | `live_focus.py` 의 획득 루프 | 이 문서 4.1, 4.4 |
| `light_set` **(제안)** | 조명 (의미 단위: 명시야 / Aura 라인 / 끔) | 런처의 `--set`, `--aura` | 4.3 |
| `lights_off` | 조명 끔 + readback | `lights_off.py` | operations-spec |
| `edge_trace` | XY 상대 이동 | `edge_track.py::EdgeTracker` | operations-spec |
| `scan_4x` | XY, Z, 조명 | `scan_4x.py` | operations-spec |
| `objective_change` | Z 후퇴, 렌즈 회전, (F5) XY 이탈/복귀 | `change_objective.py` | operations-spec, 7절 F5 |
| `focus_100x` | Z 스윕, 조명 | `focus_100x.py` | operations-spec |
| `piezo_servo`, `piezo_autofocus`, `piezo_zsweep` **(제안)** | 피에조 Z | `focus_servo.py` (`f`, `w`, `W`) | operations-spec 의 `focus_servo` 판단 (M1–M3 범위 밖일 수 있음) |
| `sample_open`, `sample_new` **(제안)** | 없음 | `--sample`, `n`, 런처 Sample | 4.2 |
| `boundary_mark`, `boundary_undo`, `boundary_reset` **(제안)** | 없음 (위치 읽기) | `b`, `u`, 재추적 전 경계 백업 | 4.2, 5절 |
| `score_tare`, `score_tare_clear` **(제안)** | 없음 | `z`, `Z` | 4.2 |
| `frame_save` **(제안)** | 없음 (최신 프레임) | `mm_grab.py` 의 `s` | 4.2 |

**이벤트** (T-002 목록 + 제안). 필드는 화면이 쓰는 것 기준의 최소 집합이다.

| 이벤트 | 필드 | 화면에서 쓰는 곳 |
|---|---|---|
| `planned` | `op`, `plan` (dict: 타일 격자, 스윕 범위, 천장 등), `dry_run` | 스캔·초점 화면의 계획 미리보기, dry run 결과 |
| `preflight_ok` / `preflight_failed` | `op`, `checks`: `[{name, ok, want, read, why}]` | 시작 버튼 옆 확인 목록. 실패 항목과 이유를 그대로 표시 |
| `started` | `op`, `args`, `start_state` (위치, 렌즈, 조명 readback) | 상태 줄 `"Running: …"`, 진행 패널 |
| `progress` | `op`, `status` (사람용 문자열), `step`, `n_steps` (선택), `data` (작업별 dict) | 진행 문자열 (1.2 의 `.status`), 스캔 타일 k/n, 추적 경로 길이 |
| `frame_ready` | `frame_id`, `shape`, `t_camera_ms`, `t_host`, `exposure_ms`, `pos` (x/y/z, 피에조), `stats` (`mean`, `max`, `sat_pct`, `bit_depth`), `source_op` | 이미지 (a), 상태 줄 (f), 스캔 미리보기. **픽셀은 이벤트에 넣지 않는다** (4.4 의 1) |
| `reading` | `source` (`"classical"` / `"model"`), `metric`, `value`, `grade` (모델이면 `"model"`), `verdict` (5개 어휘), `region` (`"box"` / `"frame"` / `"frame (box empty)"`), `frame_id`, `z_encoder_um`, `tiles` (`[{y0, x0, size, valid, verdict}]`) | 게이지 (b), 트레이스 (c), 타일 테두리 (a). 표시 규칙은 5절 |
| `position` (엔진 주기 이벤트, 기록 폴더 없음, T-002 부록 3) | `x_um`, `y_um`, `z_um`, `piezo_x_um`, `piezo_y_um`, `piezo_z_um`, `sum_um` ([x, y, z]), 읽기 실패 필드 (`xy_error`, `z_error`, `piezo_error`) | 위치 표 (e), 지도 현재 시야 (d), 상태 줄 (f), z 트레이스 |
| `light_changed` | `dialamp` (`"on"` / `"off"` / `"unknown"`), `aura` (`state`, `line`, `intensity_permille`), `verified`, `records` (readback 기록 목록) | 상태 줄의 조명 표시 (5절), 런처 조명 선택의 현재값 |
| `property_set` | `device`, `property`, `wanted`, `read`, `verified` | 로그 패널. `verified=false` 는 경고 배너 |
| `confirm_required` | `key`, `prompt` (영어 문구), `options`, `context` (dict) | 대화상자 (3절) |
| `finished` | `op`, `summary` (dict), `end_state` (조명 readback 필수), `record_dir` | 결과 표시, 상태 줄 `"Idle."` |
| `aborted` | `op`, `why`, `end_state` (F5 를 이탈·회전 뒤 멈추면 `awaiting_return`, T-011) | 진행 패널 `"stopped: <why>"`. `awaiting_return` 이면 공통 상태 줄에 복귀 대기 경고 (7절 F5) |
| `error` | `op`, `message`, `where` | 오류 배너, 로그 |
| `log` | `level`, `text` | 로그 패널 (지금 콘솔 `print` 25곳) |
| `objective` **(제안)** | `label`, `nosepiece_state`, `pixel_um`, `fov_um` | 위치 텍스트 (e), 지도 시야 크기. 렌즈가 손으로 바뀌어도 0.5 s 안에 보이게 |
| `sample_opened` **(제안)** | `sample_id`, `dir`, `created`, `hole` (`fitted_at` 포함, T-002 부록 3), `calibration`, `objectives_used`, `score_offset` (grade `"model"`) | Sample 칸, 위치 텍스트의 샘플 줄, hole 피팅 나이 (5절) |
| `map_changed` **(제안)** | `boundary` (점 목록), `circle` (`cx`, `cy`, `r`, `rms`, `n`, `arc_deg`) 또는 null, `limits`, `visits_added` (새 방문 필드들), `n_visits` | 지도 (d), 위치 텍스트의 hole 줄 |
| `calibration` **(제안)** | `um_per_px`, `angle_deg`, `M_px_per_um`, `objective` | 위치 텍스트, 샘플 기록. 지금은 추적기의 `cal_result` 이벤트 |
| `live_stats` **(제안)** | `shown_fps`, `camera_fps`, `kept`, `seen`, `recording` | 상태 줄 (f). `progress(live).data` 로 넣어도 된다 |

### 4.1 화면 항목 → 이벤트

| 화면 항목 | 받는 이벤트 | 주기 (1.6) | 비고 |
|---|---|---|---|
| (a) 이미지 | `frame_ready` + 미리보기 채널 (4.4 의 1) | fps | 비닝과 늘림은 엔진 쪽 미리보기 생성기에서 한다 (웹이면 JPEG) |
| (a) 주황 ROI | `started(live).args.roi_px` | 시작 시 | — |
| (a) 타일 테두리 | `reading(source="model").tiles` | 비동기 | 숫자 대신 판정 표시 (5절) |
| (b) 게이지 | `reading` | 비동기 | 중앙값 5개는 엔진 (WP-E) 이 계산해 한 `reading` 으로 낸다. UI 는 평균을 내지 않는다 |
| (c) 선명도 트레이스 | `reading(source="classical", metric="brenner")` | fps | 지금은 UI 가 Brenner 를 계산한다. 엔진으로 옮김 |
| (c) z 트레이스 | `position.sum_um[2]` | 0.5 s (지금은 프레임마다 같은 값을 다시 찍음) | 엔코더 값 |
| (d) 지도 | `map_changed`, `position`, `objective` | 변경 시, 0.5 s | 방문 필드 추가는 엔진이 0.5 s 마다 한다 (`XYMap.add` 규칙: 같은 렌즈, 시야 ¼ 안이면 갱신) |
| (e) 위치 표 | `position` | 0.5 s | — |
| (e) 샘플·렌즈·hole 줄 | `sample_opened`, `objective`, `map_changed` | 변경 시 | "중심에서 몇 µm", "가장자리 안쪽 몇 µm" 는 UI 가 `position` 과 `circle` 로 계산해도 된다 (표시 계산이지 안전 판단이 아님) |
| (e) 진행 상태 줄 | `progress(op).status` | 변경 시 | 작업별 한 줄 |
| (f) 상태 줄 | `frame_ready.stats`, `live_stats`, `position`, `light_changed` | fps | 조명 상태를 더한다 (5절) |
| 스캔 미리보기 | `frame_ready(source_op="scan_4x")`, `progress(scan_4x).data` (`tile`, `k`, `n`, `z_um`, `vollath`) | 스냅마다 | 곡선 점은 `progress.data` 에서 |
| 스캔 결과 (모자이크 + z 지도) | `finished(scan_4x).record_dir` → UI 가 `scan.json` 과 타일 `.npy` 를 읽음 | 끝날 때 | `plot_scan.py` 를 대신한다. 읽기 전용 |
| 런처 상태 줄 | `started`, `finished`, `aborted`, `error` | 변경 시 | 1 s 폴링이 필요 없어진다 |
| 로그 패널 (새) | `log`, `property_set`, `error` | 발생 시 | 지금의 콘솔 창들 |

### 4.2 입력 → 명령

모든 행은 REST `POST /api/commands` 이고 원격에서는 거부된다 (4.0 전송 표).
결과는 `/ws/events` 로 온다.

| 입력 | 영역 | 명령 | 인자 | 기대 이벤트 |
|---|---|---|---|---|
| 런처 샘플 선택 / `--sample` | `sample` | `start("sample_open")` | `sample_id` | `sample_opened`, `map_changed` |
| `"New"` / `n` | `sample` | `start("sample_new")` | — | 현재 샘플 `finished`, 새 `sample_opened`. 추적 중이면 `preflight_failed` (`"stop edge tracking before starting a new sample"`) |
| `b` | `map` | `start("boundary_mark")` | 없음 (엔진이 지금 위치를 읽음) | `map_changed`. 위치가 유한하지 않으면 `preflight_failed` |
| `u` | `map` | `start("boundary_undo")` | — | `map_changed` |
| 재추적 (새, 5절) | `map` | `start("boundary_reset")` | — | `map.json`·`sample.json` 백업 (`*_before_rescan_<stamp>.json`) 후 경계만 비움, `map_changed` |
| `"Start live view"` | `hardware` → `live` | `start("light_set")` → `start("live")` | 4.0, 2.3 | `light_changed`, `started`, `frame_ready` … |
| `t` | `map` | `start("edge_trace")` / `abort` | `speed_um_s`, `expect_diameter_mm` (2.3) | `started`, `calibration`, `progress`, `map_changed` (가장자리 점마다), `finished` / `aborted` |
| `+` / `-` | `map` | `update(edge_trace, {"speed_um_s": v})` | 엔진이 10..1000 으로 자른다. 걸음은 속도 × 0.5 s, 20..200 µm | `progress` (속도·걸음 표시) |
| `Esc` | 어느 영역이든 | `abort` | `op_id` 없음 = 실행 중 전부 (라이브 획득은 제외: 4.4 의 2) | `aborted` 들 |
| `f` / `w` / `W` | `live` | `start("piezo_servo" / "piezo_autofocus" / "piezo_zsweep")` / `abort` | 4.0 | `progress`, `reading`, `finished` / `aborted` |
| `z` / `Z` | `live` | `start("score_tare")` / `start("score_tare_clear")` | 엔진이 최근 2 s 의 모델 읽기를 쓴다 | `sample_opened` 갱신과 `log`. 3개 미만이면 `preflight_failed` |
| `o` | `live` | `update(live, {"read_region": …})` | `"box_first"` / `"frame"` | 이후 `reading.region` 이 바뀜 |
| `"Save frame"` (새) | `live` | `start("frame_save")` | — | `finished.summary.path` |
| `"Show objective / Z / PFS"` | `hardware` | `start("status")` | — | `finished.summary` (렌즈, Z, PFS) |
| `"Start 4x scan"` | `map` | `start("scan_4x")` | 2.4 | `planned`, `preflight_*`, `confirm_required` (3절), `progress`, `frame_ready`, `finished` |
| `"Lights off"` | `hardware` (공통 상태 줄에도) | `start("lights_off")` | — | `light_changed`, `finished.end_state` |
| 브라우저 탭 닫기 / 서버 종료 | — | 탭 닫기는 명령을 보내지 않는다. 서버 종료가 `abort` (전부) → `lights_off` → 백엔드 닫기 | — | `aborted` …, `light_changed`, 닫기 결과 (5절) |

웹에서는 "창 닫기" 가 엔진 종료가 아니다. 탭을 닫아도 서버의 작업은 계속된다. 그래서 소등을 탭 닫기에
걸지 않고, 서버 종료 경로와 작업별 `finally` 에 건다 (5절). 현미경 PC 의 마지막 로컬 탭이 끊긴 채
움직이는 작업이 돌 때의 처리는 4.4 의 6.

### 4.3 UI 안의 직접 하드웨어 호출 → 엔진으로

현재 UI 프로세스가 직접 부르는 하드웨어 호출 전부다. 새 UI 는 이 중 어느 것도 직접 부르지 않는다
(PLAN 6절 1항).

| 지금 (파일: 위치) | 하는 일 | 옮길 곳 |
|---|---|---|
| `live_focus.py`: `open_core(...)` (`mm_grab.open_core`) | config 로드, AutoShutter off, 노출, ROI | 엔진 열기 (백엔드 `open`). 노출은 `live.exposure_ms` |
| `live_focus.py`: `set_and_read` × `--set` (런처가 `Aura State 0`, `DiaLamp State 1/0` 을 넣음) | 조명을 속성 쓰기로 바꿈 | `start("light_set", {"mode": "brightfield" / "aura" / "off", …})`. 백엔드의 의미 단위 메서드 (`lamp_on/off`, `aura_line_on`, `aura_off`, T-002 부록 2) 를 쓰고 readback 은 `light_changed.records` 로. 임의 `--set` 은 UI 에서 없앤다 |
| `live_focus.py`: `aura_on(core, line, pct)`, 종료 시 `aura_off(core)` | Aura 켜기/끄기 | `light_set` / `lights_off`. 종료 소등은 엔진 가드의 `finally` (T-002 guards) |
| `live_focus.py`: `setCircularBufferMemoryFootprint`, `startContinuousSequenceAcquisition`, `getRemainingImageCount`, `popNextImageAndMD`, `stopSequenceAcquisition` | 연속 획득과 프레임 꺼내기, fps 솎기 | `live` 작업. 솎기 규칙 (카메라 타임스탬프 기준, 밀리면 다시 맞춤) 도 엔진으로 |
| `live_focus.py`: `positions(core, piezo)` 0.5 s | XY, Z, 피에조 읽기 | 엔진이 `position` 이벤트로 낸다 |
| `live_focus.py`: `getProperty("Nosepiece", "Label")`, `getPixelSizeUm()` 0.5 s | 렌즈와 시야 크기 | `objective` 이벤트 **(제안)** |
| `live_focus.py`: `getImageBitDepth()` | 포화 천장 (12-bit = 4095) | `frame_ready.stats.bit_depth`. `sat_pct` 는 엔진이 계산 |
| `live_focus.py`: `PiezoReader(...)` 열기·읽기·닫기 | 피에조 읽기 | 백엔드 |
| `edge_track.py`: `EdgeTracker` 의 `setRelativeXYPosition`, `getXYPosition`, `waitForDevice` (`t` 키) | 보정 이동 (축마다 200 µm) 과 추적 이동 (걸음 ≤ 200 µm) | `edge_trace` 작업. `feed(frame)` 은 엔진 안에서 `live` 프레임을 받는다. `on_point` → `map_changed`, `cal_result` → `calibration`, `set_speed` → `update`. 멈춤 조건 (가장자리 3프레임 소실, 시작점에서 7 mm, 한 바퀴, 경로 25 mm, 360 s) 은 작업 안에 그대로 둔다 |
| `focus_servo.py`: `FocusServo` / `AutoFocusZ` / `ZSweep` 의 `piezo.move_z(target, window)` (`f`, `w`, `W`) | 피에조 Z 이동 (시작점 ±5 µm, 0..600 µm) | `piezo_*` 작업. 창 제한은 가드로. 손으로 움직였는지 검사 (ZDrive 0.3 µm, XY 2 µm) 도 가드로 |
| `live_focus.py`: `FocusScorer` 스레드 (`dino_autofocus.live`) | DINO 읽기 | 엔진 초점 계층 (WP-E `focus/dino.py`) 이 `reading(source="model")` 을 낸다. torch 는 사용 지점에서만 |
| `live_focus.py`: `brenner(box)`, `vollath4(box)` | 고전 지표 | 엔진 초점 계층 (WP-E `focus/classical.py`) 이 `reading(source="classical")` 을 낸다 |
| `live_focus.py`: `raw.write`, `meta.write` (`--record`) | 녹화 | `live.record` 인자. 엔진 기록 |
| `live_focus.py`: `Sample`, `XYMap.add/mark_boundary/save`, `track.write` | 샘플·지도·track 기록 | 엔진 `sample.py` (T-002) 와 위 기록 작업들. 그리기 (`XYMap.draw`) 만 UI 에 남는다 |
| `launcher.py`: `hardware_users()` (PowerShell 프로세스 검사) | 다른 프로그램의 현미경 사용 탐지 | 엔진 preflight (코어 단일 소유 가드 + 외부 프로그램 검사). 결과는 `preflight_failed` 또는 `confirm_required` (3절) |
| `launcher.py`: `subprocess.Popen(CREATE_NEW_CONSOLE)` + Ctrl+C | 작업마다 별도 프로세스, 중지 | 엔진 작업은 같은 프로세스 (D3). 중지는 `abort`. 로그 파일은 엔진 기록 |
| `scan_4x.py`: `Preview` 의 `axis.position_um()`, `core.getExposure()` | 미리보기 글자 | `progress.data`, `frame_ready` |

### 4.4 T-002 / T-011 에 넘기는 열린 질문

1. **프레임 픽셀의 경로.** 2400 × 2400 uint16 은 11.5 MB 다. `frame_ready` 이벤트는 메타만 담고
   픽셀은 별도 채널로 보낸다. 엔진은 최신 프레임 하나만 들고, 서버의 `/ws/frames` 가 그것을 비닝·늘림
   (`bin_for_display` 와 같은 식) 해 JPEG 로 보낸다. 최신만 남기고 줄을 세우지 않는다 (지금의 점수
   스레드 방식). 느린 브라우저는 프레임을 건너뛴다. 원본이 필요하면 `GET` 으로 한 장 받는다.
   엔진 쪽 계약은 `latest_frame() -> (frame_id, ndarray)` 하나면 된다.
2. **`live` 와 "한 번에 작업 하나" 규칙의 충돌 (T-011).** T-011 은 실행 중 새 작업 명령을 거부한다.
   그런데 지금의 라이브 뷰는 연속 획득을 켠 채로 엣지 추적 (`t`), 서보 (`f`), 스윕 (`w`/`W`),
   경계점 (`b`), tare (`z`) 를 받는다. 추적과 서보는 라이브 프레임을 먹으며 돈다. 그대로 옮기면
   라이브 뷰를 켠 동안 `t` 가 거부된다. 권고: 연속 획득을 작업이 아니라 엔진이 소유한 **획득
   스트림**으로 둔다. 스트림은 단일 소유 규칙에 세지 않고, 작업은 스트림 프레임을 구독한다.
   `scan_4x`, `focus_100x` 처럼 스냅을 직접 하는 작업은 시작할 때 스트림을 멈추고 끝나면 되돌린다.
   `Esc` 와 `abort(op_id 없음)` 은 스트림을 멈추지 않는다. 다른 방법은 `live` 를 바탕 작업으로
   두고 함께 돌 수 있는 작업 표를 엔진이 갖는 것이다. 어느 쪽이든 T-011 에서 정해야 한다.
3. **기록 작업도 `start` 로 보낼지.** 이 문서는 경계점·tare·샘플 열기를 `start` 로 보내 기록을
   남기는 쪽을 제안했다. 다만 2 의 규칙대로면 추적 중 `b`, `z` 가 거부된다. 하드웨어를 움직이지 않는
   기록 작업은 단일 소유 규칙에서 빼거나, 별도 `sample` 명령 하나로 묶기를 권한다.
4. **`update` 의 인자 선언.** 추적 속도 (`speed_um_s`), 라이브 읽기 영역 (`read_region`), 라이브
   노출 (`exposure_ms`) 이 이 문서가 쓰는 이름이다. T-006 의 `edge_trace` 와 이름을 맞춘다.
5. **원격의 `abort`.** 원격은 읽기 전용이다. 다만 원격 화면에서 문제를 본 사람이 멈출 수 있게
   `abort` 만 허용할지 정해야 한다. 멈춤은 움직임을 줄이는 방향이라 허용을 권하지만, 사용자 결정이다.
6. **로컬 화면이 사라진 채 도는 작업.** 탭을 닫아도 작업은 계속된다. 확인이 필요한 작업
   (`confirm_required` 대기) 은 응답이 올 때까지 멈춰 있으면 된다. 엣지 추적처럼 사람이 보며
   쓰는 작업은 로컬 WebSocket 이 모두 끊기면 일정 시간 뒤 스스로 `abort` 할지 정한다. 권고는 "끊긴 뒤
   10 s 에 abort", 시간은 엔진 설정.

---

## 5. 운영 규칙의 화면 강제

(다음 커밋에서 채운다.)

---

## 6. 마일스톤 표시

(다음 커밋에서 채운다.)

---

## 7. F1–F5 화면

(다음 커밋에서 채운다. 범위 조정: `docs/tasks/T-004-ui-spec.md` 의 "v0.2 조정" 절.)
