# `hardware` screen contract (T-101 stage A)

Area `hardware` (PLAN.md 2절 F2, 9절 WP-G). This file gives the endpoints, commands and events the
screen uses, and the engine piece behind each panel. Layout and wording: `docs/ui-spec.md` 7.0, 7.2 and
5.2 (branch `exec5/T-004-ui-spec` 6fcd8a8). `hardware_scan` steps and profile fields:
`docs/operations-spec.md` 5절. Neither is restated here.

Names checked against: main b164e97 `engine/events.py`, T-002 stage 2 `engine/gates.py`
(`exec1/T-002-stage2-fix`), T-009 `server/app.py` and `server/api/__init__.py`
(`exec7/T-009-server-skeleton`), T-018 `auth/roles.py` (`exec13`).

## 1. Read endpoints (`server/api/hardware.py`, mounted at `/api/hardware`)

All are `GET`, open to remote viewers and every role (`Action.VIEW`). None of them reaches the backend:
they read the last profile and gate verdict that the engine already holds.

| Path | Response model | Body |
|---|---|---|
| `/api/hardware/profile` | `HardwareProfileOut` | `{"profile": <hardware_profile.json> \| null, "path": str \| null, "sha256": str \| null}`. `null` = never scanned; the screen shows `"Not scanned yet"` |
| `/api/hardware/gates` | `list[GateRow]` | One row per gated operation, off rows first, then by `op` |
| `/api/hardware/gates/{op}` | `GateRow` | 404 `ApiError` for an unknown `op` |
| `/api/hardware/status` | `StatusResultOut` | Last `finished(status)`: `{"op_id", "t", "user_id", "summary"}` or `null` if `status` has not run since the server started |

`GateRow` = `{op, enabled, reasons: list[str], requires: {devices, objectives, confirmed}}`. It joins
`gates.Gate` (the requirement) with `gates.GateResult` (the verdict). The router copies the engine's
verdict and never evaluates a gate itself (F2.2, PLAN 6절 2항).

Light state has no endpoint of its own. It comes from `/api/state` when the screen connects and from
`light_changed` after that (ui-spec 5.2).

## 2. Commands (T-009 `POST /api/commands`, body = engine `Command`)

| Button (ui-spec 7.2) | Body | Who may send it |
|---|---|---|
| `"Scan hardware"` | `{"kind": "start", "op": "hardware_scan", "args": {"include_properties": true, "piezo_port": ""}}` (`""` skips the piezo; G10) | Local operator with control. No experiment session needed (nothing moves, nothing turns on) |
| Save human-confirmed items | `{"kind": "start", "op": "hardware_confirm", "args": {"items": {"<item>": "<value>"}}}` | Same as scan. The engine stamps `by` (user id) and `at` |
| `"Show objective / Z / PFS"` | `{"kind": "start", "op": "status"}` | Local operator with control. No session (read only) |
| `"Brightfield on"` | `{"kind": "start", "op": "light_set", "args": {"mode": "brightfield"}}` | Local operator, control **and** an open experiment session (D15, like motion) |
| `"Aura <line> <pct> % on"` | `{"kind": "start", "op": "light_set", "args": {"mode": "aura", "line": "GREEN", "percent": 1.0}}` | Same as brightfield |
| `"Lights off"` (on this screen; the status-bar button belongs to T-010) | `{"kind": "lights_off"}` | Anyone, including a viewer, a user without control, and a locked session (`Action.STOP`). It pre-empts the running operation |

`lights_off` is a command **kind** in `engine/events.py` (`COMMAND_KINDS`). It is not sent as
`start("lights_off")` as ui-spec 4.0 and 4.2 write it (gap G1).

On refusal, the screen shows the reason next to the button, in ui-spec 7.0 order: remote, role, control,
session, gate, running op, preflight. Reasons come from the 403 `detail` or a `preflight_failed` event.
The screen never works them out itself.

## 3. Events read (`/ws/events`)

| Event | Used for |
|---|---|
| `position` | "Current state" panel: Z (plus XY on the common status bar) |
| `light_changed` | Lights panel: readback, not the requested value (ui-spec 5.2). `verified=false` or `"unknown"` shows the warning colour and the readback text |
| `finished` with `op == "status"` | "Current state" panel: objective, Z, PFS (`enabled`, `locked`, `in_range`) from `summary` |
| `finished` / `preflight_failed` / `error` with `op == "hardware_scan"` or `"hardware_confirm"` | Refetch `/profile` and `/gates`. Show the failure text |
| `started` / `finished` / `aborted` | Disable scan while any operation runs (single owner). `lights_off` stays enabled |

## 4. Panels and the engine piece behind them (ui-spec 7.2)

