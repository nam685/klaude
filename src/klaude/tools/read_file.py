"""read_file tool — reads a file and returns its contents."""

from pathlib import Path

from klaude.tools.registry import Tool


def handle_read_file(path: str) -> str:
    """Read the contents of a file at the given path."""
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"
    try:
        return p.read_text()
    except Exception as e:
        return f"Error reading {path}: {e}"


tool = Tool(
    name="read_file",
    description="Read file contents at the given path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
            }
        },
        "required": ["path"],
    },
    handler=handle_read_file,
)
