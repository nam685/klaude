"""Test session_store with ATIF format."""

import json
from pathlib import Path

from klaude.core.session_store import save_session, load_session, list_sessions


def test_save_session_writes_atif(tmp_path):
    """save_session writes ATIF v1.4 format."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    sid = save_session(
        messages, turn_count=1, session_id="test-001",
        session_dir=tmp_path, model_name="test-model",
    )
    assert sid == "test-001"

    session_file = tmp_path / "test-001.json"
    assert session_file.exists()

    data = json.loads(session_file.read_text())
    assert data["schema_version"] == "ATIF-v1.4"
    assert data["session_id"] == "test-001"
    assert data["agent"]["model_name"] == "test-model"
    # system prompt is skipped, user + assistant = 2 steps
    assert len(data["steps"]) == 2
    assert data["steps"][0]["source"] == "user"
    assert data["steps"][1]["source"] == "agent"
    assert data["final_metrics"]["total_steps"] == 2


def test_load_session_reads_atif(tmp_path):
    """load_session reads ATIF and returns chat messages."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    save_session(
        messages, turn_count=1, session_id="load-test",
        session_dir=tmp_path, model_name="test-model",
    )
    result = load_session(session_id="load-test", session_dir=tmp_path)
    assert result is not None
    msgs, turns, saved_at, sid = result
    assert sid == "load-test"
    assert turns == 1
    assert len(msgs) == 2  # user + assistant (system skipped)
    assert msgs[0] == {"role": "user", "content": "hello"}
    assert msgs[1] == {"role": "assistant", "content": "hi"}


def test_list_sessions_reads_atif(tmp_path):
    """list_sessions extracts metadata from ATIF files."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "fix the bug"},
        {"role": "assistant", "content": "done"},
    ]
    save_session(
        messages, turn_count=1, session_id="list-test",
        session_dir=tmp_path, model_name="test-model",
    )
    sessions = list_sessions(session_dir=tmp_path)
    assert len(sessions) == 1
    assert sessions[0]["id"] == "list-test"
    assert sessions[0]["turn_count"] == 1
    assert sessions[0]["summary"] == "fix the bug"
