"""Agent teams — named specialists that collaborate on complex tasks.

A team is a group of agents, each with a role (name + system prompt) and
a tool access level. The lead agent (the main Session) creates a team,
delegates tasks to members, and members can share results through a
message board.

How it differs from sub_agent:
- sub_agent: one anonymous, read-only research agent
- teams: named specialists with configurable tool access and shared context

Tool access levels:
    readonly   — read_file, glob, grep, list_directory, git_status/diff/log
    readwrite  — readonly + write_file, edit_file
    full       — readwrite + bash, git_commit, web_fetch

See Note 35 in docs/07-implementation-notes.md for design rationale.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime

from klaude.client import LLMClient
from klaude.tools.registry import Tool, ToolRegistry
from klaude.tools.read_file import tool as read_file_tool
from klaude.tools.glob_search import tool as glob_tool
from klaude.tools.grep_search import tool as grep_tool
from klaude.tools.list_directory import tool as list_directory_tool
from klaude.tools.git import git_status_tool, git_diff_tool, git_log_tool, git_commit_tool
from klaude.tools.write_file import tool as write_file_tool
from klaude.tools.edit_file import tool as edit_file_tool
from klaude.tools.bash import tool as bash_tool
from klaude.tools.web_fetch import tool as web_fetch_tool

# Max iterations per team member to prevent runaway loops
_MAX_MEMBER_ITERATIONS = 20


@dataclass
class AgentRole:
    """A team member definition — who they are and what they can do."""
    name: str
    description: str
    system_prompt: str = ""
    tool_access: str = "readonly"  # "readonly", "readwrite", "full"


@dataclass
class TeamMessage:
    """A message on the team's shared message board."""
    sender: str
    content: str
    recipient: str | None = None  # None = broadcast to all
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")


class MessageBoard:
    """Thread-safe message board for inter-agent communication.

    Agents post findings, the lead posts context, and any agent can read
    messages to build on others' work.
    """

    def __init__(self) -> None:
        self._messages: list[TeamMessage] = []
        self._lock = threading.Lock()

    def post(self, sender: str, content: str, recipient: str | None = None) -> None:
        """Post a message to the board."""
        with self._lock:
            self._messages.append(TeamMessage(
                sender=sender, content=content, recipient=recipient
            ))

    def get_all(self) -> list[TeamMessage]:
        """Get all messages on the board."""
        with self._lock:
            return list(self._messages)

    def get_for(self, agent_name: str) -> list[TeamMessage]:
        """Get messages visible to a specific agent (broadcasts + direct messages)."""
        with self._lock:
            return [
                m for m in self._messages
                if m.recipient is None or m.recipient == agent_name
            ]

    def format(self, agent_name: str | None = None) -> str:
        """Format messages as readable text, optionally filtered for an agent."""
        messages = self.get_for(agent_name) if agent_name else self.get_all()
        if not messages:
            return "(no messages)"
        lines = []
        for m in messages:
            to = f" → {m.recipient}" if m.recipient else ""
            lines.append(f"[{m.timestamp}] {m.sender}{to}: {m.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all messages."""
        with self._lock:
            self._messages.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._messages)


def _create_registry(tool_access: str) -> ToolRegistry:
    """Create a tool registry based on the access level.

    readonly   — exploration tools only (same as sub_agent)
    readwrite  — add file writing/editing
    full       — add bash, git_commit, web_fetch
    """
    registry = ToolRegistry()

    # Always available: read-only exploration tools
    registry.register(read_file_tool)
    registry.register(glob_tool)
    registry.register(grep_tool)
    registry.register(list_directory_tool)
    registry.register(git_status_tool)
    registry.register(git_diff_tool)
    registry.register(git_log_tool)

    if tool_access in ("readwrite", "full"):
        registry.register(write_file_tool)
        registry.register(edit_file_tool)

    if tool_access == "full":
        registry.register(bash_tool)
        registry.register(git_commit_tool)
        registry.register(web_fetch_tool)

    return registry


def _build_member_system_prompt(
    role: AgentRole,
    board: MessageBoard,
) -> str:
    """Build the system prompt for a team member, including board context."""
    parts = [
        f"You are {role.name}, a team member in klaude (an AI coding assistant).",
        f"Your role: {role.description}",
    ]

    if role.system_prompt:
        parts.append(f"\n{role.system_prompt}")

    access_desc = {
        "readonly": "read-only access (search, read files, view git status)",
        "readwrite": "read-write access (search, read, write, and edit files)",
        "full": "full access (search, read, write, edit, run commands, git commit, web fetch)",
    }
    parts.append(f"\nYou have {access_desc.get(role.tool_access, 'read-only access')}.")
    parts.append("\nBe thorough but concise. Complete your task and summarize your findings.")

    # Include message board context
    board_messages = board.get_for(role.name)
    if board_messages:
        parts.append("\n--- Team Message Board ---")
        for m in board_messages:
            to = f" → {m.recipient}" if m.recipient else ""
            parts.append(f"[{m.timestamp}] {m.sender}{to}: {m.content}")
        parts.append("--- End Messages ---")

    return "\n".join(parts)


def run_agent(
    client: LLMClient,
    role: AgentRole,
    task: str,
    board: MessageBoard,
) -> str:
    """Run a single team member on a task.

    Creates an isolated conversation with tools matching the role's access level.
    The member sees relevant messages from the board in their system prompt.
    Results are automatically posted to the board when done.

    Returns the member's final text response.
    """
    registry = _create_registry(role.tool_access)
    schemas = registry.get_schemas()
    system_prompt = _build_member_system_prompt(role, board)

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    for _iteration in range(_MAX_MEMBER_ITERATIONS):
        response = client.chat(messages, tools=schemas)
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

        # No tool calls — agent is done
        if not msg.tool_calls:
            result = msg.content or "(no response)"
            # Auto-post result to the message board
            board.post(role.name, result)
            return result

        # Execute tool calls and feed results back
        for tc in msg.tool_calls:
            result = registry.execute(tc.function.name, tc.function.arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    error = f"Error: {role.name} hit maximum iterations without completing."
    board.post(role.name, error)
    return error
