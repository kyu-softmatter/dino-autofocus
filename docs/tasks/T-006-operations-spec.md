# T-006 WP-C 준비: 작업(operation)별 명세

- 담당: AF 실행4 · 개발
- 묶음: WP-C 의 선행 문서
- 선행: 없음. T-002 와 파일이 겹치지 않는다
- 배정: 2026-10-01
- 브랜치: `exec4/T-006-operations-spec`

## 목표

WP-C 이식을 기계적으로 만들기 위해, 각 벤치 스크립트가 하는 일을 엔진 작업의
`plan → preflight → run → abort` 단계로 풀어 쓴다. T-002 (실행1) 가드 설계와 T-004 (실행5) UI
명세의 입력이 된다. 이식 코드는 T-002 병합 뒤 별도 과제로 배정한다.

## 소유 경로

- `docs/operations-spec.md` 하나. 코드 변경 없음.

## 내용

대상: `status` (`change_objective.py --status`), `lights_off`, `scan_4x`, `objective_change`,
`focus_100x`, `edge_trace` (`edge_track.py` 와 `live_focus.py` 의 `t` 추적). `find_particle_z` 는
사용 불가 판정이므로 "보류" 로만 적는다. `focus_servo.py` 는 무엇을 하는지 한 단락으로 적고
M1–M3 범위 밖인지 판단을 붙인다.

작업마다:

1. **입력 인자**: 명령행 인자 전부와 기본값, 엔진 명령 인자로 옮길 이름.
2. **plan**: 실행 전에 계산해 보여 줄 수 있는 것 (타일 격자, 스윕 범위, 천장).
3. **preflight**: 시작 전 읽기 확인 (렌즈 라벨, PFS, Z 창, 조명 상태, 샘플의 hole 피팅 유무와 시각).
4. **run**: 하드웨어 호출 순서. 각 호출이 부록의 FocusAxis API 또는 백엔드 메서드 중 무엇에
   해당하는지 표로 적는다 (T-002 부록 목록 기준).
5. **abort / finally**: 중단 시 순서, 소등, Z 를 어디에 두는지.
6. **기록**: 지금 쓰는 파일과 필드 (`scan.json`, `.npy`, `focus100x_*.json` 등). 엔진 기록
   (`log.jsonl`, `summary.json`) 으로 옮길 때 무엇이 어디로 가는지.
7. **확인 지점**: 사용자 승인이 필요한 곳 (렌즈 회전, 오일, 100x 상향 연장) → `confirm_required`.
8. **운영 기록 대응**: `docs/runs/2026-09-30_substrate-scan.md` 의 해당 단계, 그날의 실패 사례
   (광 드롭아웃, 3037/3036 readback, 30 ms 암전, 이중 피크와 오일).

FocusAxis 의 실제 구현(`C:\agentic_microscope`)은 이 PC 에 없다. 사용 방식에서 추론한 동작은
"추론" 으로 표시하고, 현미경 PC 에서 확인할 질문을 마지막 절에 모은다.

문서는 한국어, 코드 이름과 UI 문구는 영어. 표를 적극 쓴다.

## 진행 방식

- `lights_off`, `status`, `scan_4x` 를 먼저 쓰고 커밋한 뒤 매니저에게 `[초안 T-006]` 으로 알린다.
  매니저가 실행1 에 전달한다. 나머지는 같은 브랜치에 이어서 커밋한다 (`--amend` 금지).

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests` 는 변경이 없으니 그대로 통과,
  `git diff main --stat` 에 `docs/operations-spec.md` 만, 커밋 메시지 끝 `Session: AF 실행4`)
- 위 대상 작업이 모두 1–8 항목을 갖고, 인자와 호출 순서가 코드와 일치한다
- 끝나면 `[검토요청 T-006]` 를 검토 세션에
