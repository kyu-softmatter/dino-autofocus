# T-104 WP-J objective screen (F5 and 100x focus): server router and web area

- Owner: AF 실행5 (after its ui-spec follow-up, once T-004 merges)
- Package: WP-J screen part (PLAN.md 2절 F5, 9절). Assigned by AF 업무분배보조 (screen areas)
- Prerequisites: stage A none. Stage B: T-009 (server skeleton) and T-010 (web shell) first skeleton merged.
  The engine side (`objective_change` incl. the resume and re-load variants, `focus_100x`) is the manager's
  WP-J/WP-C work; until it merges, tests use a fake engine with the same command names
- Branch: `exec5/T-104-objective-screen`
- Review: `[검토요청 T-104]` to AF 검토보조4 (AF 검토보조3 if 4 has more than three queued)

## Owned paths

- Stage A: `docs/screens/objective.md` (new)
- Stage B: `src/dino_autofocus/server/api/objective.py`, `tests/server/test_api_objective.py`,
  `web/src/features/objective/`

Not yours: `engine/`, the rest of `server/` (T-009), `web/` outside `features/objective/` (T-010; the
status-bar "Waiting: load immersion oil" and "Return to sample position" banner are the shell's, fed by the
same events), `web/src/app/assistant/` (T-014), `web/package*.json`, `pyproject.toml`.

## Content

Spec: `docs/ui-spec.md` 5.1, 5.3, 7.0 and 7.5; `docs/operations-spec.md` 4.2 and 7절; PLAN 2절 F5 and v1.2
direction conventions (ZDrive up = toward sample, 0 = retract). Cite them; do not restate them.

Stage A, contract (short, English):
- Endpoints: current objective state, lens table rows with the disabled reason per lens, the planned
  seven steps for a chosen target, the 100x form defaults (centre computed from the 4x focus plane minus the
  lab offset, ceiling `min(3200, centre + 0.4 × 130)`, immersion-loaded flag for this session).
- Commands through T-009's `POST /api/commands`: `objective_change`, `confirm(op_id, "load_immersion",
  "done")`, the resume and re-load variants (names to agree with the manager), `focus_100x`. Events read:
  `started`, `progress(step=…)`, `position`, `objective`, `light_changed`, `confirm_required`, `finished`,
  `preflight_failed`.
- Gaps become requests to AF 업무분배보조, who forwards them to the manager.
- Rules: the Y step-out is +Y, 15 mm, "unmeasured provisional" (PLAN v1.3, fbc1e08). The screen shows the
  sign and distance read-only from the engine with that mark and never offers free entry; if the engine
  refuses `escape`, show its reason. The 40x WI has no working distance and stays
  disabled. `"Loading done"` is local only, always, whatever the remote setting. Rotate, return, re-load and
  100x focus need the local operator with control and an open experiment session.

Stage B, implementation (mock first):
- `objective.py`: read endpoints only; commands use the common command endpoint. Pydantic response models.
- `features/objective/index.tsx` by the T-010 registration rule: change panel (current, pick, options, plan,
  rotate), seven-step progress with readbacks, the big loading card, the Z approach bar that moves step by
  step (never a jump to the target), the 100x form, curve against `z_readback_um` with the ceiling line and
  saturated points, result with the classical verdict badge and encoder Z from the T-010 shared component.
- Upward extension after a top-edge peak lives only in the engine's confirm dialog; the form never raises
  the range past the ceiling. UI text in English.

## Tests

- pytest with `TestClient` and a fake engine: state, lens table reasons (same lens, not in table, no WD),
  plan, 100x defaults, remote/role refusals; `"Loading done"` refused from a remote origin even when other
  remote commands are allowed.
- vitest: a scripted event sequence drives the seven steps, the interrupted state shows the return action,
  the step-out shown read-only with its provisional mark, escape refused with the engine's reason,
  read-only mode.
- Tests never open browser or desktop windows, and stop any server they start. No hardware scripts.

## Done when

- Common criteria (`uv run pytest`, `uv run ruff check src tests`, owned paths only in
  `git diff --stat main...HEAD`), T-010's npm checks (`ci`, `build`, `test`, type check)
- Commit with `git commit -- <paths>`; no `git add -A`, no `--amend`, no push. Trailer `Session: AF 실행5`
- `[검토요청 T-104]` to the review assistant above, with branch, hash, changed files and test counts
