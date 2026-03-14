"""Permission system — ask before destructive tool calls.

Like Claude Code, klaude classifies tools into safety tiers:

- SAFE: read-only operations (read_file, glob, grep, list_directory)
  → always allowed, no confirmation needed
- DANGEROUS: write/execute operations (bash, write_file, edit_file)
  → requires user confirmation before execution

The permission check happens in the agentic loop, between the LLM
deciding to call a tool and actually executing it. If the user denies,
the tool result is "Permission denied" and the LLM can try a different approach.

Additional safety layers (checked before the permission prompt):
- Command denylist: certain bash commands are always blocked
- Path sandboxing: file operations restricted to the working directory
"""

import json
import os
import re
from difflib import unified_diff
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax

# --- Tool classification ---

SAFE_TOOLS = {"read_file", "glob", "grep", "list_directory", "git_status", "git_diff", "git_log", "task_list", "sub_agent", "web_fetch"}
DANGEROUS_TOOLS = {"bash", "write_file", "edit_file", "git_commit"}

# --- Command denylist (always blocked, even with user approval) ---

DENIED_COMMANDS = [
    re.compile(r"\brm\s+(-\w*f\w*\s+)*\s*/\s*$"),      # rm -rf /
    re.compile(r"\brm\s+(-\w*f\w*\s+)*\s*/\w"),          # rm -rf /etc, /home, etc.
    re.compile(r"\bsudo\b"),                               # any sudo
    re.compile(r"\bchmod\s+777\b"),                        # chmod 777
    re.compile(r"\bmkfs\b"),                               # format filesystem
    re.compile(r"\bdd\s+.*of=/dev/"),                      # dd to device
    re.compile(r">\s*/dev/sd[a-z]"),                       # write to raw device
    re.compile(r"\bcurl\b.*\|\s*\bbash\b"),                # curl | bash (pipe to shell)
    re.compile(r"\bwget\b.*\|\s*\bbash\b"),                # wget | bash
]

# --- Path sandboxing ---

BLOCKED_PATHS = [
    Path.home() / ".ssh",
    Path.home() / ".gnupg",
    Path.home() / ".aws",
    Path.home() / ".env",
    Path.home() / ".netrc",
    Path.home() / ".kube",
    Path("/etc/shadow"),
    Path("/etc/passwd"),
]


def is_command_denied(command: str) -> str | None:
    """Check if a bash command matches the denylist.

    Returns a reason string if denied, None if allowed.
    """
    for pattern in DENIED_COMMANDS:
        if pattern.search(command):
            return f"Blocked: matches safety rule ({pattern.pattern})"
    return None


def is_path_allowed(path_str: str, working_dir: str | None = None) -> str | None:
    """Check if a file path is within the allowed sandbox.

    Returns a reason string if blocked, None if allowed.

    Rules:
    1. Must be within the working directory (or below it)
    2. Must not be in the blocked paths list
    """
    try:
        path = Path(path_str).resolve()
    except (ValueError, OSError):
        return f"Invalid path: {path_str}"

    # Check blocked paths
    for blocked in BLOCKED_PATHS:
        blocked_resolved = blocked.resolve()
        if path == blocked_resolved or blocked_resolved in path.parents:
            return f"Blocked: access to {blocked} is not allowed"

    # Check sandbox (must be within working directory)
    cwd = Path(working_dir or os.getcwd()).resolve()
    if cwd not in path.parents and path != cwd:
        return f"Blocked: {path} is outside the working directory ({cwd})"

    return None


def format_diff(path: str, old_string: str, new_string: str) -> str:
    """Generate a colored diff for edit_file operations."""
    old_lines = old_string.splitlines(keepends=True)
    new_lines = new_string.splitlines(keepends=True)

    diff = unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{Path(path).name}",
        tofile=f"b/{Path(path).name}",
    )
    return "".join(diff)


class PermissionManager:
    """Manages tool execution permissions.

    Modes:
    - interactive (default): prompts user for dangerous operations
    - auto_approve: skips prompts (for testing or trusted contexts)
    """

    def __init__(
        self,
        console: Console,
        auto_approve: bool = False,
        working_dir: str | None = None,
    ) -> None:
        self.console = console
        self.auto_approve = auto_approve
        self.working_dir = working_dir or os.getcwd()

    def check_tool(self, tool_name: str, arguments_json: str) -> str | None:
        """Check if a tool call is allowed.

        Returns None if allowed, or an error message string if denied.
        This runs BEFORE execution and BEFORE the user prompt.

        Checks (in order):
        1. Command denylist (bash)
        2. Path sandboxing (file tools)
        """
        try:
            args = json.loads(arguments_json)
        except json.JSONDecodeError:
            return None  # let the registry handle bad JSON

        # --- Bash denylist ---
        if tool_name == "bash":
            command = args.get("command", "")
            denial = is_command_denied(command)
            if denial:
                return denial

        # --- Path sandboxing for file tools ---
        if tool_name in ("read_file", "write_file", "edit_file"):
            path = args.get("path", "")
            if path:
                denial = is_path_allowed(path, self.working_dir)
                if denial:
                    return denial

        return None

    def prompt_permission(self, tool_name: str, arguments_json: str) -> bool:
        """Ask the user for permission to execute a dangerous tool.

        Returns True if approved, False if denied.
        """
        if tool_name in SAFE_TOOLS:
            return True

        if self.auto_approve:
            return True

        try:
            args = json.loads(arguments_json)
        except json.JSONDecodeError:
            args = {}

        # Show what's about to happen
        self.console.print()
        self.console.print(f"  [bold yellow]Permission required:[/bold yellow] {tool_name}")

        if tool_name == "bash":
            command = args.get("command", "")
            self.console.print(f"  [dim]Command:[/dim] {command}")

        elif tool_name == "write_file":
            path = args.get("path", "")
            content = args.get("content", "")
            self.console.print(f"  [dim]File:[/dim] {path}")
            self.console.print(f"  [dim]Size:[/dim] {len(content)} bytes")

        elif tool_name == "edit_file":
            path = args.get("path", "")
            old_string = args.get("old_string", "")
            new_string = args.get("new_string", "")
            self.console.print(f"  [dim]File:[/dim] {path}")

            # Show diff
            diff_text = format_diff(path, old_string, new_string)
            if diff_text:
                syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
                self.console.print(syntax)

        elif tool_name == "git_commit":
            message = args.get("message", "")
            files = args.get("files", ["."])
            self.console.print(f"  [dim]Message:[/dim] {message}")
            self.console.print(f"  [dim]Files:[/dim] {', '.join(files)}")

        # Prompt
        try:
            response = input("  Allow? [y/n] ").strip().lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return False
