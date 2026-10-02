"""The FastAPI app: the only owner of the engine. It turns requests into engine commands and
engine events into WebSocket messages, and decides nothing itself.

Access scope (PLAN.md 5, D13, D16; the rules live in `server/api/__init__.py`):
- The server listens on 127.0.0.1 only; `remote_view` opens it to other PCs for viewing.
- The Host header must be in an allow-list (loopback names, plus this PC's names and
  addresses under remote view), so a page that rebinds its own domain to 127.0.0.1 is refused.
- Every `/api/*` route and `/ws/*` needs a live login (the `dinoaf_session` cookie), except
  `GET /api/health`, `GET /api/auth/setup`, the login routes `POST /api/auth/{login, logout,
  lock, unlock, activity, signup}`, first-run `POST /api/auth/setup/admin` (from the microscope
  PC and this server's own page only), `POST /api/shutdown` from the microscope PC (the
  launcher has no login), and the stops `abort` / `lights_off` from the microscope PC.
- A write (any method other than GET/HEAD/OPTIONS, and command messages on `/ws/events`) is
  accepted only from the microscope PC itself, and only from a page served by this server or
  a dev server named with `dev_origins` (or a non-browser client), so a page in another tab,
  even one on another loopback port that carries the login cookie, cannot drive the stage.
  WebSocket handshakes get the same origin check.
- D13: a logged-in remote viewer may send `abort` and nothing else (`remote_abort`).
- D16: map writes are refused on `/api/commands`; they go through `/api/map`.
- The server stamps every engine Command with who sent it, from where and with which control
  grant (T-018); the browser never sees the grant.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
import pkgutil
import threading
from collections.abc import AsyncIterator, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.openapi.utils import get_openapi
from pydantic.json_schema import models_json_schema
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..agents import AgentStore, MockStore
from ..engine.operations import sample_ops  # registers the sample operations (T-027)
from . import static, ws
from .api import (
    MAP_WRITE_OPS,
    SERVER_ACTIONS,
    STOPS,
    Auth,
    AuthSeat,
    Engine,
    Refusal,
    SessionSeat,
    command_refusal,
    command_why,
    include_area_routers,
    is_local,
    logged_in_refusal,
    login_state,
    normalize_origin,
    origin_refusal,
    own_origin_refusal,
    remote_view,
    server_action_why,
)
from .schemas import (
    WS_MODELS,
    ApiError,
    CommandAccepted,
    CommandIn,
    EngineAPI,
    Health,
    PermissionOut,
    ShutdownAccepted,
    ShutdownIn,
    Snapshot,
)

log = logging.getLogger(__name__)

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
COMMANDS_PATH = "/api/commands"  # checked in the endpoint, which knows the command kind
SHUTDOWN_PATH = "/api/shutdown"
OPEN_READS = frozenset({"/api/health", "/api/auth/setup"})  # setup: first-run state (T-105)
# reads a locked login still gets: the lock screen needs who is locked (T-105 `/me`)
LOCKED_OK_READS = frozenset({"/api/auth/me"})
# the one write that works with no login: making the first admin (T-105 handles 409 after)
SETUP_ADMIN_PATH = "/api/auth/setup/admin"
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


SHUTTING_DOWN = Refusal(503, "shutting_down", "the server is shutting down")


def _shutdown_refusal(request: Request) -> Refusal | None:
    """The launcher stops the server from this PC without a login; no D13 exception."""
    if not is_local(request):
        return remote_view("remote view: only the microscope PC may stop the server")
    return origin_refusal(request)


def _http_refusal(request: Request) -> Refusal | None:
    """The cookie check and the write rule for every `/api/*` request but the commands
    route, which needs the command kind and checks in its handler."""
    path = request.url.path
    if request.method in READ_METHODS:
        if path in OPEN_READS:
            return None
        return logged_in_refusal(login_state(request), locked_ok=path in LOCKED_OK_READS)
    if path == SETUP_ADMIN_PATH:
        if not is_local(request):
            return remote_view("remote view: first-run setup is done on the microscope PC")
        return own_origin_refusal(request)
    if path in AUTH_OPEN_PATHS:
        return origin_refusal(request)
    if path == COMMANDS_PATH:
        return None
    if path == SHUTDOWN_PATH:
        return _shutdown_refusal(request)
    return command_refusal(request)  # any other write: loopback, logged in, unlocked


def hardware_root(records_root: str | Path) -> Path:
    """The microscope's own hardware profile folder (not per session; manager, T-028)."""
    return Path(records_root) / "microscope" / "hardware"


def import_operations() -> list[str]:
    """Import every module in `engine.operations`: operations register themselves in
    `OPERATIONS` on import (WP-C). Called by `build_runner`, not at server import, so the
    server package stays light. Returns the module names."""
    from ..engine import operations

    names = sorted(m.name for m in pkgutil.iter_modules(operations.__path__)
                   if not m.name.startswith("_"))
    for name in names:
        importlib.import_module(f"{operations.__name__}.{name}")
    return names