| Panel | Fields | Engine source | State on main now |
|---|---|---|---|
| Detection summary | `detected_at`, `backend`, `host`, `config.{path, sha256, changed_during_load, startup_preset_applied}`, profile sha256, diff against the previous profile | `hardware_scan` writes `hardware_profile.json` (ops-spec 5) | Skeleton has `backend_kind`, `detected_at` only (G3) |
| Devices | per device: `label`, `type`, `library`, `present`, `read_back`, `write_verified`, `note`; problem rows first | Backend `describe_devices()` (T-015) via `hardware_scan` | Skeleton `DeviceStatus{present, readable, label, note}` keyed by role (G3) |
| Objectives | `state`, `label`, `magnification`, `na`, `immersion`, `working_distance_um` (`"not set"` if missing), `pixel_um` | `nosepiece_labels()` (T-015) + lens table | Skeleton: list of labels only. Lens table owner open (Q8, G4) |
| Camera / piezo | `camera.{name, sensor, roi, bit_depth, ceiling_adu, pixel_type}`, `piezo.{port, connected, x_um, y_um, z_um, error}` | `info()`, `piezo_read()` (T-015) | Skeleton: `camera_bit_depth` only (G3) |
| Human-confirmed items | per item: `value`, `by`, `at`; editable form for the local operator, read only otherwise | `hardware_confirm` | Skeleton `confirmed: {item: "who/when"}` has no value field (G5) |
| Gates | `GateRow` (section 1) | `gates.GATES` + `gates.evaluate(profile)` | Skeleton has 3 example gates. WP-G writes the real list (ops-spec 5 gate table) |
| Current state (Step 0) | objective label, Z, PFS triple | `status` op + `position` | `status` op not yet written (WP-C) |
| Lights | DiaLamp on/off/unknown, Aura `state`/`line`/`intensity_permille`, `verified`, last readback time | `light_set`, `lights_off`, `light_changed` | Backend has `lamp_on/off`, `aura_line_on/off`, `all_off`; `light_set` op does not exist (G2) |

## 5. Gaps (requests to AF 업무분배보조, to forward to the manager)

- **G1** `lights_off` is a command kind in `events.py`; ui-spec 4.0/4.2 send it as `start("lights_off")`.
  This contract follows `events.py`. ui-spec should be corrected to match.
- **G2** No `light_set` operation. Proposed args: `mode` (`"brightfield"` / `"aura"` / `"off"`), `line`, `percent`.
  The op calls the backend's semantic light methods and emits `light_changed` with readback `records`. Owner?
  WP-C (port) or WP-G. Under D15 it needs the operator, control and an open session.
- **G3** `HardwareProfile` (T-002-2) carries only part of the ops-spec 5 profile. Missing: `host`, `config{}`, device
  `type`/`library`/`properties`/`write_verified`, objective rows, `camera{}`, `piezo{}`, `positions`, `pfs`,
  `lights`. Stage B shows what exists and `"not reported"` for the rest. WP-G should extend the dataclass.
- **G4** Objective NA and magnification are not in the ops-spec profile fields. They need the lens table
  (registry key, working distance, immersion; ops-spec Q8). Who owns the lens table, and where does it live?
- **G5** `confirmed` maps item → `"who/when"` and has no value. The UI needs `{value, by, at}`, for example
  DiaLamp 608/2100. Proposed `hardware_confirm` args: `{"items": {name: value}}`. The engine adds `by` and `at`.
- **G6** `EngineAPI` exposes only `submit`/`subscribe`/`snapshot`. The router needs the latest profile and gate
  verdict, and the last `status` summary. Proposal: `snapshot()` carries
  `hardware: {profile, profile_path, gates, last_status}`. The alternative is a read method on the
  engine. Either way, the location of the latest profile is still open (ops-spec 5 leaves it to T-002/WP-G).
- **G7** Per-operation permission table. T-009 `/api/commands` checks only loopback today. This screen needs:
  `hardware_scan`, `hardware_confirm`, `status` → `Action.OPERATE` + control, no session;
  `light_set` → `Action.OPERATE` + control + open session (D15); `lights_off` → `Action.STOP`.
  Who maps op → (action, control, session): T-011 runner or a T-009 follow-up? Stage B tests depend on
  it.
- **G8** ui-spec 5.2 and 7.0 disable `"Lights off"` for viewers. PLAN 5절, T-018 `Action.STOP` and D15 allow
  every user to send it. This contract follows PLAN. For a remote client, `lights_off` follows the same
  setting as remote `abort` (checklist U3, default allowed). But T-009 currently refuses every remote
  POST, so remote `lights_off` and `abort` need a T-009 exception.
- **G9** "Diff against the previous profile" needs profile history. Proposal: keep each
  `hardware_scan_<stamp>/summary.json` (ops-spec 5) and have the engine report the previous profile's
  sha256 and changed keys. Until then the panel shows `"no previous profile"`.
- **G10** ops-spec 5 defaults `piezo_port` to `COM4`, and whether opening the port alone changes the
  controller is still unconfirmed (Q19). Answer (업무분배보조): the scan form and the tests default to
  `piezo_port: ""` (skip the piezo), and tests never touch COM ports.
- **G8 interim** (업무분배보조): treat `lights_off` like `abort`: anyone locally; a remote client gets
  whatever T-009 does for remote `abort` (D13).

## 6. Stage B plan (after T-009 and T-010 skeletons merge)

- `hardware.py`: the four `GET` routes above with pydantic models, using a fake engine whose snapshot has
  the G6 shape. No command routes.
- `web/src/features/hardware/index.tsx`, registered per the T-010 rule. Types come from `web/src/api/` only.
  UI text in English.
- Tests: section 1 routes, unknown gate 404, remote GET allowed, and remote/viewer refusals as T-009 and
  G7 define them (pytest `TestClient`). vitest covers: off gates show their reasons, problem devices sort
  first, the confirm form is read only for remote/viewer, and the lights panel shows readback. No browser
  or desktop windows; any server started in a test is stopped.
