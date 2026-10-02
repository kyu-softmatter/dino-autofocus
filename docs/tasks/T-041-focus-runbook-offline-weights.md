# T-041 Focus-head runbook: offline DINOv2 weights (docs only)

- Owner: AF 실행3
- Branch: `exec3/T-041-runbook-offline-weights`
- Review: AF 검토보조1
- From BACKLOG "런북 보강" (AF 검토's suggestion at the T-003 merge).

## Owned paths

- `docs/runbooks/train-focus-head.md`

## Content

- Section 1: the DINOv2 weights download from the internet on first use. If the microscope PC is offline, copy them
  beforehand into `~/.cache/torch/hub/checkpoints` (give the file names the code expects, read from the focus code;
  do not download anything yourself). Add a one-line check the user can run to confirm the weights are found.

## Done when

- Docs only, no tests. Send `[검토요청 T-041]` to AF 검토보조1. Trailer `Session: AF 실행3`.

## T-041b (AF 실행3; review AF 검토보조1) — no account name in paths

- `docs/runbooks/train-focus-head.md:109` writes the user's Windows account name in a cache path. Use
  `%USERPROFILE%\.cache\torch\hub\checkpoints` (and `~/.cache/...` where the text is shell-neutral). Check the rest
  of docs/runbooks for the same.
