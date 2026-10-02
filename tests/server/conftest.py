"""A fake engine for the server tests: records commands, lets the test emit events and frames."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dino_autofocus.agents import MockStore
from dino_autofocus.server import create_app
from dino_autofocus.server.schemas import Command, Event

LOCAL = ("127.0.0.1", 50000)
REMOTE = ("192.168.1.20", 50000)


class FakeEngine:
    def __init__(self) -> None:
        self.commands: list[Command] = []
        self.sinks: list[Callable[[Event], None]] = []
        self.frame: tuple[np.ndarray, dict[str, Any]] | None = None
        self.frame_reads = 0
        self.shutdowns: list[str] = []
        self.fail_shutdown = False  # the next shutdown raises once
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
        return {"positions": {"x_um": 1.0, "y_um": 2.0, "z_um": 3000.0}, "running": None}

    def emit(self, kind: str, op_id: str = "", **data: Any) -> None:
        for s in list(self.sinks):
            s(Event(kind=kind, op_id=op_id, data=data))


class FakeFrameEngine(FakeEngine):
    def latest_frame(self) -> tuple[np.ndarray, dict[str, Any]] | None:
        self.frame_reads += 1
        return self.frame


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def frame_engine() -> FakeFrameEngine:
    return FakeFrameEngine()


class LoopbackClient(TestClient):
    """TestClient sends WebSockets to ws://testserver whatever base_url says; the Host
    allow-list refuses that, so relative WebSocket paths go to the loopback base instead."""

    def websocket_connect(self, url: str, *args, **kwargs):
        if url.startswith("/"):
            url = f"ws://{self.base_url.netloc.decode()}{url}"
        return super().websocket_connect(url, *args, **kwargs)


@pytest.fixture(scope="session")
def agent_store(tmp_path_factory):
    """One MockStore for the whole run: building one takes a fraction of a second."""
    return MockStore(tmp_path_factory.mktemp("agent-store"))


@pytest.fixture
def make_client(tmp_path, agent_store):
    """`make_client(engine, remote=False, **create_app_kwargs)`; no web build unless given."""

    def make(engine: Any, *, remote: bool = False, **kw) -> TestClient:
        kw.setdefault("web_dist", tmp_path / "no-web-dist")
        kw.setdefault("agent_store", agent_store)
        app = create_app(engine, engine_name="fake", **kw)
        return LoopbackClient(app, base_url="http://127.0.0.1:8765",
                              client=REMOTE if remote else LOCAL)

    return make
