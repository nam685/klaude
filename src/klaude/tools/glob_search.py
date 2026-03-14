"""glob tool — find files matching a pattern."""

from pathlib import Path

from klaude.tools.registry import Tool


def handle_glob(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern under a directory."""
    base = Path(path).resolve()
    if not base.exists():
        return f"Error: directory not found: {path}"
    if not base.is_dir():
        return f"Error: not a directory: {path}"

    try:
        matches = sorted(base.glob(pattern))
        if not matches:
            return f"No files matched pattern '{pattern}' in {base}"

        # Return relative paths for readability, absolute for unambiguity
        lines = []
        for m in matches[:200]:  # cap at 200 to avoid overwhelming the LLM
            try:
                lines.append(str(m.relative_to(base)))
            except ValueError:
                lines.append(str(m))

        result = "\n".join(lines)
        if len(matches) > 200:
            result += f"\n... and {len(matches) - 200} more files"
        return result
    except Exception as e:
        return f"Error searching for '{pattern}': {e}"


tool = Tool(
    name="glob",
    description="Find files matching a glob pattern (e.g. **/*.py).",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)",
            },
        },
        "required": ["pattern"],
    },
    handler=handle_glob,
)
