# T-001 ruff 기준선 수정

- 담당: AF 실행2 · 개발
- 묶음: 공통 (PLAN.md 8절 소유 경로 밖 파일, 매니저가 명시 배정)
- 선행: 없음
- 배정: 2026-10-01

## 목표

main(1a538c5)에서 `uv run ruff check src tests` 가 3건 실패해 모든 과제의 공통 완료 조건이
막혀 있다. 이 3건만 고친다. 동작은 바꾸지 않는다.

## 소유 경로

- `src/dino_autofocus/live.py`
- `tests/test_live.py`

## 할 일

- `live.py:134` B905: `zip(..., strict=True)`. 두 시퀀스 길이가 같음이 보장되는지 확인하고,
  보장되지 않으면 `strict=False` 와 이유를 한 줄 주석으로 남긴다.
- `live.py:144` E501: 100자 안으로 줄바꿈.
- `tests/test_live.py:20` B905: 위와 같은 기준.

## 완료 조건

- `uv run ruff check src tests` 0건
- `uv run pytest` 통과 (128 passed, 1 skipped 기준선 유지)
- `git diff main --stat` 에 위 두 파일만
- 브랜치 `exec2/T-001-ruff-baseline`, 커밋 메시지 끝 `Session: AF 실행2`
- 끝나면 `[검토요청 T-001]` 을 검토 세션에 보낸다
