from __future__ import annotations

import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dino_autofocus.server.api import include_area_routers


def test_health_and_state(engine, make_client):
    c = make_client(engine, remote_view=True)
    assert c.get("/api/health").json() == {"status": "ok", "engine": "fake", "remote_view": True}
    assert c.get("/api/state").json() == engine.snapshot()


def test_command_round_trip(engine, make_client):
    c = make_client(engine)
    r = c.post("/api/commands", json={"kind": "start", "op": "status", "args": {"n": 2}})
    assert r.status_code == 200
    assert r.json() == {"op_id": "op1"}
    (cmd,) = engine.commands
    assert (cmd.kind, cmd.op, cmd.args) == ("start", "status", {"n": 2})
    assert cmd.t > 0

    r = c.post("/api/commands", json={"kind": "abort", "op_id": "op1"})
    assert r.json() == {"op_id": "op1"}
    assert c.post("/api/commands", json={"kind": "lights_off"}).status_code == 200
    assert [x.kind for x in engine.commands] == ["start", "abort", "lights_off"]


def test_bad_commands(engine, make_client):
    c = make_client(engine)
    assert c.post("/api/commands", json={"kind": "move_z"}).status_code == 422
    r = c.post("/api/commands", json={"kind": "start", "op": "unknown_op"})
    assert r.status_code == 400
    assert "unknown_op" in r.json()["detail"]
    assert engine.commands == []


def test_remote_may_read_but_not_command(engine, make_client):
    c = make_client(engine, remote=True, remote_view=True)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/state").status_code == 200
    r = c.post("/api/commands", json={"kind": "lights_off"})
    assert r.status_code == 403
    assert "192.168.1.20" in r.json()["detail"]
    # any non-read method, on any path, including area routers and unknown paths
    assert c.put("/api/anything", json={}).status_code == 403
    assert c.delete("/api/anything").status_code == 403
    assert engine.commands == []


def test_commands_refused_from_foreign_pages(engine, make_client):
    c = make_client(engine)
    body = {"kind": "lights_off"}
    evil = c.post("/api/commands", json=body, headers={"origin": "https://example.com"})
    assert evil.status_code == 403
    same = c.post("/api/commands", json=body, headers={"origin": "http://testserver"})
    assert same.status_code == 200
    # the Vite dev server on this PC proxies to the API from another port
    dev = c.post("/api/commands", json=body, headers={"origin": "http://localhost:5173"})
    assert dev.status_code == 200
    assert len(engine.commands) == 2


def test_area_router_discovery(tmp_path, monkeypatch, engine):
    pkg = tmp_path / "fake_areas"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "_private.py").write_text("raise RuntimeError('must be skipped')\n")
    (pkg / "demo.py").write_text(
        "from fastapi import APIRouter\n"
        "from dino_autofocus.server.api import Engine\n"
        "router = APIRouter()\n"
        "@router.get('/ping')\n"
        "def ping(eng: Engine) -> dict:\n"
        "    return {'pong': eng.snapshot()['running']}\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    app = FastAPI()
    app.state.engine = engine
    assert include_area_routers(app, "fake_areas") == ["demo"]
    assert TestClient(app).get("/api/demo/ping").json() == {"pong": None}

    (pkg / "broken.py").write_text("x = 1\n")
    sys.modules.pop("fake_areas", None)
    try:
        include_area_routers(FastAPI(), "fake_areas")
    except TypeError as e:
        assert "broken" in str(e)
    else:
        raise AssertionError("a module without a router must be refused")


def test_no_area_routers_yet():
    assert include_area_routers(FastAPI()) == []
