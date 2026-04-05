"""Session persistence — save/load conversation history as ATIF v1.4.

Saves conversations to .klaude/sessions/{id}.json on exit using ATIF format.
Keeps the last MAX_SESSIONS conversations. Each session stores the full
trajectory as ATIF steps, converted to chat messages on resume.

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

from klaude.core.trace import TraceWriter

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


def save_session(
    messages: list[dict[str, Any]],
    turn_count: int,
    session_id: str | None = None,
    session_dir: Path | None = None,
    model_name: str = "",
) -> str:
    """Save session state as ATIF v1.4. Returns the session ID.

    Converts chat messages to ATIF steps, writes the trajectory,
    and prunes old sessions beyond MAX_SESSIONS.
    """
    if session_id is None:
        session_id = time.strftime("%Y%m%d-%H%M%S")

    sessions = _sessions_dir(session_dir)
    path = sessions / f"{session_id}.json"

    tw = TraceWriter(path, model_name=model_name)

    # Convert chat messages to ATIF steps (skip system prompt at index 0)
    for msg in messages[1:]:
        role = msg.get("role")
        if role == "user":
            tw.write_user_step(msg["content"])
        elif role == "assistant":
            tw.write_agent_step(
                msg.get("content"),
                tool_calls=msg.get("tool_calls"),
            )
        elif role == "tool":
            tw.write_tool_result_step(
                msg["tool_call_id"],
                msg.get("content", ""),
            )

    tw.finalize()
    _prune_old_sessions(sessions)
    return session_id


def _prune_old_sessions(sessions_dir: Path) -> None:
    """Remove sessions beyond MAX_SESSIONS (oldest first)."""
    files = sorted(sessions_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
    while len(files) > MAX_SESSIONS:
        files.pop(0).unlink()


def list_sessions(session_dir: Path | None = None) -> list[dict[str, Any]]:
    """List saved sessions (most recent first).

    Returns list of dicts with: id, saved_at, turn_count, summary.
    """
    if session_dir is not None:
        sessions_path = Path(session_dir)
    else:
        sessions_path = Path(os.getcwd()) / SESSIONS_DIR
    if not sessions_path.exists():
        return []

    result = []
    for f in sorted(sessions_path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            steps = data.get("steps", [])
            turn_count = sum(1 for s in steps if s["source"] == "user")
            # Summary from first user step
            summary = "(empty session)"
            for s in steps:
                if s["source"] == "user":
                    summary = (s.get("message") or "")[:80]
                    break
            result.append({
                "id": data.get("session_id", f.stem),
                "saved_at": steps[-1]["timestamp"] if steps else "",
                "turn_count": turn_count,
                "summary": summary,
                "message_count": len(steps),
            })
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    return result


def load_session(
    session_id: str | None = None,
    session_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], int, str, str] | None:
    """Load a session by ID, or the most recent if ID is None.

    Returns (messages_without_system_prompt, turn_count, saved_at, session_id) or None.
    """
    if session_dir is not None:
        sessions_path = Path(session_dir)
    else:
        sessions_path = Path(os.getcwd()) / SESSIONS_DIR
    if not sessions_path.exists():
        return None

    if session_id:
        session_file = sessions_path / f"{session_id}.json"
    else:
        files = sorted(sessions_path.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not files:
            return None
        session_file = files[-1]

    if not session_file.exists():
        return None

    try:
        msgs, turn_count = TraceWriter.load(session_file)
        data = json.loads(session_file.read_text())
        steps = data.get("steps", [])
        saved_at = steps[-1]["timestamp"] if steps else ""
        sid = data.get("session_id", session_file.stem)
        return (msgs, turn_count, saved_at, sid)
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
            f"{s.get('message_count', 0)} steps — {s['summary']}"
        )
    lines.append("")
    lines.append("Resume with: klaude -c  (latest) or klaude -c <id>")
    return "\n".join(lines)
