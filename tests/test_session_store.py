"""Test session_store with custom session_dir."""

import json
from pathlib import Path

from klaude.core.session_store import save_session, load_session


def test_save_session_custom_dir(tmp_path):
    """save_session writes to a custom directory when session_dir is provided."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    sid = save_session(messages, turn_count=1, session_id="test-001", session_dir=tmp_path)
    assert sid == "test-001"

    session_file = tmp_path / "test-001.json"
    assert session_file.exists()

    data = json.loads(session_file.read_text())
    assert data["id"] == "test-001"
    assert data["turn_count"] == 1
    assert len(data["messages"]) == 2  # system prompt skipped


def test_save_session_returns_absolute_path(tmp_path):
    """save_session returns the absolute path to the session file."""
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "test"},
    ]
    sid = save_session(messages, turn_count=1, session_id="abs-test", session_dir=tmp_path)
    session_file = tmp_path / "abs-test.json"
    assert session_file.is_absolute()
    assert session_file.exists()


def test_load_session_custom_dir(tmp_path):
    """load_session reads from a custom directory."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    save_session(messages, turn_count=1, session_id="load-test", session_dir=tmp_path)
    result = load_session(session_id="load-test", session_dir=tmp_path)
    assert result is not None
    msgs, turns, saved_at, sid = result
    assert sid == "load-test"
    assert turns == 1
    assert len(msgs) == 1  # only user message (system skipped)
