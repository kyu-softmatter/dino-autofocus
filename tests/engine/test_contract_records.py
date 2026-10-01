"""Operation scope: record folder, lights off on every exit path, manual steps, ownership."""

import json
import threading

import pytest

from dino_autofocus.engine import Command, Event, GuardError, exclusive, operation
from dino_autofocus.engine.records import model_value


def test_operation_leaves_a_record_folder_with_lights_off(fake, tmp_path):
    seen = []
    with operation(fake, tmp_path, "demo_op", sink=seen.append, args={"n": 1}) as op:
        op.lights(fake.lamp_on())
        op.emit(Event("reading", op.op_id, {"dz": json.loads(json.dumps(
            model_value(-1.3, "head").__dict__))}))
        op.result = {"best_z_um": 3051.2}
    s = json.loads((tmp_path / op.op_id / "summary.json").read_text())
    assert s["status"] == "finished" and s["result"] == {"best_z_um": 3051.2}
    assert s["lights_off"]["verified"] and s["end_state"]["lights"] == {"DiaLamp": "0",
                                                                         "Aura": "0"}
    lines = (tmp_path / op.op_id / "log.jsonl").read_text().splitlines()
    kinds = [json.loads(x)["kind"] for x in lines]
    assert kinds == ["started", "light_changed", "reading", "light_changed", "finished"]
    assert kinds == [e.kind for e in seen]
    assert json.loads(lines[2])["data"]["dz"]["grade"] == "model"


def test_an_unverified_light_stops_the_operation_and_a_prefix_names_the_folder(fake, tmp_path):
    fake.stuck.add("DiaLamp")
    with pytest.raises(GuardError, match="DiaLamp.State wanted 1"), \
            operation(fake, tmp_path, "scan_4x", prefix="scan4x") as op:
        op.lights(fake.lamp_on())
    assert op.op_id.startswith("scan4x_") and (tmp_path / op.op_id / "summary.json").exists()
    assert json.loads((tmp_path / op.op_id / "summary.json").read_text())["status"] == "error"


@pytest.mark.parametrize("exc, status", [(RuntimeError("boom"), "error"),
                                         (KeyboardInterrupt(), "aborted")])
def test_lights_go_off_on_every_exit_path(fake, tmp_path, exc, status):
    with pytest.raises(type(exc)), operation(fake, tmp_path, "op") as op:
        fake.aura_line_on("GREEN", 1)
        raise exc
    s = json.loads((tmp_path / op.op_id / "summary.json").read_text())
    assert s["status"] == status and fake.lights == {"DiaLamp": "0", "Aura": "0"}
    assert s["lights_off"]["verified"]


def test_a_failing_lights_off_is_recorded_not_hidden(fake, tmp_path):
    fake.all_off_raises = True
    with pytest.raises(ValueError), operation(fake, tmp_path, "op") as op:
        raise ValueError("the operation's own error")
    s = json.loads((tmp_path / op.op_id / "summary.json").read_text())
    assert not s["lights_off"]["verified"] and "OSError" in s["lights_off"]["error"]


def test_manual_step_waits_for_the_matching_confirm(fake, tmp_path):
    with operation(fake, tmp_path, "objective_change") as op:
        def operator():
            op.answers.put(Command("confirm", args={"key": "other", "ok": False}))
            op.answers.put(Command("confirm", args={"key": "oil_loaded", "ok": True}))
        threading.Thread(target=operator).start()
        assert op.ask("oil_loaded", "Load oil, then click Done.", timeout_s=5)
    log = (tmp_path / op.op_id / "log.jsonl").read_text()
    assert '"confirmed"' in log and '"origin": "human"' in log


def test_abort_while_waiting_ends_as_aborted(fake, tmp_path):
    with pytest.raises(Exception, match="aborted"), operation(fake, tmp_path, "op") as op:
        op.answers.put(Command("abort"))
        op.ask("oil_loaded", "Load oil.")
    assert json.loads((tmp_path / op.op_id / "summary.json").read_text())["status"] == "aborted"


def test_one_owner_at_a_time(fake):
    with exclusive(fake), pytest.raises(GuardError), exclusive(fake):
        pass
    assert not fake.is_open and ("close",) in fake.calls
    with exclusive(fake):  # released again
        pass
