"""Tool registry — maps tool names to their schemas and handler functions.

This is the core of the tool system. A "tool" is just three things:
1. A name (string)
2. A JSON schema (dict) — tells the LLM what parameters the tool accepts
3. A handler function — actually executes the tool and returns a string result

The registry holds all registered tools and can:
- Return schemas in OpenAI tool format (for sending to the LLM)
- Execute a tool by name with given arguments

Tools are organized into tiers for dynamic loading:
- core: always sent (read, write, edit, bash, glob, grep, list_dir, task_list, ask_user, web_search)
- git: sent when in a git repo (git_status, git_diff, git_log, git_commit)
- extended: sent on demand or when context allows (sub_agent, web_fetch, lsp, etc.)
- plugin: custom tools from plugins/MCP (always sent if loaded)
"""

import json
from dataclasses import dataclass
from typing import Any, Callable

# Tool tier definitions — which tools belong to which tier
CORE_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "edit_file",
        "bash",
        "glob",
        "grep",
        "list_directory",
        "task_list",
        "ask_user",
        "web_search",
    }
)

GIT_TOOLS = frozenset(
    {
        "git_status",
        "git_diff",
        "git_log",
        "git_commit",
    }
)

EXTENDED_TOOLS = frozenset(
    {
        "sub_agent",
        "web_fetch",
        "lsp",
        "notebook_edit",
        "background_task",
        "worktree",
        "team_create",
        "team_delegate",
        "team_message",
    }
)


@dataclass
class Tool:
    """A single tool: name + schema + handler."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]


class ToolRegistry:
    """Holds all available tools. Provides schemas for the LLM and executes tool calls."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._plugin_tools: set[str] = set()

    def register(self, tool: Tool, is_plugin: bool = False) -> None:
        """Add a tool to the registry."""
        self._tools[tool.name] = tool
        if is_plugin:
            self._plugin_tools.add(tool.name)

    def get_schemas(
        self,
        tiers: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return tool schemas in OpenAI function-calling format.

        If tiers is None, returns ALL tools (backwards compatible).
        Otherwise, returns tools in the specified tiers plus any plugin tools.
        Valid tiers: "core", "git", "extended".
        """
        if tiers is None:
            # All tools
            tools_to_include = set(self._tools.keys())
        else:
            tools_to_include: set[str] = set()
            if "core" in tiers:
                tools_to_include |= CORE_TOOLS
            if "git" in tiers:
                tools_to_include |= GIT_TOOLS
            if "extended" in tiers:
                tools_to_include |= EXTENDED_TOOLS
            # Always include plugin/MCP tools
            tools_to_include |= self._plugin_tools

        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
            if tool.name in tools_to_include
        ]

    def execute(self, name: str, arguments: str) -> str:
        """Execute a tool by name. Arguments come as a JSON string from the LLM.

        Returns the tool's output as a string (this gets sent back to the LLM
        as a tool result message).

        Note: execution works for ALL registered tools regardless of which
        schemas were sent to the LLM. If the LLM hallucinates a tool name
        that exists in the registry, it still runs.
        """
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"

        tool = self._tools[name]

        try:
            kwargs = json.loads(arguments)
        except json.JSONDecodeError as e:
            return f"Error: invalid JSON arguments: {e}"

        try:
            return tool.handler(**kwargs)
        except Exception as e:
            return f"Error executing {name}: {type(e).__name__}: {e}"

    @property
    def tool_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
