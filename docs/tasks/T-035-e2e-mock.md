# T-035 M1 end-to-end mock tests (PLAN 8 M1: F1–F5 without hardware)

- Owner: AF 실행6
- Prerequisites: grows with merges. Start with what is on main (MockBackend T-021, mock world T-007, records T-019,
  auth T-018, agent store T-008/T-025); add steps as T-011, T-009/T-009b, T-027, T-028, T-029, T-031, T-032 land.
- Branch: `exec6/T-035-e2e-mock` (from a hash; merge main as pieces land)
- Review: AF 검토보조1

## Owned paths

- `tests/e2e/` (file names `test_e2e_*.py`), `tests/e2e/conftest.py`

## Content

- One scripted M1 day on the mock, through the engine (and through the server's TestClient once T-009 is on main):
  log in as a local operator (example.test), take control, open an experiment session, hardware_scan + gates (F2),
  sample geometry and loading (F3), edge_trace + scan_4x + sample map + flag + goto_xy (F4), objective change 4x →
  100x Oil with the loading confirm and stepwise approach (F5), focus_100x, lights_off, close the session.
- Assert the safety properties on the way: lights off on every non-normal end, motion refused without control or
  session, remote abort only, records carry user_id and session_id, sample events fold to the expected state.
- Steps whose op is not on main yet are `pytest.skip` with the task number, so the suite shows M1 progress.
- No windows, no network, temp dirs only.

## Done when

- Common criteria, trailer `Session: AF 실행6`. Send `[검토요청 T-035]` (first version with what exists) to
  AF 검토보조1; later steps as follow-up commits.

## T-035b (AF 실행6; review AF 검토보조1) — lower the e2e memory footprint

- Crash frames now point at tests/e2e (검토보조3, three full runs on 121456c/336ec69): scipy.special import via
  mock_world.py:47 while collecting tests/e2e/conftest.py:35; `git` subprocess in GitFolderStore.ensure_repo from the
  `bench`/`day` fixtures (conftest.py:201, 368, 378); and edge_trace in test_e2e_m1_day.py:166. Runs before tests/e2e
  landed had no faults. The machine's commit charge is the limit (BACKLOG), and e2e is the heaviest part.
- Reduce it: one records repo per module or session (not `git init` per test fixture), reuse one mock world per
  module, and import scipy lazily where only some tests need it (mock_world.py is T-021's; a lazy import there is
  allowed in this task, imports only). Measure peak memory before and after (e.g. psutil in a conftest hook or
  `pytest --durations`), and put the numbers in the review request.
- Keep coverage the same. Done when tests/e2e passes alone and in the full run, and the peak is lower.
