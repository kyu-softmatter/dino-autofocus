# T-037 Re-tune particle-candidate thresholds on a saved mosaic (offline script)

- Owner: AF 실행16 (after T-022b)
- Prerequisite: T-032 part 1 merged (203a8f7, `engine/mosaic.py` candidate detection)
- Branch: `exec16/T-037-retune-candidates` (from a hash)
- Review: AF 검토보조2
- Director suggestion (checklist Q18): one real 4x mosaic from the bench lets the threshold be re-tuned on the desktop.

## Owned paths

- `scripts/retune_candidates.py` (new file; no other `scripts/*`)
- `tests/test_retune_candidates.py`

## Content

- `uv run python scripts/retune_candidates.py <scan4x_dir or mosaic.npy> [--thresholds ...]` re-runs the T-032
  candidate detection over a range of thresholds and prints counts per threshold (and optionally writes a small
  CSV and a PNG contact sheet into a given output folder, never into the sample folder).
- Read-only on the input; no hardware; no windows (write images to files, do not show them).
- Test on a synthetic mosaic from `engine/mosaic.py` helpers.

## Done when

- Common criteria, trailer `Session: AF 실행16`. Send `[검토요청 T-037]` to AF 검토보조2.

## After merge (efdbcef)

- `scripts/retune_candidates.py::detect_once` swaps `mosaic.detect_blobs` temporarily (restored in finally). Offline
  only: never import it from the server or engine; any later engine use needs a parameter on `detect_blobs`
  instead of the swap (AF 검토).
