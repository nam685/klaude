"""write_file tool — creates or overwrites a file with given contents."""

from pathlib import Path

from klaude.tools.registry import Tool


def handle_write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed."""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


tool = Tool(
    name="write_file",
    description="Write content to a file at the given path. Creates the file if it doesn't exist, overwrites if it does. Creates parent directories as needed.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["path", "content"],
    },
    handler=handle_write_file,
)
