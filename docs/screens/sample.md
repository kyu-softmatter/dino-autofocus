# `sample` screen contract (T-103 stage A)

Sample and loading-check screen (PLAN.md 2절 F3, 9절 WP-H). This file is the contract between the screen
(`web/src/features/sample/`), its router (`server/api/sample.py`, mounted at `/api/sample` by T-009) and the
engine operations. Layout and wording come from `docs/ui-spec.md` 7.0 and 7.3 (main); they are cited here,
not restated. Section 7 lists the manager's answers (G1–G9); the one item still open is marked **open**.

Names checked against: main 770291d `engine/events.py`, T-009 `server/app.py` (`exec7/T-009-server-skeleton`
b9fb6cc), T-018 `auth/roles.py` (`exec13/T-018-auth-core`).

## 1. Rules this screen follows

- The screen and the router decide nothing about safety. Geometry values feed the engine's safety limits
  (PLAN F3: coverslip thickness → working distance and correction collar, orientation → focus search range);
  the engine computes those limits, never the screen or the router.
- `"Loading confirmed (person + image)"` is shown only when the engine's loading state says all three steps
  are recorded. The screen does not combine the steps itself, and a value selected in a form is not a state
  check (PLAN F3, ui-spec 7.3).
- Sample state is append-only (decision D1 from AF 업무분배보조, PLAN 5절 v0.9): geometry entries and loading
  steps are entries in the open experiment session's `records/sample_events.jsonl`. T-019
  `records.events.fold()` is the only fold; `engine/sample.py` (T-027) projects it into one named sample view
  (geometry, loading, boundary, flags, candidates, `awaiting_return`, last session). `sample.json` and
  `map.json` are derived files. `sample.py` reads only that view and never opens sample files directly (G1).
- Images never go into the prompt context (D7). Prompt context: sample id, geometry values with their
  sources, loading-check state (ui-spec 7.3).

## 2. Geometry fields (provisional, PLAN 10절: F3.1 is not confirmed by the user)

The field list lives in **one place on each side**, so a change is one edit per side:
- engine: one tuple `GEOMETRY_FIELDS` in `engine/sample.py` (T-027, AF 실행1);
- server: `GET /api/sample/geometry-fields` serves that tuple as `GeometryField[]`; the response models
  carry values as `{key: GeometryValue}`, so no field name is hard-coded in `sample.py`;
- web: the form renders from the `geometry-fields` response, labels included; no field name appears in the
  screen code. Until gen:api, the provisional list sits only in the fake client in `features/sample/api.ts`.

`GeometryField` = `{key, label, kind ("number" | "pair" | "choice"), unit, choices[] | null, default | null,
safety: bool}`. Fields with `safety: true` get the safety mark (ui-spec 7.3).

| `key` | Label | Kind, unit | Default | `safety` | Source of the entry |
|---|---|---|---|---|---|
| `sample_size_mm` | Sample size | pair, mm | `[24, 50]` | no | ui-spec 7.3 |
| `chamber_shape` | Chamber | choice (`"hole"`, more TBD) | `"hole"` | no | ui-spec 7.3 (**open**, G5) |
| `hole_diameter_mm` | Hole diameter | number, mm | none (hint: "2026-09-30 sample ≈ 6 mm") | no | ui-spec 7.3 |
| `coverslip_thickness_um` | Coverslip thickness | number, µm | `170` | **yes** | ui-spec 7.3, PLAN F3 |
| `sample_thickness_um` | Sample thickness | number, µm | none | **yes** | PLAN F3.1 |
| `orientation` | Orientation | choice (`"upright"`, `"flipped"`) | none | **yes** | PLAN F3.1 |

Each value carries its source: `GeometryValue` = `{value | null, source: {kind ("entered" | "default" |
"not_set"), by | null, t | null}}`. The screen prints `"entered by <by> <t>"`, `"default"` or `"not set"`.
Sample thickness and orientation have no default on purpose: a guessed safety value must not look entered.
While a safety field is `not_set`, the ops that depend on it refuse (G5); the screen only shows the reason.

## 3. Read endpoints (`server/api/sample.py`, all GET, everyone incl. remote and viewer: `Action.VIEW`)

Response bodies are pydantic models; the TypeScript types are generated from OpenAPI into `web/src/api/`.

