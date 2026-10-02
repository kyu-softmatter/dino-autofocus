"""Backend contract v2 (T-015): set_property allow-list, light tokens, notes.

`BackendContract` holds the checks every backend must pass. It is not collected on its own
(no `Test` prefix); a backend's test file subclasses it and provides a `backend` fixture
(an opened backend, closed after the test). Other backends reuse it with

    from test_contract_backend_v2 import BackendContract

    class TestMockBackendContract(BackendContract):
        @pytest.fixture
        def backend(self): ...

The light property used for the token check defaults to the bench DiaLamp; a backend with
other device names sets `light_write` (device, prop, value). The value switches light off.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from conftest import FakeBackend

from dino_autofocus.engine.backend import (
    CAMERA_PROPERTIES,
    GUARD_TOKEN,
    LIGHT_PROPERTIES,
    MOTION_DEVICES,
    PROVISIONAL,
    Backend,
    PropertyNotAllowed,
    Readback,
    UnguardedMotion,
    check_set_property,
)


def _where(b: Backend) -> tuple:
    p = b.positions()
    return p.x_um, p.y_um, p.z_um, b.nosepiece()


class BackendContract:
    light_write: tuple[str, str, object] = ("DiaLamp", "State", 0)
    unlisted_write: tuple[str, str, object] = ("LightPath", "State", "4-L100")

    def test_meets_the_protocol(self, backend):
        assert isinstance(backend, Backend)

    @pytest.mark.parametrize("device", sorted(MOTION_DEVICES))
    def test_set_property_refuses_motion_devices_even_with_the_token(self, backend, device):
        before = _where(backend)
        for prop in ("State", "Position", "Focus"):
            with pytest.raises(UnguardedMotion):
                backend.set_property(device, prop, 1, token=GUARD_TOKEN)
            with pytest.raises(UnguardedMotion):
                backend.set_property(device, prop, 1)
        assert _where(backend) == before

    def test_light_property_needs_the_token(self, backend):
        device, prop, value = self.light_write
        before = backend.light_state()
        with pytest.raises(UnguardedMotion):
            backend.set_property(device, prop, value)
        assert backend.light_state() == before
        rec = backend.set_property(device, prop, value, token=GUARD_TOKEN)
        assert isinstance(rec, Readback) and rec.device == device and rec.prop == prop

    def test_listed_camera_property_needs_no_token(self, backend):
        info = backend.info()
        rec = backend.set_property(info.camera, "Exposure", info.exposure_ms)
        assert isinstance(rec, Readback)

    def test_unlisted_property_is_refused_with_the_allow_list(self, backend):
        device, prop, value = self.unlisted_write
        with pytest.raises(PropertyNotAllowed, match="allow-list"):
            backend.set_property(device, prop, value, token=GUARD_TOKEN)
        cam = backend.info().camera
        with pytest.raises(PropertyNotAllowed):  # camera names only on the camera device
            backend.set_property("Not" + cam, "Exposure", 10)

    def test_light_on_needs_the_token_and_off_never_does(self, backend):
        before = backend.light_state()
        with pytest.raises(UnguardedMotion):
            backend.lamp_on(token=None)
        with pytest.raises(UnguardedMotion):
            backend.aura_line_on("GREEN", 1.0, token=None)
        assert backend.light_state() == before
        assert backend.lamp_on(token=GUARD_TOKEN)
        for off in (backend.lamp_off, backend.aura_off, backend.all_off):
            assert all(isinstance(r, Readback) for r in off())

    def test_info_and_readbacks_carry_json_safe_notes(self, backend):
        info = backend.info()
        assert isinstance(info.notes, dict)
        json.dumps(info.to_dict())
        for r in backend.all_off():
            assert isinstance(r.notes, dict)
            json.dumps(asdict(r))


class TestFakeBackendContract(BackendContract):
    @pytest.fixture
    def backend(self):
        b = FakeBackend()
        b.open()
        yield b
        b.close()


def test_allow_list_groups_do_not_overlap():
    assert not {d for d, _ in LIGHT_PROPERTIES} & MOTION_DEVICES
    assert {"ZDrive", "XYStage", "Nosepiece", "PFS"} <= MOTION_DEVICES
    assert ("Aura", "GREEN_Intensity") in LIGHT_PROPERTIES
    assert {"Exposure", "PixelType"} <= CAMERA_PROPERTIES


def test_check_set_property_cases():
    check_set_property("Cam", "Exposure", None, camera="Cam")
    check_set_property("DiaLamp", "Intensity", GUARD_TOKEN, camera="Cam")
    with pytest.raises(UnguardedMotion):
        check_set_property("DiaLamp", "Intensity", None, camera="Cam")
    with pytest.raises(UnguardedMotion):
        check_set_property("Core", "Focus", GUARD_TOKEN, camera="Cam")
    with pytest.raises(PropertyNotAllowed):
        check_set_property("Cam", "Gain", None, camera="Cam")


def test_refused_writes_never_reach_the_fake_device():
    b = FakeBackend()
    for args in (("ZDrive", "Position", 3000), ("DiaLamp", "State", 1), ("Foo", "Bar", 1)):
        with pytest.raises((UnguardedMotion, PropertyNotAllowed)):
            b.set_property(*args)
    assert not b.props and not b.calls


def test_notes_round_trip_and_default_empty():
    r = Readback.of("Aura", "CYAN", 1, 1, notes={"line": PROVISIONAL})
    assert r.verified and r.notes == {"line": PROVISIONAL}
    assert Readback.of("Aura", "State", 0, 0).notes == {}
    assert Readback(**json.loads(json.dumps(asdict(r)))) == r
