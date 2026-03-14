"""sub_agent tool — spawn a separate LLM conversation for research or subtasks.

A sub-agent is a lightweight, isolated conversation. It gets:
- Its own message history (starts fresh)
- Read-only tools (no writes, no bash, no git_commit)
- A focused task prompt

The parent conversation sends a task, the sub-agent works on it (potentially
making multiple tool calls), and returns a text summary. This is useful for:
- Exploring code without polluting the parent's context
- Investigating a question that requires multiple searches
- Isolating research from the main task flow

See Note 26 in docs/07-implementation-notes.md for design rationale.
"""

from klaude.client import LLMClient
from klaude.tools.registry import Tool, ToolRegistry
from klaude.tools.read_file import tool as read_file_tool
from klaude.tools.glob_search import tool as glob_tool
from klaude.tools.grep_search import tool as grep_tool
from klaude.tools.list_directory import tool as list_directory_tool
from klaude.tools.git import git_status_tool, git_diff_tool, git_log_tool

# Shared client — set by Session at startup so sub-agents reuse the connection
_client: LLMClient | None = None

# Max iterations for sub-agent to prevent runaway loops
_MAX_SUB_ITERATIONS = 15

SUB_AGENT_SYSTEM_PROMPT = """You are a research sub-agent for klaude, an AI coding assistant.
You've been given a focused task. Complete it using your tools and return a clear,
concise answer. You have read-only access to the codebase — you cannot write files
or run commands.

Be thorough but concise. When done, give your findings as a direct answer."""


def _create_sub_registry() -> ToolRegistry:
    """Create a registry with read-only tools only."""
    registry = ToolRegistry()
    registry.register(read_file_tool)
    registry.register(glob_tool)
    registry.register(grep_tool)
    registry.register(list_directory_tool)
    registry.register(git_status_tool)
    registry.register(git_diff_tool)
    registry.register(git_log_tool)
    return registry


def handle_sub_agent(task: str) -> str:
    """Spawn a sub-agent conversation to research a task."""
    if _client is None:
        return "Error: sub-agent not available (LLM client not configured)."

    registry = _create_sub_registry()
    schemas = registry.get_schemas()

    messages: list[dict] = [
        {"role": "system", "content": SUB_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    for _iteration in range(_MAX_SUB_ITERATIONS):
        response = _client.chat(messages, tools=schemas)
        choice = response.choices[0]
        msg = choice.message

        # Build assistant message for history
        assistant_msg: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        # No tool calls — sub-agent is done
        if not msg.tool_calls:
            return msg.content or "(sub-agent returned no response)"

        # Execute tool calls and feed results back
        for tc in msg.tool_calls:
            result = registry.execute(tc.function.name, tc.function.arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return "Error: sub-agent hit maximum iterations without completing."


def set_client(client: LLMClient) -> None:
    """Set the shared LLM client for sub-agents. Called by Session.__init__."""
    global _client
    _client = client


tool = Tool(
    name="sub_agent",
    description=(
        "Spawn a separate LLM conversation for research or subtasks. "
        "The sub-agent has read-only access to the codebase (read_file, glob, grep, "
        "list_directory, git_status, git_diff, git_log) but cannot write files or "
        "run commands. Give it a clear, focused task and it will return findings. "
        "Use for: exploring unfamiliar code, investigating questions, or isolating "
        "research that would clutter your main context."
    ),
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "A clear description of what the sub-agent should research or figure out. "
                    "Be specific — include file paths, function names, or patterns to look for."
                ),
            }
        },
        "required": ["task"],
    },
    handler=handle_sub_agent,
)