def build_runner(backend: Any, *, records_root: str | Path, auth: AuthSeat | None = None,
                 registry: Any = None, **runner_kw: Any) -> tuple[Any, Any]:
    """The engine the server owns: a `Runner` over `backend` with every registered operation,
    the hardware provider (T-028 `register_hardware` over `ProfileStore(<records root>/
    microscope/hardware)`) as its `hardware=`, and T-018 device control as its control seat.
    The registry is a copy, so building twice (tests, a restart) never re-registers into the
    shared `OPERATIONS`. Returns `(runner, hardware)`; pass `hardware` to `create_app` too, so
    the assistant's tool `gates=` can use `hardware.check`. `runner_kw` goes to `Runner`."""
    from ..engine.gates import ProfileStore
    from ..engine.operations.hardware_scan import register_hardware
    from ..engine.runner import OPERATIONS, DeviceControlSeat, Registry, Runner

    import_operations()
    source = registry if registry is not None else OPERATIONS
    reg = Registry()
    hw_ops = ("hardware_scan", "hardware_confirm")
    for name in source.names():
        if name not in hw_ops:  # bound to this runner's profile store below
            reg.register(source.get(name))
    hw = register_hardware(reg, ProfileStore(hardware_root(records_root)))
    if auth is not None:
        runner_kw.setdefault("control", DeviceControlSeat(auth.control))
    return Runner(backend, registry=reg, hardware=hw, **runner_kw), hw


def install_sample_seat(engine: EngineAPI, records: Any, samples_root: Path | None,
                        sessions: SessionSeat) -> None:
    """The one seam between the server and the sample operations (T-027)."""
    seat = sample_ops.SampleSeat(records, Path(samples_root or sample_ops.SAMPLES_ROOT),
                                 sessions.session_for)
    sample_ops.install_sample_seat(engine, seat)


INTERRUPTED_NOTE = "interrupted: server restart"
COMMITTER_STOP_S = 30.0


def close_interrupted_sessions(records: Any, committer: Any = None) -> list[str]:
    """Close every experiment session a crash left `open` (manager decision, T-009e). None is
    handed to the engine: the operator carries on with `continue_from` (T-106 "Continue"), so
    a restarted server never resumes motion context on its own. Returns the closed ids."""
    from ..records import ExperimentSession

    closed = []
    for info in records.list_sessions():
        if info.get("status") != "open":
            continue
        sid = info["session_id"]
        try:
            ExperimentSession.load(records, sid, committer=committer).close(note=INTERRUPTED_NOTE)
        except Exception:
            log.exception("could not close interrupted session %s", sid)
            continue
        log.warning("closed experiment session %s left open by the last run", sid)
        closed.append(sid)
    return closed


def stop_committer(committer: Any, timeout_s: float = COMMITTER_STOP_S) -> None:
    """Let queued record commits finish, then end the worker. Never raises."""
    try:
        if not committer.flush(timeout_s):
            log.warning("record commits still queued after %.0f s at shutdown", timeout_s)
        committer.stop(timeout_s)
    except Exception:
        log.exception("stopping the records auto-committer failed")


def _package_version() -> str:
    try:
        return version("dino-autofocus")
    except PackageNotFoundError:
        return "0+unknown"


