"""Tool registry — maps tool names to their schemas and handler functions.

This is the core of the tool system. A "tool" is just three things:
1. A name (string)
2. A JSON schema (dict) — tells the LLM what parameters the tool accepts
3. A handler function — actually executes the tool and returns a string result

The registry holds all registered tools and can:
- Return schemas in OpenAI tool format (for sending to the LLM)
- Execute a tool by name with given arguments
"""

import json
from dataclasses import dataclass
from typing import Any, Callable


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

    def register(self, tool: Tool) -> None:
        """Add a tool to the registry."""
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return all tools in OpenAI function-calling format.

        This is what we pass to the LLM API in the `tools` parameter.
        Format:
        [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "...",
                    "parameters": { ... JSON schema ... }
                }
            },
            ...
        ]
        """
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
        ]

    def execute(self, name: str, arguments: str) -> str:
        """Execute a tool by name. Arguments come as a JSON string from the LLM.

        Returns the tool's output as a string (this gets sent back to the LLM
        as a tool result message).
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
