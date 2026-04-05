"""Tests for ATIF v1.4 trace writer."""

import json
from pathlib import Path

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
