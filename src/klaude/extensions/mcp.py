"""MCP (Model Context Protocol) integration — connect to external tool servers.

MCP lets klaude use tools provided by external servers (GitHub, Slack, databases,
etc.) without building custom integrations. We use the official `mcp` Python SDK
from Anthropic.

Architecture:
    .klaude.toml          →  MCPServerConfig (name, command, args, env)
    MCPServerConfig       →  stdio_client() → ClientSession
    ClientSession         →  list_tools() → MCP Tool schemas
    MCP Tool schemas      →  our Tool() format → registered in ToolRegistry
    Tool call in loop     →  call_tool() on the MCP session → result string

The bridge between our sync code and MCP's async API uses asyncio.run()
for setup and a running event loop + run_coroutine_threadsafe for tool calls.

See Note 31 in docs/07-implementation-notes.md.
"""

import asyncio
import threading
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from klaude.config import MCPServerConfig
from klaude.tools.registry import Tool


class MCPBridge:
    """Manages connections to MCP servers and bridges their tools to klaude.

    Lifecycle:
        bridge = MCPBridge()
        tools = bridge.connect_all(server_configs)  # returns list[Tool]
        # ... register tools in registry, run the session ...
        bridge.close()  # clean up all connections
    """

    def __init__(self) -> None:
        # Background event loop for async MCP operations
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        # Async context manager stack for cleanup
        self._exit_stack: AsyncExitStack | None = None
        # Active sessions keyed by server name
        self._sessions: dict[str, ClientSession] = {}

    def connect_all(self, configs: list[MCPServerConfig]) -> list[Tool]:
        """Connect to all configured MCP servers and return their tools.

        This is called once at Session startup. It:
        1. Connects to each MCP server via stdio
        2. Lists their tools
        3. Converts MCP tools to our Tool format
        4. Returns them for registration
        """
        future = asyncio.run_coroutine_threadsafe(
            self._connect_all_async(configs), self._loop
        )
        return future.result(timeout=30)

    async def _connect_all_async(self, configs: list[MCPServerConfig]) -> list[Tool]:
        """Async implementation of connect_all."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        all_tools: list[Tool] = []

        for config in configs:
            if not config.command:
                continue

            try:
                tools = await self._connect_server(config)
                all_tools.extend(tools)
            except Exception as e:
                # Don't crash klaude if one MCP server fails
                print(f"Warning: MCP server '{config.name}' failed to connect: {e}")

        return all_tools

    async def _connect_server(self, config: MCPServerConfig) -> list[Tool]:
        """Connect to a single MCP server and return its tools."""
        params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env or None,
        )

        # stdio_client returns (read_stream, write_stream)
        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )

        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        self._sessions[config.name] = session

        # List tools from this server
        result = await session.list_tools()

        # Convert MCP tools to our Tool format
        tools: list[Tool] = []
        for mcp_tool in result.tools:
            tool = self._make_tool(config.name, mcp_tool, session)
            tools.append(tool)

        return tools

    def _make_tool(
        self, server_name: str, mcp_tool: object, session: ClientSession
    ) -> Tool:
        """Convert an MCP tool to our Tool format.

        The handler calls back into the MCP session via the background event loop.
        """
        # Extract fields from the MCP tool object
        name = f"mcp_{server_name}_{mcp_tool.name}"  # type: ignore[attr-defined]
        description = mcp_tool.description or f"MCP tool from {server_name}"  # type: ignore[attr-defined]
        parameters = mcp_tool.inputSchema  # type: ignore[attr-defined]
        tool_name = mcp_tool.name  # type: ignore[attr-defined]

        def handler(**kwargs: object) -> str:
            """Bridge: sync handler → async MCP call_tool."""
            future = asyncio.run_coroutine_threadsafe(
                session.call_tool(tool_name, arguments=kwargs),
                self._loop,
            )
            try:
                result = future.result(timeout=60)
                # Extract text from result content
                parts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        parts.append(content.text)
                    else:
                        parts.append(str(content))
                return "\n".join(parts) or "(empty result)"
            except Exception as e:
                return f"Error calling MCP tool {tool_name}: {e}"

        return Tool(
            name=name,
            description=f"[MCP:{server_name}] {description}",
            parameters=parameters,
            handler=handler,
        )

    def close(self) -> None:
        """Shut down all MCP connections and the background event loop."""
        if self._exit_stack:
            future = asyncio.run_coroutine_threadsafe(
                self._exit_stack.aclose(), self._loop
            )
            try:
                future.result(timeout=10)
            except Exception:
                pass

        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    @property
    def server_names(self) -> list[str]:
        """Names of connected MCP servers."""
        return list(self._sessions.keys())
