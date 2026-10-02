"""`/api/hardware` (T-101): read-only views of the engine's hardware state, on a fake engine."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from dino_autofocus.engine.gates import DeviceStatus, HardwareProfile, evaluate

VIEWER = "vera@example.test"  # the seeded viewer in conftest.py


@pytest.fixture
def with_hardware(engine):
    """`with_hardware(block)`: conftest's FakeEngine, whose snapshot carries the T-011 hardware
    block `snapshot()["hardware"]`."""

    def make(block: dict[str, Any]):
        plain = engine.snapshot
        engine.snapshot = lambda: {**plain(), "hardware": block}
        return engine

    return make


def skeleton_profile() -> HardwareProfile:
    return HardwareProfile(
        backend_kind="mock",
        detected_at="2026-10-01T18:00:00",
        devices={
            "camera": DeviceStatus(True, True, "Kinetix_red"),
            "xy_stage": DeviceStatus(True, False, "XYStage", "no read-back"),
            "z_drive": DeviceStatus(True, True, "ZDrive"),
        },
        objectives=["1-Plan Apo LmbdD20 4x"],
        camera_bit_depth=12,
        confirmed={"DiaLamp intensity": "otto@example.test 2026-10-01T18:05"},
    )


def hardware_block(p: HardwareProfile | None = None, **extra: Any) -> dict[str, Any]:
    p = p or skeleton_profile()
    verdict = {op: asdict(r) for op, r in evaluate(p).items()}
    return {
        "profile": asdict(p),
        "profile_path": "D:/AutoFocus/hardware/hardware_profile.json",
        "gates": verdict,
        "last_status": None,
        **extra,
    }


@pytest.fixture
def hw_engine(with_hardware):
    return with_hardware(hardware_block())


def test_router_is_mounted_read_only(make_client, hw_engine):
    c = make_client(hw_engine)
    paths = c.get("/openapi.json").json()["paths"]
    mine = {p: m for p, m in paths.items() if p.startswith("/api/hardware")}
    assert set(mine) == {
        "/api/hardware/profile",
        "/api/hardware/gates",
        "/api/hardware/gates/{op}",
        "/api/hardware/status",
    }
    assert all(set(methods) == {"get"} for methods in mine.values())
    assert c.post("/api/hardware/profile", json={}).status_code == 405


def test_profile_is_null_before_the_first_scan(make_client, with_hardware):
    c = make_client(
        with_hardware({"profile": None, "profile_path": None, "gates": {}, "last_status": None})
    )
    r = c.get("/api/hardware/profile")
    assert r.status_code == 200
    assert r.json() == {"profile": None, "path": None, "sha256": None, "error": None}


def test_profile_without_a_hardware_block(make_client, engine):
    """An engine that reports no hardware block at all reads as "never scanned"."""
    c = make_client(engine)
    assert c.get("/api/hardware/profile").json()["profile"] is None
    assert c.get("/api/hardware/gates").json() == []
    assert c.get("/api/hardware/status").json() is None


def test_skeleton_profile_is_reshaped_for_the_screen(make_client, hw_engine):
    body = make_client(hw_engine).get("/api/hardware/profile").json()
    p = body["profile"]
    assert body["path"].endswith("hardware_profile.json")
    assert len(body["sha256"]) == 64
    assert p["backend"] == "mock" and p["detected_at"] == "2026-10-01T18:00:00"
    xy = next(d for d in p["devices"] if d["role"] == "xy_stage")
    assert xy == {
        "label": "XYStage",
        "role": "xy_stage",
        "type": None,
        "library": None,
        "present": True,
        "read_back": False,
        "write_verified": None,
        "note": "no read-back",
    }
    assert p["objectives"] == [
        {
            "label": "1-Plan Apo LmbdD20 4x",
            "state": None,
            "magnification": None,
            "na": None,
            "immersion": None,
            "working_distance_um": None,
            "pixel_um": None,
        }
    ]
    assert p["camera"]["bit_depth"] == 12
    # the skeleton keeps only who/when: the value is shown as not reported (contract G5)
    assert p["human_confirmed"]["DiaLamp intensity"] == {
        "value": "not reported",
        "by": "otto@example.test 2026-10-01T18:05",
        "at": None,
    }


def test_operations_spec_profile_passes_through(make_client, with_hardware):
    rich = {
        "detected_at": "2026-10-02T09:00:00",
        "backend": "mm-demo",
        "host": "MICROSCOPE",
        "config": {"path": "C:/mm/demo.cfg", "sha256": "ab" * 32},
        "previous_sha256": "cd" * 32,
        "changed": ["devices"],
        "devices": [
            {
                "label": "Camera",
                "type": "CameraDevice",
                "library": "DemoCamera",
                "read_back": True,
                "write_verified": None,
                "properties": {"Binning": {}},
            }
        ],
        "objectives": [
            {
                "label": "6-Plan Apo 100x Oil",
                "state": 5,
                "magnification": 100,
                "na": 1.45,
                "immersion": "oil",
                "working_distance_um": 130,
                "pixel_um": 0.065,
                "registry_key": "100x-Oil",
            }
        ],
        "camera": {"name": "Camera", "sensor": [512, 512], "bit_depth": 12, "ceiling_adu": 4095},
        "piezo": {"port": "", "connected": False},
        "human_confirmed": {
            "DiaLamp intensity": {"value": "608/2100", "by": "otto", "at": "09:01"}
        },
    }
    eng = with_hardware({"profile": rich, "profile_path": None, "gates": {}, "last_status": None})
    p = make_client(eng).get("/api/hardware/profile").json()["profile"]
    assert p["host"] == "MICROSCOPE" and p["changed"] == ["devices"]
    assert p["devices"][0]["present"] is True and p["devices"][0]["library"] == "DemoCamera"
    assert p["objectives"][0]["working_distance_um"] == 130
    assert p["camera"]["sensor"] == [512, 512]
    assert p["piezo"] == {"port": "", "connected": False, "z_um": None, "error": None}
    assert p["human_confirmed"]["DiaLamp intensity"]["value"] == "608/2100"


def test_gates_off_first_with_reasons_and_requirements(make_client, hw_engine):
    rows = make_client(hw_engine).get("/api/hardware/gates").json()
    assert [r["enabled"] for r in rows] == sorted(r["enabled"] for r in rows)  # off rows first
    sample_map = next(r for r in rows if r["op"] == "sample_map")
    assert sample_map["enabled"] is False
    assert "xy_stage detected but its state did not read back" in sample_map["reasons"]
    assert sample_map["requires"]["devices"] == ["camera", "xy_stage", "z_drive", "dia_lamp"]
    assert sample_map["requires"]["objectives"] == ["4x"]


def test_gate_requirements_from_the_engine_win(make_client, with_hardware):
    gates = {
        "light_set": {
            "op": "light_set",
            "enabled": True,
            "reasons": [],
            "requires": {"devices": ["dia_lamp", "aura"]},
        }
    }
    eng = with_hardware({"profile": None, "gates": gates, "last_status": None})
    row = make_client(eng).get("/api/hardware/gates/light_set").json()
    assert row == {
        "op": "light_set",
        "enabled": True,
        "reasons": [],
        "requires": {"devices": ["dia_lamp", "aura"], "objectives": [], "confirmed": []},
    }


def test_unknown_gate_is_404_with_a_refusal_code(make_client, hw_engine):
    r = make_client(hw_engine).get("/api/hardware/gates/no_such_op")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "unknown_gate"
    assert r.headers["X-DinoAF-Refusal"] == "unknown_gate"


def test_status_is_the_last_result(make_client, with_hardware):
    last = {
        "op_id": "op7",
        "t": 1759340000.0,
        "summary": {
            "nosepiece_label": "1-Plan Apo LmbdD20 4x",
            "z_um": 3012.5,
            "pfs_in_range": "Out of Range",
        },
    }
    eng = with_hardware(hardware_block(last_status=last))
    body = make_client(eng).get("/api/hardware/status").json()
    assert body == {"op_id": "op7", "t": 1759340000.0, "user_id": None, "summary": last["summary"]}


def test_engine_hardware_error_is_reported(make_client, with_hardware):
    eng = with_hardware(
        {"profile": None, "gates": {}, "last_status": None, "error": "profile file unreadable"}
    )
    assert (
        make_client(eng).get("/api/hardware/profile").json()["error"] == "profile file unreadable"
    )


def test_a_remote_viewer_reads(make_client, hw_engine):
    c = make_client(hw_engine, remote=True, login=VIEWER)
    for path in ("/api/hardware/profile", "/api/hardware/gates", "/api/hardware/status"):
        assert c.get(path).status_code == 200, path


def test_reads_need_a_login(make_client, hw_engine):
    r = make_client(hw_engine, login=None).get("/api/hardware/profile")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "login_required"


def test_router_never_writes_to_the_engine(make_client, hw_engine):
    c = make_client(hw_engine)
    for path in (
        "/api/hardware/profile",
        "/api/hardware/gates",
        "/api/hardware/gates/status",
        "/api/hardware/status",
    ):
        c.get(path)
    assert hw_engine.commands == []
