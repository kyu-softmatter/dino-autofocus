"""Registration point for the area routers (console, hardware, sample, map, objective, ...),
and the dependencies they share.

An area adds one module here, `server/api/<area>.py`, holding a module-level
`router = fastapi.APIRouter()`. It is found on start-up and mounted at `/api/<area>` with the
tag `<area>`; this file is not edited per area. Modules whose names start with `_` are skipped.

Dependencies for handlers (`Annotated`, so `def handler(eng: Engine, local: IsLocal): ...`):
- `Engine`: the engine. `AgentStoreDep`: the agent store (F1).
- `IsLocal`: whether the request comes from the microscope PC itself (loopback socket).
- `LocalOnly`: refuse with 403 unless the request may write from here (loopback, and not
  from a foreign page). Area writes that move nothing but must stay local use this.

Access rules (PLAN.md 5, D13, D16), one place for REST and WebSocket: `command_refusal`.
"""

from __future__ import annotations

import importlib
import ipaddress
import pkgutil
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from starlette.requests import HTTPConnection

from ...agents import AgentStore
from ..schemas import EngineAPI

# D16: map writes go only through server/api/map.py, which checks WRITE_MAP_FLAG
MAP_WRITE_OPS = frozenset({"map_flag", "map_flag_retire", "candidate_confirm", "candidate_reject"})


def get_engine(request: Request) -> EngineAPI:
    return request.app.state.engine


def get_agent_store(request: Request) -> AgentStore:
    return request.app.state.agent_store


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def is_local(conn: HTTPConnection) -> bool:
    return is_loopback_host(conn.client.host if conn.client else None)


def origin_refusal(conn: HTTPConnection) -> str | None:
    """A browser page from another site may not write (CSRF). Pages served by this server and
    loopback dev servers may; non-browser clients send no Origin."""
    origin = conn.headers.get("origin")
    if origin is None:
        return None
    o = urlsplit(origin)
    if o.netloc == conn.headers.get("host", "") or is_loopback_host(o.hostname):
        return None
    return f"writes are not accepted from pages served by {origin}"


def command_refusal(conn: HTTPConnection, kind: str | None = None, op: str = "") -> str | None:
    """Why this connection may not send a command of `kind` (and `op` for `start`), or None if
    it may. `kind=None` means "some write whose kind is unknown" and gets no D13 exception."""
    if kind == "start" and op in MAP_WRITE_OPS:
        return f"{op!r} goes through /api/map, not /api/commands (D16)"
    remote_abort = getattr(conn.app.state, "remote_abort", False)
    if not is_local(conn) and not (kind == "abort" and remote_abort):
        client = conn.client.host if conn.client else None
        allowed = "abort only" if remote_abort else "nothing"
        return (f"commands are accepted only on the microscope PC (request from {client}; "
                f"remote viewers may send {allowed})")
    return origin_refusal(conn)


def local_only(request: Request) -> None:
    why = command_refusal(request)
    if why is not None:
        raise HTTPException(status_code=403, detail=why)


Engine = Annotated[EngineAPI, Depends(get_engine)]
AgentStoreDep = Annotated[AgentStore, Depends(get_agent_store)]
IsLocal = Annotated[bool, Depends(is_local)]
LocalOnly = Depends(local_only)  # router- or route-level: dependencies=[LocalOnly]


def include_area_routers(app: FastAPI, package: str = __name__) -> list[str]:
    """Mount every area router found in `package`; returns the area names, sorted."""
    pkg = importlib.import_module(package)
    areas = []
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("_") or info.ispkg:
            continue
        module = importlib.import_module(f"{package}.{info.name}")
        router = getattr(module, "router", None)
        if not isinstance(router, APIRouter):
            raise TypeError(f"{module.__name__} has no module-level `router = APIRouter()`")
        app.include_router(router, prefix=f"/api/{info.name}", tags=[info.name])
        areas.append(info.name)
    return areas
