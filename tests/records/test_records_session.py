"""Session lifecycle on the folder store: layout, stamps, manifest, read-only after close."""

import hashlib
import json
import subprocess
from datetime import datetime

import pytest

from dino_autofocus.records import (
    ExperimentSession,
    FolderStore,
    RecordsConfig,
    SessionClosedError,
    code_version,
    open_session_started_at,
    sample_state,
    sessions_of_sample,
)

USER = "operator@example.test"


@pytest.fixture
def store(tmp_path):
    return FolderStore(RecordsConfig(records_root=tmp_path / "records",
                                     data_root=tmp_path / "data", max_tracked_bytes=1000))


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=T", "-c",
                           "user.email=t@example.test", *args],
                          check=True, capture_output=True, text=True).stdout


def test_open_writes_the_folder_and_session_json(store, tmp_path):
    hw = tmp_path / "hardware_profile.json"
    hw.write_text('{"camera": "Kinetix_red"}')
    s = ExperimentSession.open(store, USER, "20260930_1849_1", user_name="Op",
                               hardware_profile=hw,
                               now=lambda: datetime(2026, 10, 1, 9, 5))
    assert s.session_id == "20261001-0905-operator-1"
    root = tmp_path / "records" / "microscope" / "sessions" / s.session_id
    assert s.layout.root == root
    info = json.loads((root / "session.json").read_text())
    assert info["user_id"] == USER and info["sample_id"] == "20260930_1849_1"
    assert info["status"] == "open" and info["closed_at"] is None
    assert info["hardware_profile"]["sha256"] == hashlib.sha256(hw.read_bytes()).hexdigest()
    assert info["sma_run_id"] is None and "commit" in info["code"]
    assert json.loads((root / "manifest.json").read_text()) == {"files": []}
    assert (root / "records").is_dir() and s.log_lines()[0]["msg"] == "session opened"


def test_session_ids_do_not_collide(store):
    fixed = lambda: datetime(2026, 10, 1, 9, 5)  # noqa: E731
    a = ExperimentSession.open(store, USER, "s1", now=fixed)
    b = ExperimentSession.open(store, USER, "s1", now=fixed)
    assert (a.session_id, b.session_id) == ("20261001-0905-operator-1",
                                            "20261001-0905-operator-2")


def test_every_line_carries_session_and_user(store):
    s = ExperimentSession.open(store, USER, "s1")
    s.log("live view started", exposure_ms=12)
    s.record("scan_4x", {"tile": "r0c0", "z_focus_um": 3048.9})
    s.end_operation("scan_4x", {"tiles": 1})
    s.manual_step("oil_loaded", objective="100x Oil")
    s.sample_event("note", text="edge looks clean")
    files = [s.layout.log, s.layout.operation_record("scan_4x"), s.layout.manual_steps,
             s.layout.sample_events]
    for p in files:
        for line in p.read_text().splitlines():
            d = json.loads(line)
            assert d["session_id"] == s.session_id and d["user_id"] == USER and d["t"]


def test_small_files_go_in_the_folder_and_large_ones_to_data(store, tmp_path):
    s = ExperimentSession.open(store, USER, "s1")
    small, big = tmp_path / "plan.json", tmp_path / "tile_r0c0.npy"
    small.write_bytes(b"x" * 10)
    big.write_bytes(b"y" * 5000)
    es, eb = s.attach(small, kind="plan"), s.attach(big, kind="frame")
    assert es.where == "session" and (s.layout.root / "files" / "plan.json").is_file()
    assert eb.where == "data" and (tmp_path / "data" / s.session_id / "tile_r0c0.npy").is_file()
    assert not (s.layout.root / "files" / "tile_r0c0.npy").exists()
    assert eb.sha256 == hashlib.sha256(b"y" * 5000).hexdigest() and eb.size == 5000
    m = s.manifest()
    assert m.names() == {"plan.json", "tile_r0c0.npy"}
    with pytest.raises(FileExistsError):
        s.attach(small)


def test_closed_session_is_read_only(store):
    s = ExperimentSession.open(store, USER, "s1")
    s.close(note="done")
    assert s.info.status == "closed" and s.info.closed_at
    for write in (lambda: s.log("x"), lambda: s.record("op", {}),
                  lambda: s.manual_step("x"), lambda: s.sample_event("note", text="x"),
                  lambda: s.end_operation("op"), lambda: s.close()):
        with pytest.raises(SessionClosedError):
            write()
    again = ExperimentSession.load(store, s.session_id)
    assert not again.writable
    with pytest.raises(SessionClosedError):
        again.log("still closed")
    assert again.log_lines()[-1]["msg"] == "session closed"


def test_previous_sessions_and_continuing_a_sample(store):
    a = ExperimentSession.open(store, USER, "s1")
    a.sample_event("flag_set", flag_id="f1", name="good area", x_um=1.0, y_um=2.0)
    a.close()
    b = ExperimentSession.continue_from(store, a.session_id, "second@example.test")
    assert b.info.sample_id == "s1" and b.info.continues == a.session_id
    b.sample_event("flag_set", flag_id="f2", name="debris", x_um=3.0, y_um=4.0)
    ExperimentSession.open(store, USER, "other")
    assert [i["session_id"] for i in sessions_of_sample(store, "s1")] == [a.session_id,
                                                                          b.session_id]
    st = sample_state(store, "s1")
    assert set(st.flags) == {"f1", "f2"} and st.sessions == [a.session_id, b.session_id]


def test_bad_inputs_are_refused(store):
    with pytest.raises(ValueError):
        ExperimentSession.open(store, "", "s1")
    with pytest.raises(ValueError):
        ExperimentSession.open(store, USER, "../escape")
    s = ExperimentSession.open(store, USER, "s1")
    with pytest.raises(ValueError):
        s.record("sample_events", {})  # would shadow the event file
    with pytest.raises(ValueError):
        s.sample_event("flag_set", name="no id")


def test_code_version_reads_commit_and_dirty_state(tmp_path):
    repo = tmp_path / "code"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "a.py").write_text("x = 1\n")
    git(repo, "add", "a.py")
    git(repo, "commit", "-q", "-m", "init")
    head = git(repo, "rev-parse", "HEAD").strip()
    cv = code_version(repo)
    assert cv.commit == head and cv.dirty is False and cv.error is None
    (repo / "a.py").write_text("x = 2\n")
    assert code_version(repo).dirty is True
    missing = code_version(tmp_path / "not-a-repo")
    assert missing.commit is None and missing.dirty is None and missing.error


def test_session_records_the_code_version_it_ran_with(store, tmp_path):
    repo = tmp_path / "code"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "a.py").write_text("x = 1\n")
    git(repo, "add", "a.py")
    git(repo, "commit", "-q", "-m", "init")
    (repo / "b.py").write_text("untracked\n")
    s = ExperimentSession.open(store, USER, "s1", code_repo=repo)
    info = json.loads(s.layout.info.read_text())
    assert info["code"]["commit"] == git(repo, "rev-parse", "HEAD").strip()
    assert info["code"]["dirty"] is True


def test_open_session_start_time_for_the_retrace_rule(store):
    assert open_session_started_at(store) is None
    a = ExperimentSession.open(store, USER, "s1")
    started = open_session_started_at(store)
    assert started == datetime.fromisoformat(a.info.started_at) and started.tzinfo
    a.close()
    assert open_session_started_at(store) is None
