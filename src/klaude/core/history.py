"""Message history — structured wrapper around the conversation message list.

The agentic loop builds up a flat list of messages:
    [system, user, assistant, tool, tool, assistant, tool, assistant, ...]

This module gives that list structure so we can:
1. Add messages with proper typing (not raw dicts everywhere)
2. Identify which messages are safe to compact (summarize)
3. Replace old messages with a summary to free context space

The key concept is "protected" vs "compactable" messages:
- Protected: system prompt, the latest user message, and everything after it
  (the LLM needs these to understand the current task)
- Compactable: older assistant/tool exchanges that can be summarized

This is the foundation for context compaction (next feature).
"""

from typing import Any


class MessageHistory:
    """Manages the conversation message list with structure-aware operations.

    Usage:
        history = MessageHistory("You are klaude...")
        history.add_user("Fix the bug in main.py")

        # In the loop:
        history.add_assistant(result.to_message_dict())
        history.add_tool_result("call_1", "file contents here...")

        # Pass to API:
        client.chat_stream(history.messages, tools=schemas)

        # For compaction:
        start, end = history.compactable_range()
        if start < end:
            history.replace_range(start, end, "Summary: fixed the bug...")
    """

    def __init__(self, system_prompt: str) -> None:
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

    @property
    def messages(self) -> list[dict[str, Any]]:
        """The raw message list, suitable for passing to the LLM API."""
        return self._messages

    def __len__(self) -> int:
        return len(self._messages)

    def add_user(self, content: str) -> None:
        """Add a user message."""
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, message_dict: dict[str, Any]) -> None:
        """Add an assistant message (from StreamResult.to_message_dict())."""
        self._messages.append(message_dict)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Add a tool result message."""
        self._messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
        )

    def compactable_range(self, keep_recent: int = 6) -> tuple[int, int]:
        """Return (start, end) indices of messages safe to compact.

        Protected messages (never compacted):
        - Index 0: system prompt
        - Index 1: original user message (the task)
        - Last `keep_recent` messages (the current turn's context)

        Compactable: the older exchanges in the middle.

        Why this split? In a single-task conversation:
            [0] system prompt           <- protected (instructions)
            [1] user message            <- protected (the task)
            [2] assistant: read_file    <- old turn, compactable
            [3] tool: file contents     <- old turn, compactable
            [4] assistant: edit_file    <- old turn, compactable
            [5] tool: success           <- old turn, compactable
            [6] assistant: read_file    <- recent, protected
            [7] tool: file contents     <- recent, protected
            ...

        The `keep_recent` default of 6 keeps ~2-3 recent turns visible
        to the LLM so it doesn't repeat actions it just took.

        Returns (start, end) where messages[start:end] can be replaced.
        If start >= end, nothing is compactable.
        """
        # Start after system prompt + user message
        start = 2
        # End before the last `keep_recent` messages
        end = max(start, len(self._messages) - keep_recent)
        return (start, end)

    def replace_range(self, start: int, end: int, summary: str) -> None:
        """Replace messages[start:end] with a single summary message.

        The summary is inserted as a "system" message (not "user" or "assistant")
        so the LLM treats it as authoritative context, not as a previous
        conversation turn it needs to continue from.
        """
        if start >= end or start < 1:
            return

        summary_message: dict[str, Any] = {
            "role": "system",
            "content": f"[Conversation summary]\n{summary}",
        }
        self._messages[start:end] = [summary_message]

    def format_debug(self) -> str:
        """Format the message list for debugging. Shows role + content preview."""
        lines = []
        start, end = self.compactable_range()
        for i, msg in enumerate(self._messages):
            role = msg["role"]
            content = msg.get("content", "")
            preview = (content or "")[:60].replace("\n", " ")
            tool_calls = msg.get("tool_calls")

            marker = ""
            if i == 0:
                marker = " [system]"
            elif i == 1:
                marker = " [user task]"
            elif start <= i < end:
                marker = " [compactable]"
            else:
                marker = " [recent]"

            if tool_calls:
                names = [tc["function"]["name"] for tc in tool_calls]
                lines.append(f"  [{i}] {role}: tool_calls={names}{marker}")
            else:
                lines.append(
                    f"  [{i}] {role}: {preview}...{marker}"
                    if len(content or "") > 60
                    else f"  [{i}] {role}: {preview}{marker}"
                )
        return "\n".join(lines)
