# 현미경 PC 에서 확인할 것 (2026-10-01 기준)

> **경고 (2026-10-01): 실제 장비에서는 아직 아무것도 움직이지 않는다.** 실제 장비 백엔드(mm-real)는
> main 에 있지만, 벤치에서 Z 접근 때 간격을 확인하는 장치(T-027 가드, T-011 벤치 검사)가 아직 main 에 없다.
> 둘 다 병합될 때까지 현미경 PC 에서는 **읽기 전용**으로만 쓴다. 상태 보기, 카메라 프레임, 광원 켜기/끄기(D15)
> 까지만 하고, 재물대·Z·대물렌즈를 움직이는 작업은 돌리지 않는다. 새 앱의 실제 장비 백엔드는 코드로도 잠겨 있다
> (T-036, main 2c61b7b: `BENCH_MOTION = "LOCKED"`). **기존 `scripts/*` (scan_4x, focus_100x, change_objective 등) 는
> 이 잠금 밖이다.** 9월 30일처럼 그 스크립트를 쓰는 것은 사용자의 판단이고, 쓸 때도 아래 설정 파일 확인(시작·종료 프리셋)을 먼저 한다.
> 잠금은 T-027 과 T-011b 가 병합되고 매니저와 총괄이 확인한 뒤 풀고, 그때 총괄 세션이 이 경고를 지운다.

작성: 총괄 세션. 개발 데스크톱에서는 답할 수 없고, 현미경 PC 에서 읽거나 한 번 돌려 봐야 답이 나오는
항목을 한곳에 모았다. 답이 나오면 이 파일에 적고 총괄 세션에 알린다. 그때까지 코드는 아래의
임시 값으로 돌고, 코드와 기록에 `unmeasured provisional` 로 표시된다.

## 1. 사용자가 정할 것

