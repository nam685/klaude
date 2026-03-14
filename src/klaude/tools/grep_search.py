"""grep tool — search file contents for a pattern."""

import os
import re
from pathlib import Path

from klaude.tools.registry import Tool

# Skip binary files and common non-text directories
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", "venv"}
MAX_RESULTS = 100


def handle_grep(pattern: str, path: str = ".", include: str = "") -> str:
    """Search for a text/regex pattern in files under a directory."""
    base = Path(path).resolve()
    if not base.exists():
        return f"Error: path not found: {path}"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex '{pattern}': {e}"

    matches: list[str] = []

    # If path is a single file, just search that file
    if base.is_file():
        matches.extend(_search_file(base, regex, base.parent))
        return _format_results(matches, pattern)

    # Walk directory tree
    for root, dirs, files in os.walk(base):
        # Skip hidden/build directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        for fname in files:
            # Apply include filter if specified
            if include and not Path(fname).match(include):
                continue

            filepath = Path(root) / fname
            matches.extend(_search_file(filepath, regex, base))

            if len(matches) >= MAX_RESULTS:
                matches.append(f"... (stopped at {MAX_RESULTS} results)")
                return _format_results(matches, pattern)

    return _format_results(matches, pattern)


def _search_file(filepath: Path, regex: re.Pattern, base: Path) -> list[str]:
    """Search a single file, returning matching lines with context."""
    results: list[str] = []
    try:
        text = filepath.read_text(errors="ignore")
    except (OSError, PermissionError):
        return results

    try:
        relpath = filepath.relative_to(base)
    except ValueError:
        relpath = filepath

    for i, line in enumerate(text.splitlines(), 1):
        if regex.search(line):
            results.append(f"{relpath}:{i}: {line.rstrip()}")
    return results


def _format_results(matches: list[str], pattern: str) -> str:
    """Format grep results."""
    if not matches:
        return f"No matches found for '{pattern}'"
    return "\n".join(matches)


tool = Tool(
    name="grep",
    description="Search for a text pattern (regex) in files. Returns matching lines with file paths and line numbers. Skips binary files, .git, node_modules, __pycache__, and .venv directories.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search in (default: current directory)",
            },
            "include": {
                "type": "string",
                "description": "Only search files matching this glob (e.g., '*.py', '*.ts')",
            },
        },
        "required": ["pattern"],
    },
    handler=handle_grep,
)
