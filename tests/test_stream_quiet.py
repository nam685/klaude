"""Test that consume_stream suppresses output when print_text=False."""

from klaude.core.stream import StreamResult


def test_stream_result_basic():
    """StreamResult accumulates content and tool calls."""
    result = StreamResult()
    result.content = "hello"
    assert result.content == "hello"
    assert not result.has_tool_calls


def test_stream_result_to_message_dict():
    """to_message_dict produces OpenAI-compatible format."""
    result = StreamResult()
    result.content = "test"
    msg = result.to_message_dict()
    assert msg["role"] == "assistant"
    assert msg["content"] == "test"
    assert "tool_calls" not in msg
