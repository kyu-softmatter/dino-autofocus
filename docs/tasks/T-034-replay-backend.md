# T-034 WP-B: replay backend (saved z-stacks replayed through the Backend protocol)

- Owner: AF 실행12
- Prerequisites: T-005 (stacks), T-015, T-021 merged (done)
- Branch: `exec12/T-034-replay-backend` (from a hash)
- Review: AF 검토보조2

## Owned paths

- `src/dino_autofocus/engine/backends/replay.py`, `tests/engine/test_backends_replay.py`

## Content

- The Backend protocol over `engine/backends/stacks.py` (T-005): `snap()` returns the frame nearest the current z
  of the loaded ZStack (in-memory, synth shard, or samples scan/stack folders); z moves go through the token slot
  and only change the virtual z; XY moves pick another stack if the source has several, else stay.
- Lights: virtual states with readback; the allow-list and token checks as in mock/mm-demo.
- Pass T-015's `BackendContract` (in-memory stacks in tests; real `data/` only with skip when absent).
- `info().bench = False`.

## Done when

- Common criteria, trailer `Session: AF 실행12`. Send `[검토요청 T-034]` to AF 검토보조2.
