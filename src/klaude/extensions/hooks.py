"""Hooks — run shell commands before/after tool execution.

Hooks are configured in .klaude.toml:

    [hooks]
    pre_tool = "echo 'Running: {tool_name} {arguments}'"
    post_tool = ""

The hook string is a shell command. Placeholders:
    {tool_name}  — name of the tool being called
    {arguments}  — JSON string of arguments

If the hook command is empty, it's skipped (disabled).
If the hook fails (non-zero exit), a warning is printed but execution continues.

See Note 29 in docs/07-implementation-notes.md.
"""

import subprocess


HOOK_TIMEOUT = 5  # seconds


def run_hook(hook_cmd: str, tool_name: str, arguments: str) -> None:
    """Run a hook shell command. No-op if hook_cmd is empty."""
    if not hook_cmd:
        return

    # Substitute placeholders
    cmd = hook_cmd.replace("{tool_name}", tool_name)
    cmd = cmd.replace("{arguments}", arguments.replace('"', '\\"'))

    try:
        subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        pass  # don't block the main loop for a slow hook
    except Exception:
        pass  # hooks are best-effort, never crash the main loop
