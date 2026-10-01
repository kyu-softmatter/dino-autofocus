# T-019 WP-N 실험 세션과 기록 저장소: 핵심 (F7)

- 담당: AF 실행2 · 개발
- 묶음: WP-N (PLAN.md v0.7–v0.8 5절 "실험 세션과 기록 저장소")
- 선행: 없음. 엔진 기록 형식 (T-002 3단계) 과 사용자 id (T-018) 는 문자열 필드로 받는다.
  `server/api/sessions.py` 와 세션 화면은 T-009, T-010 병합 뒤 후속 과제
- 배정: 2026-10-01, 총괄 지시
- 브랜치: `exec2/T-019-experiment-sessions`

## 목표

실험 세션 하나 = 기록 저장소의 브랜치 하나 + 워크트리 폴더 하나. 그 수명주기, 자동 커밋, manifest,
덧붙이기 샘플 이벤트, 가짜 라이브러리언 병합을 UI 없이 돌아가는 모듈로 만든다.
"실험 세션" 은 현미경 측정 한 번이다. Claude 개발 세션과 다르다.

## 소유 경로

- `src/dino_autofocus/records/` (`__init__.py`, `repo.py`, `session.py`, `manifest.py`, `events.py`,
  `committer.py`, `librarian_mock.py`. 나누는 방식은 담당이 정해도 된다)
- `tests/records/` (파일 이름 `test_records_*.py`)

## 결정 (PLAN.md 7절 D10)

- 기록 저장소는 **현미경 PC 의 로컬 git 저장소**. **원격 push 는 만들지 않는다.**
- 경로는 설정 (기본 예: 저장소 `D:\AutoFocus\records`, 세션 폴더 `D:\AutoFocus\sessions\<id>`,
  큰 데이터 `D:\AutoFocus\data\<id>`). 이 데스크톱에는 없으므로 테스트는 `tmp_path` 의 저장소로만.
- git 은 `git` 명령을 subprocess 로 부른다 (새 의존성 없음). 커밋 작성자는 로그인한 사용자.
  매번 `-c user.name -c user.email` 로 넘기고 전역 설정을 바꾸지 않는다.

## 내용

- 세션 열기: 브랜치 `session/<날짜-시각>-<사용자>-<n>` 과 워크트리 폴더. `session.json` 에 사용자,
  샘플, 시작 시각, **이 코드 저장소의 커밋 해시와 미커밋 변경 여부**, 하드웨어 구성 파일 해시.
- 폴더 구조: `session.json`, `log/` (실험 세션 로그), `records/` (작업별 jsonl, 수동 단계),
  `records/sample_events.jsonl` (맵 변경, flag, 입자 위치를 덧붙이기 이벤트로), `manifest.json`
  (큰 파일의 경로, 크기, sha256).
- 큰 파일: 크기 상한 (설정) 을 넘는 파일은 git 에 넣지 않고 데이터 폴더에 두며 manifest 에만.
- **샘플 현재 상태 = 이벤트를 모아 만든 것.** 여러 세션이 같은 샘플을 고쳐도 병합 충돌이 없음을
  테스트로 확인한다.
- 자동 커밋: 작업이 끝날 때와 세션을 닫을 때. **별도 작업자 (스레드 또는 큐) 에서** 돌려 장비 루프를
  막지 않는다. 커밋이 실패해도 측정은 계속되고 실패는 로그에 남는다.
- 닫기: `ready-to-merge` 표시를 남기고, 그 뒤 세션 폴더는 읽기 전용 (쓰기 API 가 거부).
- 이전 세션 열람, 같은 샘플로 새 세션 이어 시작 (F7.4).
- `librarian_mock.py`: `ready-to-merge` 브랜치들을 기록 저장소 `main` 에 병합하는 가짜 라이브러리언.
  이 앱 자체는 병합하지 않는다. 가짜는 테스트와 시연용이다.
- soft-matter-agents `runs/<run_id>/` 와의 연결은 통합 단계. 필드 자리만 둔다.

## 완료 조건

- 공통 조건 (커밋 메시지 끝 `Session: AF 실행2`)
- 테스트 (`tmp_path` 저장소): 열기, 자동 커밋, 큰 파일 manifest, 커밋 실패 시 계속, 닫기 후 읽기 전용,
  두 세션의 같은 샘플 이벤트가 충돌 없이 병합, 가짜 라이브러리언 병합, 코드 버전 기록, push 없음
- 끝나면 `[검토요청 T-019]` 을 검토보조 또는 검토 세션에

## v0.8 보류 사항 (총괄, 2026-10-01)

사용자가 "세션별 브랜치 + 워크트리" 대신 "한 브랜치에 세션별 폴더로 커밋" 하는 구조를 검토 중이다.
결론이 날 때까지:

- **먼저 만든다**: 세션 수명주기 (열기, 닫기, ready-to-merge 표시, 닫힌 뒤 읽기 전용), 세션 폴더 레이아웃,
  `session.json`, `manifest.json` (sha256), 코드 버전 기록, 덧붙이기 이벤트 기록 (`sample_events.jsonl`)
  과 이벤트를 모아 샘플 상태를 만드는 것, 실험 세션 로그.
- **인터페이스 하나 뒤로 미룬다**: git 쪽. 예: `RecordsStore` 프로토콜 (`open_session`, `commit`,
  `close_session`, `list_sessions`). 구현은 테스트용 "git 없음" 구현 (폴더만) 하나만 둔다.
  브랜치/워크트리 구현과 한 브랜치 폴더별 커밋 구현, 자동 커밋 작업자, 가짜 라이브러리언 병합은
  결정 뒤 같은 과제의 후속 단계로 한다.
- 위 "내용" 의 브랜치 이름 규칙과 워크트리 경로는 결정 전까지 쓰지 않는다.

## v0.9 확정 (PLAN.md 070813c, D11). 위 "v0.8 보류 사항" 과 "내용" 의 브랜치/워크트리 부분을 대체한다

- 기록 저장소는 `D:\AutoFocus\records` 하나, 로컬 git, **브랜치는 `main` 하나**. 하위 폴더는
  `microscope\sessions\<session_id>\` (이 앱), `simulation\runs\<run_id>\`, `librarian\`.
- 각자 자기 폴더만 쓰고 남의 폴더는 읽기만 한다. 커밋은 **자기 세션 폴더 경로만 지정**해서 한다.
- 세션 상태는 `open → closed`. 닫힌 폴더는 읽기 전용. `ready-to-merge` 는 쓰지 않는다.
- 브랜치/워크트리 코드는 만들지 않는다.
- 이 과제에 넣는다 (실행2 권고 승인): 한 브랜치 경로 지정 커밋 구현, 별도 작업자의 자동 커밋 (실패해도
  측정 계속), 가짜 라이브러리언 (closed 세션을 읽고 반영 기록을 `librarian\` 에만 쓴다, 병합 없음).
- soft-matter-agents 저장소 (공개) 에는 쓰지 않는다. 시뮬레이션이 어디에 쓰는지는 미해결 (PLAN 10절).
- 완료 조건의 테스트 목록에서 "병합" 은 "같은 샘플의 이벤트를 두 세션 폴더에서 모아도 충돌 없음" 으로 읽는다.

## From the T-004 spec (실행5, 6fcd8a8, ui-spec 5.1)

- Expose the open experiment session's start time (and `None` when no session is open). The engine uses
  it for the "re-trace every session" rule: a hole fit older than the open session's start is stale, and
  with no open session the engine falls back to its own start time.
