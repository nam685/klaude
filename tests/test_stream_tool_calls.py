"""Tests for tool-call accumulation in consume_stream, including Gemini's
extra_content/thought_signature round-trip (see klaude.core.tool_call_dict).
"""

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from klaude.core.stream import consume_stream


def _chunk(
    index: int, delta: dict, finish_reason: str | None = None
) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "gemini-flash-latest",
            "choices": [
                {"index": index, "delta": delta, "finish_reason": finish_reason}
            ],
        }
    )


def test_tool_call_without_extra_content_round_trips_plain() -> None:
    stream = [
        _chunk(
            0,
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "x"}'},
                    }
                ],
            },
        ),
        _chunk(0, {}, finish_reason="tool_calls"),
    ]
    result = consume_stream(stream, print_text=False, quiet=True)
    msg = result.to_message_dict()
    assert msg["tool_calls"][0]["id"] == "call_1"
    assert "extra_content" not in msg["tool_calls"][0]


def test_tool_call_extra_content_is_captured_and_replayed() -> None:
    extra = {"google": {"thought_signature": "sig123"}}
    stream = [
        _chunk(
            0,
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "read_document",
                            "arguments": '{"path": "x"}',
                        },
                        "extra_content": extra,
                    }
                ],
            },
        ),
        _chunk(0, {}, finish_reason="tool_calls"),
    ]
    result = consume_stream(stream, print_text=False, quiet=True)
    msg = result.to_message_dict()
    assert msg["tool_calls"][0]["extra_content"] == extra


def test_tool_call_extra_content_arriving_in_later_fragment() -> None:
    """Some providers may attach extra_content to a later delta fragment for
    the same tool-call index rather than the first one; it must still be
    captured wherever it lands."""
    extra = {"google": {"thought_signature": "sig456"}}
    stream = [
        _chunk(
            0,
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_document"},
                    }
                ],
            },
        ),
        _chunk(
            0,
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "function": {"arguments": '{"path": "x"}'},
                        "extra_content": extra,
                    }
                ]
            },
        ),
        _chunk(0, {}, finish_reason="tool_calls"),
    ]
    result = consume_stream(stream, print_text=False, quiet=True)
    msg = result.to_message_dict()
    assert msg["tool_calls"][0]["extra_content"] == extra
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"path": "x"}'
