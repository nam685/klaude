"""Session persistence — save/load conversation history across sessions.

Saves conversations to .klaude/sessions/{id}.json on exit.
Keeps the last MAX_SESSIONS conversations. Each session stores full
message history so it can be resumed exactly where it left off.

Usage:
    klaude -c              resume most recent session
    klaude -c <id>         resume a specific session
    /sessions              list saved sessions (in REPL)
"""

import json
import os
import time
from pathlib import Path
from typing import Any

SESSIONS_DIR = ".klaude/sessions"
MAX_SESSIONS = 10


def _sessions_dir(session_dir: Path | None = None) -> Path:
    """Get the sessions directory, creating it if needed."""
    if session_dir is not None:
        path = Path(session_dir)
    else:
        path = Path(os.getcwd()) / SESSIONS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extract_summary(messages: list[dict[str, Any]]) -> str:
    """Extract a short summary from the first user message."""
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("content", "")
            # First line, truncated
            line = text.split("\n")[0][:80]
            return line
    return "(empty session)"


def save_session(
    messages: list[dict[str, Any]],
    turn_count: int,
    session_id: str | None = None,
    session_dir: Path | None = None,
) -> str:
    """Save session state. Returns the session ID.

    Skips the system prompt (index 0) since it's regenerated on resume.
    Prunes old sessions beyond MAX_SESSIONS.
    """
    if session_id is None:
        session_id = time.strftime("%Y%m%d-%H%M%S")

    sessions = _sessions_dir(session_dir)
    non_system = messages[1:]  # skip system prompt

    data = {
        "id": session_id,
        "cwd": os.getcwd(),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "turn_count": turn_count,
        "summary": _extract_summary(non_system),
        "message_count": len(non_system),
        "messages": non_system,
    }

    session_file = sessions / f"{session_id}.json"
    session_file.write_text(json.dumps(data, indent=2))

    _prune_old_sessions(sessions)
    return session_id


def _prune_old_sessions(sessions_dir: Path) -> None:
    """Remove sessions beyond MAX_SESSIONS (oldest first)."""
    files = sorted(sessions_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
    while len(files) > MAX_SESSIONS:
        files.pop(0).unlink()


def list_sessions() -> list[dict[str, Any]]:
    """List saved sessions (most recent first).

    Returns list of dicts with: id, saved_at, turn_count, summary, message_count.
    """
    sessions_dir = Path(os.getcwd()) / SESSIONS_DIR
    if not sessions_dir.exists():
        return []

    result = []
    for f in sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            result.append({
                "id": data["id"],
                "saved_at": data.get("saved_at", ""),
                "turn_count": data.get("turn_count", 0),
                "summary": data.get("summary", ""),
                "message_count": data.get("message_count", 0),
            })
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    return result


def load_session(session_id: str | None = None, session_dir: Path | None = None) -> tuple[list[dict[str, Any]], int, str, str] | None:
    """Load a session by ID, or the most recent if ID is None.

    Returns (messages_without_system_prompt, turn_count, saved_at, session_id) or None.
    """
    if session_dir is not None:
        sessions_dir = Path(session_dir)
    else:
        sessions_dir = Path(os.getcwd()) / SESSIONS_DIR
    if not sessions_dir.exists():
        return None

    if session_id:
        session_file = sessions_dir / f"{session_id}.json"
    else:
        # Most recent
        files = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not files:
            return None
        session_file = files[-1]

    if not session_file.exists():
        return None

    try:
        data = json.loads(session_file.read_text())
        return (
            data["messages"],
            data["turn_count"],
            data.get("saved_at", ""),
            data["id"],
        )
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def format_session_list(sessions: list[dict[str, Any]]) -> str:
    """Format the session list for display."""
    if not sessions:
        return "No saved sessions."

    lines = ["Saved sessions (most recent first):", ""]
    for i, s in enumerate(sessions):
        marker = " *" if i == 0 else "  "
        lines.append(
            f"{marker} {s['id']}  {s['turn_count']} turns, "
            f"{s['message_count']} msgs — {s['summary']}"
        )
    lines.append("")
    lines.append("Resume with: klaude -c  (latest) or klaude -c <id>")
    return "\n".join(lines)
