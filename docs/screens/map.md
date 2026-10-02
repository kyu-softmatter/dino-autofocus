# `map` screen contract (T-102 stage A)

Sample map screen (PLAN.md 2절 F4). This file is the contract between the screen
(`web/src/features/map/`), its router (`server/api/map.py`, mounted at `/api/map` by T-009) and the
engine operations. Behaviour and wording come from `docs/ui-spec.md` 5.1, 5.3, 7.0 and 7.4 (branch
`exec5/T-004-ui-spec`) and `docs/operations-spec.md` 3, 6 and 8절; they are cited here, not restated.
Items marked **gap** are open requests (section 7).

## 1. Rules this screen follows

- The screen and the router decide nothing about safety. The box check, the retract decision, the
  stale-fit check and all refusals come from the engine (`preflight_failed`, `confirm_required`). The
  hover hint "outside the scanned area" is display only (ui-spec 7.4, click-move step 1).
- Directions (PLAN.md 5절, v1.2): ZDrive up = toward the sample, 0 µm = retract, so a retract shows
  as Z decreasing. The camera image is mirrored against the stage; the stage position of pixel `p` is
  `stage + inv(M) @ (centre − p)`, with the 2026-09-30 4x `M` as the initial calibration. 4x tiles are
  serpentine.
- The map is drawn in **stage µm**. `M` is applied once, by the engine, when it assembles the mosaic
  and places candidates (operations-spec 6.1 run steps 4–5). The screen never uses `M`: a canvas click
  maps to stage µm through the display transform only.
- Display transform: both axes flipped (joystick direction, ui-spec 1.2 (d)): +x to the left, +y down.
  The scale label says so: `"<span> um across   +stage x ←  +y ↓"`. Every layer uses the same transform.
- Z values shown are encoder readback, entered values or plan values, each labelled (ui-spec 5.3).
  Visited fields are coloured by verdict only. Mosaic images never go into the prompt context (D7).

## 2. Read endpoints (`server/api/map.py`, all GET, everyone incl. remote and viewer)

The router reads sample files through one reader function (**gap G1**: where flags and candidates live).
Response bodies are pydantic models; the TypeScript types are generated from OpenAPI (PLAN.md 5절).

| Route | Returns |
|---|---|
| `GET /api/map/{sample_id}` | `MapState`: `boundary[] {x_um, y_um, t}`, `hole {centre_um, diameter_mm, fit_rms_um, n_points, arc_deg, fitted_at} \| null`, `expected_diameter_mm \| null`, `visits[] {x_um, y_um, w_um, h_um, verdict, source}`, `scan_box_um` and `allowed_box_um` of the latest scan (`{x0, x1, y0, y1}` or null), `session_started_at` (experiment session start, else engine start; ui-spec 5.1) |
| `GET /api/map/{sample_id}/results` | `ResultSummary[]`: `result_id` (folder name), `kind` (`scan_4x` \| `sample_map`), `started`, `finished`, `light`, `n_tiles`, `grid_n`, `has_mosaic`, `scan_box_um`, `allowed_box_um`. Sources: `scan4x_*/`, `sample_map_*/` |
| `GET /api/map/{sample_id}/results/{result_id}` | `ResultDetail`: the summary + `tiles[] {name, row, col, x_um, y_um, z_focus_um, focus_note, block_z_um[], blocks_per_side, dropout_z_um[]}`, `fov_um`, `um_per_px`, `mosaic {x0, x1, y0, y1, um_per_px, bin} \| null` |
| `GET /api/map/{sample_id}/results/{result_id}/mosaic.png` | `image/png`, 8-bit grey. Contrast from the 0.5 / 99.8 percentiles of non-empty pixels (`plot_scan.py`). Optional `?max_px=` (default 2048, longest side). 404 with a reason if the result has no mosaic |
| `GET /api/map/{sample_id}/flags?include_retired=false` | `Flag[]`: `flag_id, name, note, t, objective, x_um, y_um, z_um (read), replaces \| null, retired_at \| null` |
| `GET /api/map/{sample_id}/candidates?include_rejected=false` | `Candidate[]`: `candidate_id, x_um, y_um, source (classical_candidate \| person_confirmed \| person_rejected), score, result_id, decides \| null, t, by \| null` |

Mosaic orientation: `mosaic.npy` is assembled as in `plot_scan.py`, tiles already flipped by the sign
of `M` and row 0 = `y0`. The server therefore only reverses the row order so that the PNG has +x to
the right and +y up, matching `x0..x1`, `y0..y1`. It does not flip by `M` a second time. To make this
explicit the server requires `mosaic.json` to say so (**gap G4**); if the field is missing it refuses
with 409 rather than guess.

