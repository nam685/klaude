"""Context tracking — tracks token usage and context window consumption.

Two counting strategies:

  1. Exact (preferred): server's /tokenize endpoint, cached for repeated strings
     (system prompt, tool schemas). Used for tool overhead when client is available.
  2. Estimate (fallback): chars/4 heuristic (~75-80% accurate for English/code).
     Used for per-message counts and when /tokenize is unavailable.

The per-message overhead (~4 tokens) accounts for the role label, message
delimiters, and other formatting that the model sees but isn't in the content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from klaude.core.client import LLMClient

# Qwen3-Coder-30B-A3B context window (matches our mlx-lm server config)
# 32K with Q4_K_M + --parallel 1 (17GB model + 3.2GB KV cache ≈ 21GB total, fits 48GB Mac)
DEFAULT_CONTEXT_WINDOW = 32768

# Rough estimate: 1 token ≈ 4 characters for English/code
CHARS_PER_TOKEN = 4

# Each message has overhead for role, delimiters, etc. (~4 tokens)
MESSAGE_OVERHEAD_TOKENS = 4

# Warn the user when context usage exceeds this fraction
WARN_THRESHOLD = 0.80


def estimate_tokens(text: str) -> int:
    """Estimate token count for a string using chars/4 heuristic.

    This is intentionally simple. For English and code, 1 token ≈ 4 chars
    is a reasonable middle ground. Some tokens are 1 char (punctuation),
    some are 6+ chars (common words). It averages out.
    """
    return max(1, len(text) // CHARS_PER_TOKEN)


# Cache for exact tokenization results (system prompt, tool schemas repeat every call)
_token_count_cache: dict[str, int] = {}


def exact_token_count(text: str, client: LLMClient) -> int:
    """Get exact token count via server /tokenize endpoint.

    Caches results for repeated strings (system prompt, tool schemas).
    Falls back to chars/4 estimate if endpoint is unavailable.
    """
    if text in _token_count_cache:
        return _token_count_cache[text]

    tokens = client.tokenize(text)
    if tokens is not None:
        count = len(tokens)
        _token_count_cache[text] = count
        return count

    return estimate_tokens(text)


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate tokens for a single message in the conversation.

    Accounts for:
    - The message content (text)
    - Tool call arguments and function names (if assistant message with tool calls)
    - Per-message overhead (role label, delimiters)
    """
    tokens = MESSAGE_OVERHEAD_TOKENS

    # Content (text body of the message)
    content = message.get("content")
    if content:
        tokens += estimate_tokens(content)

    # Tool calls in assistant messages
    tool_calls = message.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", "")
            tokens += estimate_tokens(name) + estimate_tokens(args)

    return tokens


def estimate_tools_tokens(tool_schemas: list[dict[str, Any]]) -> int:
    """Estimate tokens consumed by tool definitions sent with each request.

    Tool schemas are included in every API call. They eat into the context
    window but are easy to forget about. We serialize to JSON and estimate.
    """
    if not tool_schemas:
        return 0
    return estimate_tokens(json.dumps(tool_schemas))


@dataclass
class ContextTracker:
    """Tracks token usage across the conversation.

    Usage:
        tracker = ContextTracker(context_window=32768)
        tracker.set_tool_overhead(tool_schemas)
        # After each LLM turn:
        tracker.update(messages)
        print(tracker.format_status())
    """

    context_window: int = DEFAULT_CONTEXT_WINDOW
    message_tokens: list[int] = field(default_factory=list)
    tool_overhead: int = 0
    _client: LLMClient | None = field(default=None, repr=False)

    @property
    def total_tokens(self) -> int:
        """Total estimated tokens in the conversation (messages + tool schemas)."""
        return sum(self.message_tokens) + self.tool_overhead

    @property
    def usage_fraction(self) -> float:
        """Fraction of context window used (0.0 to 1.0+)."""
        if self.context_window == 0:
            return 0.0
        return self.total_tokens / self.context_window

    @property
    def is_warning(self) -> bool:
        """Whether usage has crossed the warning threshold."""
        return self.usage_fraction >= WARN_THRESHOLD

    def set_client(self, client: LLMClient) -> None:
        """Set client for exact tokenization via /tokenize."""
        self._client = client

    def set_tool_overhead(self, tool_schemas: list[dict[str, Any]]) -> None:
        """Calculate and store the token overhead from tool definitions."""
        if self._client:
            schema_json = json.dumps(tool_schemas)
            self.tool_overhead = exact_token_count(schema_json, self._client)
        else:
            self.tool_overhead = estimate_tools_tokens(tool_schemas)

    def update(self, messages: list[dict[str, Any]]) -> None:
        """Recalculate token counts from the full message list.

        We recalculate from scratch each time rather than incrementally.
        This is simpler and avoids drift from accumulated rounding errors.
        The message list is at most ~100 messages, so this is fast.
        """
        self.message_tokens = [estimate_message_tokens(m) for m in messages]

    def format_status(self) -> str:
        """Format a status string showing context usage.

        Returns something like:
            "Context: 12,400 / 65,536 tokens (19%)"
        or with warning:
            "Context: 54,000 / 65,536 tokens (82%) ⚠ approaching limit"
        """
        total = self.total_tokens
        window = self.context_window
        pct = self.usage_fraction * 100

        status = f"Context: {total:,} / {window:,} tokens ({pct:.0f}%)"

        if pct >= 95:
            status += " — CRITICAL: context nearly full"
        elif self.is_warning:
            status += " — approaching limit"

        return status

    def format_turn_summary(self, turn: int) -> str:
        """Format a per-turn summary with token breakdown.

        Shows: turn number, total tokens, and what's using the most space.
        """
        total = self.total_tokens
        msg_total = sum(self.message_tokens)
        pct = self.usage_fraction * 100

        parts = [f"Turn {turn}"]
        parts.append(f"{total:,} / {self.context_window:,} tokens ({pct:.0f}%)")
        if self.tool_overhead:
            parts.append(f"schema overhead: {self.tool_overhead:,}")
        parts.append(f"conversation: {msg_total:,} in {len(self.message_tokens)} msgs")

        return " | ".join(parts)

    def format_compact(self, turn: int) -> str:
        """Compact one-liner for the persistent status bar."""
        total = self.total_tokens
        window = self.context_window
        pct = self.usage_fraction * 100
        n_msgs = len(self.message_tokens)

        s = f" Turn {turn} \u00b7 {total:,}/{window:,} tokens ({pct:.0f}%) \u00b7 {n_msgs} msgs"

        if pct >= 95:
            s += " \u26a0 CRITICAL"
        elif self.is_warning:
            s += " \u26a0"

        return s
