# T-026 Launcher follow-ups (from the T-016 merge review)

- Owner: AF 실행10
- Branch: `exec10/T-026-launcher-followups` from main (ac8f928 or later)
- Review: AF 검토보조4

## Owned paths

- `tools/launcher/`, `docs/runbooks/launcher.md`
- `docs/setup-new-pc.md` (launcher and Python sections only)

## Stage 1 (now)

1. `build.ps1 -Out <path>` fails with CS1567 when the folder does not exist. Create the folder first.
2. `docs/setup-new-pc.md` still describes the system-Python launcher. Rewrite those sections for the uv
   launcher (PLAN 4절). Leave the other sections as they are.

## Stage 2 (after T-009 merges with the shutdown route)

3. Stop is `taskkill /T /F`, which skips lights-off and record finish. Call the server's graceful shutdown
   route first (`POST /api/shutdown`, loopback only, see T-009), wait for the process to exit with a
   timeout, and only then fall back to kill. Log which path was taken. Headless test mode covers all three
   outcomes (graceful, timeout then kill, server already gone).

## Done when

- Common criteria, headless tests only (no windows on the desktop), trailer `Session: AF 실행10`.
- Real exe runs are listed as "user check needed" in the review request.
