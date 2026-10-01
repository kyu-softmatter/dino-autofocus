# T-020 학습 런북 보강: 오프라인 가중치

- 담당: AF 실행14 · 개발
- 선행: 없음 (T-003 병합됨)
- 브랜치: `exec14/T-020-runbook-offline-weights`

## 소유 경로

- `docs/runbooks/train-focus-head.md`

## 내용

검토 세션 제안 (T-003 병합 때): 런북 1절에 다음을 넣는다.

- DINOv2 가중치는 첫 실행 때 인터넷에서 받아진다. `src/dino_autofocus/backbone.py` 의 로딩 경로를 읽고
  실제로 어느 URL 에서 어느 폴더로 받는지 확인해 적는다 (`torch.hub` 캐시, 보통
  `~/.cache/torch/hub/checkpoints`, `TORCH_HOME` 으로 바뀜).
- 현미경 PC 가 오프라인이면 그 파일을 미리 복사하는 절차와 확인 방법 (파일 이름, 크기, 해시).
- `DINOV2_REPO` 클론 (커밋 7764ea0) 도 같은 방식으로 미리 옮겨야 한다는 점.
- 이 데스크톱에서 가중치를 내려받는 명령을 실행하지 않는다. 코드를 읽어 문서만 쓴다.

## 완료 조건

- 공통 조건, `git diff main --stat` 에 위 파일 하나, 커밋 메시지 끝 `Session: AF 실행14`
- 끝나면 `[검토요청 T-020]`
