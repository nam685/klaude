"""The agentic loop — the heart of klaude.

This implements the core pattern:
    while LLM returns tool_calls:
        execute each tool
        feed results back to LLM
    print final text response (streamed token-by-token)

The Session class holds persistent state across turns (for multi-turn REPL).
Each call to session.turn() processes one user message through the full loop.

See docs/01-how-agentic-loops-work.md for the conceptual explanation.
"""

import copy
import os

from openai import APIConnectionError, APITimeoutError, InternalServerError
from rich.console import Console

from klaude.config import KlaudeConfig
from klaude.core.client import LLMClient
from klaude.core.trace import TraceWriter
from klaude.core.compaction import compact
from klaude.core.context import ContextTracker
from klaude.core.history import MessageHistory
from klaude.core.prompt import SYSTEM_PROMPT
from klaude.core.stream import consume_stream
from klaude.extensions.hooks import run_hook
from klaude.extensions.mcp import MCPBridge
from klaude.extensions.plugins import load_plugin_tools
from klaude.extensions.skills import Skill, load_all_skills
from klaude.permissions import PermissionManager
from klaude.tools.registry import ToolRegistry
from klaude.ui.status_bar import StatusBar
from klaude.tools.bash import tool as bash_tool
from klaude.tools.edit_file import tool as edit_file_tool
from klaude.tools.glob_search import tool as glob_tool
from klaude.tools.grep_search import tool as grep_tool
from klaude.tools.list_directory import tool as list_directory_tool
from klaude.tools.read_file import tool as read_file_tool
from klaude.tools.write_file import tool as write_file_tool
from klaude.tools.git import (
    git_status_tool,
    git_diff_tool,
    git_log_tool,
    git_commit_tool,
)
from klaude.tools.task_list import tool as task_list_tool
from klaude.tools.sub_agent import (
    tool as sub_agent_tool,
    set_client as set_sub_agent_client,
)
from klaude.tools.team import (
    team_create_tool,
    team_delegate_tool,
    team_message_tool,
    set_client as set_team_client,
)
from klaude.tools.web_fetch import tool as web_fetch_tool
from klaude.tools.web_search import tool as web_search_tool
from klaude.tools.ask_user import (
    tool as ask_user_tool,
    set_console as set_ask_user_console,
)
from klaude.tools.lsp import tool as lsp_tool
from klaude.tools.notebook_edit import tool as notebook_edit_tool
from klaude.tools.background_task import tool as background_task_tool
from klaude.tools.worktree import tool as worktree_tool

# Maximum iterations per turn to prevent infinite loops (safety valve)
MAX_ITERATIONS = 50


def _is_git_repo() -> bool:
    """Check if the current directory is inside a git repository."""
    path = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(path, ".git")):
            return True
        parent = os.path.dirname(path)
        if parent == path:
            return False
        path = parent


def _select_tool_tiers(context_window: int) -> set[str]:
    """Select which tool tiers to load based on environment and context budget.

    Always loads core. Loads git if in a git repo. Loads extended only
    if the context window is large enough (>16K) to afford the overhead.
    """
    tiers = {"core"}

    if _is_git_repo():
        tiers.add("git")

    # Extended tools add ~1500 tokens of schema overhead.
    # Only load them if we have enough room.
    if context_window > 16384:
        tiers.add("extended")

    return tiers


def create_registry() -> ToolRegistry:
    """Create a registry with all built-in tools."""
    registry = ToolRegistry()
    registry.register(read_file_tool)
    registry.register(write_file_tool)
    registry.register(edit_file_tool)
    registry.register(bash_tool)
    registry.register(glob_tool)
    registry.register(grep_tool)
    registry.register(list_directory_tool)
    registry.register(git_status_tool)
    registry.register(git_diff_tool)
    registry.register(git_log_tool)
    registry.register(git_commit_tool)
    registry.register(task_list_tool)
    registry.register(sub_agent_tool)
    registry.register(web_fetch_tool)
    registry.register(web_search_tool)
    registry.register(ask_user_tool)
    registry.register(lsp_tool)
    registry.register(notebook_edit_tool)
    registry.register(background_task_tool)
    registry.register(worktree_tool)
    registry.register(team_create_tool)
    registry.register(team_delegate_tool)
    registry.register(team_message_tool)
    return registry


