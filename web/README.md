# dino-autofocus web app

The browser UI (PLAN.md 5, D1). FastAPI (`python -m dino_autofocus.server`, T-009) serves the
built `web/dist`; Node is needed to build, not to run. Node comes from the uv `web` group, so
there is no system install: always go through `uv run`.

```
uv sync                                  # once: installs Node 22 into the repo env
uv run npm --prefix web ci               # install the locked packages
uv run npm --prefix web run dev          # dev server; /api and /ws go to 127.0.0.1:8000
uv run npm --prefix web test             # vitest (jsdom, no browser window)
uv run npm --prefix web run typecheck    # tsc --noEmit
uv run npm --prefix web run build        # typecheck + vite build -> web/dist (not committed)
uv run npm --prefix web run gen:api      # regenerate src/api/ from the server's OpenAPI
```

Set `DINO_AF_SERVER` to point the dev server at another address.

## Layout

| Path | Owner | What |
|---|---|---|
| `src/app/` | shell (T-010) | layout, navigation, area registry, screen context, status bar, shared components |
| `src/app/assistant/` | prompt box (T-014) | the prompt box on every screen. Not part of the shell |
| `src/api/` | generated | OpenAPI types from `npm run gen:api`. Never edited by hand |
| `src/features/<area>/` | that area's work package | the area's screen |
| `src/features/live/` | shell (T-010) | the live view |
| `package.json`, `package-lock.json` | T-010 only | ask the manager for a package; one session changes these at a time |

## Adding an area screen

The areas and their order are fixed in `src/app/areas.ts`: `console`, `hardware`, `sample`,
`map`, `objective`, `live`, `simulation`, `sessions`. Login (`src/app/login/`, T-105) is not an
area and has no navigation entry. To give an area its screen:

1. Create `src/features/<area>/index.tsx`.
2. Default-export a React component that takes no props.
3. That is all. The shell finds the file at build time (`import.meta.glob`) and lazy-loads it
   when the area is opened. Do not edit `src/app/`.

Until the file exists the shell shows "<Area>: not implemented yet". A folder whose name is not
one of the areas is ignored with a console warning; adding a new area is a shell change (ask the
manager). If the screen throws while loading, the shell shows the error inside the area and the
rest of the app keeps working.

Inside `src/features/<area>/` the area owns its files and folders. Keep imports from other
areas out; shared pieces belong in `src/app/` (ask for them).

## Routes and links between areas

Routes are hashes `#/<area>/<rest>`. The shell routes on `<area>` only and hands everything after
it, query included, to the area untouched. The area decides what `<rest>` means:

| Hash | Area | `rest` |
|---|---|---|
| `#/simulation/runs/run-20260924-001` | simulation | `runs/run-20260924-001` |
| `#/map?sample_id=20260930_1849_1` | map | `?sample_id=20260930_1849_1` |
| `#/console` | console | (empty) |

An unknown area falls back to the console. Inside a screen:

```tsx
import { areaHref, useAreaPath } from "../../app/route";

const [rest, setRest] = useAreaPath();        // read and change your own rest; no remount
<a href={areaHref("simulation", `runs/${runId}`)}>open run</a>   // link to another area
```

Linking is a plain href, so areas never import each other. Each area documents the `rest` forms it
accepts in its own `index.tsx`.

## Screen context for the prompt box

Every prompt carries the context of the screen in view (PLAN X1). The shell fills `area`. A
screen adds short ids and names only, never frames or file contents (PLAN D7):

```tsx
import { useMemo } from "react";
import { useScreenContext } from "../../app/screenContext";

export default function MapScreen() {
  const details = useMemo(() => ({ sample_id, region }), [sample_id, region]);
  useScreenContext(details);   // cleared when the screen unmounts or the area changes
  ...
}
```

The prompt box reads it with `useCurrentScreenContext()`. Its component goes in
`src/app/assistant/index.tsx` (default export, no props). The shell's prompt slot picks that
file up the same way as an area screen, with a placeholder until it exists.

## Shared components

- `FocusVerdict` (`src/app/Verdict.tsx`): a model verdict, only the five words
  `in_focus | step_up | step_down | no_sample_here | unsure`, tagged "model". Anything else is
  shown as "Unsure" and marked invalid. A model never gives a Z (PLAN 6, rule 3).
- `EncoderZ`: Z from the ZDrive encoder read-back, in µm. The only way a screen shows Z.

UI text is English.
