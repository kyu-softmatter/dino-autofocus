# T-028 WP-G: hardware scan, hardware profile and gate rules (engine side)

- Owner: AF 실행17 (after T-024)
- Prerequisites: T-002 stage 2 merged (`gates.py` skeleton), T-015 merged (`describe_devices` and the
  other reads). Until T-015 merges, build against FakeBackend stubs.
- Branch: `exec17/T-028-hardware-scan-gates`
- Review: AF 검토보조1
- Screen contract: `docs/screens/hardware.md` (T-101, 0bf1f11). Spec: `docs/operations-spec.md` 5 (hardware_scan).

## Owned paths

- `src/dino_autofocus/engine/gates.py` (rules and profile content; the skeleton is from T-002)
- `src/dino_autofocus/engine/operations/hardware_scan.py`
- `tests/engine/test_operations_hardware*.py`, `tests/engine/test_gates_rules*.py`

## Content

- Ops: `hardware_scan{include_properties, piezo_port}` (detect only; nothing moves or turns on) and
  `hardware_confirm{items}`.
- HardwareProfile fields (ops-spec 5): host, config record, and per device the type, library, properties
  and write_verified. Also objective rows, camera, piezo, positions, PFS and lights. Confirmed items are
  `{value, by, at}`. Keep a profile history with a diff against the previous profile.
- Gate rules per operation, with reasons when off. Include `loading_check_image` (camera, DiaLamp, 4x) for
  T-027 and the light ops for D15.
- Snapshot block for the screen (T-011 provides the slot): `{profile, profile_path, gates, last_status}`.
- Permissions: `hardware_scan` needs a local operator with control (it opens devices). `hardware_confirm`
  needs a local operator and an open session.

## Done when

- Common criteria, trailer `Session: AF 실행17`. Send `[검토요청 T-028]` to AF 검토보조1.