The current sample id, position, objective and lights come from `GET /api/state` and `/ws/events`
(T-009, T-010), not from `map.py`.

## 3. Commands

### 3.1 Through T-009 `POST /api/commands` (local operator with control and an open session)

| Input (ui-spec 7.4) | Command |
|---|---|
| `"Start tracing"` / `t` | `start edge_trace {sample_id, speed_um_s, hole_diameter_mm, light: "bf"}` (**gap G7** on the arg name) |
| `+` / `-` while tracing | `update {op_id, args: {speed_um_s}}` (T-011 adds `update`) |
| `b` / `u` | `start boundary_mark {sample_id}` / `start boundary_undo {sample_id}` |
| `"Re-trace"` | `start edge_trace` (the engine backs up and asks, C4); `"Clear boundary"` = `start boundary_reset {sample_id}` |
| `"Start scan"` | `start scan_4x {...}` or `start sample_map {...}` with the args of operations-spec 3절 1항 / 6.1 1항 |
| map click | `start goto_xy {sample_id, x_um, y_um}` |
| dialog answers | `confirm {op_id, args: {key, ok}}`; `abort {op_id}` |

The live view keys `b`, `u`, `t` belong to the shell (T-010) and send the same commands.

### 3.2 D16 writes go through `map.py`, not the common endpoint

Flag write, flag retire and candidate confirm/reject write the sample record, so PLAN.md D16 allows
them only for an operator on the microscope PC. They are separate POST routes in `map.py` so that the
check sits in one owned, tested place:

| Route | Body | Engine command it submits |
|---|---|---|
| `POST /api/map/{sample_id}/flags` | `{x_um, y_um, name, note, replaces?}` | `start map_flag {sample_id, x_um, y_um, name, note, replaces}` (a note edit is a new flag with `replaces`) |
| `POST /api/map/{sample_id}/flags/{flag_id}/retire` | `{}` | `start map_flag_retire {sample_id, flag_id}` |
| `POST /api/map/{sample_id}/candidates/{candidate_id}/confirm` | `{note?}` | `start candidate_confirm {sample_id, candidate_id}` |
| `POST /api/map/{sample_id}/candidates/{candidate_id}/reject` | `{note?}` | `start candidate_reject {sample_id, candidate_id}` |

Every one of these routes:
1. passes T-009's loopback/origin middleware (remote requests get 403 before the route runs);
2. checks T-018 `auth/roles.py` `WRITE_MAP_FLAG` (operator, local) for the logged-in user; refusal is
   403 `{"detail": "Needs the operator role on the microscope PC"}`;
3. submits the command with `user_id` and `session_id` and returns `CommandAccepted {op_id}`. The
   entry itself is written by the engine; the screen sees it via `map_changed`.

None of these overwrite: confirm/reject add an entry with `decides: <candidate_id>`, retire adds
`retired_at`, a note edit adds a flag with `replaces` (ui-spec 7.4, operations-spec 6.2).

Bypass: `/api/commands` must refuse these four op names, otherwise a viewer could post them there
(**gap G2**). Assistant proposals for them must pass the same check when a human confirms (**gap G3**).

## 4. Events the screen reads (`/ws/events`)

