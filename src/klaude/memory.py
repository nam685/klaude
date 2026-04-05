"""Long-term memory — persists important context across sessions.

The problem: every time klaude starts a new conversation, it forgets
everything from the last one. It doesn't know the project structure,
conventions, or what you've been working on.

The solution: a KLAUDE.md file in the project directory (like Claude Code's
CLAUDE.md). This file is loaded into the system prompt at startup, giving
the LLM persistent context about the project.

Memory is read-only for now — the LLM reads it but doesn't write to it.
The user maintains it manually. A future improvement could let the LLM
update memory via a tool.
"""

import os
from pathlib import Path

# Default memory file name (mirrors Claude Code's CLAUDE.md convention)
MEMORY_FILE = "KLAUDE.md"

# Max memory file size to load (prevent accidentally huge files from
# blowing up the context window)
MAX_MEMORY_BYTES = 8192


def find_memory_file(start_dir: str | None = None) -> Path | None:
    """Find the KLAUDE.md file, searching from start_dir upward.

    Looks in the given directory first, then walks up to the root.
    This means a KLAUDE.md in a subdirectory overrides a parent one,
    and a project root KLAUDE.md is always found regardless of cwd.

    Returns the Path if found, None otherwise.
    """
    current = Path(start_dir or os.getcwd()).resolve()

    while True:
        candidate = current / MEMORY_FILE
        try:
            if candidate.is_file():
                return candidate
        except PermissionError:
            pass
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def load_memory(start_dir: str | None = None) -> str:
    """Load the KLAUDE.md memory file contents.

    Returns the file contents as a string, or empty string if not found.
    Truncates to MAX_MEMORY_BYTES to prevent context window blowup.
    """
    path = find_memory_file(start_dir)
    if path is None:
        return ""

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

    if len(content) > MAX_MEMORY_BYTES:
        content = content[:MAX_MEMORY_BYTES] + "\n... (truncated)"

    return content


def build_memory_section(memory: str) -> str:
    """Format memory content as a system prompt section.

    Returns an empty string if there's no memory to include.
    """
    if not memory.strip():
        return ""

    return f"""
# Project memory (from KLAUDE.md)

The following is persistent context about this project, maintained by the user.
Use this information to understand the project and follow its conventions.

{memory}"""
