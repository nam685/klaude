"""Shared helper for building OpenAI-format tool_call dicts.

Gemini's OpenAI-compat endpoint attaches an opaque
`extra_content.google.thought_signature` to each function-call part of its
response. It isn't part of the OpenAI schema, but Gemini requires it to be
echoed back verbatim on the next request for multi-turn function calling —
omit it and the API 400s with "Function call is missing a thought_signature".

Every place that reconstructs a tool_call dict from an SDK object (streaming
accumulation, sub-agents, team members) must forward this field if present,
so it needs to go through this one helper rather than being hand-rolled.
"""

from typing import Any


def build_tool_call_dict(
    call_id: str, name: str, arguments: str, extra_content: Any = None
) -> dict:
    """Build an OpenAI-format tool_call dict, preserving extra_content if present."""
    d: dict = {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }
    if extra_content:
        d["extra_content"] = extra_content
    return d
