"""Who may command: D13 remote abort, and the Host header allow-list (DNS rebinding)."""

from __future__ import annotations

import json

import pytest
from starlette.websockets import WebSocketDisconnect


def test_remote_viewer_may_abort_only(engine, make_client):
    c = make_client(engine, remote=True, remote_view=True)
    assert c.post("/api/commands", json={"kind": "abort", "op_id": "op9"}).json() == \
        {"op_id": "op9"}
    for kind in ("start", "confirm", "lights_off"):
        r = c.post("/api/commands", json={"kind": kind, "op": "status"})
        assert r.status_code == 403
        assert "abort only" in r.json()["detail"]
    assert [x.kind for x in engine.commands] == ["abort"]


def test_remote_abort_can_be_switched_off(engine, make_client):
    c = make_client(engine, remote=True, remote_view=True, remote_abort=False)
    assert c.get("/api/health").json()["remote_abort"] is False
    assert c.post("/api/commands", json={"kind": "abort", "op_id": "op9"}).status_code == 403
    assert engine.commands == []


def test_remote_abort_over_websocket(engine, make_client):
    with make_client(engine, remote=True, remote_view=True) as c, \
            c.websocket_connect("/ws/events") as ws:
        ws.send_text(json.dumps({"type": "command", "command": {"kind": "abort", "op_id": "a"}}))
        assert json.loads(ws.receive_text()) == {"type": "accepted", "op_id": "a"}
        ws.send_text(json.dumps({"type": "command", "command": {"kind": "lights_off"}}))
        assert json.loads(ws.receive_text())["status"] == 403
    assert [x.kind for x in engine.commands] == ["abort"]


def test_foreign_page_may_not_abort_either(engine, make_client):
    c = make_client(engine)
    r = c.post("/api/commands", json={"kind": "abort"}, headers={"origin": "https://example.com"})
    assert r.status_code == 403


def test_host_allow_list(engine, make_client):
    """A page whose domain was rebound to 127.0.0.1 sends its own name as Host: refused,
    reads included, even though it is same-origin with itself and the socket is loopback."""
    c = make_client(engine)
    rebound = {"host": "evil.example:8765", "origin": "http://evil.example:8765"}
    assert c.get("/api/state", headers=rebound).status_code == 400
    assert c.post("/api/commands", json={"kind": "lights_off"}, headers=rebound).status_code \
        == 400
    assert c.get("/api/state", headers={"host": "localhost:8765"}).status_code == 200
    with pytest.raises(WebSocketDisconnect), \
            c.websocket_connect("/ws/events", headers=rebound) as ws:
        ws.receive_text()
    assert engine.commands == [] and engine.sinks == []


def test_extra_allowed_hosts_for_remote_view(engine, make_client):
    c = make_client(engine, remote=True, remote_view=True, allowed_hosts=["scope-pc"])
    assert c.get("/api/state", headers={"host": "scope-pc:8765"}).status_code == 200
    assert c.get("/api/state", headers={"host": "other-pc:8765"}).status_code == 400


@pytest.mark.parametrize("op", ["map_flag", "map_flag_retire", "candidate_confirm",
                                "candidate_reject"])
def test_map_writes_only_through_map_router(op, engine, make_client):
    """D16: the common endpoint must not bypass WRITE_MAP_FLAG in server/api/map.py."""
    c = make_client(engine)
    r = c.post("/api/commands", json={"kind": "start", "op": op})
    assert r.status_code == 403
    assert "/api/map" in r.json()["detail"]
    with c.websocket_connect("/ws/events") as ws:
        ws.send_text(json.dumps({"type": "command", "command": {"kind": "start", "op": op}}))
        assert json.loads(ws.receive_text())["status"] == 403
    assert engine.commands == []


def test_login_routes_open_to_remote_viewers(engine, make_client):
    """Exactly the five login routes skip the loopback rule (they 404 until T-018 adds them);
    any other write under /api/auth stays local only, and foreign pages are still refused."""
    c = make_client(engine, remote=True, remote_view=True)
    for name in ("login", "logout", "unlock", "activity", "signup"):
        assert c.post(f"/api/auth/{name}", json={}).status_code == 404
    assert c.post("/api/auth/users", json={}).status_code == 403
    assert c.post("/api/auth/login/extra", json={}).status_code == 403
    foreign = c.post("/api/auth/login", json={}, headers={"origin": "https://example.com"})
    assert foreign.status_code == 403