| Route | Returns |
|---|---|
| `GET /api/sample/list` | `SampleSummary[]`: `sample_id` (`YYYYMMDD_HHMM_n`), `created`, `fitted_at \| null`, `objectives_used[]`, `last_session {session_id, opened_at} \| null`, `awaiting_return: bool`, `reserved: bool`. Newest first (last three from the sample view, G8). A reserved sample (made by `sample_new`, no session yet) is listed with its id, folder and `created` from the folder; `fitted_at` and `last_session` are null, `objectives_used` is empty |
| `GET /api/sample/geometry-fields` | `GeometryField[]` (section 2) |
| `GET /api/sample/{sample_id}` | `SampleDetail`: the summary + `dir` (path string), `hole {centre_um, diameter_mm, fit_rms_um, n_points, arc_deg, fitted_at} \| null`, `calibration {um_per_px, objective} \| null`, `counts {scans, maps, flags}` |
| `GET /api/sample/access?sample_id=` | `SampleAccess`: the reasons a control is off **before** a click (ui-spec 7.0), worked out by the server from the request, T-018 login/control and engine `snapshot()["sample"]`: `read_only_reason` (remote, role or control, the first that applies), `can_open_folder` (local request only), `open_reason` (a session is open for another sample: `sample_open` / `sample_new` would be refused), `session_reason` (no open session of this sample: geometry and loading ops would be refused). The engine still refuses on its own; this only lets the screen show the reason early |
| `GET /api/sample/{sample_id}/geometry` | `Geometry`: `{values: {key: GeometryValue}}` for every field in section 2 |
| `GET /api/sample/{sample_id}/loading` | `LoadingState`: `session_id \| null`, `geometry {done, by, t}`, `person {done, by, t}`, `image {done, ok, by, t, why \| null, result_ref \| null}`, `confirmed: bool` (from the sample view, G6) |

404 `ApiError` for an unknown `sample_id`. The current sample comes from `GET /api/state`, i.e. engine
`snapshot()["sample"]` = `{sample_id, reserved, session_id}` (T-011), and then from `sample_opened`; not from
`sample.py`.

## 4. Commands (T-009 `POST /api/commands`, body = engine `Command`)

| Input (ui-spec 7.3) | Body | Who may send it |
|---|---|---|
| pick from the list | `{"kind": "start", "op": "sample_open", "args": {"sample_id": "<id>"}}`. Picks the sample for the next experiment session; nothing moves | Local operator with control. No session needed; with a session open for **another** sample the engine refuses (`preflight_failed`) (G4) |
| `"New sample"` | `{"kind": "start", "op": "sample_new"}`. The engine reserves the id and the folder and writes no event (G1); the id comes back in `finished.data.summary.sample_id`. The geometry form then opens, but saving it needs this sample's session, so until one is open it shows the reason `"Open an experiment session first"` (ui-spec 7.0) | Same as `sample_open`: any session that is open must be this sample's, which a new sample never has, so `sample_new` with a session open is refused (G4) |
| geometry `"Save"` | `{"kind": "start", "op": "sample_geometry_set", "args": {"sample_id", "values": {"<key>": <value>}}}`, changed keys only. The engine stamps `by` and `t` | Local operator with control and **this sample's** open session (G4) |
| `"Sample is on the stage"` | `{"kind": "start", "op": "loading_confirm_person", "args": {"sample_id"}}` (manual-step record) | Same as geometry save (G4) |
| `"Check with an image"` | `{"kind": "start", "op": "loading_check_image", "args": {"sample_id"}}`. Turns on brightfield, takes one 4x frame, turns the light off; computed edge check | Same as geometry save (D15, like motion). Gate: camera, DiaLamp, 4x in place (T-028, G7) |

The two session refusals come from the engine as `preflight_failed`, not from the router as 403: the screen
shows their `why` text. While a session is open, the list stays readable but other samples cannot be opened.

`"Open folder"` is not an engine command (it writes no record): `POST /api/sample/{sample_id}/open-folder`,
local requests only. Remote requests get 403 and the screen shows the path from `SampleDetail.dir` instead
of the button. The action that opens Explorer is injected into the router (`app.state.open_folder`), and
tests replace it with a recorder, so tests never open a window (docs/sessions.md). Role for it: any logged-in
local user, never remote (G9, approved).

