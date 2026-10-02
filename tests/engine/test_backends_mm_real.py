"""mm-real backend (T-033). No hardware here: the shared `BackendContract` runs the real code
on Micro-Manager's demo config (`DEMO_DEVICES`), skipped without the demo adapters, and
the bench light order runs on a stub core with the bench device names. Each test releases
the core it opened; nothing opens a window.

The T-036 bench motion lock is in tests/engine/test_backends_mm_real_lock.py.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from test_contract_backend_v2 import BackendContract

from dino_autofocus.engine.backend import (
    GUARD_TOKEN,
    PROVISIONAL,
    PropertyNotAllowed,
    UnguardedMotion,
)
from dino_autofocus.engine.backends import mm_real
from dino_autofocus.engine.backends.mm_real import (
    BENCH_CONFIG,
    DEMO_DEVICES,
    BenchMotionLocked,
    MmRealBackend,
    MmUnavailable,
    config_path,
)

T = GUARD_TOKEN  # tests stand in for engine.guards


def open_on_demo(**kw) -> MmRealBackend:
    from dino_autofocus.engine.backends.mm_demo_core import DemoUnavailable, find_demo_config

    try:
        b = MmRealBackend(find_demo_config(), devices=DEMO_DEVICES, **kw)
        b.open()
    except (DemoUnavailable, MmUnavailable) as e:
        pytest.skip(f"Micro-Manager demo adapters not available: {e}")
    return b


@pytest.fixture
def real():
    b = open_on_demo(roi=128)
    try:
        yield b
    finally:
        b.close()


class TestMmRealOnDemoContract(BackendContract):
    light_write = ("White Light Shutter", "State", 0)
    bench = True  # mm-real is the bench even on the demo config

    @pytest.fixture
    def backend(self, real):
        return real

    def test_move_xy_rel_needs_the_token_and_moves_by_the_step(self, backend):
        """T-036: on mm-real the shared relative-move check becomes a refusal while locked."""
        p0 = backend.positions()
        with pytest.raises(BenchMotionLocked, match="T-027, T-011"):
            backend.move_xy_rel(10.0, -5.0, token=GUARD_TOKEN)
        assert (backend.positions().x_um, backend.positions().y_um) == (p0.x_um, p0.y_um)


# -- no hardware needed


def test_import_pulls_in_no_device_library():
    code = ("import sys, dino_autofocus.engine.backends.mm_real; "
            "bad = {'pymmcore', 'pymmcore_plus', 'torch', 'tkinter'} & set(sys.modules); "
            "assert not bad, bad")
    subprocess.run([sys.executable, "-c", code], check=True)


def test_config_path_argument_env_settings_default(monkeypatch, tmp_path):
    monkeypatch.delenv(mm_real.CONFIG_ENV, raising=False)
    monkeypatch.setenv("DINO_AF_CONFIG_DIR", str(tmp_path))
    assert config_path() == BENCH_CONFIG
    (tmp_path / "settings.json").write_text(json.dumps({"mm_config": "D:/cfg/a.cfg"}))
    assert str(config_path()).replace("\\", "/") == "D:/cfg/a.cfg"
    monkeypatch.setenv(mm_real.CONFIG_ENV, "D:/cfg/env.cfg")
    assert str(config_path()).replace("\\", "/") == "D:/cfg/env.cfg"
    assert config_path(tmp_path / "x.cfg") == tmp_path / "x.cfg"


def test_missing_config_is_unavailable_not_a_crash(tmp_path):
    b = MmRealBackend(tmp_path / "nope.cfg")
    with pytest.raises(MmUnavailable):
        b.open()
    b.close()  # never opened: nothing to release


def test_piezo_is_read_only_and_a_missing_link_is_a_field(monkeypatch, tmp_path):
    assert not any(hasattr(mm_real._PiezoReadOnly, n) for n in ("move_z", "_do",
                                                                 "ensure_user_level"))
    monkeypatch.setattr(mm_real._PiezoReadOnly, "LIBRARY", tmp_path / "none.dll")
    b = MmRealBackend(tmp_path / "x.cfg")
    r = b.piezo_read("COM4")
    assert not r.connected and "NanoBench" in r.error
    r0 = b.piezo_read("")
    assert r0.port == "" and not r0.connected and r0.error is None


class StubCore:
    """The few core calls the light and property paths make, with bench device names."""

    def __init__(self):
        self.props = {("DiaLamp", "State"): "0", ("Aura", "State"): "0",
                      **{("Aura", ln): "0" for ln in ("GREEN", "CYAN")},
                      **{("Aura", f"{ln}_Intensity"): "0" for ln in ("GREEN", "CYAN")}}
        self.writes: list[tuple[str, str, str]] = []

    def getLoadedDevices(self):
        return ["DiaLamp", "Aura", "Kinetix_red", "ZDrive", "XYStage", "Nosepiece", "PFS"]

    def getCameraDevice(self):
        return "Kinetix_red"

    def hasProperty(self, dev, prop):
        return (dev, prop) in self.props

    def getProperty(self, dev, prop):
        return self.props[(dev, prop)]

    def setProperty(self, dev, prop, value):
        self.writes.append((dev, prop, str(value)))
        self.props[(dev, prop)] = str(value)

    def waitForDevice(self, dev):
        pass


@pytest.fixture
def stub(tmp_path):
    b = MmRealBackend(tmp_path / "bench.cfg")
    b.core = StubCore()
    yield b
    b.core = None


def test_bench_aura_follows_the_mm_grab_order(stub):
    with pytest.raises(UnguardedMotion):
        stub.aura_line_on("GREEN", 1, token=None)
    assert not stub.core.writes
    rbs = stub.aura_line_on("green", 1, token=T)
    assert stub.core.writes == [("DiaLamp", "State", "0"), ("Aura", "GREEN_Intensity", "10"),
                                ("Aura", "GREEN", "1"), ("Aura", "State", "1")]
    assert all(r.verified and not r.notes for r in rbs)
    cyan = stub.aura_line_on("CYAN", 2, token=T)
    assert cyan[1].notes == {"aura_line": PROVISIONAL}
    assert stub.light_state() == {"DiaLamp": "0", "Aura": "1"}
    assert [(r.device, r.read) for r in stub.all_off()] == [("Aura", "0"), ("DiaLamp", "0")]


def test_bench_lamp_and_set_property_allow_list(stub):
    stub.lamp_on(token=T)
    assert stub.core.writes[-2:] == [("Aura", "State", "0"), ("DiaLamp", "State", "1")]
    for dev in ("ZDrive", "XYStage", "Nosepiece", "PFS"):
        with pytest.raises(UnguardedMotion):
            stub.set_property(dev, "State", 1, token=T)
    with pytest.raises(UnguardedMotion):
        stub.set_property("DiaLamp", "State", 1)
    with pytest.raises(PropertyNotAllowed):
        stub.set_property("Kinetix_red", "ReadoutRate", "100MHz 12bit")  # not listed yet
    with pytest.raises(PropertyNotAllowed):  # listed, but not on this config
        stub.set_property("White Light Shutter", "State", 0, token=T)


# -- the real code on the demo config


def test_info_is_bench_flagged_with_user_checks(real):
    info = real.info()
    assert info.bench and info.kind == "mm-real" and info.camera == "Camera"
    assert "user check needed" in info.notes["stage_limits"]
    assert "ReadoutRate" in info.notes["user_check"]
    assert info.notes["aura.CYAN"] == PROVISIONAL
    json.dumps(info.to_dict())


def test_config_record_shows_autoshutter_off_and_the_startup_preset(real):
    c = real.config_record()
    assert c.autoshutter.verified and c.autoshutter.read == "0"
    assert c.startup_preset == "System/Startup" and c.sha256
    assert c.changed_during_load is False


def test_motion_code_reads_back_on_the_demo_once_unlocked(real, monkeypatch):
    """The code that runs after a reviewed commit lifts the T-036 lock. Unlocking here is a
    test-only monkeypatch; the shipped constant stays LOCKED (test_backends_mm_real_lock)."""
    monkeypatch.setattr(mm_real, "BENCH_MOTION", "UNLOCKED")
    assert real.move_z(12.5, token=T) == pytest.approx(12.5, abs=0.01)
    x, y = real.move_xy(100.0, -50.0, token=T, timeout_s=10)
    assert (x, y) == pytest.approx((100.0, -50.0), abs=0.5)
    labels = real.nosepiece_labels()
    rb = real.set_nosepiece(1, token=T)
    assert rb.verified and real.nosepiece() == labels[1].label
    with pytest.raises(ValueError):
        real.set_nosepiece(len(labels), token=T)


def test_no_aura_or_pfs_on_the_demo_config(real):
    assert real.pfs().enabled is None and real.pfs_off(token=T).notes
    with pytest.raises(PropertyNotAllowed):
        real.aura_line_on("GREEN", 1, token=T)
    assert set(real.light_state()) == {"DiaLamp"}
    assert real.lamp_on(token=T)[-1].read == "1"
    assert [r.read for r in real.all_off()] == ["0"]
