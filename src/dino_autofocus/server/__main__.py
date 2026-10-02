"""`uv run python -m dino_autofocus.server [--remote-view] [--port N] [--backend placeholder]`
`uv run python -m dino_autofocus.server --dump-openapi PATH` writes the OpenAPI JSON and exits.

Until the engine runner (T-011) and the mock backend land, the only engine is a placeholder
that moves nothing: it acknowledges commands with events, reports a fixed position and
streams a synthetic picture, so the web shell has something to show.
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from .app import create_app
from .schemas import Command, Event

DEFAULT_PORT = 8765
REMOTE_VIEW_ENV = "DINO_AF_REMOTE_VIEW"
BACKENDS = ("placeholder",)

log = logging.getLogger("dino_autofocus.server")


class PlaceholderEngine:
    """Stands in for the engine runner. No hardware, no backend, no decisions."""

    frame_hz = 10.0
    position_every_s = 1.0

    def __init__(self, shape: tuple[int, int] = (1200, 1600)) -> None:
        self._sinks: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        self._ticker: threading.Thread | None = None
        self._frame: tuple[np.ndarray, dict[str, Any]] | None = None
        self._lights = {"aura": "off", "dia_lamp": "off"}
        self._positions = {"x_um": 0.0, "y_um": 0.0, "z_um": 3000.0}
        self._shape = shape
        # a fresh noise field per frame costs more than the 10 Hz budget; cycle two
        rng = np.random.default_rng(0)
        self._noise = [np.clip(rng.normal(400, 30, shape), 0, 4095).astype(np.uint16)
                       for _ in range(2)]
        self._n = 0

    def _emit(self, kind: str, op_id: str = "", **data: Any) -> None:
        ev = Event(kind=kind, op_id=op_id, data=data)
        with self._lock:
            sinks = list(self._sinks)
        for s in sinks:
            try:
                s(ev)
            except Exception:
                log.exception("sink failed")

    def submit(self, cmd: Command) -> str:
        if cmd.kind == "start":
            op_id = uuid.uuid4().hex[:8]
            self._emit("started", op_id, op=cmd.op, placeholder=True)
            self._emit("finished", op_id, op=cmd.op, placeholder=True,
                       note="placeholder engine: nothing was run")
            return op_id
        if cmd.kind == "abort":
            self._emit("aborted", cmd.op_id)
        elif cmd.kind == "confirm":
            self._emit("confirmed", cmd.op_id, **cmd.args)
        elif cmd.kind == "lights_off":
            self._emit("light_changed", **self._lights)
        return cmd.op_id

    def subscribe(self, sink: Callable[[Event], None]) -> Callable[[], None]:
        with self._lock:
            self._sinks.append(sink)
            if self._ticker is None:
                self._ticker = threading.Thread(target=self._tick, daemon=True)
                self._ticker.start()

        def unsubscribe() -> None:
            with self._lock:
                if sink in self._sinks:
                    self._sinks.remove(sink)

        return unsubscribe

    def shutdown(self, reason: str) -> None:
        self._emit("light_changed", **self._lights)  # already off: nothing was ever lit
        self._emit("log", msg=f"placeholder engine stopped: {reason}")

    def snapshot(self) -> dict[str, Any]:
        return {"engine": "placeholder", "positions": dict(self._positions),
                "lights": dict(self._lights), "running": None}

    def latest_frame(self) -> tuple[np.ndarray, dict[str, Any]] | None:
        return self._frame

    def _tick(self) -> None:
        last_position = 0.0
        while True:
            with self._lock:
                if not self._sinks:
                    self._ticker = None
                    return
            now = time.time()
            self._frame = (self._picture(now), {"t": now, **self._positions,
                                                "bit_depth": 12, "placeholder": True})
            self._emit("frame_ready")
            if now - last_position >= self.position_every_s:
                self._emit("position", **self._positions)
                last_position = now
            time.sleep(max(0.0, now + 1.0 / self.frame_hz - time.time()))

    def _picture(self, t: float) -> np.ndarray:
        h, w = self._shape
        self._n += 1
        img = self._noise[self._n % 2].copy()
        sigma, r = 40.0, 160  # each drifting blob is drawn only within 4 sigma of its centre
        for k in range(5):
            cy = int(h * (0.5 + 0.3 * np.sin(0.3 * t + 1.3 * k)))
            cx = int(w * (0.5 + 0.3 * np.cos(0.2 * t + 1.7 * k)))
            y0, y1, x0, x1 = max(cy - r, 0), min(cy + r, h), max(cx - r, 0), min(cx + r, w)
            gy = np.exp(-((np.arange(y0, y1) - cy) ** 2) / (2 * sigma**2))
            gx = np.exp(-((np.arange(x0, x1) - cx) ** 2) / (2 * sigma**2))
            patch = img[y0:y1, x0:x1] + 3000.0 * np.outer(gy, gx)
            img[y0:y1, x0:x1] = np.minimum(patch, 4095)
        return img


def make_engine(backend: str) -> tuple[Any, str]:
    if backend == "placeholder":
        return PlaceholderEngine(), "placeholder"
    raise SystemExit(f"unknown backend {backend!r}; available now: {', '.join(BACKENDS)}")


def this_pc_hosts() -> list[str]:
    """Names other PCs may use to reach this one: host name, FQDN and IPv4 addresses."""
    name = socket.gethostname()
    hosts = {name, socket.getfqdn()}
    with contextlib.suppress(OSError):
        hosts.update(socket.gethostbyname_ex(name)[2])
    return sorted(h for h in hosts if h)


def install_exit_hooks(app: Any, server: Any) -> Callable[[], None]:
    """Hardware must not depend on `POST /api/shutdown` alone. Lights go off on every way out:
    the route, a signal (uvicorn traps SIGINT, SIGTERM and on Windows SIGBREAK; we start the
    engine stop at once instead of after open connections drain), the app's lifespan end, the
    `finally` around `server.run()`, and `atexit`. The engine is stopped once; returns the
    atexit hook."""
    stop = app.state.stop_engine

    def request_exit() -> None:
        server.should_exit = True

    app.state.request_exit = request_exit
    trap = server.handle_exit

    def handle_exit(sig: int, frame: Any) -> None:
        trap(sig, frame)  # graceful exit, or forced on a second Ctrl+C
        name = signal.Signals(sig).name
        threading.Thread(target=stop.quietly, args=(f"signal {name}",), name="engine-stop").start()

    server.handle_exit = handle_exit

    def at_exit() -> None:
        stop.quietly("process exit")

    atexit.register(at_exit)
    return at_exit


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m dino_autofocus.server", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--remote-view", action="store_true",
                   help=f"listen on 0.0.0.0 so other PCs can view (also {REMOTE_VIEW_ENV}=1); "
                        "commands are still accepted from this PC only")
    p.add_argument("--no-remote-abort", action="store_true",
                   help="refuse abort from remote viewers too (D13 default: allowed)")
    p.add_argument("--allow-host", action="append", default=[], metavar="NAME",
                   help="extra Host header name to accept (repeatable); under --remote-view "
                        "this PC's host name and addresses are added automatically")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--backend", choices=BACKENDS, default="placeholder",
                   help="only the placeholder engine exists until the runner (T-011) and the "
                        "mock backend land")
    p.add_argument("--web-dist", type=Path, default=None,
                   help="built web app to serve (default: <repo>/web/dist)")
    p.add_argument("--dump-openapi", metavar="PATH",
                   help="write the OpenAPI JSON to PATH ('-' for stdout) and exit")
    args = p.parse_args(argv)

    remote_view = args.remote_view or os.environ.get(REMOTE_VIEW_ENV, "") == "1"
    engine, name = make_engine(args.backend)
    hosts = [*args.allow_host, *(this_pc_hosts() if remote_view else ())]
    app = create_app(engine, remote_view=remote_view, remote_abort=not args.no_remote_abort,
                     allowed_hosts=hosts, engine_name=name, web_dist=args.web_dist)

    if args.dump_openapi:
        text = json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"
        if args.dump_openapi == "-":
            sys.stdout.write(text)
        else:
            Path(args.dump_openapi).write_text(text, encoding="utf-8")
        return 0

    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
    host = "0.0.0.0" if remote_view else "127.0.0.1"
    print(f"dino-autofocus server, engine={name}: open http://127.0.0.1:{args.port} on this PC"
          + (" (other PCs: view only)" if remote_view else ""))
    # proxy headers off: the client address must be the socket's, it decides who may command
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=args.port, proxy_headers=False,
                                           log_level="info"))
    install_exit_hooks(app, server)
    try:
        server.run()
    finally:
        app.state.stop_engine.quietly("server exit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
