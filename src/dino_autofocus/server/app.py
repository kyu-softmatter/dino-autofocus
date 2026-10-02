"""The FastAPI app: the only owner of the engine. It turns requests into engine commands and
engine events into WebSocket messages, and decides nothing itself.

Access scope (PLAN.md 5, D13):
- The server listens on 127.0.0.1 only; `remote_view` opens it to other PCs for viewing.
- The Host header must be in an allow-list (loopback names, plus this PC's names and
  addresses under remote view), so a page that rebinds its own domain to 127.0.0.1 is refused.
- A request that could move hardware (any HTTP method other than GET/HEAD/OPTIONS, and
  command messages on `/ws/events`) is accepted only from the microscope PC itself, and only
  from a page served by this server or a loopback dev server (or a non-browser client), so a
  web page open in another tab cannot drive the stage.
- D13: a remote viewer may send `abort` and nothing else (`remote_abort`, default on).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic.json_schema import models_json_schema
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import HTTPConnection

from . import static, ws
from .api import Engine, include_area_routers
from .schemas import WS_MODELS, ApiError, CommandAccepted, CommandIn, EngineAPI, Health

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
COMMANDS_PATH = "/api/commands"  # checked in the endpoint, which knows the command kind


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def command_refusal(conn: HTTPConnection, kind: str | None = None) -> str | None:
    """Why this connection may not send a command of `kind`, or None if it may. `kind=None`
    means "some write whose kind is unknown" and gets no D13 exception."""
    client = conn.client.host if conn.client else None
    remote_ok = kind == "abort" and getattr(conn.app.state, "remote_abort", False)
    if not remote_ok and not _is_loopback(client):
        allowed = "abort only" if getattr(conn.app.state, "remote_abort", False) else "nothing"
        return (f"commands are accepted only on the microscope PC (request from {client}; "
                f"remote viewers may send {allowed})")
    origin = conn.headers.get("origin")
    if origin is not None:
        o = urlsplit(origin)
        if o.netloc != conn.headers.get("host", "") and not _is_loopback(o.hostname):
            return f"commands are not accepted from pages served by {origin}"
    return None


def _package_version() -> str:
    try:
        return version("dino-autofocus")
    except PackageNotFoundError:
        return "0+unknown"


def create_app(
    engine: EngineAPI,
    *,
    remote_view: bool = False,
    remote_abort: bool = True,
    allowed_hosts: Sequence[str] = (),
    engine_name: str = "unknown",
    web_dist: Path | None = None,
) -> FastAPI:
    """`allowed_hosts` adds Host header names beyond the loopback ones; under remote view the
    launcher passes this PC's host names and addresses."""
    app = FastAPI(title="dino-autofocus", version=_package_version())
    app.state.engine = engine
    app.state.remote_view = remote_view
    app.state.remote_abort = remote_abort

    @app.middleware("http")
    async def writes_from_this_pc_only(request: Request, call_next):
        if request.method not in READ_METHODS and request.url.path != COMMANDS_PATH:
            why = command_refusal(request)
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
        why = command_refusal(request, cmd.kind)
        if why is not None:
            raise HTTPException(status_code=403, detail=why)
        try:
            op_id = eng.submit(cmd.to_engine())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return CommandAccepted(op_id=op_id)

    include_area_routers(app)
    ws.install(app, engine, refuse=command_refusal)
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
