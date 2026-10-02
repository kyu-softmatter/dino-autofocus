# Patterns: designer and live overlay (card T-20261002-2205, stage 2)

A **pattern** says what the XYZ piezo stage and the tweezer traps do over time. Designing and
showing one moves nothing; running one is stage 4 (an engine operation behind the guards and
both bench locks).

## 1. Shape (`engine/patterns.py`)

```
Pattern = {version: 1, id, name, loop, notes, meta: {created_at, updated_at, by},
           tracks: [{target: "piezo" | "trap:N" (N 0..7), points: [[t_s, x_um, y_um, z_um], ...]}]}
```

- One track per target. Points are linear in between; every track starts at `t = 0` and its
  times go up. The pattern lasts as long as its longest track; a shorter one holds its end.
  With `loop` the time wraps.
- `piezo`: offsets from where the stage is when a run starts. `trap:N`: from the centre of the
  camera field, in the sample plane; `z` is the trap's focus offset.
- Axes: x to the right, y down, as on the camera image (orientation provisional until the
  piezo and the tweezers are measured on the bench).
- Ranges are PROVISIONAL and refused outside: piezo x, y ±100 µm, z ±50 µm; traps x, y ±60 µm,
  z ±10 µm. At most 20 000 points per track, 3600 s.

## 2. API (`server/api/patterns.py`, mounted at `/api/patterns`)

| Route | Who | Does |
|---|---|---|
| `GET /api/patterns` | logged in | `[PatternSummary]` (id, name, duration_s, targets, updated_at) |
| `GET /api/patterns/{id}` | logged in | `PatternOut` |
| `POST /api/patterns/{id}` | operator / admin, microscope PC | `PatternIn` → `PatternOut`; create or replace; `422 invalid_pattern` with the reason |
| `POST /api/patterns/{id}/delete` | operator / admin, microscope PC | `204`; `404 not_found` |

Patterns are designs, not records: one JSON file each in `<settings>/patterns/`, shared by the
mock and the bench.

## 3. Screens

- **Patterns** area (`#/patterns`, `#/patterns/<id>`): saved list, name, loop, one box per
  track (target, shape generator: circle, line, raster, spiral, hold; z start/end ramps z over
  the shape; duration; points per second; points editable as CSV), a preview coloured by time
  (gray `#9e9e9e` at the start to dark green `#1b5e20` at the end) with Play and a time slider,
  each target's x/y/z at that time, Save, Delete (with a confirm) and "Show on live view".
- **Live** area overlay (`#/live?pattern=<id>`): the pattern drawn over every camera panel
  (side by side, merged, one at a time) in the same colours, markers where each target is at
  the slider's time (piezo a square, a trap a numbered circle), a 10 µm scale bar. The scale is
  the frame's `meta.pixel_um` × binning; a frame without it uses 0.1 µm/px and says "assumed".
