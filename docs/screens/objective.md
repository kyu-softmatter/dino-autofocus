# Objective screen contract (T-104, stage A)

Area `objective`: objective change with immersion loading (PLAN 2절 F5) and the 100x focus sweep.
Server: `src/dino_autofocus/server/api/objective.py`. Web: `web/src/features/objective/`.

This is the contract between the two, and with the engine. Behaviour is specified elsewhere and is
cited, not restated:

- Screen: `docs/ui-spec.md` 5.1 (operating rules), 5.3 (verdicts and Z), 7.0 (shared rules, disabled
  reasons), 7.5 (this area), 3.1 C6–C11 (confirm points).
- Operations: `docs/operations-spec.md` 4.2 (`objective_change`, seven steps, abort table) and 7
  (`focus_100x`).
- Directions: PLAN 5절 direction basis (v1.2). ZDrive up = toward the sample, 0 µm = retracted.
- Commands and events: `src/dino_autofocus/engine/events.py` (`COMMAND_KINDS`, `EVENT_KINDS`).

Names marked **assumed** are not yet in engine code; they are listed again under Gaps.

## 1. Read endpoints (`GET`, allowed remotely)

All responses are pydantic models. Z values are encoder readbacks unless the field name says `plan_`.

### `GET /api/objective/state`

| Field | Type | Source |
|---|---|---|
| `nosepiece_state`, `label` | int, str | engine snapshot (last `nosepiece_read()`) |
| `pixel_um` | float | backend `info()` |
| `z_um` | float | last `position` event (encoder) |
| `pfs` | `{enabled, locked, in_range}` | last `pfs_read()` |
| `immersion_loaded_this_session` | `{loaded: bool, immersion, at, by} \| null` | the session's last `manual_step load_immersion` record |
| `awaiting_return` | `{since, return_xy_um, objective_before} \| null` | sample record (ops-spec 4.2 abort table) |
| `running` | `{op_id, op, step, n_steps} \| null` | snapshot |
| `pending_confirm` | `{op_id, key, kind, prompt, options, context} \| null` | snapshot (ui-spec 3.0: survives reconnect) |

### `GET /api/objective/lenses`

One row per lens in the engine's lens table (guards data, BACKLOG "Lens table").

| Field | Type | Notes |
|---|---|---|
| `nosepiece_state`, `label`, `registry_key` | int, str, str | e.g. 5, `6-Plan Apo LmbdD0.13 100x Oil`, `100x-Oil` |
| `magnification`, `na`, `immersion` | float, float, `"dry" \| "oil" \| "water"` | |
| `working_distance_um` | float \| null | provisional values are flagged `"unmeasured provisional"` |
| `selectable` | bool | false when any reason applies |
| `disabled_reason` | str \| null | engine preflight text, quoted as is: `"already on that objective"`, `"not in the lens table"`, `"no working distance value"` (40x WI) |

The server asks the engine to evaluate these reasons; it does not compute them itself.

### `GET /api/objective/plan?target_state=<int>&escape=<bool>`

Returns the engine's `planned` payload for `objective_change` without starting it (dry plan):

| Field | Notes |
|---|---|
| `steps[]` | seven rows `{step: 1..7, name, target}`: record; lights off; `Z -> 0`; `Y -> y + dy` (absent when `escape=false`); rotate to `label`; `load_immersion` (manual); `XY -> return_xy`; `Z approach -> approach_target_um` in `approach_step_um` steps |
| `escape` | `{allowed: false, reason: "escape distance not set"}` until the user sets the Y sign and distance (PLAN 10절). The screen sends `escape=false` only |
| `immersion` | of the target lens |
| `approach_target_um`, `approach_step_um` | 2800 default; step value is open (ops-spec 10 Q) |
| `refusal` | preflight text if the plan itself is refused |

### `GET /api/objective/focus100x/defaults`

| Field | Value / source |
|---|---|
| `z_4x_focus_um` | 4x focus plane of the open sample at the current XY (latest `scan4x_*`), or null |
| `lab_offset_um` | −60 (2026-09-30 run log), with `"to be re-measured"` |
| `centre_um` | `z_4x_focus_um + lab_offset_um`, null when there is no 4x plane |
| `half_um`, `step_um`, `fine_half_um`, `fine_step_um` | 40, 2, 3, 0.2 (ops-spec 7 inputs) |
| `exposure_ms` | 20 (2026-09-30 result, no saturation) |
| `metric` | `"peak"` |
| `ceiling_um` | `min(3200, centre + 0.4 × 130)`, computed by the engine for the given centre |
| `immersion_loaded_this_session` | as in `/state`; false triggers C10 at start |

`GET /api/objective/focus100x/defaults?centre_um=<x>` recomputes `ceiling_um` and an
`above_4x_focus: bool` flag for a centre the operator typed. The screen never raises the range past the
ceiling (ui-spec 5.1).

## 2. Commands (`POST /api/commands`, T-009)

Shape is `engine.events.Command`. `origin="human"`; `user_id` and `session_id` are filled by the server.

