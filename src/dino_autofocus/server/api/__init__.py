"""Registration point for the area routers (console, hardware, sample, map, objective, ...).

An area adds one module here, `server/api/<area>.py`, holding a module-level
`router = fastapi.APIRouter()`. It is found on start-up and mounted at `/api/<area>` with the
tag `<area>`; this file is not edited per area. Handlers reach the engine through
`Engine` (an `Annotated` dependency): `def handler(eng: Engine): ...`. Modules whose names
start with `_` are skipped.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request

from ..schemas import EngineAPI


def get_engine(request: Request) -> EngineAPI:
    return request.app.state.engine


Engine = Annotated[EngineAPI, Depends(get_engine)]


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
