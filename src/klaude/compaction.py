"""Context compaction — summarize older messages to free context space.

When the conversation grows long, earlier tool calls and their results
eat up the context window. Compaction solves this by:
1. Identifying which messages are safe to summarize (old exchanges)
2. Asking the LLM to summarize them into a concise paragraph
3. Replacing the originals with the summary

This is how Claude Code handles long sessions — it periodically compacts
the conversation history so the model can keep working within its context
window.

The tricky part: we use the LLM itself to generate the summary, which
means we need to be careful not to use too much context for the
summarization request itself.
"""

from klaude.client import LLMClient
from klaude.context import ContextTracker
from klaude.history import MessageHistory

# Compact when context usage exceeds this fraction (adaptive by window size)
COMPACT_THRESHOLD_SMALL = 0.60  # for context_window ≤ 16384
COMPACT_THRESHOLD_NORMAL = 0.75  # for larger windows

# Recent messages to keep (fewer for small windows)
KEEP_RECENT_SMALL = 4
KEEP_RECENT_NORMAL = 6

# Window size boundary for adaptive behavior
SMALL_WINDOW_THRESHOLD = 16384

SUMMARIZE_PROMPT = """\
Summarize the following conversation exchanges concisely. Focus on:
- What files were read or modified, and what changes were made
- What commands were run and their outcomes
- Key decisions or findings
- Any errors encountered and how they were resolved

Be brief but preserve important details (file paths, function names, error messages).
Write in past tense as a factual record. Do not include greetings or filler."""


def _get_threshold(context_window: int) -> float:
    """Get compaction threshold based on context window size."""
    if context_window <= SMALL_WINDOW_THRESHOLD:
        return COMPACT_THRESHOLD_SMALL
    return COMPACT_THRESHOLD_NORMAL


def _get_keep_recent(context_window: int) -> int:
    """Get number of recent messages to keep based on context window size."""
    if context_window <= SMALL_WINDOW_THRESHOLD:
        return KEEP_RECENT_SMALL
    return KEEP_RECENT_NORMAL


def should_compact(tracker: ContextTracker) -> bool:
    """Check if compaction is needed based on context usage."""
    threshold = _get_threshold(tracker.context_window)
    return tracker.usage_fraction >= threshold


def build_summary_messages(messages_to_summarize: list[dict]) -> list[dict]:
    """Build the message list for the summarization request.

    We construct a small, focused conversation:
    1. A system prompt with summarization instructions
    2. The messages to summarize, formatted as a readable transcript
    """
    # Format the messages as a readable transcript
    lines = []
    for msg in messages_to_summarize:
        role = msg["role"]
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")

        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", "")
                lines.append(f"[assistant called {name}({args})]")
        elif content:
            # Truncate very long tool results to keep the summary request small
            if role == "tool" and len(content) > 2000:
                content = content[:2000] + "\n... (truncated)"
            lines.append(f"[{role}]: {content}")

    transcript = "\n".join(lines)

    return [
        {"role": "system", "content": SUMMARIZE_PROMPT},
        {"role": "user", "content": f"Summarize this conversation:\n\n{transcript}"},
    ]


def compact(
    history: MessageHistory,
    tracker: ContextTracker,
    client: LLMClient,
) -> bool:
    """Run context compaction if needed.

    Returns True if compaction was performed, False if not needed.

    Steps:
    1. Check if compaction is needed (context > 75% full)
    2. Find the compactable range in the message history
    3. Ask the LLM to summarize those messages (non-streaming, no tools)
    4. Replace the originals with the summary
    5. Update the tracker
    """
    if not should_compact(tracker):
        return False

    keep_recent = _get_keep_recent(tracker.context_window)
    start, end = history.compactable_range(keep_recent=keep_recent)
    if start >= end:
        return False

    # Extract the messages we'll summarize
    messages_to_summarize = history.messages[start:end]

    # Ask the LLM to summarize (non-streaming, no tools — simple request)
    summary_messages = build_summary_messages(messages_to_summarize)
    response = client.chat(summary_messages)

    summary = response.choices[0].message.content or "No summary generated."

    # Replace the old messages with the summary
    history.replace_range(start, end, summary)

    # Recalculate token counts
    tracker.update(history.messages)

    return True