| Action | Command | Who |
|---|---|---|
| Rotate | `{kind: "start", op: "objective_change", args: {target_state, escape: false, approach_target_um, approach_step_um}}` | local operator with control, session open |
| Loading done | `{kind: "confirm", op_id, args: {key: "load_immersion", ok: true}}` | **local only, always**, whatever D13 allows; the server refuses it from a remote origin |
| Return to sample position | `{kind: "start", op: "objective_change", args: {resume: true}}` (T-011) | as Rotate; the only motion op allowed while `awaiting_return` |
| Re-load immersion | `{kind: "start", op: "objective_change", args: {reload: true}}` **assumed** | as Rotate; runs steps 2, 3, 5, 6, 7 on the current lens (ops-spec 4.2 item 8) |
| Continue after a dry-lens rotation (C8) | `{kind: "confirm", op_id, args: {key: <event key>, ok: true}}` | local operator |
| Find 100x focus | `{kind: "start", op: "focus_100x", args: {centre_um, half_um, step_um, fine_half_um, fine_step_um, exposure_ms, metric, aura_line, aura_percent, sample_id}}` | as Rotate |
| Answer C9 / C10 / C11 | `{kind: "confirm", op_id, args: {key, ok}}` | local operator |
| Abort | `{kind: "abort", op_id}` | anyone logged in; remote allowed (D13) |
| Lights off | `{kind: "lights_off"}` | anyone logged in, local |

Refusals come back synchronously from `POST /api/commands` (403 remote, permission table) or later as
`preflight_failed`. The screen shows the reason text as is.

## 3. Events read (`/ws/events`)

| Event | Fields used | Drives |
|---|---|---|
| `planned` | `data.steps`, `data.ceiling_um` | plan table, sweep plan |
| `preflight_failed` | `data.why` | reason next to the button |
| `started` | `data.start_state` (`return_xy`, `z_before`, `objective_before`) | step 1 row |
| `progress` | `data.step` (1..7), readbacks per step; for step 7 `{z_um, target_um, step, n_steps}`; for `focus_100x` `{phase: coarse \| fine, z_readback_um, score, sat}` | step rows, Z approach bar (moves per event, never jumps), sweep curve |
| `position` | `z_um`, `x_um`, `y_um` | current Z, readbacks |
| `light_changed` | `dialamp`, `aura`, `verified` | step 1b row, result line |
| `confirm_required` | `data.key`, `data.kind` (`manual_step` for `load_immersion`), `data.prompt`, `data.options`, `data.context` | the loading card (C7) and dialogs C6, C8–C11 |
| `confirmed` | who, when | loading card "done by … at …" |
| `motion` | axis, target, readback | optional detail line |
| `finished` | `data.state` (`done` / `awaiting_return`), `data.summary`, `data.end_state` | result panel, return banner |
| `aborted` | `data.state` (`awaiting_return` or not), `data.why` | step row "stopped", return banner |
| `reading` | `source: "classical"`, `verdict`, `z_encoder_um`, warnings | 100x result badge (T-010 shared component) |

## 4. Gaps (requests to AF 업무분배보조)

1. **`objective` event**: ui-spec 4.0 proposed an `objective` event (`label`, `nosepiece_state`, `pixel_um`).
   `EVENT_KINDS` has none. Either add it, or say which event carries a lens change (`progress` step 4 plus
   `/state`?). The card's event list names `objective`.
2. **Confirm shape**: `events.Command` documents `confirm` args as `{key, ok: bool}`. The card and ui-spec
   write `confirm(op_id, "load_immersion", "done")`. This contract uses `{key: "load_immersion", ok: true}`.
3. **Re-load variant name**: assumed `args: {reload: true}` with no `target_state`, because preflight
   refuses a target equal to the current lens. Needs the manager / WP-J owner to agree.
4. **Dry plan**: `GET /api/objective/plan` needs an engine call that returns `planned` without starting.
   T-011's runner has `submit(cmd)`; a `plan(cmd)` (or `dry_run=True` start that only plans) is needed.
5. **Lens reasons**: the server needs the lens table and per-lens preflight reasons from the engine
   (one call returning rows), so the reasons stay engine text.
6. **Per-step readback payloads**: field names inside `progress.data` for steps 2–6 are not fixed in
   ops-spec 4.2 (it gives the calls, not payload keys). Proposed: `{step, axis, commanded, readback}` plus
   `pfs_in_range` at step 2 and `label_read` at step 4.
7. **`lights_off` remotely**: the manager's D13 note says remote clients may send `abort` only, but T-011's
   D15 section says `lights_off` stays accepted "also when locked or remote under D13". This contract
   follows the manager (local only). Please settle it.
8. **`approach_step_um`** has no value yet (ops-spec 10 Q). The form shows it read-only from the engine.
9. **4x focus plane at XY**: `focus100x/defaults` needs a helper that evaluates the latest `scan4x_*`
   plane (block z fit) at the current XY. Owner unclear (WP-C or WP-J).
