# T-018 WP-M 로그인과 로그: 핵심 (X3, X4)

- 담당: AF 실행13 · 개발 (그다음 T-014)
- 묶음: WP-M (PLAN.md v0.7–v0.8 5절 "사용자와 로그인")
- 선행: 없음. `server/api/auth.py` 와 로그인 화면은 T-009, T-010 병합 뒤 후속 과제
- 배정: 2026-10-01, 총괄 지시
- 브랜치: `exec13/T-018-auth-core`

## 목표

계정, 역할, 장비 제어권, 잠금, 세 가지 로그의 핵심을 UI 와 서버 없이 import 되는 모듈로 만든다.

## 소유 경로

- `src/dino_autofocus/auth/` (`__init__.py`, `accounts.py`, `passwords.py`, `roles.py`, `control.py`,
  `audit.py`, `applog.py`. 나누는 방식은 담당이 정해도 된다)
- `tests/auth/` (파일 이름 `test_auth_*.py`), `tests/auth/fixtures/` (가짜 사용자 시드)

`tools/launcher/` 는 T-016 (실행10) 소유다. 런처는 첫 화면 주소만 열고, 로그인 화면으로 보내는 것은
웹 앱이 한다. 그래서 이 묶음은 런처를 고치지 않는다.

## 결정 (PLAN.md 7절 D9, 5절)

- **계정 id 는 계정을 만들 때 쓴 이메일**. 로그인은 이메일 + 비밀번호. 이메일은 대소문자 구분 없이
  비교하고, 한 이메일에 계정 하나.
- **관리자 이메일은 코드와 git 에 넣지 않는다** (저장소는 통합 때 공개된다). 로컬 설정 파일이나 환경
  변수 (예: `DINO_AF_ADMIN_EMAIL`) 에서 읽고, 없으면 첫 실행 설정 단계가 필요하다고 알린다.
  테스트는 `example.test` 같은 가짜 주소만 쓴다.
- 계정 파일은 **저장소 밖 설정 폴더** (예: `%LOCALAPPDATA%\dino-autofocus\`, 인자로 바꿀 수 있게).
- 비밀번호는 표준 라이브러리 `hashlib.scrypt` 로 해시 (솔트, 매개변수를 함께 저장). 원문은 어디에도
  남기지 않는다. 비교는 `hmac.compare_digest`.
- 역할: `admin` (사용자 관리), `operator` (장비를 움직임), `viewer` (보기만). 원격 보기도 로그인 필요.
- 이메일 인증 메일, Google 로그인은 만들지 않는다.

## 내용

- `control.py` **장비 제어권**: 한 번에 operator 한 명. 획득, 반납, 강제 회수 (admin). 엔진이 확인할
  토큰을 낸다. 엔진 쪽 확인은 T-002 의 토큰 자리 / T-011 이 쓴다. **정지 (abort, lights_off) 는 제어권
  없이도, 잠긴 상태에서도 누구나 보낼 수 있다.**
- 잠금: 일정 시간 입력이 없으면 세션 잠금. 잠겨도 진행 중인 작업과 가드는 멈추지 않는다.
- `audit.py` **감사 로그** `audit.jsonl`: 덧붙이기만. 모든 줄에 시각, 사용자 id, 실험 세션 id (없으면
  null), 종류 (로그인, 로그아웃, 명령 제안·확인·실행·거부, Claude 대화). 쓰기는 스레드 안전.
  기존 줄을 고치거나 지우는 API 를 두지 않는다.
- `applog.py` **앱 로그**: 날짜별 파일, 보관 기간이 지난 것 자동 정리. 기록 폴더와 섞지 않는다.
- 실험 세션 로그는 WP-N (T-019) 소유다. 여기서는 만들지 않는다.
- 쿠키 정책 (HttpOnly, SameSite=Strict) 은 서버 후속 과제에서. 여기서는 세션 토큰 발급과 만료만.
- torch, pymmcore, UI 툴킷, 웹 프레임워크 import 금지.

## 완료 조건

- 공통 조건 (커밋 메시지 끝 `Session: AF 실행13`)
- 테스트: 해시 왕복과 틀린 비밀번호, 이메일 대소문자, 중복 계정 거부, 관리자 이메일이 코드에 없음
  (설정이 없을 때의 동작), 역할별 허용, 제어권 단일성과 회수, 잠금 중 정지 허용, 감사 로그 덧붙이기와
  필드, 앱 로그 정리. 실제 사용자 정보는 저장소에 없다
- 끝나면 `[검토요청 T-018]` 을 검토보조 또는 검토 세션에 (docs/sessions.md 의 흐름)

## v0.9 조정 (PLAN.md 070813c, D12)

- 가입 때 받는 것은 **이름, 이메일, 비밀번호**뿐이다.
- 새 계정은 승인 대기 상태로 만들어지고, 관리자가 승인하면서 역할을 정한다. 역할은 본인이 고르지 않는다.
  승인 전의 기본 역할 값은 `viewer` 로 둔다.
- **승인 대기 계정은 로그인할 수 없다.** 로그인 시도에 "승인 대기" 안내를 돌려준다 (총괄 권고대로).
- 생성 시각과 승인한 관리자, 정한 역할은 `audit.jsonl` 에 남긴다.
- 첫 관리자 계정은 위의 설정/환경변수 경로로 만들어지며 승인 절차를 거치지 않는다.

## D16 (PLAN v1.1, 6beb85a)

- Viewers may not submit questions or write map flags. Only an operator on the microscope PC (loopback) may.
- Expose this as named permissions in `roles.py` (for example `SUBMIT_QUESTION`, `WRITE_MAP_FLAG`, both
  operator-only, local-only) so the server routes check them. The UI hiding a button is not enough.
- Tests: viewer and remote operator are refused, local operator allowed.
