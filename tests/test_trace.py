"""Tests for ATIF v1.4 trace writer."""

import json
from pathlib import Path
from typing import Any

from klaude.core.trace import TraceWriter


def test_init_creates_atif_document(tmp_path):
    """TraceWriter creates a valid ATIF v1.4 document on first flush."""
    path = tmp_path / "test-session.json"
    tw = TraceWriter(path, model_name="openrouter/auto")
    tw.write_user_step("hello")

    data = json.loads(path.read_text())
    assert data["schema_version"] == "ATIF-v1.4"
    assert data["session_id"] == "test-session"
    assert data["agent"]["name"] == "klaude"
    assert data["agent"]["model_name"] == "openrouter/auto"
    assert len(data["steps"]) == 1


def test_write_agent_step_text_only(tmp_path):
    """Agent step with text content, no tool calls."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("hello")
    tw.write_agent_step("Hi there!", tool_calls=None)

    data = json.loads(path.read_text())
    agent_step = data["steps"][1]
    assert agent_step["step_id"] == 2
    assert agent_step["source"] == "agent"
    assert agent_step["message"] == "Hi there!"
    assert agent_step["model_name"] == "test-model"
    assert "tool_calls" not in agent_step


def test_write_agent_step_with_tool_calls(tmp_path):
    """Agent step with tool calls."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("fix bug")
    tw.write_agent_step(None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "main.py"}'}},
    ])

    data = json.loads(path.read_text())
    agent_step = data["steps"][1]
    assert agent_step["source"] == "agent"
    assert agent_step["message"] is None
    assert len(agent_step["tool_calls"]) == 1
    tc = agent_step["tool_calls"][0]
    assert tc["tool_call_id"] == "call_1"
    assert tc["function_name"] == "read_file"
    assert tc["arguments"] == {"path": "main.py"}


def test_write_tool_result_step(tmp_path):
    """System step with observation for a tool result."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("fix bug")
    tw.write_agent_step(None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}},
    ])
    tw.write_tool_result_step("call_1", "def main(): pass")

    data = json.loads(path.read_text())
    sys_step = data["steps"][2]
    assert sys_step["step_id"] == 3
    assert sys_step["source"] == "system"
    assert sys_step["message"] == "def main(): pass"
    assert sys_step["observation"]["results"][0]["tool_call_id"] == "call_1"
    assert sys_step["observation"]["results"][0]["content"] == "def main(): pass"


def test_finalize_writes_final_metrics(tmp_path):
    """finalize() adds final_metrics to the document."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("hello")
    tw.write_agent_step("hi", tool_calls=None)
    tw.finalize()

    data = json.loads(path.read_text())
    fm = data["final_metrics"]
    assert fm["total_steps"] == 2
    assert fm["total_cost_usd"] == 0
    assert fm["total_prompt_tokens"] == 0
    assert fm["total_completion_tokens"] == 0
    assert fm["total_cached_tokens"] == 0


def test_to_chat_messages_roundtrip(tmp_path):
    """ATIF steps convert back to OpenAI chat messages."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("fix bug")
    tw.write_agent_step(None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}},
    ])
    tw.write_tool_result_step("call_1", "contents")
    tw.write_agent_step("Done!", tool_calls=None)

    msgs = tw.to_chat_messages()
    assert len(msgs) == 4

    assert msgs[0] == {"role": "user", "content": "fix bug"}

    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] is None
    assert len(msgs[1]["tool_calls"]) == 1
    assert msgs[1]["tool_calls"][0]["id"] == "call_1"
    assert msgs[1]["tool_calls"][0]["type"] == "function"
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "read_file"
    assert msgs[1]["tool_calls"][0]["function"]["arguments"] == '{"path": "x.py"}'

    assert msgs[2] == {"role": "tool", "tool_call_id": "call_1", "content": "contents"}

    assert msgs[3] == {"role": "assistant", "content": "Done!"}


def test_load_returns_chat_messages_and_turn_count(tmp_path):
    """load() reads an ATIF file and returns chat messages + turn count."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("first task")
    tw.write_agent_step("done", tool_calls=None)
    tw.write_user_step("second task")
    tw.write_agent_step("also done", tool_calls=None)
    tw.finalize()

    msgs, turn_count = TraceWriter.load(path)
    assert turn_count == 2  # two user steps = two turns
    assert len(msgs) == 4
    assert msgs[0]["content"] == "first task"
    assert msgs[3]["content"] == "also done"


def test_from_existing_continues_step_counter(tmp_path):
    """from_existing() loads an ATIF file and continues appending steps."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("first task")
    tw.write_agent_step("done", tool_calls=None)

    # Simulate new session picking up the trace
    tw2 = TraceWriter.from_existing(path)
    tw2.write_user_step("second task")
    tw2.write_agent_step("also done", tool_calls=None)

    data = json.loads(path.read_text())
    assert len(data["steps"]) == 4
    assert data["steps"][2]["step_id"] == 3  # continues from 2
    assert data["steps"][2]["source"] == "user"
    assert data["steps"][2]["message"] == "second task"
    assert data["agent"]["model_name"] == "test-model"  # preserved


def test_flush_is_atomic_valid_json_at_all_times(tmp_path):
    """The trace file is always valid JSON — never a partial write."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")

    # After each write, the file should be valid JSON
    tw.write_user_step("step 1")
    data = json.loads(path.read_text())
    assert len(data["steps"]) == 1

    tw.write_agent_step("response", tool_calls=None)
    data = json.loads(path.read_text())
    assert len(data["steps"]) == 2

    tw.write_user_step("step 2")
    data = json.loads(path.read_text())
    assert len(data["steps"]) == 3


def test_no_temp_files_left_after_flush(tmp_path):
    """Atomic flush does not leave .tmp files behind."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("hello")
    tw.write_agent_step("hi", tool_calls=None)

    remaining = list(tmp_path.glob("*.tmp"))
    assert remaining == []
