"""Tests for the shared build_tool_call_dict helper."""

from klaude.core.tool_call_dict import build_tool_call_dict


def test_build_tool_call_dict_basic() -> None:
    d = build_tool_call_dict("call_1", "read_file", '{"path": "x"}')
    assert d == {
        "id": "call_1",
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"path": "x"}'},
    }
    assert "extra_content" not in d


def test_build_tool_call_dict_includes_extra_content_when_present() -> None:
    extra = {"google": {"thought_signature": "abc123"}}
    d = build_tool_call_dict("call_1", "read_file", "{}", extra)
    assert d["extra_content"] == extra


def test_build_tool_call_dict_omits_empty_extra_content() -> None:
    d = build_tool_call_dict("call_1", "read_file", "{}", {})
    assert "extra_content" not in d

    d = build_tool_call_dict("call_1", "read_file", "{}", None)
    assert "extra_content" not in d
