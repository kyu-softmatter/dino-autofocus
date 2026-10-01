# T-024 Align operations-spec names with the T-002-1 protocol

- Owner: AF 실행17
- Prerequisite: T-002-1 merged (pre-review passed; the reviewer is merging it)
- Branch: `exec17/T-024-ops-spec-names`
- Review: AF 검토보조2

## Owned paths

- `docs/operations-spec.md`

## Content

검토보조1 found that `docs/operations-spec.md` 0.1 still uses working names. Replace them with the protocol
names in `src/dino_autofocus/engine/backend.py` as merged:

| spec working name | protocol name |
|---|---|
| `xy_move` | `move_xy(x, y, token, timeout_s)` |
| `nosepiece_read` | `nosepiece()` (returns the label) |
| `nosepiece_set` | `set_nosepiece(state, token)` |
| `pfs_read` | `pfs()` (returns `PfsState`) |
| (PFS off) | `pfs_off(token)` |

- Read `backend.py` and `events.py` on main and fix every other mismatch you find in 0.1 and in the
  per-operation call tables. List each change in the review request.
- Names that T-015 (실행12) will add (`describe_devices`, `xy_move_rel`, stream calls) stay as written and
  are marked "T-015".
- Docs only. The spec stays in Korean; keep the existing structure.

## Done when

- Common criteria, `git diff main --stat` shows only this file, commit trailer `Session: AF 실행17`
- Send `[검토요청 T-024]` to AF 검토보조2
