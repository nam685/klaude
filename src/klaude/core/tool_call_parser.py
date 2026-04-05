"""Fallback parser for text-based tool calls.

When the LLM server doesn't convert model-native tool calls to API-level
tool_calls (e.g., mlx-lm with certain quantized models where <tool_call>
isn't a single vocab token), the model outputs tool calls as text:

    <tool_call>
    <function=read_file><parameter=path>/foo/bar.py</parameter></function>
    </tool_call>

This module detects and parses these text-based tool calls so the agentic
loop can execute them normally.

See Note 49 in docs/07-implementation-notes.md.
"""

import json
import re
import uuid

from klaude.core.stream import ToolCallAccumulator

# Qwen3-Coder XML format: <function=NAME>...<parameter=KEY>VALUE</parameter>...</function>
# Optionally wrapped in <tool_call>...</tool_call>
_FUNCTION_CALL_RE = re.compile(
    r"<function=([^>]+)>(.*?)</function>",
    re.DOTALL,
)

_PARAMETER_RE = re.compile(
    r"<parameter=([^>]+)>(.*?)</parameter>",
    re.DOTALL,
)

# Entire tool call block including optional wrappers and surrounding whitespace
_TOOL_BLOCK_RE = re.compile(
    r"\s*(?:<tool_call>\s*)?"
    r"<function=[^>]+>.*?</function>"
    r"\s*(?:</tool_call>)?\s*",
    re.DOTALL,
)

# Stray wrapper tags left after stripping
_STRAY_TAGS_RE = re.compile(
    r"\s*</?tool_call>\s*",
)

# JSON tool call format: <tool_call>{"name": "...", "arguments": {...}}</tool_call>
_JSON_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)


def _parse_xml_tool_call(func_name: str, body: str) -> ToolCallAccumulator:
    """Parse a single <function=NAME>BODY</function> into a ToolCallAccumulator."""
    params: dict[str, str] = {}
    for m in _PARAMETER_RE.finditer(body):
        key = m.group(1).strip()
        value = m.group(2)
        # Strip leading/trailing newlines (model often adds them)
        if value.startswith("\n"):
            value = value[1:]
        if value.endswith("\n"):
            value = value[:-1]
        params[key] = value

    return ToolCallAccumulator(
        id=f"call_{uuid.uuid4().hex[:12]}",
        name=func_name.strip(),
        arguments=json.dumps(params),
    )


def _parse_json_tool_call(json_str: str) -> ToolCallAccumulator | None:
    """Parse a JSON-format tool call: {"name": "...", "arguments": {...}}."""
    try:
        data = json.loads(json_str)
        name = data.get("name", "")
        args = data.get("arguments", {})
        if not name:
            return None
        return ToolCallAccumulator(
            id=f"call_{uuid.uuid4().hex[:12]}",
            name=name,
            arguments=json.dumps(args) if isinstance(args, dict) else str(args),
        )
    except (json.JSONDecodeError, AttributeError):
        return None


def parse_tool_calls_from_text(
    text: str,
) -> tuple[str, list[ToolCallAccumulator]]:
    """Parse tool calls embedded in text content.

    Returns:
        (cleaned_text, tool_calls) — content with markup removed,
        and a list of parsed tool calls ready for execution.
        If no tool calls found, returns (text, []).
    """
    tool_calls: list[ToolCallAccumulator] = []

    # Try Qwen3-Coder XML format first (most common for our setup)
    for m in _FUNCTION_CALL_RE.finditer(text):
        tc = _parse_xml_tool_call(m.group(1), m.group(2))
        tool_calls.append(tc)

    # Try JSON format if no XML calls found
    if not tool_calls:
        for m in _JSON_TOOL_CALL_RE.finditer(text):
            tc = _parse_json_tool_call(m.group(1))
            if tc:
                tool_calls.append(tc)

    if not tool_calls:
        return text, []

    # Strip tool call markup from text
    cleaned = _TOOL_BLOCK_RE.sub("", text)
    cleaned = _JSON_TOOL_CALL_RE.sub("", cleaned)
    cleaned = _STRAY_TAGS_RE.sub("", cleaned)
    cleaned = cleaned.strip()

    return cleaned, tool_calls
