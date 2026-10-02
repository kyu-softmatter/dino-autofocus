"""SmaFiles reads and never writes. Format checks run on a read-only copy of mock_data;
the real soft-matter-agents checkout is read when it is present, else skipped."""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from dino_autofocus.agents import NotFoundError, ReadOnlyStoreError, SmaFiles
from dino_autofocus.agents.mock_store import MOCK_DATA
from dino_autofocus.agents.sma_files import ROOT_ENV, default_root, guess_kind, split_version


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*")}


def read_everything(s: SmaFiles) -> int:
    n = 0
    for agent in ("microscope", "simulation"):
        for q in s.list_questions(agent):
            for v in q.versions:
                s.get_question(q.qid, v)
                n += 1
        for r in s.list_runs(agent):
            s.get_run(agent, r.run_id)
            n += 1
    n += len(s.list_inbox())
    return n


def test_version_prefix():
    assert split_version("v3_goal.json") == (3, "goal.json")
    assert split_version("v12_axis_x_a1.json") == (12, "axis_x_a1.json")
    assert split_version("goal.json") == (1, "goal.json")
    assert split_version("vx_goal.json") == (1, "vx_goal.json")


def test_kind_from_file_name():
    assert guess_kind("axis_bd_pairwise_a7.json") == "axis"
    assert guess_kind("plan_simulation_sim-20260923-001.json") == "plan"
    assert guess_kind("refusal_s4_sim-20260923-001.json") == "refusal"
    assert guess_kind("synthesis.json") == "synthesis"
    assert guess_kind("configs.json") == "configs"


def test_root_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(ROOT_ENV, str(tmp_path))
    assert default_root() == tmp_path
    assert SmaFiles().root == tmp_path
    monkeypatch.delenv(ROOT_ENV)
    assert default_root() == Path(r"D:\codes\github\soft-matter-agents")


@pytest.fixture
def readonly_copy(tmp_path):
    root = tmp_path / "sma"
    shutil.copytree(MOCK_DATA, root)
    files = [p for p in root.rglob("*") if p.is_file()]
    for p in files:
        os.chmod(p, stat.S_IREAD)
    yield root
    for p in files:
        os.chmod(p, stat.S_IREAD | stat.S_IWRITE)


def test_reads_a_read_only_copy_and_changes_nothing(readonly_copy):
    before = snapshot(readonly_copy)
    s = SmaFiles(readonly_copy)
    assert s.available()
    assert read_everything(s) > 5
    with pytest.raises(ReadOnlyStoreError):
        s.submit_question("q", "microscope")
    assert snapshot(readonly_copy) == before


def test_same_reading_as_the_mock_store(readonly_copy):
    s = SmaFiles(readonly_copy)
    d = s.get_question("sim-20260923-001")
    assert d.summary.source == "soft-matter-agents"
    assert (d.version, d.goal.name, d.summary.versions) == (3, "v3_goal.json", [1, 2, 3])


def test_odd_files_are_listed_not_fatal(tmp_path):
    q = tmp_path / "microscope_agent" / "questions" / "mic-20260101-001"
    q.mkdir(parents=True)
    (q / "goal.json").write_text('{"card": "goal", "status": "DRAFT", '
                                 '"created_at": "2026-01-01T00:00:00Z"}', encoding="utf-8")
    (q / "v2_goal.json").write_text("{ not json", encoding="utf-8")
    (q / "failures.jsonl").write_text("{}\n", encoding="utf-8")
    (q / "picture.png").write_bytes(b"\x89PNG")
    (q / "goal.json.tmp").write_text("{}", encoding="utf-8")
    (tmp_path / "microscope_agent" / "questions" / "notes").mkdir()
    run = tmp_path / "microscope_agent" / "runs" / "run-x"
    run.mkdir(parents=True)
    (run / "log.json").write_text("{ cut off", encoding="utf-8")

    s = SmaFiles(tmp_path)
    (summary,) = s.list_questions("microscope")
    assert summary.versions == [1, 2]
    v1 = s.get_question(summary.qid, 1)
    assert v1.goal.status == "DRAFT"
    assert sorted(f.name for f in v1.files) == ["failures.jsonl", "picture.png"]
    v2 = s.get_question(summary.qid, 2)
    assert v2.goal is None and [f.name for f in v2.files] == ["v2_goal.json"]
    (run,) = s.list_runs("microscope")
    assert run.status is None and run.created_at is None
    assert s.get_run("microscope", "run-x").not_opened == ["log.json"]
    assert s.list_questions("simulation") == [] and s.list_inbox() == []


def test_missing_root_is_empty_not_an_error(tmp_path):
    s = SmaFiles(tmp_path / "nowhere")
    assert not s.available()
    assert s.list_questions("microscope") == [] and s.list_runs("simulation") == []
    assert s.list_inbox() == []
    with pytest.raises(NotFoundError):
        s.get_question("mic-20260101-001")


def test_importing_pulls_in_no_heavy_or_ui_module():
    heavy = "{'torch', 'pymmcore', 'pymmcore_plus', 'tkinter', 'PySide6'}"
    code = (f"import sys, dino_autofocus.agents; bad = {heavy} & set(sys.modules); "
            "assert not bad, bad")
    subprocess.run([sys.executable, "-c", code], check=True)


REAL = SmaFiles()


@pytest.mark.skipif(not REAL.available(), reason=f"no soft-matter-agents at {REAL.root}")
def test_real_checkout_is_read_and_left_unchanged():
    watched = [REAL.root / f"{a}_agent" / sub for a in ("microscope", "simulation")
               for sub in ("questions", "runs", "inbox")] + [REAL.root / "bridge" / "threads"]
    watched = [w for w in watched if w.is_dir()]
    before = {str(w): snapshot(w) for w in watched}

    for agent in ("microscope", "simulation"):
        qs = REAL.list_questions(agent)
        assert qs and all(q.source == "soft-matter-agents" for q in qs)
        for q in qs:
            d = REAL.get_question(q.qid)
            assert d.version == q.latest_version
        runs = REAL.list_runs(agent)
        assert runs
        for r in runs[:5]:
            assert REAL.get_run(agent, r.run_id).files
    assert REAL.list_inbox()
    with pytest.raises(ReadOnlyStoreError):
        REAL.submit_question("q", "simulation")

    assert {str(w): snapshot(w) for w in watched} == before
