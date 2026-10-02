# T-013 WP-L Claude 연동: 서버 쪽 (도구, 실행기, 가짜 공급자, 제안 카드)

- 담당: AF 실행8 · 개발
- 묶음: WP-L (PLAN.md v0.4 5절 "Claude 연동", 6절 11항)
- 선행: 도구 정의와 가짜 공급자는 지금 시작할 수 있다. 엔진 연결은 T-002, T-011 병합 뒤.
  `server/api/assistant.py` 는 T-009 병합 뒤
- 배정: 2026-10-01 작성
- 브랜치: `execN/T-013-assistant-backend`

## 목표

화면의 프롬프트 칸이 보낸 질문과 화면 문맥을 받아, 서버 안에서 Claude 와 대화하고 앱 기능을 도구로
쓰게 한다. **읽기 도구는 바로 실행하고, 동작 도구는 제안 카드만 만든다.** 사람이 확인해야 엔진으로
가고, 확인 뒤에도 게이트와 가드를 그대로 지난다.

## 소유 경로

- `src/dino_autofocus/assistant/__init__.py`, `tools.py`, `runner.py`, `records.py`
- `src/dino_autofocus/assistant/providers/__init__.py`, `fake.py`, `anthropic.py`
- `src/dino_autofocus/server/api/assistant.py` (T-009 병합 뒤)
- `tests/assistant/` (파일 이름 `test_assistant_*.py`)
- 의존성: `anthropic` 패키지 추가는 **T-009 가 병합된 뒤** 이 과제에 `pyproject.toml` 권한을 넘겨서 한다.
  그 전에는 `providers/anthropic.py` 가 함수 안에서만 import 하고, 테스트는 가짜 공급자만 쓴다

## 결정과 제약

- **실제 Claude 호출은 꺼진 것이 기본이다.** D6–D8 (연동 방식, 보낼 수 있는 데이터, 비용 한도) 을
  사용자가 정하기 전에는 켜지 않는다. 설정으로 공급자를 고르고 기본값은 `fake`.
- 테스트는 네트워크와 비용 없이 통과해야 한다. 가짜 공급자는 정해진 대본대로 도구 호출을 낸다.
- API 키는 서버에만 둔다 (환경 변수 또는 `ant auth login` 프로필). 브라우저로 보내지 않는다. 키가
  없으면 상태 API 가 "not connected" 를 돌려주고 나머지 기능은 돈다.
- 구현면은 Anthropic Python SDK 의 Messages API 와 Tool Runner. 기본 모델 `claude-opus-5-5`.
  SDK 사용법은 구현 시점의 공식 문서를 확인한다 (Tool Runner 는 beta 인터페이스).
- 캐싱: 시스템 프롬프트와 도구 목록은 고정해 캐시하고, 화면 문맥과 질문은 그 뒤에 붙인다. 시스템
  프롬프트에 시각이나 매번 바뀌는 값을 넣지 않는다.
- Claude 는 안전 판단과 모션 한계에 들어가지 않는다. Claude 가 낸 숫자는 기록에서 `"model"` 등급.
- D7 이 정해지기 전에는 카메라 프레임과 맵 이미지를 보내는 도구를 만들지 않는다 (텍스트만).

## 내용

- `tools.py`: 도구 정의 한 곳. 두 종류를 형식으로 구분한다.
  - 읽기: 하드웨어 상태 (`snapshot`), 샘플 기록, 맵, 질문과 카드 (T-008 AgentStore), 시뮬레이션
    진행률과 결과 (T-012). 아직 없는 대상은 가짜 구현으로 두고 표시한다.
  - 동작: 이동, 광원, 렌즈 전환, 스캔 시작. 실행 함수가 아니라 **제안 생성 함수**다. 결과는
    엔진 Command 초안 + 사람이 읽을 설명 + 예상 게이트 판정.
- `runner.py`: 대화 루프. Tool Runner 의 턴 훅에서 동작 도구를 가로채 제안으로 바꾸고 기록한다.
  같은 대화 기록을 모든 화면이 이어 본다 (대화 id).
