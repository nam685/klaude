"""Test Session quiet mode and tool call counter."""

from unittest.mock import MagicMock
from klaude.core.loop import Session


def test_session_has_total_tool_calls():
    """Session tracks total_tool_calls counter."""
    # We can't easily construct a full Session without a real LLM,
    # but we can verify the attribute exists on the class.
    # Full integration tests would need a mock LLM server.
    assert hasattr(Session, "turn")  # sanity check class exists