| Event | Used for |
|---|---|
| `map_changed` (**gap G5**) | boundary, hole fit, visits, flags, candidates of the open sample; the screen re-reads the matching GET |
| `sample_opened` (**gap G5**) | switch `sample_id`, reload all layers |
| `position` | current field rectangle, Z readback, click-target distance |
| objective label (**gap G5**) | field-of-view size of the current field rectangle |
| `planned`, `started`, `progress`, `finished`, `aborted`, `error` | edge-trace and scan panels (tile k/n, curve, dropped frames, path length, points), click-move steps, results list refresh on `finished` |
| `preflight_failed` | the `why` text next to the control (ui-spec 7.0 disabled-reason table) |
| `confirm_required` | C1–C5, C12 dialogs; answered with `confirm` |
| `light_changed` | the end-of-operation light line in the panels (status bar is the shell's) |

## 5. Map layers (bottom to top; ui-spec 7.4 layer table)

| Layer | Data |
|---|---|
| Mosaic | `mosaic.png` of the result picked in the results panel, placed at `mosaic {x0..y1}` |
| Scan box | `allowed_box_um` of the picked result (or of the latest, from `MapState`) |
| Visited fields | `MapState.visits`, verdict colour (ui-spec 5.3) |
| Boundary and hole | `MapState.boundary`, `hole`; fit time and "this session / previous session" against `session_started_at` (ui-spec 5.1) |
| Candidates | `/candidates`: hollow circle = classical, filled = person confirmed, grey × = rejected (hidden by default) |
| Flags | `/flags`; retired hidden by default |
| Current field | `position` + objective field of view |
| Click target | display only: stage µm under the cursor, distance from `position`, inside/outside `allowed_box_um` |

## 6. Click-to-move (ui-spec 7.4 steps 1–6) as events

| Step | Screen | Events and the fields the screen reads |
|---|---|---|
| 1 hover | target, distance, hint | none |
| 2 click | pin; `start goto_xy` | `planned {distance_um, large_move, retract_needed, z_safe_um, provisional}` |
| 3a outside | pin turns red ×, reason | `preflight_failed {why}`; nothing moves |
| 3b other refusal | reason in the same place | `preflight_failed {why}` |
| 3c retract needed | C12 dialog | `confirm_required {key: "retract_then_move", z_um, z_safe_um, x_um, y_um}` → `confirm` |
| 4 retract | `"Retracting Z <z> -> <z_safe>"`, Z readback going down | `progress {step: "retract"}`, `position` |
| 5 XY move | `"Moving to (x, y)"`, field rectangle moves | `progress {step: "move_xy"}`, `position` |
| 6 done | `"Arrived (x, y read back). Z left retracted at <z>: refocus with a scan tile or focus_100x"` | `finished {x_um, y_um, z_um, retracted}` (readback) |

The screen never raises Z after arrival; it shows only the refocus hint and buttons to the next focus
operation (operations-spec 6.3 run step 4). An `aborted` or `error` at any step clears the pin and
shows the reason. Field names in this table are assumed (**gap G6**).

## 7. Gaps (requests to AF 업무분배보조 for the manager)

| # | Gap | Proposal |
|---|---|---|
| G1 | Where flags, candidates and boundary edits are stored: operations-spec 6.1/6.2 says `<sample>/flags.json`, `features.json`, `map.json`; PLAN.md 5절 (v0.9) says append-only `records\sample_events.jsonl` in the experiment session folder, with sample state folded from events | One reader in the engine (`engine/sample.py`, T-002-3 or its successor) that returns the folded map state, flags and candidates; `map.py` calls only that. Also decide whether flag and candidate writes need an open experiment session (they do if they go to the session folder) |
| G2 | `/api/commands` accepts any op name, so it would bypass D16 | T-009 owner: refuse `map_flag`, `map_flag_retire`, `candidate_confirm`, `candidate_reject` on `/api/commands` with 403 "use /api/map" |
| G3 | Claude proposals (T-013) for the same ops are confirmed outside `map.py` | The proposal-confirm path checks `WRITE_MAP_FLAG` for these ops |
| G4 | `mosaic.json` has only `x0, x1, y0, y1, um_per_px, bin` | Add `orientation: "stage"` (tiles flipped, row 0 = y0), `M_px_per_um` used, `objective`, `n_tiles`. Also make `scan_4x` write `mosaic.npy` + `mosaic.json` with the same helper, so its results get a mosaic without the server assembling tiles |
| G5 | `map_changed`, `sample_opened` and an objective event are not in `engine/events.py` `EVENT_KINDS`; `update` is not in `COMMAND_KINDS` | T-011 (owner of `events.py`): add them, or say which existing kind carries them (e.g. objective label inside `position.data`) |
| G6 | Event payload fields for `goto_xy` (section 6) and the scan box | `goto_xy` emits the fields in section 6; `scan_4x` / `sample_map` `summary.json` record `scan_box_um` and `allowed_box_um` so the screen does not recompute the guard box |
| G7 | Edge-trace diameter arg: ui-spec 7.4 `expect_diameter_mm`, operations-spec 8절 `hole_diameter_mm` | Use `hole_diameter_mm` (the engine-facing spec) |
| G8 | Ids: candidates and flags have no ids in operations-spec 6.1/6.2 | Engine assigns `candidate_id` / `flag_id` (stable, unique per sample); decisions reference them with `decides` / `replaces`. A reject is a new entry with `source: "person_rejected"` (operations-spec 6.1 names only the other two) |
| G9 | Op names `map_flag_retire`, `candidate_confirm`, `candidate_reject` are proposals (ui-spec 7.4) | Confirm the names with the WP-C/WP-I engine work |

Until the engine side merges, stage B tests use a fake engine with these command names and a fixture
sample folder in the G1/G4 proposed shape.