def create_app(
    engine: EngineAPI,
    *,
    agent_store: AgentStore | None = None,
    auth: AuthSeat | None = None,
    records: Any = None,
    committer: Any = None,
    hardware: Any = None,
    samples_root: Path | None = None,
    remote_view: bool = False,
    remote_abort: bool = True,
    allowed_hosts: Sequence[str] = (),
    dev_origins: Sequence[str] = (),
    engine_name: str = "unknown",
    web_dist: Path | None = None,
) -> FastAPI:
    """`agent_store` defaults to a `MockStore` (dev); `auth` to an `AuthSeat` with no accounts
    in a temporary folder (nobody can log in; the launcher passes `AuthSeat.from_config()`).
    `records` (a T-019 RecordsStore) installs the engine's sample seat (T-027): the sample
    operations write through the server's one open ExperimentSession (`app.state.sessions`,
    set by the sessions router). Without it the sample operations refuse. It is also on
    `app.state.records` for the sessions router. `committer` (the T-019 AutoCommitter the
    records are written with) is flushed and stopped when the app shuts down.
    `hardware` (from `build_runner`) is kept on `app.state.hardware`: the gates the
    assistant's tools ask (`gates=app.state.hardware.check`, T-013b) and the screens read.
    `allowed_hosts` adds Host header names beyond the loopback ones; under remote view the
    launcher passes this PC's host names and addresses. `dev_origins` names page origins
    besides this server's own that may write, e.g. the Vite dev server
    `http://localhost:5173` (T-010); none by default."""
    stopper = EngineStopper(engine)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        app.state.sessions.clear()  # nothing open until the operator opens or continues one
        if records is not None:
            app.state.interrupted_sessions = await asyncio.to_thread(
                close_interrupted_sessions, records, committer)
        yield
        await asyncio.to_thread(stopper.quietly, "server stopping")
        if committer is not None:  # after the engine's last records, before exit
            await asyncio.to_thread(stop_committer, committer)

    app = FastAPI(title="dino-autofocus", version=_package_version(), lifespan=lifespan)
    app.state.engine = engine
    app.state.agent_store = agent_store if agent_store is not None else MockStore()
    app.state.auth = auth if auth is not None else AuthSeat.throwaway()
    app.state.sessions = SessionSeat()
    app.state.records = records
    app.state.committer = committer
    app.state.interrupted_sessions = []  # closed at start-up, for the sessions screen
    app.state.hardware = hardware
    if records is not None:
        install_sample_seat(engine, records, samples_root, app.state.sessions)
    app.state.remote_view = remote_view
    app.state.remote_abort = remote_abort
    app.state.dev_origins = frozenset(normalize_origin(o) for o in dev_origins)
    app.state.stop_engine = stopper
    app.state.request_exit = None  # set by the launcher: makes the server process exit

    @app.middleware("http")
    async def access(request: Request, call_next):
        if request.url.path.startswith("/api/") and (why := _http_refusal(request)):
            return why.response()
        return await call_next(request)

    # added last, so it runs first, for HTTP and WebSocket alike
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=[*LOOPBACK_HOSTS, *allowed_hosts], www_redirect=False)

    @app.get("/api/health", response_model=Health, tags=["server"])
    def health() -> Health:
        return Health(engine=engine_name, remote_view=remote_view, remote_abort=remote_abort)

    @app.get("/api/state", response_model=Snapshot, tags=["server"])
    def state(eng: Engine) -> Snapshot:
        """The engine's snapshot: positions, lights, running operations, session, sample..."""
        return Snapshot.model_validate(eng.snapshot())

    @app.get("/api/permissions", response_model=dict[str, PermissionOut], tags=["server"])
    def permissions(request: Request, eng: Engine, seat: Auth,
                    ops: str = "") -> dict[str, PermissionOut]:
        """`?ops=a,b,c` -> may I do each now, and if not, why. Engine operations and the stops
        come from the engine's `check()` with login, loopback, role and D13 on top; the
        session actions and `submit_question` from the T-018 permissions plus loopback."""
        me = login_state(request)
        names = list(dict.fromkeys(n.strip() for n in ops.split(",") if n.strip()))
        engine_ops = [n for n in names if n not in SERVER_ACTIONS]
        checked = (eng.check(engine_ops, {"user_id": me.user_id,
                                          "control_grant": seat.grant_for(me.info)})
                   if engine_ops else {})
        out = {}
        for n in names:
            if n in SERVER_ACTIONS or n in MAP_WRITE_OPS:
                why = server_action_why(me, n)
            else:
                why = command_why(me, n if n in STOPS else "start", n,
                                  remote_abort=remote_abort)
            if why is not None:
                out[n] = PermissionOut(allowed=False, reason=why.message, code=why.code)
            elif n in SERVER_ACTIONS:
                out[n] = PermissionOut(allowed=True)
            else:
                e = checked.get(n) or {"allowed": False, "reason": "the engine did not answer"}
                out[n] = PermissionOut(allowed=bool(e.get("allowed")), reason=e.get("reason"))
        return out

    @app.post(
        COMMANDS_PATH,
        response_model=CommandAccepted,
        responses={400: {"model": ApiError}, 401: {"model": ApiError},
                   403: {"model": ApiError}, 423: {"model": ApiError},
                   503: {"model": ApiError}},
        tags=["server"],
    )
    def commands(cmd: CommandIn, request: Request, eng: Engine, seat: Auth) -> CommandAccepted:
        """Hand a command to the engine. Whether it runs is reported by events."""
        if why := command_refusal(request, cmd.kind, cmd.op):
            raise why.http()
        if stopper.done:
            raise SHUTTING_DOWN.http()
        me = login_state(request)
        try:
            op_id = eng.submit(cmd.to_engine(remote=not me.local, user_id=me.user_id,
                                             control_grant=seat.grant_for(me.info)))
        except ValueError as e:  # runner.CommandRefused
            raise Refusal(400, "refused", str(e)).http() from e
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
        if why := _shutdown_refusal(request):
            raise why.http()
        request_exit = app.state.request_exit
        try:
            stopped = stopper(body.reason)
        except Exception as e:
            log.exception("engine shutdown failed")
            if request_exit is not None:
                request_exit()  # exit anyway; the atexit hook tries the engine once more
            raise Refusal(500, "shutdown_failed", f"engine shutdown failed: {e}").http() from e
        if request_exit is not None:
            tasks.add_task(request_exit)  # after the response has gone out
        return ShutdownAccepted(reason=stopper.reason or body.reason, already=not stopped)

    include_area_routers(app)
    ws.install(app, engine, stopped=lambda: stopper.done)
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
