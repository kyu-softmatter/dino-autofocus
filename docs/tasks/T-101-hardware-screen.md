# T-101 WP-G hardware screen (F2): server router and web area

- Owner: AF 실행19
- Package: WP-G screen part (PLAN.md 2절 F2, 9절). Assigned by AF 업무분배보조 (screen areas)
- Prerequisites: stage A none. Stage B: T-009 (server skeleton) and T-010 (web shell) first skeleton merged.
  The engine side (`hardware_scan`, gate rules, `hardware_confirm`) is the manager's WP-G work; until it
  merges, the router and tests use a fake engine with the same command names
- Branch: `exec19/T-101-hardware-screen`
- Review: `[검토요청 T-101]` to AF 검토보조4 (AF 검토보조3 if 4 has more than three queued)

## Owned paths

- Stage A: `docs/screens/hardware.md` (new)
- Stage B: `src/dino_autofocus/server/api/hardware.py`, `tests/server/test_api_hardware.py`,
  `web/src/features/hardware/`

Not yours: `engine/` (including `gates.py`, `operations/hardware_scan.py`), the rest of `server/` (T-009),
`web/` outside `features/hardware/` (T-010; the common status bar and `"Lights off"` button are the shell's),
`web/src/app/assistant/` (T-014), `web/package*.json`, `pyproject.toml`.

## Content

Spec: `docs/ui-spec.md` 5.2, 7.0 and 7.2 (branch `exec5/T-004-ui-spec`, 6fcd8a8, until it merges);
`docs/operations-spec.md` 5절 for `hardware_scan` and the profile fields. Cite them; do not restate them.

Stage A, contract (short, English):
- Endpoints: `GET` the hardware profile (`hardware_profile.json`), `GET` the gate table (feature, on/off,
  reasons, required devices), `GET` the last `status` result. Commands go through T-009's
  `POST /api/commands`: `hardware_scan`, `hardware_confirm` (proposed, WP-G), `status`, `light_set`,
  `lights_off`. Events read: `position`, `light_changed`, `finished(status)`.
- Field list for each panel in ui-spec 7.2 (devices, objectives, camera/piezo, human-confirmed items,
  gates, current state, lights), and which engine piece provides it. Missing pieces become requests to
  AF 업무분배보조, who forwards them to the manager.
- Remote and role rules: reads for everyone; scan and confirm need the local operator with control.
  PLAN v1.1 D15: `light_set` and `lights_off` are M3 items; `light_set` needs the operator with control and
  an open experiment session, like motion. `lights_off` stays available to everyone as a stop (PLAN 5절).

Stage B, implementation (mock first):
- `hardware.py`: router registered through T-009's mechanism, read endpoints only; commands use the common
  command endpoint. Pydantic response models.
- `features/hardware/index.tsx` by the T-010 registration rule. Panels from ui-spec 7.2. Disabled features
  stay visible with their reason (F2.2); the screen never decides a gate, it draws the engine's verdict.
- Light state follows ui-spec 5.2 (readback, not the requested value).
- UI text in English. Generated types from `web/src/api/` only.

## Tests

- pytest with `TestClient` and a fake engine/profile: profile and gate endpoints, unknown-feature 404,
  remote/role refusals as T-009 defines them.
- vitest: gate table shows off features with reasons, problem devices sort first, human-confirmed item form
  disabled in read-only mode, light panel shows readback.
- Tests never open browser or desktop windows, and stop any server they start. No hardware scripts.

## Done when

- Common criteria (`uv run pytest`, `uv run ruff check src tests`, owned paths only in
  `git diff --stat main...HEAD`), T-010's npm checks (`ci`, `build`, `test`, type check)
- Commit with `git commit -- <paths>`; no `git add -A`, no `--amend`, no push. Trailer `Session: AF 실행19`
- `[검토요청 T-101]` to the review assistant above, with branch, hash, changed files and test counts