class Session:
    """A conversation session — persists state across multiple turns.

    In one-shot mode: one session, one turn.
    In REPL mode: one session, many turns (history accumulates).
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        context_window: int = 0,
        console: Console | None = None,
        auto_approve: bool = False,
        max_tokens: int = 0,
        config: KlaudeConfig | None = None,
        quiet: bool = False,
        model_name: str = "",
    ) -> None:
        self.config = config or KlaudeConfig()
        self.client = client or LLMClient()
        self.console = console or Console()
        self.quiet = quiet
        set_sub_agent_client(self.client)  # share client with sub-agents
        set_team_client(self.client)  # share client with team agents
        set_ask_user_console(self.console)  # share console with ask_user tool
        self.registry = create_registry()

        # Load custom tool plugins from .klaude/tools/
        for plugin_tool in load_plugin_tools(self.config.tools_dir):
            self.registry.register(plugin_tool, is_plugin=True)
            if not self.quiet:
                self.console.print(f"[dim]Loaded plugin tool: {plugin_tool.name}[/dim]")

        # Connect to MCP servers (if configured)
        self._mcp_bridge: MCPBridge | None = None
        if self.config.mcp_servers:
            self._mcp_bridge = MCPBridge()
            mcp_tools = self._mcp_bridge.connect_all(self.config.mcp_servers)
            for mcp_tool in mcp_tools:
                self.registry.register(mcp_tool, is_plugin=True)
                if not self.quiet:
                    self.console.print(f"[dim]MCP tool: {mcp_tool.name}[/dim]")
            if self._mcp_bridge.server_names and not self.quiet:
                self.console.print(
                    f"[dim]Connected to MCP servers: {', '.join(self._mcp_bridge.server_names)}[/dim]"
                )

        # --- Context window resolution ---
        # Priority: explicit arg > auto-detect from server > config file > default
        effective_window = context_window
        if effective_window == 0:
            effective_window = self.config.context_window

        detected = self.client.detect_context_window()
        if detected:
            # Server reports its actual capacity — use the smaller value
            if detected < effective_window:
                if not self.quiet:
                    self.console.print(
                        f"[dim]Server context: {detected:,} tokens "
                        f"(config: {effective_window:,}, using server value)[/dim]"
                    )
                effective_window = detected
            else:
                if not self.quiet:
                    self.console.print(
                        f"[dim]Server context: {detected:,} tokens[/dim]"
                    )

        # --- Dynamic tool loading ---
        self._tool_tiers = _select_tool_tiers(effective_window)
        self.tool_schemas = self.registry.get_schemas(tiers=self._tool_tiers)

        tier_names = ", ".join(sorted(self._tool_tiers))
        schema_count = len(self.tool_schemas)
        if not self.quiet:
            self.console.print(
                f"[dim]Tools: {schema_count} loaded (tiers: {tier_names})[/dim]"
            )

        # --- Context tracker with optional exact tokenization ---
        self.tracker = ContextTracker(context_window=effective_window)
        self.tracker.set_client(self.client)
        self.tracker.set_tool_overhead(self.tool_schemas)
        self.history = MessageHistory(SYSTEM_PROMPT)
        self.permissions = PermissionManager(
            console=self.console, auto_approve=auto_approve
        )
        self.max_tokens = max_tokens
        self.turn_count = 0
        self.total_tool_calls = 0

        # Skills (reusable prompt templates)
        self.skills: dict[str, Skill] = load_all_skills(self.config.skills_dir)

        # Persistent status bar (caller must .start()/.stop())
        self.status_bar = StatusBar(quiet=self.quiet)

        # ATIF trace writer (initialized when session dir is known)
        self.model_name = model_name
        self.trace: TraceWriter | None = None

        # Undo snapshots: list of (turn_count, history_messages_copy)
        self._snapshots: list[tuple[int, list[dict]]] = []
        self._undo_depth = self.config.undo_depth

    def snapshot(self) -> None:
        """Save a snapshot of the current state for undo."""
        snap = (self.turn_count, copy.deepcopy(self.history.messages))
        self._snapshots.append(snap)
        if len(self._snapshots) > self._undo_depth:
            self._snapshots.pop(0)

    def undo(self) -> bool:
        """Restore the previous snapshot. Returns True if successful."""
        if not self._snapshots:
            return False
        turn_count, messages = self._snapshots.pop()
        self.turn_count = turn_count
        self.history._messages = messages
        self.tracker.update(self.history.messages)
        return True

    @property
    def can_undo(self) -> bool:
        """Whether there's a snapshot to undo to."""
        return len(self._snapshots) > 0

    def restore(self, saved_messages: list[dict], turn_count: int) -> None:
        """Restore a previous session's conversation history.

        The saved_messages should NOT include the system prompt (index 0) —
        that's already set up by __init__.  This just appends the old
        user/assistant/tool exchanges and resets the turn counter.
        """
        for msg in saved_messages:
            self.history._messages.append(msg)
        self.turn_count = turn_count
        self.tracker.update(self.history.messages)

    def turn(self, user_message: str) -> str:
        """Process one user message through the agentic loop.

        This is the core loop:
        1. Save snapshot for undo
        2. Add user message to history
        3. Call LLM (streaming)
        4. If tool calls → execute them, feed results back, repeat
        5. If just text → return it

        Returns the final text response from the LLM.
        """
        # Save state before this turn (for undo)
        self.snapshot()
        self.turn_count += 1
        self.history.add_user(user_message)
        if self.trace:
            self.trace.write_user_step(user_message)

        for iteration in range(MAX_ITERATIONS):
            # Update context tracker before each LLM call
            self.tracker.update(self.history.messages)

            # Token budget check
            if self.max_tokens > 0 and self.tracker.total_tokens > self.max_tokens:
                if not self.quiet:
                    self.console.print(
                        f"\n[red]Token budget exceeded: "
                        f"{self.tracker.total_tokens:,} / {self.max_tokens:,}[/red]"
                    )
                return "Stopped: token budget exceeded."

            self.status_bar.update(self.tracker.format_compact(self.turn_count))

            # --- LLM call with error recovery ---
            try:
                stream = self.client.chat_stream(
                    self.history.messages, tools=self.tool_schemas
                )
            except (APIConnectionError, APITimeoutError, InternalServerError) as e:
                if not self.quiet:
                    self.console.print(
                        f"\n[red]LLM API error (after retries): {e}[/red]"
                    )
                return f"Stopped: LLM API error — {e}"

            # consume_stream prints text tokens as they arrive and
            # accumulates tool call fragments into complete tool calls
            result = consume_stream(stream, print_text=True, quiet=self.quiet)

            # --- Case 1: No tool calls → LLM is done ---
            if not result.has_tool_calls:
                self.history.add_assistant(result.to_message_dict())
                if self.trace:
                    self.trace.write_agent_step(
                        result.content,
                        tool_calls=None,
                    )
                self.tracker.update(self.history.messages)
                self.status_bar.update(self.tracker.format_compact(self.turn_count))
                if not self.quiet:
                    self.console.print()  # blank line after response
                return result.content

            # --- Case 2: Tool calls → execute and continue ---
            self.history.add_assistant(result.to_message_dict())
            if self.trace:
                self.trace.write_agent_step(
                    result.content or None,
                    tool_calls=result.to_message_dict().get("tool_calls"),
                )

            for tc in result.tool_calls:
                self.total_tool_calls += 1
                if not self.quiet:
                    self.console.print(
                        f"  [yellow]Tool:[/yellow] {tc.name}"
                        f"  [dim]{_truncate(tc.arguments, 100)}[/dim]"
                    )

                # --- Safety checks ---
                # 1. Hard blocks (denylist, path sandbox)
                denial = self.permissions.check_tool(tc.name, tc.arguments)
                if denial:
                    tool_result = f"Error: {denial}"
                    if not self.quiet:
                        self.console.print(f"  [red]Blocked:[/red] {denial}")
                # 2. Permission prompt for dangerous tools
                elif not self.permissions.prompt_permission(tc.name, tc.arguments):
                    tool_result = "Error: permission denied by user"
                    if not self.quiet:
                        self.console.print("  [yellow]Denied by user.[/yellow]")
                # 3. Execute (with hooks and structured error recovery)
                else:
                    # Pre-tool hook
                    run_hook(self.config.pre_tool, tc.name, tc.arguments)
                    tool_result = self.registry.execute(tc.name, tc.arguments)
                    # Post-tool hook
                    run_hook(self.config.post_tool, tc.name, tc.arguments)

                    is_error = tool_result.startswith("Error")
                    if is_error:
                        if not self.quiet:
                            self.console.print(
                                f"  [red]Error:[/red] [dim]{_truncate(tool_result, 200)}[/dim]"
                            )
                    else:
                        if not self.quiet:
                            self.console.print(
                                f"  [green]Result:[/green] [dim]{_truncate(tool_result, 200)}[/dim]"
                            )

                self.history.add_tool_result(tc.id, tool_result)
                if self.trace:
                    self.trace.write_tool_result_step(tc.id, tool_result)

            # --- Context compaction ---
            if compact(self.history, self.tracker, self.client):
                if not self.quiet:
                    self.console.print(
                        "[dim italic]  (compacted conversation history)[/dim italic]"
                    )

        # Hit MAX_ITERATIONS
        self.tracker.update(self.history.messages)
        self.status_bar.update(self.tracker.format_compact(self.turn_count))
        if not self.quiet:
            self.console.print("[red]Warning: hit maximum iterations, stopping.[/red]")
        return "Stopped: exceeded maximum iterations."


def run(
    user_message: str,
    client: LLMClient | None = None,
    context_window: int = 0,
) -> str:
    """One-shot convenience function: create a session, run one turn, return."""
    session = Session(client=client, context_window=context_window)
    return session.turn(user_message)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text for display, replacing newlines with spaces."""
    flat = text.replace("\n", " ")
    if len(flat) > max_len:
        return flat[:max_len] + "..."
    return flat
