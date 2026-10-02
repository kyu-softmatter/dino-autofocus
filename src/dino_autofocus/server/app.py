"""The FastAPI app: the only owner of the engine. It turns requests into engine commands and
engine events into WebSocket messages, and decides nothing itself.

Access scope (PLAN.md 5, D13, D16; the rules live in `server/api/__init__.py`):
- The server listens on 127.0.0.1 only; `remote_view` opens it to other PCs for viewing.
- The Host header must be in an allow-list (loopback names, plus this PC's names and
  addresses under remote view), so a page that rebinds its own domain to 127.0.0.1 is refused.
- A request that could move hardware (any HTTP method other than GET/HEAD/OPTIONS, and
  command messages on `/ws/events`) is accepted only from the microscope PC itself, and only
  from a page served by this server or a loopback dev server (or a non-browser client), so a
  web page open in another tab cannot drive the stage.
- D13: a remote viewer may send `abort` and nothing else (`remote_abort`, default on).
- Exception: the six login routes `POST /api/auth/{login, logout, lock, unlock, activity, signup}`
  are open to remote viewers (they must log in); none of them reaches the engine.
- D16: map writes are refused on `/api/commands`; they go through `/api/map`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import AsyncIterator, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic.json_schema import models_json_schema
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..agents import AgentStore, MockStore
from . import static, ws
from .api import Engine, command_refusal, include_area_routers, is_local, origin_refusal
from .schemas import (
    WS_MODELS,
    ApiError,
    CommandAccepted,
    CommandIn,
    EngineAPI,
    Health,
    ShutdownAccepted,
    ShutdownIn,
)

log = logging.getLogger(__name__)

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
COMMANDS_PATH = "/api/commands"  # checked in the endpoint, which knows the command kind
# remote viewers must be able to log in (PLAN.md 5); T-018 adds the routes in server/api/auth.py
AUTH_OPEN_PATHS = frozenset(
    f"/api/auth/{name}" for name in ("login", "logout", "lock", "unlock", "activity", "signup")
)


class EngineStopper:
    """Stops the engine once, from whichever exit path gets there first: `POST /api/shutdown`,
    a signal, the app's lifespan end, the launcher's `finally`, or `atexit`. A failed attempt
    does not count, so a later path tries again."""

    def __init__(self, engine: EngineAPI) -> None:
        self._engine = engine
        self._lock = threading.Lock()
        self.reason: str | None = None

    @property
    def done(self) -> bool:
        return self.reason is not None

    def __call__(self, reason: str) -> bool:
        """True if this call stopped the engine, False if it was already stopped."""
        with self._lock:
            if self.reason is not None:
                return False
            self._engine.shutdown(reason)
            self.reason = reason
            log.info("engine stopped (%s)", reason)
            return True

    def quietly(self, reason: str) -> None:
        """For exit hooks: never raise, log instead."""
        try:
            self(reason)
        except Exception:
            log.exception("engine shutdown (%s) failed", reason)


def _package_version() -> str:
    try:
        return version("dino-autofocus")
    except PackageNotFoundError:
        return "0+unknown"


def create_app(
    engine: EngineAPI,
    *,
    agent_store: AgentStore | None = None,
    remote_view: bool = False,
    remote_abort: bool = True,
    allowed_hosts: Sequence[str] = (),
    engine_name: str = "unknown",
    web_dist: Path | None = None,
) -> FastAPI:
    """`agent_store` defaults to a `MockStore` (dev). `allowed_hosts` adds Host header names
    beyond the loopback ones; under remote view the launcher passes this PC's host names and
    addresses."""
    stopper = EngineStopper(engine)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await asyncio.to_thread(stopper.quietly, "server stopping")

    app = FastAPI(title="dino-autofocus", version=_package_version(), lifespan=lifespan)
    app.state.engine = engine
    app.state.agent_store = agent_store if agent_store is not None else MockStore()
    app.state.remote_view = remote_view
    app.state.remote_abort = remote_abort
    app.state.stop_engine = stopper
    app.state.request_exit = None  # set by the launcher: makes the server process exit

    @app.middleware("http")
    async def writes_from_this_pc_only(request: Request, call_next):
        path = request.url.path
        if request.method not in READ_METHODS and path != COMMANDS_PATH:
            why = origin_refusal(request) if path in AUTH_OPEN_PATHS else command_refusal(request)
            if why is not None:
                return JSONResponse({"detail": why}, status_code=403)
        return await call_next(request)

    # added last, so it runs first, for HTTP and WebSocket alike
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=[*LOOPBACK_HOSTS, *allowed_hosts], www_redirect=False)

    @app.get("/api/health", response_model=Health, tags=["server"])
    def health() -> Health:
        return Health(engine=engine_name, remote_view=remote_view, remote_abort=remote_abort)

    @app.get("/api/state", tags=["server"])
    def state(eng: Engine) -> dict:
        """The engine's snapshot: positions, lights, running operation."""
        return eng.snapshot()

    @app.post(
        COMMANDS_PATH,
        response_model=CommandAccepted,
        responses={400: {"model": ApiError}, 403: {"model": ApiError}},
        tags=["server"],
    )
    def commands(cmd: CommandIn, request: Request, eng: Engine) -> CommandAccepted:
        """Hand a command to the engine. Whether it runs is reported by events."""
        why = command_refusal(request, cmd.kind, cmd.op)
        if why is not None:
            raise HTTPException(status_code=403, detail=why)
        if stopper.done:
            raise HTTPException(status_code=503, detail="the server is shutting down")
        try:
            op_id = eng.submit(cmd.to_engine(remote=not is_local(request)))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return CommandAccepted(op_id=op_id)

    @app.post(
        "/api/shutdown",
        response_model=ShutdownAccepted,
        responses={403: {"model": ApiError}, 500: {"model": ApiError}},
        tags=["server"],
    )
    def shutdown(body: ShutdownIn, request: Request, tasks: BackgroundTasks) -> ShutdownAccepted:
        """Stop the engine (lights off with readback, abort, finish records), then exit. The
        launcher calls this before any hard kill. Microscope PC only, no D13 exception."""
        why = command_refusal(request)
        if why is not None:
            raise HTTPException(status_code=403, detail=why)
        request_exit = app.state.request_exit
        try:
            stopped = stopper(body.reason)
        except Exception as e:
            log.exception("engine shutdown failed")
            if request_exit is not None:
                request_exit()  # exit anyway; the atexit hook tries the engine once more
            raise HTTPException(status_code=500, detail=f"engine shutdown failed: {e}") from e
        if request_exit is not None:
            tasks.add_task(request_exit)  # after the response has gone out
        return ShutdownAccepted(reason=stopper.reason or body.reason, already=not stopped)

    include_area_routers(app)
    ws.install(app, engine, refuse=command_refusal, stopped=lambda: stopper.done)
    static.mount_web(app, web_dist)

    def openapi() -> dict:
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            # WebSocket messages are not routes; list them so the TS types cover them too
            _, defs = models_json_schema(
                [(m, "validation") for m in WS_MODELS],
                ref_template="#/components/schemas/{model}",
            )
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            for name, s in defs.get("$defs", {}).items():
                components.setdefault(name, s)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app
