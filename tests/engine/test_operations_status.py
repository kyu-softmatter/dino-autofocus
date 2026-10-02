"""status: read-only snapshot op (operations-spec 2) on FakeBackend."""

from __future__ import annotations

import json

from conftest import FakeBackend

from dino_autofocus.engine.backend import Positions
from dino_autofocus.engine.operations.status import read_status, run_status


def test_status_reads_every_field(fake: FakeBackend) -> None:
    fake.state = 5
    st = read_status(fake)
    assert st["nosepiece_label"] == "6-Plan Apo LmbdD0.13 100x Oil"
    assert st["nosepiece_state"] == 5
    assert st["z_um"] == 2900.0
    assert st["pfs_enabled"] is False and st["pfs_in_range"] == "Out of Range"
    assert st["lights"] == {"DiaLamp": "0", "Aura": "0"}
    assert st["bit_depth"] == 12 and st["ceiling_adu"] == 4095
    assert st["info"]["camera"] == "FakeCam"
    json.dumps(st)  # JSON-native


def test_failed_reads_are_fields_not_errors(fake: FakeBackend, monkeypatch) -> None:
    def broken():
        raise OSError("PFS not answering")

    monkeypatch.setattr(fake, "pfs", broken)
    monkeypatch.setattr(fake, "positions",
                        lambda: Positions(1.0, 2.0, None, errors={"z": "ZDrive timeout"}))
    st = read_status(fake)
    assert st["pfs_enabled"].startswith("unreadable: OSError")
    assert st["z_um"] is None
    assert st["positions"]["errors"] == {"z": "ZDrive timeout"}
    assert st["nosepiece_label"] == "1-Plan Apo LmbdD20 4x"  # the rest still reads


def test_status_without_record_emits_one_reading_and_writes_nothing(fake, tmp_path) -> None:
    events = []
    run_status(fake, tmp_path, events.append)
    assert [e.kind for e in events] == ["reading"]
    assert events[0].data["source"] == "status"
    assert list(tmp_path.iterdir()) == []
    assert not [c for c in fake.calls if c[0] in ("light", "move_z", "move_xy")]


def test_status_record_when_asked_keeps_lights_as_they_were(fake, tmp_path) -> None:
    fake.lights["DiaLamp"] = "1"  # brightfield set by a light_set before
    events = []
    st = run_status(fake, tmp_path, events.append, keep_record=True, user_id="u1")
    assert [e.kind for e in events] == ["started", "reading", "finished"]
    (folder,) = tmp_path.iterdir()
    assert folder.name.startswith("status_")
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "finished" and summary["user_id"] == "u1"
    assert summary["result"]["z_um"] == st["z_um"]
    assert summary["lights_off"]["switched_off"] is False
    assert fake.lights["DiaLamp"] == "1"  # nothing was switched
    assert not [c for c in fake.calls if c[0] == "light"]
    assert len((folder / "log.jsonl").read_text(encoding="utf-8").splitlines()) == 3
