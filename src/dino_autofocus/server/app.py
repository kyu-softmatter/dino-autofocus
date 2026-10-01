"""The FastAPI app: the only owner of the engine. It turns requests into engine commands and
engine events into WebSocket messages, and decides nothing itself.

Access scope (PLAN.md 5): by default the server listens on 127.0.0.1 only; `remote_view`
opens it to other PCs for viewing. Either way a request that could move hardware (any HTTP
method other than GET/HEAD/OPTIONS, and command messages on `/ws/events`) is accepted only
from the microscope PC itself, and only from a page served by this server (or a non-browser
client), so a web page open in another tab cannot drive the stage.
"""

from __future__ import annotations

import ipaddress
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic.json_schema import models_json_schema
from starlette.requests import HTTPConnection

from . import static, ws
from .api import Engine, include_area_routers
from .schemas import WS_MODELS, ApiError, CommandAccepted, CommandIn, EngineAPI, Health

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOOPBACK_NAMES = frozenset({"localhost"})


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def command_refusal(conn: HTTPConnection) -> str | None:
    """Why this connection may not send commands, or None if it may."""
    client = conn.client.host if conn.client else None
    if not _is_loopback(client):
        return f"commands are accepted only on the microscope PC (request from {client})"
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
    engine_name: str = "unknown",
    web_dist: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="dino-autofocus", version=_package_version())
    app.state.engine = engine
    app.state.remote_view = remote_view

    @app.middleware("http")
    async def commands_from_this_pc_only(request: Request, call_next):
        if request.method not in READ_METHODS:
            why = command_refusal(request)
            if why is not None:
                return JSONResponse({"detail": why}, status_code=403)
        return await call_next(request)

    @app.get("/api/health", response_model=Health, tags=["server"])
    def health() -> Health:
        return Health(engine=engine_name, remote_view=remote_view)

    @app.get("/api/state", tags=["server"])
    def state(eng: Engine) -> dict:
        """The engine's snapshot: positions, lights, running operation."""
        return eng.snapshot()

    @app.post(
        "/api/commands",
        response_model=CommandAccepted,
        responses={400: {"model": ApiError}, 403: {"model": ApiError}},
        tags=["server"],
    )
    def commands(cmd: CommandIn, eng: Engine) -> CommandAccepted:
        """Hand a command to the engine. Whether it runs is reported by events."""
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