- 제안 카드 흐름: 제안은 엔진 실행기 (T-011) 의 `proposed` 상태로 들어가고 `origin: "assistant"`,
  제안 id, 대화 id 를 가진다. 확인 / 거부 API 는 `server/api/assistant.py` 에. 확인은 루프백에서만
  (T-009 규칙).
- `records.py`: 모든 대화, 도구 호출, 제안, 사람의 확인 / 거부를 기록 파일에. 답변마다 사용 토큰.
- `server/api/assistant.py`: 질문 제출 (스트리밍 응답), 대화 기록, 제안 목록과 확인 / 거부, 연결 상태.

## 테스트

- 가짜 공급자로: 읽기 도구 즉시 실행, 동작 도구가 실행되지 않고 제안만 생김, 확인 전 하드웨어 호출
  없음, 거부 기록, 키 없을 때 not connected, 시스템 프롬프트와 도구 목록이 호출마다 같음 (캐시 조건),
  import 시 `anthropic` 과 torch 가 로드되지 않음.

## 완료 조건

- 공통 조건 (커밋 메시지 끝 `Session: AF 실행N`)
- 네트워크를 끊은 상태와 같은 조건 (가짜 공급자) 에서 전체 테스트 통과
- 끝나면 `[검토요청 T-013]`

## v0.6 조정 (PLAN.md 4652b4b, 7절 D6–D8)

D6 은 권고안으로 진행, D7 은 텍스트만, D8 은 우선 제한 없음으로 결정됐다. 위 "결정과 제약" 의
"D6–D8 결정 전에는 켜지 않는다" 를 아래로 바꾼다.

- **실제 호출은 사용자가 API 키를 넣고 켤 때** 동작한다. 기본 공급자는 계속 `fake` 이고, 테스트는
  계속 가짜 공급자만 쓴다.
- **D7 데이터 정책을 서버 설정 하나로 강제한다**: `prompt_only` | `text` (기본) | `images`.
  `prompt_only` 는 프롬프트와 화면 문맥만 보내고 읽기 도구를 쓰지 않는다. `text` 는 읽기 도구의
  텍스트 결과까지. `images` 는 사용자가 따로 허락하기 전에는 켜지 않는다 (설정값으로 막는다).
- 도구 결과에 이미지가 섞이면 서버가 빼고, 뺐다는 사실을 기록한다. 테스트로 확인한다.
- 연결 상태 API (`GET /api/assistant/status`) 가 공급자 (`fake` | `anthropic`), 연결 여부, **현재 데이터
  단계**를 돌려준다. 화면 상단 표시는 T-010 상태 표시줄이 이 값을 읽어 한다.
- D8: 비용 한도는 없지만 사용 토큰은 답변마다 표시하고 기록한다. 모델 `claude-opus-5-5`.

## Own loop accepted (PLAN 9ebf488, section 5 "Claude 연동", D6). Conditions the loop must meet

1. Read `stop_reason` first. On `refusal` or `max_tokens`, run no tools.
2. When one response has several `tool_use` blocks, run all of them and return every `tool_result` in ONE
   user message. Failed tools come back with `is_error: true`.
3. Append-only history: resend the assistant response content blocks unchanged, thinking blocks included.
4. No forced `tool_choice` (`any` / `tool` returns 400 on claude-opus-5-5). Use `auto`, a prompt instruction,
   and `strict: true` on tool definitions.
5. Set `output_config.effort` explicitly (this model defaults to medium). Do not send a thinking config
   that disables thinking.
6. Server-side refusal fallbacks on by default.
7. Validate tool input against its schema before running the tool.
8. Keep the system prompt and tool list byte-stable so prompt caching works (test: identical bytes across calls).

The review assistant checks each condition against the branch before passing it to the reviewer.

## From the screen contracts (D16)

- The proposal-confirm path checks `WRITE_MAP_FLAG` for `map_flag`, `map_flag_retire`, `candidate_confirm` and
  `candidate_reject`, the same as the map routes. Claude proposals must not bypass D16.

## Status names (from T-010)

- `GET /api/assistant/status` returns exactly `{provider, connected, data_stage}`; the web shell reads these names.
