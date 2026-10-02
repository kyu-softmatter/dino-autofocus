# Desktop launcher ("DINO Autofocus.exe")

The exe starts the web app server from this clone's uv env and opens the browser. It needs
no system Python: it finds `uv` and runs `uv run python -m dino_autofocus.server`.
Source: `tools/launcher/Launcher.cs`, built by `tools/launcher/build.ps1`.

## Build

Needs `uv` and the .NET Framework 4 compiler that ships with Windows (no SDK).

```
powershell -ExecutionPolicy Bypass -File tools\launcher\build.ps1
```

| Option | Default | Meaning |
|---|---|---|
| `-Port N` | `8765` | port the server is started on and probed at |
| `-Out path` | `Desktop\DINO Autofocus.exe` | where the exe is written (a missing folder is created) |
| `-Force` | off | replace an existing exe at `-Out`. Without it the build stops and prints the old file's size and date: check that it is not a build you want to keep first |

- The repo path compiled into the exe is the clone `build.ps1` runs from. Build from the
  clone you use day to day, not from a session worktree. Moving the clone means rebuilding.
- `autofocus.ico` is in git. If it is missing, `build.ps1` redraws it with
  `uv run python tools\launcher\make_icon.py`.
- Server code changes need no rebuild; only `Launcher.cs`, the port, or the clone path do.

## Run

| Action | Result |
|---|---|
| Click | Server already answering `GET /api/health` → opens `http://127.0.0.1:<port>/`. Otherwise starts the server hidden, shows "Starting the server…" until `/api/health` answers (up to 60 s), then opens the browser. |
| Click while a start is in progress | Waits for that server; never starts a second one. |
| Shift + click (or `--classic`) | Old tkinter launcher: `uv run python scripts\launcher.py`. |
| Ctrl + click (or `--stop`) | Stops the server this launcher started, after a confirmation. |

- The server binds `127.0.0.1` only. The exe never turns on remote view.
- Server output goes to `%LOCALAPPDATA%\dino-autofocus\server.log` (the previous run is kept as
  `server.prev.log`), away from the sample records. `server.pid` there names the process the
  launcher started.
- The first start after `git pull` can be slow: `uv run` syncs the env first (torch is large).
  If the 60 s wait runs out, the server keeps starting; click again to keep waiting.
- The old launcher run this way starts its hardware jobs with the repo `.venv` Python, not the
  system Python described in `docs/setup-new-pc.md`. Check that on the microscope PC before
  relying on it.

## Remote view (read-only)

Not available from the exe. Start the server by hand from the clone:

```
uv run python -m dino_autofocus.server --port 8765 --remote-view
```

or set `DINO_AF_REMOTE_VIEW=1`. The server then binds `0.0.0.0`; other PCs can read state and
watch events, and commands are still accepted only from this PC (T-009). Allow the port in
Windows Firewall only for the network you need.

## Stop

- Ctrl + click the exe, or run `"DINO Autofocus.exe" --stop`. This ends the process tree
  (`cmd.exe` → `uv.exe` → `python.exe`) with `taskkill /T /F`. It is a forced stop: the server
  gets no chance to clean up. With mock hardware that is harmless. Before real hardware is
  connected, the server needs a graceful shutdown path, and the launcher should use it.
- A server started by hand in a terminal stops with Ctrl+C there. The launcher only stops the
  one it started.

## Testing without a desktop

Set `DINO_AF_LAUNCHER_HEADLESS=<file>` before starting the exe. No window or browser opens;
each message, confirmation (answered OK), wait and browser open is appended to `<file>`, and
`server.log` / `server.pid` go next to it. Build a test copy with `-Out` so the Desktop exe is
untouched, and stop any server the test started (`--stop` with the same variable set).

## Troubleshooting

| Message | Cause and fix |
|---|---|
| `uv not found` | uv is not on `PATH`, `%USERPROFILE%\.local\bin`, `%USERPROFILE%\.cargo\bin`, the winget links folder, or scoop shims. Install uv, run `uv sync` in the clone. |
| `Repository not found` | The clone moved or was deleted. Rebuild from the clone you use. |
| `Server not found in this clone` | `src\dino_autofocus\server\__main__.py` is missing: the clone predates the web server (T-009). `git pull`, `uv sync`. Shift + click still opens the old launcher. |
| `Port N is in use, but no DINO Autofocus server answers there` | Another program holds the port. Find it with `netstat -ano \| findstr :N`, close it, or rebuild with `-Port`. |
| `The server stopped while starting` | The server exited. The message shows the end of `server.log`; the full log has the traceback. Run the same command in a terminal to see it live: `uv run python -m dino_autofocus.server --port 8765`. |
| `The server did not answer … within 60 s` | Usually a slow first `uv run` after a pull. Click again to keep waiting, or Ctrl + click to stop it, then check `server.log`. |
| Nothing happens for a few seconds after clicking | Antivirus scans a freshly built, unsigned exe on its first runs. |
