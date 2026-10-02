"""Fakes for the server tests: an engine that records commands and lets the test emit events
and frames, and seeded fake accounts (example.test only) with a test-only password.

Test modules import them from here, by name (T-015e); the fixtures stay in
tests/server/conftest.py."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np
from fastapi.testclient import TestClient

from dino_autofocus.server.api import SESSION_COOKIE, AuthSeat
from dino_autofocus.server.schemas import Command, Event

LOCAL = ("127.0.0.1", 50000)
REMOTE = ("192.168.1.20", 50000)
#: the one password every seeded fake user gets (a test value, not a real credential)
TEST_PASSWORD = "server-test-pass-1"
ADMIN, OPERATOR, OPERATOR2, VIEWER = (
    "admin@example.test", "otto@example.test", "olga@example.test", "vera@example.test")
USERS = [
    {"name": "Ada Admin", "email": ADMIN, "role": "admin"},
    {"name": "Otto Operator", "email": OPERATOR, "role": "operator"},
    {"name": "Olga Operator", "email": OPERATOR2, "role": "operator"},
    {"name": "Vera Viewer", "email": VIEWER, "role": "viewer"},
]


class FakeEngine:
    def __init__(self) -> None:
        self.commands: list[Command] = []
        self.sinks: list[Callable[[Event], None]] = []
        self.frame: tuple[np.ndarray, dict[str, Any]] | None = None
        self.frame_reads = 0
        self.shutdowns: list[str] = []
        self.fail_shutdown = False  # the next shutdown raises once
        self.viewers: list[int] = []  # every set_local_viewers report
        self.checks: list[tuple[list[str] | None, dict | None]] = []
        self._lock = threading.Lock()

    def submit(self, cmd: Command) -> str:
        if cmd.op == "unknown_op":
            raise ValueError("no operation named 'unknown_op'")
        self.commands.append(cmd)
        return cmd.op_id or f"op{len(self.commands)}"

    def subscribe(self, sink: Callable[[Event], None]) -> Callable[[], None]:
        with self._lock:
            self.sinks.append(sink)
        return lambda: self.sinks.remove(sink)

    def shutdown(self, reason: str) -> None:
        if self.fail_shutdown:
            self.fail_shutdown = False
            raise RuntimeError("readback timed out")
        self.shutdowns.append(reason)

    def snapshot(self) -> dict[str, Any]:
        return {"positions": {"x_um": 1.0, "y_um": 2.0, "z_um": 3000.0}, "running": []}

    def check(self, ops: list[str] | None = None, context: dict | None = None) -> dict:
        """The engine's own answer: allowed unless the op is `busy_op`, and only with a grant
        for ops other than the stops."""
        self.checks.append((ops, context))
        out = {}
        for op in ops or []:
            if op == "busy_op":
                out[op] = {"allowed": False, "reason": "busy: scan_4x_1 holds the core"}
            elif op not in ("abort", "lights_off") and not (context or {}).get("control_grant"):
                out[op] = {"allowed": False, "reason": "does not hold equipment control"}
            else:
                out[op] = {"allowed": True, "reason": None}
        return out

    def set_local_viewers(self, count: int) -> None:
        self.viewers.append(count)

    def emit(self, kind: str, op_id: str = "", **data: Any) -> None:
        for s in list(self.sinks):
            s(Event(kind=kind, op_id=op_id, data=data))


class FakeFrameEngine(FakeEngine):
    def latest_frame(self) -> tuple[np.ndarray, dict[str, Any]] | None:
        self.frame_reads += 1
        return self.frame


class LoopbackClient(TestClient):
    """TestClient sends WebSockets to ws://testserver whatever base_url says; the Host
    allow-list refuses that, so relative WebSocket paths go to the loopback base instead."""

    login_token: str | None = None

    def websocket_connect(self, url: str, *args, **kwargs):
        if url.startswith("/"):
            url = f"ws://{self.base_url.netloc.decode()}{url}"
        return super().websocket_connect(url, *args, **kwargs)


def log_in(seat: AuthSeat, client: LoopbackClient, email: str) -> str:
    result = seat.logins.login(email, TEST_PASSWORD)
    assert result.ok, result.message
    client.cookies.set(SESSION_COOKIE, result.token)
    client.login_token = result.token
    return result.token
