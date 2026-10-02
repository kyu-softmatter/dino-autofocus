# T-025 AgentStore follow-up fixes (from the T-008 pre-review)

- Owner: AF 실행6
- Prerequisite: T-008 (28eaec8) merged
- Branch: `exec6/T-025-store-fixes` from main after the merge
- Review: AF 검토보조1 (reviewed T-008)

## Owned paths

Same as T-008: `src/dino_autofocus/agents/{__init__,store,mock_store,sma_files}.py`, `tests/agents/test_agents_*.py`.

## Content

1. Windows MAX_PATH: under a deep root, `SmaFiles` silently skips files because `is_file()` returns False.
   Use the `\?\` long-path prefix for roots on Windows. Any entry that `iterdir()` returns but `stat()`
   cannot see goes into `files` / `not_opened` instead of vanishing. Test with a deep `tmp_path`.
2. `MockStore()` without `write_dir` leaves its `mkdtemp` folder behind. Add `close()` and context-manager
   support that removes a temp dir the store created itself. A caller-supplied `write_dir` is never deleted.

## Done when

- Common criteria, commit trailer `Session: AF 실행6`. Send `[검토요청 T-025]` to AF 검토보조1.

## From the screen contracts

- Add `writable: bool` to the AgentStore protocol (`MockStore` True, `SmaFiles` False), so the console submit
  route need not test the class.

## Summary fields for the console list (from T-100, ui-spec 7.1)

- `QuestionSummary` gains `purpose`, `intent` and `observable_name`; `RunSummary` gains `approval_kind`. Read from
  the card dicts, None when absent.
