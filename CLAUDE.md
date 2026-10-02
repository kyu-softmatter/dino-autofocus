# dino-autofocus

Frozen DINOv2 features for microscope autofocus (focus score / signed z-error), plus a local
web app (FastAPI + React, mock-first) that will become a hardware engine for soft-matter-agents.

## Commands (always through uv; Node comes from the uv `web` group)
- `uv sync` · `uv run pytest <test files>` · `uv run ruff check src tests`
- Server: `uv run python -m dino_autofocus.server --port 8765` (add `--dev-origin http://localhost:5173` for Vite dev)
- Web: `uv run npm --prefix web ci | run dev | test | run typecheck | run build`

## Docs
- `docs/PLAN.md` — goals, requirements F*, current state, architecture, design rules, decisions D* (Korean)
- `docs/ui-spec.md` — screen and behaviour spec · `docs/operations-spec.md` — engine operations (plan/preflight/run/abort)
- `docs/sessions.md` — multi-session roles and git rules · `docs/tasks/` — task cards; `BACKLOG.md` HANDOVER section = current state
- `docs/screens/` — per-screen notes · `docs/runbooks/` — launcher, first bench motion, head training
- `docs/runs/` — bench run records · `docs/synthetic-results.md` — first synthetic DINO check
- `docs/integration-notes.md` — dinov2 and sibling-repo findings · `docs/setup-new-pc.md`, `docs/microscope-pc-checklist.md` — PC setup and bench checks
- **Do not read PLAN.md, ui-spec.md or operations-spec.md whole.** Grep `^## ` for the section index (or a D/F/T number), then Read only that line range.

## Rules (summary of docs/sessions.md)
- Code, comments, commits, task cards in English; PLAN.md stays Korean.
- Execution work happens in your own worktree/branch; never touch other sessions' worktrees or branches, no `git stash`, no `git add -A`/`--amend`; check `git diff --cached --stat` before committing.
- Run only your task's tests; the full suite is for review seats (max 3 at once, memory limits). 0xc000070a / 0x8007000e = rerun, not a failure.
- Never run hardware scripts, dataset generation or DINO training on this desktop; never open windows/browsers from tests.
- `pyproject.toml` / `uv.lock` change through the manager only. Model output never sets motion limits or safety (PLAN.md 5).