| # | 질문 | 지금 상태 |
|---|---|---|
| U1 | Python 환경 (PLAN D2): 이 저장소의 uv 환경 하나로 Windows 쪽을 모두 돌릴지 | 권고: uv 하나로 통일 |
| U2 | WSL 시뮬레이션이 실행 기록을 `D:\AutoFocus\records\simulation\` 에 직접 쓸지, 지금 위치에 두고 읽을지 | **통합할 때 정한다** (사용자). mock 은 영향 없음 |
| U3 | 원격 접속 화면에서 정지(abort) 만은 허용할지 | **결정: 허용** (PLAN D13) |
| U4 | 사람이 보면서 쓰는 작업(엣지 추적 등) 중 현미경 PC 의 브라우저가 모두 끊기면 자동 정지할지 | **결정: 10 s 뒤 자동 정지** (PLAN D14) |

## 2. 현미경 PC 에서 읽거나 재 볼 것

### 시뮬레이션 (WSL)

- 실행 중인 시뮬레이션이 진행 상태(현재 step, 전체 step)를 파일로 남기는가. 남긴다면 어디에.
- 궤적(GSD)과 로그 파일의 실제 경로. 서버는 `\\wsl$\<배포판>\...` 로 읽기만 한다.

### 방향 기준

방향은 2026-09-30 실행 기록을 기준으로 한다 (PLAN 5절 Guards). F5 Y 이탈은 +Y 로 먼저 설정했다 (Q12 에서 확인).

### 작업 명세의 질문 Q1–Q21

질문 원문과 이유는 [operations-spec.md 10절](operations-spec.md) 에 있다. 대부분
`C:\agentic_microscope\hardware\focus.py` (FocusAxis) 를 읽으면 답이 나온다.

| 묶음 | 질문 | 어떻게 확인 |
|---|---|---|
| Z 이동과 스윕 | Q1 스윕 시작점 접근 방향, Q2 readback 허용 오차, Q3 `park_at` 반환값, Q4 `best_z_um` 규칙, Q6 `dry_run` 동작, Q7 이동 중 Ctrl+C, Q15 100x 천장 계산 위치, Q21 단계 접근 함수 유무 | FocusAxis 코드 읽기 |
| 렌즈와 PFS | Q5 `require_pfs_quiet`, Q8 렌즈별 상한·작동 거리의 위치, Q13 100x 를 0→2800 µm 로 올리는 안전한 걸음, Q14 `waitForDevice("Nosepiece")` 의미 | 코드 읽기 + 벤치 한 번 |
| 광원과 설정 | Q9 Startup 프리셋의 눈에 보이는 변화, Q10 Aura State 0 이 모든 라인을 끄는지 | 벤치에서 눈으로 |
| XY 와 재물대 | Q11 XYStage readback 오차, Q12 F5 이탈 방향·거리·Y 한계·24 mm 변 방향, Q20 100x 오일에서 Z 후퇴가 필요한 XY 거리 | 벤치 측정 |
| 샘플 맵 | Q16 명시야 4x 타일 Vollath 초점, Q17 명시야 자동 노출 목표, Q18 약 6.7 µm 입자가 4x 모자이크에 보이는지, 그리고 입자 후보 검출 문턱값 (T-032, 지금은 합성 타일로만 맞춤) | 벤치 한 번. 실제 모자이크 하나를 저장해 두면 문턱값은 데스크톱에서 다시 맞출 수 있다 |
| 피에조 | Q19 `PiezoReader` 를 여는 것만으로 바뀌는 것, NanoBench 프로그램과 포트가 겹칠 때 | 벤치 한 번 |

### 초점 판정 임시 상수 (`src/dino_autofocus/focus/verdict.py`)

| 상수 | 임시 값 | 뜻 |
|---|---|---|
| `MIN_DYNAMIC_RANGE_ADU` | 20 | 이보다 밝기 범위가 작으면 읽을 것이 없다고 본다 |
| `MIN_CURVE_CONTRAST` | 0.05 | 초점 곡선의 최소 대비 |
| `IN_FOCUS_DOF` | 1.0 | 이 안이면 `in_focus` |
| `MAX_SIGMA_DOF` | 3.0 | 불확실성이 이보다 크면 `unsure` |

### 매니저가 정한 임시 가드 값

| 값 | 임시 | 측정할 것 |
|---|---|---|
| 큰 XY 이동 문턱 | 대물렌즈별 표 (가드 안). 4x 는 타일 이동 허용, 100x Oil 은 min(시야, 1 mm), 모르는 렌즈는 가장 엄격 | Q20, 렌즈별 표의 값 전부 |
| `z_safe` | 0 µm (완전 후퇴) | Q20 |
| `approach_step_um` (F5 단계 접근 걸음) | 렌즈별 표에 둔다. 100x Oil 10 µm (작동 거리 130 µm 의 약 1/13), 다른 렌즈도 우선 10 µm. 접근은 기존 절차대로 0 → 2800 µm 를 한 번에 간 뒤 2800 부터 걸음으로 올라간다 | Q13. M4 의 실제 벤치 사용 전에 확인 |
| F5 이탈 방향과 거리 | **+Y, 15 mm** (사용자가 +Y 로 먼저 설정, 거리는 15–20 mm 중 짧은 쪽). 재물대 Y 한계를 넘으면 거부 | Q12. M4 전에 확인 |

### 장치 속성 이름 (T-015)

| 질문 | 지금 상태 | 확인 방법 |
|---|---|---|
| Kinetix_red 의 판독 모드 속성 이름과 값 목록 | 카메라 쓰기 허용 목록에 아직 없다. 9월 30일 기록에는 `ReadoutRate = 100MHz 12bit` 로 적혀 있어 이름은 `ReadoutRate` 로 보이지만 확인 전이다 | Micro-Manager 에서 Kinetix_red 속성 목록과 허용 값 읽기 |
| Aura 의 GREEN 외 라인 이름 (VIOLET, CYAN, RED 등) 과 `<LINE>_Intensity` 속성 | GREEN 만 9월 30일에 썼다. 나머지는 `unmeasured provisional` | Aura 장치 속성 목록 읽기 |

### 실제 장비 백엔드 (T-033)

| 질문 | 지금 상태 | 확인 방법 |
|---|---|---|
| **설정 파일을 불러올 때 움직이는 장치를 건드리지 않는가** (T-036b, T-036c) | 설정을 불러오면 Micro-Manager 가 `System` 그룹의 `Startup` 프리셋과 `Property,Core,Initialize,1` 뒤의 `Property` 줄을 스스로 적용한다. 그 안에 ZDrive, XYStage, Nosepiece, PFS 값이 있으면 **열기만 해도 장비가 움직인다.** 9월 30일 기록에는 `LappMainBranch1 State 1` (광경로) 만 적혀 있고 전체는 확인 전이다. Micro-Manager 의 기본 데모 설정은 Startup 에서 대물렌즈를 돌려서 새 검사에 걸린다. 새 앱은 열기 전에 검사해 거부하지만, 기존 `scripts/*` 는 같은 파일을 검사 없이 연다 | 아래 두 명령. 움직이는 장치 이름이 하나라도 나오면 그 설정으로 아무것도 열지 말고 총괄 세션에 알린다 |
| **설정의 종료 프리셋이 움직이는 장치를 건드리지 않는가** (T-036c) | 장치를 내릴 때 Core 가 `System/Shutdown` 프리셋을 적용하는지 확인 전이다. 적용한다면 그 안의 Z·재물대·대물렌즈 값은 끌 때 장비를 움직인다. 새 앱은 Shutdown 프리셋도 같은 규칙으로 거부한다 | 아래 명령의 Shutdown 줄을 본다. 끌 때 적용되는지는 벤치에서 Shutdown 프리셋에 눈에 보이는 무해한 값(광경로 등)이 있다면 끄면서 바뀌는지 본다 |
| 벤치 설정 파일 경로와 Micro-Manager 설치 폴더 | 기존 스크립트(`scripts/mm_grab.py`)는 `C:\agentic_microscope\config\micromanager\single_cam_red_noDMD_nocom10.cfg` 를 쓴다. 설치 폴더는 pymmcore-plus 가 찾는다 | 파일이 있는지, `uv run python -c "from pymmcore_plus import find_micromanager; print(find_micromanager())"` |
| Core 의 AutoFocus 장치가 PFS 인가 | 확인 전 | 설정을 불러온 뒤 Core 의 AutoFocus 역할 읽기 |
| `enableContinuousFocus(False)` 뒤에 꺼짐으로 읽히는가 | 확인 전 | 끄고 `isContinuousFocusEnabled()` 읽기 |
| XY 이동 대기 시간 30 s 가 가장 긴 이동에 충분한가 | `DEFAULT_XY_TIMEOUT_S = 30` 임시값 | 가장 먼 두 점 사이 이동 시간 재기 |
| 재물대 이동 한계 (X, Y) | 실제 장비 백엔드는 지금 "모름" 을 돌려준다. 그래서 **실제 장비에서는 F5 Y 이탈이 거부된다** | 재물대 한계 값 읽기 또는 측정 (Q12 와 함께) |

설정 파일 확인 명령 (현미경 PC 의 PowerShell, 둘 다 읽기만 한다. 장비를 열지 않는다):

```powershell
Select-String -Path "C:\agentic_microscope\config\micromanager\single_cam_red_noDMD_nocom10.cfg" -Pattern "^ConfigGroup,System,(Startup|Shutdown)"
```

T-036b 가 main 에 병합된 뒤에는 새 앱의 검사를 그대로 돌릴 수 있다 (Micro-Manager 를 불러오지 않는다). 불러올 때 설정되는 것을 모두 보여 주고, 문제가 없으면 마지막에 `OK` 를 찍는다. 움직이는 장치가 있으면 `UnsafeConfig` 로 그 이름을 보여 준다:

```powershell
uv run python -c "from pathlib import Path; from dino_autofocus.engine.backends.mm_real import load_time_settings, check_load_settings; p = Path(r'C:\agentic_microscope\config\micromanager\single_cam_red_noDMD_nocom10.cfg'); s = load_time_settings(p.read_text(encoding='utf-8')); [print(x.text()) for x in s]; check_load_settings(s, p.name); print('OK')"
```

### 설치 상태 (T-020)

| 질문 | 왜 필요한가 | 확인 명령 |
|---|---|---|
| git 이 설치되어 있는가 | DINO 백본은 dinov2 클론의 커밋을 `git rev-parse` 로 확인하고, 없으면 실행을 거부한다. 기록 저장소(PLAN D10)도 로컬 git 이다 | `git --version` |
| torch 가중치 폴더는 어디인가 | 그 폴더 아래 `checkpoints` 에 가중치 파일을 둔다 (오프라인 복사) | `uv run python -c "import torch; print(torch.hub.get_dir())"` |
| 원격 보기를 켤 때 Windows 방화벽 창 (T-009) | `--remote-view` 로 서버를 켜면 모든 주소(0.0.0.0)에 바인딩해서, 처음 한 번 방화벽이 허용 여부를 묻는다. **원격 보기가 필요할 때만, "개인 네트워크"만 허용한다.** 공용 네트워크는 허용하지 않는다. 원격 보기를 쓰지 않으면 이 창은 나오지 않는다 | 서버를 `--remote-view` 로 처음 켤 때 |

### 그 밖에 측정할 것 (9월 30일 기록에서)

- 4x→100x 동초점 오프셋. 9월 30일에는 약 −60 µm 였고 기준 시료로 다시 잰다.
- A4000 에서 DINO 지연 시간과 fp16 헤드의 실측 성능.
- 40x WI 대물렌즈의 0.17 mm 보정 링 위치에서의 작동 거리. 이 값이 없으면 40x WI 경로는 막혀 있다.
