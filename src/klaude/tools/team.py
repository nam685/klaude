"""Team tools — create agent teams, delegate tasks, and exchange messages.

Three tools that give the LLM the ability to orchestrate multiple specialists:

    team_create   — define a team with named members and roles
    team_delegate — assign a task to a member, run it, get results
    team_message  — read/post on the shared message board

These tools use module-level state (like task_list uses _tasks).
The LLM client is shared via set_client(), called by Session.__init__.

See Note 35 in docs/07-implementation-notes.md.
"""

from klaude.client import LLMClient
from klaude.team import AgentRole, MessageBoard, run_agent
from klaude.tools.registry import Tool

# Module-level state — shared across tool calls within a session
_client: LLMClient | None = None
_team_name: str = ""
_members: dict[str, AgentRole] = {}
_board: MessageBoard = MessageBoard()


def set_client(client: LLMClient) -> None:
    """Set the shared LLM client. Called by Session.__init__."""
    global _client
    _client = client


def _reset() -> None:
    """Reset team state (for testing or creating a new team)."""
    global _team_name, _members
    _team_name = ""
    _members = {}
    _board.clear()


# --- Tool 1: team_create ---

def handle_team_create(
    team_name: str,
    members: list[dict],
) -> str:
    """Create a team with named members."""
    global _team_name, _members

    if not members:
        return "Error: at least one member is required."

    valid_access = ("readonly", "readwrite", "full")
    parsed: dict[str, AgentRole] = {}

    for m in members:
        name = m.get("name", "").strip()
        if not name:
            return "Error: each member must have a 'name'."
        description = m.get("description", name)
        system_prompt = m.get("system_prompt", "")
        tool_access = m.get("tool_access", "readonly")
        if tool_access not in valid_access:
            return f"Error: tool_access must be one of {valid_access}, got '{tool_access}'."
        parsed[name] = AgentRole(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tool_access=tool_access,
        )

    _team_name = team_name
    _members = parsed
    _board.clear()

    lines = [f"Team '{team_name}' created with {len(parsed)} members:"]
    for role in parsed.values():
        lines.append(f"  - {role.name} ({role.tool_access}): {role.description}")
    return "\n".join(lines)


team_create_tool = Tool(
    name="team_create",
    description="Define a team of agents with roles and tool access levels.",
    parameters={
        "type": "object",
        "properties": {
            "team_name": {
                "type": "string",
            },
            "members": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                        },
                        "description": {
                            "type": "string",
                        },
                        "system_prompt": {
                            "type": "string",
                        },
                        "tool_access": {
                            "type": "string",
                            "enum": ["readonly", "readwrite", "full"],
                            "description": (
                                "readonly: read files. "
                                "readwrite: + write/edit. full: + bash/git/web."
                            ),
                        },
                    },
                    "required": ["name", "description"],
                },
                "description": "List of team members. Each needs name and description.",
            },
        },
        "required": ["team_name", "members"],
    },
    handler=handle_team_create,
)


# --- Tool 2: team_delegate ---

def handle_team_delegate(
    member_name: str,
    task: str,
    include_messages: bool = True,
) -> str:
    """Delegate a task to a specific team member."""
    if not _members:
        return "Error: no team exists. Use team_create first."

    if member_name not in _members:
        available = ", ".join(_members.keys())
        return f"Error: unknown member '{member_name}'. Available: {available}"

    if _client is None:
        return "Error: LLM client not configured."

    role = _members[member_name]

    # Run the agent — this is synchronous (one at a time)
    result = run_agent(
        client=_client,
        role=role,
        task=task,
        board=_board if include_messages else MessageBoard(),
    )

    return f"[{role.name}] {result}"


team_delegate_tool = Tool(
    name="team_delegate",
    description="Assign a task to a team member and get their results.",
    parameters={
        "type": "object",
        "properties": {
            "member_name": {
                "type": "string",
                "description": "Must match a name from team_create.",
            },
            "task": {
                "type": "string",
            },
            "include_messages": {
                "type": "boolean",
                "description": "Include the team message board in context (default true).",
            },
        },
        "required": ["member_name", "task"],
    },
    handler=handle_team_delegate,
)


# --- Tool 3: team_message ---

def handle_team_message(
    action: str,
    content: str = "",
    from_name: str = "lead",
    to_name: str | None = None,
) -> str:
    """Read or post messages on the team's shared message board."""
    if action == "read":
        if not _board:
            return "(no messages on the board)"
        return _board.format()

    elif action == "post":
        if not content:
            return "Error: 'content' is required for action 'post'."
        _board.post(sender=from_name, content=content, recipient=to_name)
        return f"Posted message from {from_name}" + (f" to {to_name}" if to_name else " (broadcast)")

    else:
        return f"Error: unknown action '{action}'. Must be 'read' or 'post'."


team_message_tool = Tool(
    name="team_message",
    description="Read or post on the team's shared message board.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "post"],
            },
            "content": {
                "type": "string",
                "description": "Message content (required for 'post').",
            },
            "from_name": {
                "type": "string",
                "description": "Sender name (default: 'lead').",
            },
            "to_name": {
                "type": "string",
                "description": "Recipient name. Omit for broadcast.",
            },
        },
        "required": ["action"],
    },
    handler=handle_team_message,
)
