"""list_directory tool — list files and directories at a path."""

from pathlib import Path

from klaude.tools.registry import Tool


def handle_list_directory(path: str = ".") -> str:
    """List the contents of a directory."""
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: path not found: {path}"
    if not p.is_dir():
        return f"Error: not a directory: {path}"

    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        if not entries:
            return f"(empty directory: {path})"

        lines: list[str] = []
        for entry in entries[:500]:  # cap to avoid overwhelming the LLM
            if entry.is_dir():
                lines.append(f"  {entry.name}/")
            else:
                # Show file size for context
                try:
                    size = entry.stat().st_size
                    lines.append(f"  {entry.name}  ({_human_size(size)})")
                except OSError:
                    lines.append(f"  {entry.name}")

        result = f"{p}/\n" + "\n".join(lines)
        if len(entries) > 500:
            result += f"\n  ... and {len(entries) - 500} more entries"
        return result
    except PermissionError:
        return f"Error: permission denied: {path}"
    except Exception as e:
        return f"Error listing {path}: {e}"


def _human_size(size: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


tool = Tool(
    name="list_directory",
    description="List the contents of a directory. Shows files with sizes and directories with trailing /. Directories are listed first.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the directory to list (default: current directory)",
            }
        },
        "required": [],
    },
    handler=handle_list_directory,
)
