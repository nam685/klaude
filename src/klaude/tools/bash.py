"""bash tool — executes a shell command and returns stdout/stderr."""

import subprocess

from klaude.tools.registry import Tool

TIMEOUT_SECONDS = 30


def handle_bash(command: str) -> str:
    """Execute a bash command and return its output."""
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"Error executing command: {e}"


tool = Tool(
    name="bash",
    description="Execute a bash command and return its stdout and stderr. Commands time out after 30 seconds.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute",
            }
        },
        "required": ["command"],
    },
    handler=handle_bash,
)
