# 세션 운영 규칙 (2026-10-01)

이 저장소는 여러 Claude 세션이 역할을 나눠 개발한다. 세션끼리는 메시지와 저장소 파일로만
소통한다. 이 파일은 총괄 세션만 수정한다. 계획은 [`PLAN.md`](PLAN.md) 를 본다.

## 역할

| 세션 이름 | 역할 | 쓰는 곳 | 하지 않는 일 |
|---|---|---|---|
| AF 총괄 · 방향 설계 | 사용자와 방향 결정, 계획서 관리, 문제 최종 정리 | `docs/PLAN.md`, `docs/sessions.md` | 코드 구현, 실행 세션에 직접 배정 |
| AF 매니저 · 업무 분배 | 계획을 과제로 쪼개 실행 세션에 배정. 파일 소유가 겹치지 않게 관리 | `docs/tasks/` | 코드 구현, 병합, 푸시 |
| AF 업무분배보조 · <영역> | 매니저와 영역을 나눠 맡는 두 번째 분배 세션. **화면 영역** (web/src/features/*, web/src/app/assistant·login, 각 영역의 server/api/<영역>.py) 의 과제를 쪼개고 배정하고 추적한다. 과제 번호는 **T-100–T-199** 대역만 쓴다 | `docs/tasks/T-1NN-*.md` | 매니저 영역의 과제 수정, 공유 파일 순서 결정 (`pyproject.toml`, `web/package.json` 은 매니저가 정한다), 병합, 푸시, 코드 구현 |
| AF 검토 · 병합/푸시 | 실행 브랜치를 검토하고 `main` 에 병합, 테스트 후 푸시 | `main` 브랜치 (병합 커밋) | 기능 구현. 큰 수정은 실행 세션에 반려 |
| AF 검토보조N · <T-NNN 또는 대기> (여러 개 가능) | 검토요청 브랜치를 자기 worktree 에서 먼저 확인 (테스트, 소유 범위, PLAN 규칙). 통과한 것만 검토 세션에 넘기고 실패는 실행 세션에 반려 | 자기 worktree (읽기, 테스트 실행) | 병합, 푸시, 공유 폴더 쓰기 |
| AF 실행N · 개발 (늘어나면 같은 규칙) | 배정된 과제를 자기 worktree 브랜치에서 구현하고 커밋 | 배정된 소유 경로만 | 소유 밖 파일 수정, `main` 직접 커밋, 푸시, 하드웨어 명령 |

## Language (2026-10-01)

To save tokens, **sessions talk to each other in English**: cross-session messages, task cards in
`docs/tasks/`, review notes, commit messages, code, comments and new docs. Only the director session
talks to the user in Korean. `docs/PLAN.md` stays Korean for the user; quote its section numbers
instead of restating it. Older Korean task cards stay as they are; write new ones in English.

**The user reads only the director session.** Every other session writes its own window output in
English and keeps it minimal: no end-of-turn summaries for the user, at most one or two lines of status.
Anything that matters goes into a commit, a task card or a message to the right seat. Questions for
the user go to the manager, who sends them to the director; never ask the user in your own window.

## 세션 이름: 지금 하는 일을 보이게

세션 이름은 사이드바에서 지금 무슨 개발을 하는지 알 수 있게 유지한다.

- 실행 세션: `AF 실행N · T-NNN <짧은 작업명>`. 예: `AF 실행1 · T-002 엔진 계약`.
  과제를 받으면 바로 바꾸고, 검토 대기면 끝에 `(검토중)`, 반려면 `(반려 수정)` 을 붙인다.
  과제가 끝나 대기 상태면 `AF 실행N · 대기`.
- 검토 세션: `AF 검토 · <지금 검토 중인 T-NNN 또는 대기>`.
- 매니저와 총괄은 이름을 고정한다.
- 이름은 각 세션이 스스로 바꾼다 (세션 관리 도구의 제목 변경, 대상 self).

## 작업 공간: 실행 세션은 반드시 자기 worktree 에서

모든 세션이 처음에는 같은 폴더 `D:\codes\github\dino-autofocus` 를 공유한다.
한 작업 폴더를 여럿이 쓰면 다른 세션의 미완성 수정이 내 커밋에 섞인다.
그래서 실행 세션은 과제를 받으면 자기 worktree 를 만들어 그 안에서만 작업한다.

```
git -C D:/codes/github/dino-autofocus rev-parse main                     # 해시를 먼저 고정한다
git -C D:/codes/github/dino-autofocus worktree add ../dino-autofocus-wt/execN -b execN/T-NNN-<짧은이름> <그 해시>
```

- 다음 과제는 같은 worktree 에서 **고정한 해시로** 새 브랜치를 만든다: `git switch -c <브랜치> <main 의 해시>`.
  브랜치를 `main` 이라는 이름으로 만들지 않는다. 만드는 사이에 main 이 움직이면 브랜치는 새 main 을, 인덱스는
  옛 파일을 가리켜 최근 커밋을 되돌리는 변경이 스테이징된다 (2026-10-01, exec13, exec14, exec1 에서 세 번).
  만든 직후 `git status --short` 가 비어 있는지 확인한다. 따라잡기용 `git merge main` 은 이 문제가 없다.
- **다른 세션의 worktree 는 건드리지 않는다.** 그 안의 파일을 쓰거나, `git -C <남의 worktree>` 로 add, checkout,
  restore, reset, stash, commit 같은 명령을 돌리지 않는다. 허용되는 것은 status, log, diff, show 같은 읽기뿐이다.
  검토는 자기 검토용 worktree 에서 그 브랜치를 받아서 한다 (2026-10-01, exec13 의 ui-spec.md 가 바뀐 사건).
- **브랜치는 그 주인 세션만 움직인다.** 남의 브랜치를 `update-ref`, `branch -f`, `fetch`/`push` 로 옮기지 않는다.
  체크아웃된 브랜치를 밖에서 옮기면 그 worktree 의 인덱스만 옛 상태로 남아, 다음 커밋이 새 커밋들을 되돌린다
  (2026-10-01, exec13 과 exec1 에서 같은 모양으로 두 번). 내 브랜치를 main 에 맞추는 것은 내 worktree 안에서 `git merge main` 으로 한다.
- **임시 인덱스(`GIT_INDEX_FILE`)는 자기 scratchpad 안의 파일만 가리킨다.** 검토의 `commit-tree` 는 객체만 만들고 참조를 바꾸지 않는다.
- **`git stash` 는 쓰지 않는다.** stash 목록(`refs/stash`)은 모든 worktree 가 하나를 같이 쓴다. 한 세션이 넣은 stash 를
  다른 세션이 꺼내면 남의 옛 변경이 내 인덱스와 파일에 들어온다. 작업을 잠시 치워야 하면 내 브랜치에 커밋하거나
  `git diff > <scratchpad>/x.patch` 로 저장한다.
- **커밋 전에 `git diff --cached --stat` 를 본다.** 내가 올리지 않은 변경이나 최근 커밋을 되돌리는 변경이 보이면 커밋하지 말고 매니저에게 알린다.
- **테스트는 자기 worktree 의 `.venv` 로만 돌린다.** 공유 폴더의 `.venv` 를 여러 세션이 함께 쓰면 멈출 수 있다.
- 공유 폴더(`D:\codes\github\dino-autofocus`)는 검토 세션과 매니저, 총괄만 쓴다.
- 커밋은 경로를 지정한다. `git add -A` 와 `git commit --amend` 는 쓰지 않는다.

## 흐름

```
총괄 --(방향, 우선순위)--> 매니저 --(과제 T-NNN)--> 실행N
실행N --(검토 요청)--> 검토보조 --(1차 통과)--> 검토 --(병합, 푸시)--> 매니저에게 보고
검토 --(충돌/문제: 반려)--> 실행N,  매니저에게 보고
매니저 --(방향 수준의 문제만)--> 총괄 --> 사용자
```

## 메시지 형식

첫 줄에 머리표와 과제 번호를 쓴다. 받는 쪽은 첫 줄만 미리 본다.

- `[배정 T-NNN]` 매니저→실행: 목표, 소유 경로, 완료 조건, 선행 과제, 참고 파일
- `[검토요청 T-NNN]` 실행→검토: 브랜치, 커밋 해시, 바뀐 파일, 테스트 결과
- `[반려 T-NNN]` 검토→실행: 무엇이 충돌하거나 틀렸는지, 고칠 것
- `[보고 T-NNN]` 검토→매니저: 병합된 해시와 푸시 여부, 또는 반려 사유
- `[이슈]` 매니저→총괄: 계획이나 결정이 필요한 문제. 무엇이 막혔는지, 선택지, 권고

## 완료 조건 (모든 과제 공통)

실행 세션은 검토 요청 전에 **자기 과제의 테스트 파일만** 돌린다. 전체 묶음은 돌리지 않는다.

```
uv run pytest <과제의 테스트 파일들>
uv run ruff check src tests
```

- 둘 다 통과하고, 과제가 정한 데모 실행이 하드웨어 없이 된다.
- 소유 경로 밖 파일이 diff 에 없다 (`git diff main --stat`).
- 커밋 메시지 끝에 세션 이름을 적는다. 예: `Session: AF 실행2`.
- 검토 요청에 돌린 테스트 파일 목록을 적는다.

### 전체 테스트 묶음은 검토 쪽에서만 (2026-10-02)

이 데스크톱은 세션 수십 개가 동시에 떠 있어서, 전체 묶음(`uv run pytest`)이 여러 개 겹치면 Windows 의
커밋 메모리가 바닥나 엉뚱한 곳에서 프로세스가 죽는다 (0xc000070a, 0x8007000e). 코드 문제가 아니다.

- 전체 묶음은 검토 세션과 검토보조만 돌린다. **동시에 최대 3개.** 시작하는 세션은 검토 세션에 한 줄로
  알리고, 이미 3개가 돌고 있으면 기다린다.
- 실행 결과에 0xc000070a 또는 0x8007000e 가 나오면 실패가 아니다. 조용할 때 다시 돌린다.
- 맡은 브랜치가 없고 일이 없는 세션은 매니저에게 알린다. 쉬게 할지, 닫을지는 매니저가 총괄을 거쳐
  사용자에게 올린다. 일시 정지는 메모리를 풀지 않고, 세션을 닫아야 풀린다.

## 공통 금지 사항

- **사용자 화면에 창을 띄우지 않는다.** 브라우저 열기, 확인 대화상자, tkinter 창, exe 실행은 테스트에서
  끄거나 대체하고 호출 기록만 확인한다. 시험용 서버는 끝나면 직접 정리한다.
  실제 창을 띄워 봐야 하는 확인은 매니저를 거쳐 "사용자 확인 필요" 로 올린다 (2026-10-01, 8799 포트 사건).
- 하드웨어 스크립트 실행 금지. 이 데스크톱에는 현미경이 없고, 벤치 실행은 사용자가 현미경 PC 에서 한다.
- 데이터셋 생성과 DINO 학습은 현미경 PC 에서만 한다. 데스크톱에서 돌리지 않는다.
- `pyproject.toml`, `uv.lock` 변경은 매니저를 통해 한 세션만 한다.
- 모델 출력으로 모션 한계나 안전 판단을 정하지 않는다 (PLAN.md 5절).

## 병목이 생기면 세션을 늘린다

사용자는 매니저나 검토가 병목이면 세션을 더 띄울 수 있다 (2026-10-01).

- 검토가 밀리면 검토보조를 늘린다. **병합과 푸시는 언제나 검토 세션 하나만 한다.**
  공유 폴더에서 `main` 을 바꾸는 세션이 하나여야 충돌이 없다.
- 매니저가 밀리면 매니저에게 `[이슈]` 를 받아 총괄이 사용자에게 추가를 요청한다.
  매니저를 늘릴 때는 영역을 나눠 맡긴다. 지금은 매니저가 엔진·백엔드·서버 골격·공유 파일 순서를,
  업무분배보조가 화면 영역을 맡는다 (2026-10-01). 과제 번호는 대역으로 나눠 충돌을 막는다:
  매니저 T-001–T-099, 업무분배보조 T-100–T-199. 실행 세션은 매니저가 두 쪽에 나눠 준다.
  `docs/tasks/BACKLOG.md` 는 매니저 것이고, 업무분배보조는 요청만 보낸다.
- 새 세션은 이 파일을 읽고 스스로 이름을 정한 뒤 매니저에게 자리를 알린다.
