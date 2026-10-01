import json
import subprocess
import sys

import pytest

from dino_autofocus.assistant import Assistant, AssistantConfig, Sources, connection_status
from dino_autofocus.assistant.providers.anthropic import credentials
from dino_autofocus.assistant.providers.fake import FakeProvider
from dino_autofocus.assistant.records import RecordLog
from dino_autofocus.assistant.runner import SYSTEM_PROMPT
from dino_autofocus.assistant.tools import REMOVED_IMAGE


class FakeEngine:
    """The EngineAPI shape T-009 assumes: submit, subscribe, snapshot."""

    def __init__(self, refuse=False):
        self.submitted = []
        self.snapshots = 0
        self.refuse = refuse

    def submit(self, cmd):
        if self.refuse:
            raise RuntimeError("preflight_failed: Z window")
        self.submitted.append(cmd)
        return f"op-{len(self.submitted)}"

    def subscribe(self, sink):
        return lambda: None

    def snapshot(self):
        self.snapshots += 1
        return {"position": {"x_um": 10.0, "y_um": 20.0, "z_um": 2950.0}, "running": None}


def tool_use(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def text(s):
    return {"type": "text", "text": s}


def make(script, engine=None, **cfg):
    engine = engine or FakeEngine()
    provider = FakeProvider(script)
    a = Assistant(
        AssistantConfig(**cfg),
        provider=provider,
        sources=Sources(snapshot=engine.snapshot),
        submit=engine.submit,
        records=RecordLog(),
    )
    return a, provider, engine


def last_tool_results(request):
    return [b for b in request.messages[-1]["content"] if b["type"] == "tool_result"]


def test_read_tool_runs_and_its_text_goes_back():
    a, provider, engine = make(
        [
            [text("Checking. "), tool_use("get_hardware_state")],
            [text("Z is 2950 um.")],
        ]
    )
    events = []
    ans = a.ask("Where is the stage?", on_event=events.append)
    assert ans.text == "Checking. Z is 2950 um." and ans.stop_reason == "end_turn"
    assert engine.snapshots == 1 and engine.submitted == []
    (res,) = last_tool_results(provider.requests[1])
    assert json.loads(res["content"])["position"]["z_um"] == 2950.0
    kinds = [e["type"] for e in events]
    assert kinds[0] == "text" and "tool_call" in kinds and kinds[-1] == "done"
    assert ans.grade == "model"


def test_action_tool_makes_a_proposal_and_runs_nothing():
    a, provider, engine = make(
        [
            [
                tool_use(
                    "propose_goto_xy",
                    x_um=1200.0,
                    y_um=-300.0,
                    sample_id="s1",
                    reason="the edge is there",
                )
            ],
            [text("I proposed the move; please confirm it.")],
        ]
    )
    ans = a.ask("Go to the edge", user_id="kyu", session_id="sess-1")
    assert engine.submitted == []  # no hardware call before a person confirms
    (p,) = ans.proposals
    assert p["status"] == "proposed" and p["origin"] == "assistant"
    assert p["conversation_id"] == ans.conversation_id
    assert p["command"] == {
        "kind": "start",
        "op": "goto_xy",
        "args": {"x_um": 1200.0, "y_um": -300.0, "sample_id": "s1"},
    }
    assert p["reason"] == "the edge is there" and p["expected_gate"]["checked"] is False
    (res,) = last_tool_results(provider.requests[1])
    body = json.loads(res["content"])
    assert body["status"] == "proposed" and "Not executed" in body["note"]
    rec = a.records.entries("proposal")[0]
    assert rec["args"]["x_um"] == {
        "value": 1200.0,
        "grade": "model",
        "source": f"assistant:{p['proposal_id']}",
    }
    assert rec["user_id"] == "kyu" and rec["session_id"] == "sess-1"


def test_confirm_sends_the_command_with_its_origin():
    a, _, engine = make([[tool_use("propose_lights_off", reason="finished")], [text("ok")]])
    pid = a.ask("lights off please").proposals[0]["proposal_id"]
    done = a.confirm(pid, by="kyu", session_id="sess-2")
    assert done["status"] == "confirmed" and done["op_id"] == "op-1"
    (cmd,) = engine.submitted
    assert cmd["kind"] == "lights_off" and cmd["origin"] == "assistant"
    assert cmd["proposal_id"] == pid and cmd["confirmed_by"] == "kyu"
    assert cmd["session_id"] == "sess-2"
    (rec,) = a.records.entries("proposal_confirmed")
    assert rec["op_id"] == "op-1" and rec["user_id"] == "kyu"
    with pytest.raises(ValueError):
        a.confirm(pid, by="kyu")  # once only
    assert len(engine.submitted) == 1


def test_reject_is_recorded_and_never_reaches_the_engine():
    a, _, engine = make(
        [[tool_use("propose_scan_4x", sample_id="s1", reason="map it")], [text("proposed")]]
    )
    pid = a.ask("scan").proposals[0]["proposal_id"]
    out = a.reject(pid, by="kyu", note="not now")
    assert out["status"] == "rejected" and out["note"] == "not now"
    (rec,) = a.records.entries("proposal_rejected")
    assert rec["proposal_id"] == pid and rec["user_id"] == "kyu"
    with pytest.raises(ValueError):
        a.confirm(pid, by="kyu")
    assert engine.submitted == []


def test_engine_refusal_keeps_the_card_as_failed():
    a, _, engine = make(
        [[tool_use("propose_focus_100x", sample_id="s", reason="r")], [text("x")]],
        engine=FakeEngine(refuse=True),
    )
    pid = a.ask("focus").proposals[0]["proposal_id"]
    out = a.confirm(pid, by="kyu")
    assert out["status"] == "failed" and "Z window" in out["note"]
    assert a.records.entries("proposal_failed")


def test_no_engine_means_no_confirmation():
    a = Assistant(
        provider=FakeProvider([[tool_use("propose_lights_off", reason="r")], [text("x")]]),
        records=RecordLog(),
    )
    pid = a.ask("off").proposals[0]["proposal_id"]
    with pytest.raises(RuntimeError, match="no engine"):
        a.confirm(pid, by="kyu")


def test_system_prompt_and_tools_are_the_same_on_every_call():
    a, provider, _ = make(
        [
            [tool_use("get_hardware_state")],
            [text("one")],
            [tool_use("list_simulations")],
            [text("two")],
        ]
    )
    a.ask("first", context={"area": "live"})
    a.ask("second", context={"area": "simulation", "run_id": "run-1"})
    reqs = provider.requests
    assert len(reqs) == 4
    assert all(r.system == SYSTEM_PROMPT for r in reqs)
    assert all(r.tools == reqs[0].tools for r in reqs)
    assert all(r.model == "claude-opus-5-5" for r in reqs)
    # the screen context travels in the user message, not in the cached prefix
    assert "run-1" not in reqs[3].system and "run-1" in json.dumps(reqs[3].messages)


def test_screen_context_is_short_text_only():
    a, provider, _ = make([[text("ok")]])
    a.ask("what is selected?", context={"area": "map", "sample_id": "s1", "region": [1, 2, 3, 4]})
    first = provider.requests[0].messages[0]["content"][0]["text"]
    assert first.startswith("<screen_context>") and '"sample_id": "s1"' in first
    for bad in [{"img": "data:image/png;base64,AA"}, {"blob": "x" * 500}, {"f": b"raw"}]:
        with pytest.raises(ValueError):
            a.ask("q", context=bad)
    with pytest.raises(ValueError):
        a.ask("   ")


def test_one_conversation_across_screens():
    a, provider, _ = make([[text("first answer")], [text("second answer")]])
    cid = a.ask("from the live screen", context={"area": "live"}).conversation_id
    ans = a.ask("from the map screen", context={"area": "map"}, conversation_id=cid)
    assert ans.conversation_id == cid
    msgs = provider.requests[1].messages
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    hist = a.conversation(cid)
    assert len(hist["messages"]) == 4 and hist["usage"]["output_tokens"] > 0
    assert a.ask("new").conversation_id != cid


def test_usage_is_shown_and_recorded_per_answer():
    a, _, _ = make([[tool_use("get_hardware_state")], [text("done")]])
    events = []
    ans = a.ask("q", on_event=events.append)
    turns = a.records.entries("model_turn")
    assert len(turns) == 2
    total = sum(t["usage"]["input_tokens"] for t in turns)
    assert ans.usage["input_tokens"] == total > 0
    (rec,) = a.records.entries("answer")
    assert rec["usage"] == ans.usage and rec["grade"] == "model"
    assert sum(e["type"] == "usage" for e in events) == 2


def test_images_in_tool_results_are_removed_and_recorded():
    provider = FakeProvider([[tool_use("get_hardware_state")], [text("ok")]])
    a = Assistant(
        provider=provider,
        records=RecordLog(),
        sources=Sources(snapshot=lambda: {"z_um": 2950.0, "frame": b"\x00\x01" * 100}),
    )
    a.ask("show me")
    (res,) = last_tool_results(provider.requests[1])
    assert json.loads(res["content"]) == {"z_um": 2950.0, "frame": REMOVED_IMAGE}
    (rec,) = a.records.entries("tool_call")
    assert rec["images_removed"] == 1


def test_prompt_only_sends_no_read_tools_and_refuses_them():
    a, provider, engine = make(
        [[tool_use("get_hardware_state")], [text("cannot")]], data_policy="prompt_only"
    )
    a.ask("where is the stage?")
    names = {t["name"] for t in provider.requests[0].tools}
    assert "get_hardware_state" not in names and "propose_lights_off" in names
    (res,) = last_tool_results(provider.requests[1])
    assert res["is_error"] and "data policy" in res["content"]
    assert engine.snapshots == 0


def test_cut_off_turn_runs_no_tools():
    a, provider, engine = make(
        [
            {"content": [tool_use("propose_goto_xy", x_um=1.0)], "stop_reason": "max_tokens"},
        ]
    )
    ans = a.ask("move")
    assert ans.stop_reason == "max_tokens" and ans.proposals == [] and ans.tool_calls == []
    msgs = a.conversation(ans.conversation_id)["messages"]
    assert msgs[-1]["content"][0]["is_error"] is True  # every tool_use is answered
    assert a.proposals.list() == []


def test_loop_stops_after_max_steps():
    a, provider, _ = make([[tool_use("get_hardware_state")]] * 5, max_steps=3)
    ans = a.ask("loop")
    assert ans.stop_reason == "max_steps" and len(provider.requests) == 3


def test_provider_failure_is_recorded():
    class Broken:
        name = "broken"

        def turn(self, request, on_text):
            raise ConnectionError("offline")

    a = Assistant(provider=Broken(), records=RecordLog())
    with pytest.raises(ConnectionError):
        a.ask("q")
    assert "offline" in a.records.entries("error")[0]["error"]


def test_default_fake_answers_without_a_script():
    a = Assistant(records=RecordLog())
    ans = a.ask("hello")
    assert ans.provider == "fake" and "No model is connected" in ans.text


def test_records_go_to_a_file(tmp_path):
    seen = []
    a = Assistant(
        AssistantConfig(records_dir=tmp_path),
        provider=FakeProvider([[tool_use("propose_lights_off", reason="r")], [text("x")]]),
        submit=lambda cmd: "op-9",
    )
    a.records._sinks.append(seen.append)
    pid = a.ask("off", user_id="kyu").proposals[0]["proposal_id"]
    a.confirm(pid, by="kyu")
    lines = [json.loads(s) for s in (tmp_path / "assistant.jsonl").read_text("utf-8").splitlines()]
    kinds = [r["kind"] for r in lines]
    assert kinds == [
        "question",
        "model_turn",
        "proposal",
        "tool_call",
        "model_turn",
        "answer",
        "proposal_confirmed",
    ]
    assert len(seen) == len(lines)
    assert a.records.entries("answer", conversation_id=lines[0]["conversation_id"])


# --------------------------------------------------------------------------- config, status


def test_config_from_env():
    c = AssistantConfig.from_env({"DINO_AF_ASSISTANT_DATA": "prompt_only"})
    assert c.provider == "fake" and c.data_policy == "prompt_only" and c.model == "claude-opus-5-5"
    with pytest.raises(ValueError, match="blocked"):
        AssistantConfig.from_env({"DINO_AF_ASSISTANT_DATA": "images"})
    with pytest.raises(ValueError):
        AssistantConfig(provider="openai")


def test_status_fake():
    s = connection_status(AssistantConfig())
    assert s["provider"] == "fake" and s["state"] == "fake" and s["connected"] is False
    assert s["data_policy"] == "text"


def test_status_without_credentials_is_not_connected(tmp_path):
    s = connection_status(AssistantConfig(provider="anthropic"), env={}, home=tmp_path)
    assert s["state"] == "not_connected" and s["connected"] is False
    ok, why = credentials({}, home=tmp_path)
    assert not ok and "no API key" in why


def test_status_never_shows_the_key(tmp_path):
    env = {"ANTHROPIC_API_KEY": "sk-ant-secret-123"}
    ok, why = credentials(env, home=tmp_path)
    assert ok and why == "environment"
    s = connection_status(AssistantConfig(provider="anthropic"), env=env)
    assert "sk-ant-secret-123" not in json.dumps(s)


def test_import_loads_neither_anthropic_nor_torch():
    code = (
        "import sys\n"
        "import dino_autofocus.assistant, dino_autofocus.assistant.providers.anthropic\n"
        "from dino_autofocus.assistant import Assistant\n"
        "Assistant().ask('hi')\n"
        "bad = {'anthropic', 'torch'} & set(sys.modules)\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