On refusal, the screen shows the reason next to the control in ui-spec 7.0 order (remote, role, control,
session, gate, running op, preflight), from the 403 `detail` or `preflight_failed.why`. It never works out
a reason itself. Stop: remote clients may send `abort` only; locally anyone logged in may send `abort` and
`lights_off` (decision D2). Both are status-bar controls (T-010), not on this screen.

## 5. Events the screen reads (`/ws/events`)

| Event | Used for |
|---|---|
| `sample_opened` (T-011, G2) | switch the open sample, reload detail, geometry and loading |
| `map_changed` (T-011, G2) | refresh hole summary and counts of the open sample |
| `finished` with `op` in the five ops above | re-read list, geometry or loading; `sample_new` gives the new id |
| `started`, `progress`, `aborted`, `error` for `loading_check_image` | step 3 progress, `"stopped: <why>"` |
| `preflight_failed` | the `why` text next to the control |
| `light_changed` | brightfield on/off during the image check (the status-bar light is the shell's) |

The screen needs no new event for geometry or loading changes: they arrive as `finished` of the op that
wrote them, and the screen re-reads the matching GET.

## 6. Loading check (ui-spec 7.3, three steps)

| Step | Done when (sample view) | Screen |
|---|---|---|
| 1 geometry | every `safety: true` field has an `entered` or `default` value for this sample (G5) | tick, with the source of each safety value |
| 2 person | a `loading_confirm_person` entry in the open session (G6) | tick, `"confirmed by <by> <t>"` |
| 3 image | `loading_check_image` finished with `ok: true` (grade `"computed"`, never a model number) | tick, or `why` when `ok: false` |

`LoadingState.confirmed` true → `"Loading confirmed (person + image)"`; otherwise the missing steps are listed.

## 7. Decisions (manager, via AF 업무분배보조) and open items

| # | Question | Answer |
|---|---|---|
| G1 | Where geometry and loading entries live | The open session's `records/sample_events.jsonl` is the truth. `geometry_set` and `loading_step` are sample-event kinds written through T-019 `session.sample_event()` (T-027). `sample_new` only reserves the id and the folder and writes no event (T-027 option (b)); when the first session for that sample opens, the engine writes `sample_created` as the first event of that session's `sample_events.jsonl`. Until then the sample is `reserved` in the list. `D:\AutoFocus\samples\<id>\` keeps the derived views (`sample.json`, `map.json`) and large files outside git. T-019 `records.events.fold()` is the only fold; `engine/sample.py` (T-027) projects it into one named sample view, the only thing `sample.py` reads |
| G2 | `sample_opened`, `map_changed` not in `EVENT_KINDS` | Added by T-011 |
| G3 | The five op names | T-027 (AF 실행1) uses them as written here |
| G4 | Who may send the five ops | All five use the existing `OPERATE` action (local operator with control). One sample per experiment session (manager, main 9052f48): `sample_open` / `sample_new` need no session and are refused when a session is open for another sample; `sample_geometry_set`, `loading_confirm_person`, `loading_check_image` need that sample's open session. This replaces the earlier "all five need an open session" |
| G5 | `not_set` safety fields; F3.1 field list | Dependent ops refuse while thickness or orientation is `not_set`. **Open**: the field list, units and choices stay provisional until the user confirms F3.1 (PLAN 10절) |
| G6 | Scope of the loading state | Per experiment session and sample; a new session or `sample_open` starts unconfirmed; changing a safety field after confirmation clears steps 2–3 |
| G7 | `loading_check_image` gate and result | Gate in T-028 (AF 실행17): camera, DiaLamp, 4x; not 4x → `preflight_failed`, no objective change. `finished.data.summary` = `{ok, metric, value, grade: "computed", why, frame_ref}`, `end_state` light readback off (field names assumed until T-027) |
| G8 | Source of `awaiting_return` and last session | The T-027 sample view |
| G9 | Role for `"Open folder"` | Any logged-in local user, never remote. A route in `sample.py`, not an engine op |

Until T-027 merges, stage B tests use a fake engine with these op names and a fixture sample root
(`tests/server/fixtures/sample/`) in the G1 shape. They include both session refusals: `sample_open` of another
sample while a session is open, and `sample_geometry_set` without that sample's session.
