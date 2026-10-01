# T-016 데스크톱 런처를 웹 앱용으로

- 담당: AF 실행10 · 개발
- 묶음: WP-D (PLAN.md v0.3 5절 "런처")
- 선행: 없음. 서버 명령행은 T-009 가 정한 `uv run python -m dino_autofocus.server [--port N] [--remote-view]`
  를 가정한다. T-009 병합 전에는 서버가 없으므로 "서버를 찾지 못함" 경로까지 테스트한다
- 배정: 2026-10-01
- 브랜치: `exec10/T-016-launcher-web`

## 목표

PLAN.md 5절: 데스크톱 exe 는 서버를 띄우고 브라우저를 연다. 지금 exe 는 시스템 Python 으로 tkinter
런처를 띄우는데, 이 데스크톱에는 시스템 Python 이 없다. uv 환경 하나로 바꾼다.

## 소유 경로

- `tools/launcher/` (Launcher.cs, build.ps1, make_icon.py, 아이콘)
- `docs/runbooks/launcher.md` (새 파일. `docs/runbooks/` 의 다른 파일은 T-003 소유라 건드리지 않는다)

`scripts/launcher.py` 는 이식이 끝날 때까지 그대로 둔다 (PLAN.md 5절).

## 내용

- exe 가 `uv` 를 찾아 (`PATH`, 그다음 `%USERPROFILE%\.local\bin\uv.exe` 등 표준 위치) 저장소에서
  `uv run python -m dino_autofocus.server` 를 콘솔 없이 띄운다. 포트가 이미 열려 있으면 새로 띄우지
  않고 브라우저만 연다. 기본 주소 `http://127.0.0.1:<port>/`.
- 서버 준비는 `GET /api/health` 가 응답할 때까지 짧게 기다린다. 시간 초과 시 로그 파일 위치를 보여 준다.
- 서버 출력은 로그 파일로 (예: `%LOCALAPPDATA%\dino-autofocus\server.log`). 기록 폴더와 섞지 않는다.
- 원격 보기는 exe 에서 켜지 않는다 (기본 127.0.0.1 만). 켜는 방법은 런북에만 적는다.
- 옛 tkinter 런처는 옵션 (예: Shift 를 누르고 실행하면 `uv run python scripts/launcher.py`) 으로 남긴다.
- 런북: 빌드 (`build.ps1`), 실행, 종료, 문제 해결.
- 하드웨어 명령 없음. 빌드는 해도 되지만 데스크톱 바로가기를 덮어쓰기 전에 기존 파일이 있는지 보고
  결과를 보고에 적는다.

## 완료 조건

- 공통 조건 (`uv run pytest`, `uv run ruff check src tests`, 소유 밖 diff 없음,
  커밋 메시지 끝 `Session: AF 실행10`)
- `build.ps1` 로 빌드가 되고, 서버가 없을 때 안내 메시지가 뜨는 것을 확인 (결과를 검토요청에 적는다)
- 끝나면 `[검토요청 T-016]`
