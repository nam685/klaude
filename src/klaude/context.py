"""Context tracking — estimates token usage and tracks context window consumption.

Why estimation, not exact counting?

Local models like Qwen3-Coder-Next use their own tokenizer (not OpenAI's tiktoken).
Exact counting would require either:
  1. Loading the HuggingFace tokenizer (heavy dependency: transformers + torch)
  2. Hitting llama-server's /tokenize endpoint (non-standard, requires server up)

Instead, we use a simple heuristic: ~4 characters per token. This is roughly
75-80% accurate for English text and code. Good enough for tracking context
usage and knowing when to compact — we don't need exact numbers.

The per-message overhead (~4 tokens) accounts for the role label, message
delimiters, and other formatting that the model sees but isn't in the content.
"""

import json
from dataclasses import dataclass, field
from typing import Any

# Qwen3-Coder-Next context window (matches our llama-server config)
# 8K is safe for 48GB Mac with Q3_K_M (36GB model + KV cache must fit in RAM)
DEFAULT_CONTEXT_WINDOW = 8192

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
        tracker = ContextTracker(context_window=65536)
        tracker.set_tool_overhead(tool_schemas)
        tracker.add_message({"role": "system", "content": "..."})
        tracker.add_message({"role": "user", "content": "..."})
        # After each LLM turn:
        tracker.update(messages)
        print(tracker.format_status())
    """

    context_window: int = DEFAULT_CONTEXT_WINDOW
    message_tokens: list[int] = field(default_factory=list)
    tool_overhead: int = 0

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

    def set_tool_overhead(self, tool_schemas: list[dict[str, Any]]) -> None:
        """Calculate and store the token overhead from tool definitions."""
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
