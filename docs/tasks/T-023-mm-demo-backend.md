# T-023 WP-B: mm-demo backend (Backend protocol on Micro-Manager demo devices)

- Owner: AF 실행11
- Package: WP-B (PLAN.md 5절 Backend)
- Prerequisites: T-002-1 merged (Backend protocol, events, FakeBackend). T-015 (protocol extension, 실행12)
  is not required to start; add its methods when it merges
- Branch: `exec11/T-023-mm-demo-backend`

## Owned paths

- `src/dino_autofocus/engine/backends/mm_demo.py`
- `tests/engine/test_backends_mm_demo.py`

`mm_demo_core.py` (T-017, merged) may get small fixes in this task if needed; list them in the review request.

## Content

- Implement the T-002 Backend protocol on top of `mm_demo_core`. Bench coordinates everywhere (PLAN 5절);
  the demo offset stays inside the core.
- Every motion method goes through the control-token slot defined in T-002.
- Open items from the T-017 review:
  1. Bench retract Z 0 µm is outside the demo Z range (offset 3000). Add a demo-only rule: the demo backend
     maps retract to the lowest reachable bench Z (e.g. 2700) and reports it as `demo_retract` in readback,
     so the guard's retract check still passes on the demo and the record shows the substitution.
     Do not change the guard constants.
  2. Only Aura GREEN is bench-confirmed. Other lines map to the nearest demo wavelength; mark them
     `"unmeasured provisional"` in `info()` and in light readback records.
- Tests skip when the demo adapters are missing. Each test releases its core.
- Tests never open windows and always release what they start (docs/sessions.md).

## Done when

- Common criteria (`uv run pytest`, `uv run ruff check src tests`, owned paths only), commit trailer
  `Session: AF 실행11`
- The T-002 contract tests also run against the mm-demo backend (parametrised, skipped without adapters)
- Send `[검토요청 T-023]` to AF 검토보조1
