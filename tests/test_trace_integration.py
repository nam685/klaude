"""Integration test: a simulated turn writes correct ATIF trace."""

import json
from pathlib import Path

from klaude.core.trace import TraceWriter


def test_full_turn_trace(tmp_path):
    """Simulate a complete agentic turn and verify the ATIF output."""
    path = tmp_path / "integration.json"
    tw = TraceWriter(path, model_name="test-model")

    # User sends a message
    tw.write_user_step("read main.py and explain it")

    # Agent responds with a tool call
    tw.write_agent_step(None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "main.py"}'}},
    ])

    # Tool result
    tw.write_tool_result_step("call_1", "def main():\n    print('hello')")

    # Agent responds with text
    tw.write_agent_step("This is a simple Python script that prints 'hello'.", tool_calls=None)

    # Finalize
    tw.finalize()

    # Verify the complete ATIF document
    data = json.loads(path.read_text())
    assert data["schema_version"] == "ATIF-v1.4"
    assert data["session_id"] == "integration"
    assert len(data["steps"]) == 4
    assert data["final_metrics"]["total_steps"] == 4

    # Verify roundtrip: ATIF → chat messages → usable by LLM
    msgs = tw.to_chat_messages()
    assert len(msgs) == 4
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "read_file"
    assert msgs[2]["role"] == "tool"
    assert msgs[3]["role"] == "assistant"
    assert "hello" in msgs[3]["content"]

    # Verify resume: load from file, get same messages
    loaded_msgs, turn_count = TraceWriter.load(path)
    assert turn_count == 1
    assert loaded_msgs == msgs


def test_resume_appends_to_existing_trace(tmp_path):
    """Resuming a session appends new steps to the existing ATIF trace."""
    path = tmp_path / "resume.json"

    # First session
    tw1 = TraceWriter(path, model_name="test-model")
    tw1.write_user_step("first task")
    tw1.write_agent_step("done with first", tool_calls=None)
    tw1.finalize()

    # Resume
    tw2 = TraceWriter.from_existing(path)
    tw2.write_user_step("second task")
    tw2.write_agent_step("done with second", tool_calls=None)
    tw2.finalize()

    data = json.loads(path.read_text())
    assert len(data["steps"]) == 4
    assert data["steps"][0]["step_id"] == 1
    assert data["steps"][2]["step_id"] == 3
    assert data["final_metrics"]["total_steps"] == 4

    msgs, turns = TraceWriter.load(path)
    assert turns == 2
    assert len(msgs) == 4
