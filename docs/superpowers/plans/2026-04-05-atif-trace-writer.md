# ATIF Trace Writer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace klaude's raw chat JSON session format with ATIF v1.4 — written incrementally during execution so external consumers can poll for live progress.

**Architecture:** New `TraceWriter` class in `src/klaude/core/trace.py` owns the ATIF document in memory and rewrites the full JSON file after each step. The agentic loop (`loop.py`) calls TraceWriter at 4 insertion points. Session store (`session_store.py`) delegates to TraceWriter for save/load, with a conversion layer from ATIF steps to OpenAI chat messages for session resume.

**Tech Stack:** Python 3.11+, pytest, json, pathlib, tempfile (for atomic writes)

**Spec:** `docs/superpowers/specs/2026-04-05-atif-trace-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/klaude/core/trace.py` | Create | TraceWriter class — ATIF document management, step writing, atomic flush, ATIF↔chat conversion |
| `src/klaude/core/loop.py` | Modify | Create TraceWriter in Session.__init__, call it at 4 points in Session.turn() |
| `src/klaude/core/session_store.py` | Modify | Delegate save/load to TraceWriter, read ATIF format |
| `src/klaude/ui/cli.py` | Modify | Pass model_name to Session for ATIF agent block |
| `tests/test_trace.py` | Create | Tests for TraceWriter (write, flush, load, conversion) |
| `tests/test_session_store.py` | Modify | Update existing tests for ATIF format |

---

### Task 1: TraceWriter — Core ATIF Document and Step Writing

**Files:**
- Create: `src/klaude/core/trace.py`
- Create: `tests/test_trace.py`

- [ ] **Step 1: Write failing test for TraceWriter initialization**

```python
# tests/test_trace.py
"""Tests for ATIF v1.4 trace writer."""

import json
from pathlib import Path

from klaude.core.trace import TraceWriter


def test_init_creates_atif_document(tmp_path):
    """TraceWriter creates a valid ATIF v1.4 document on first flush."""
    path = tmp_path / "test-session.json"
    tw = TraceWriter(path, model_name="openrouter/auto")
    tw.write_user_step("hello")

    data = json.loads(path.read_text())
    assert data["schema_version"] == "ATIF-v1.4"
    assert data["session_id"] == "test-session"
    assert data["agent"]["name"] == "klaude"
    assert data["agent"]["model_name"] == "openrouter/auto"
    assert len(data["steps"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_trace.py::test_init_creates_atif_document -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'klaude.core.trace'`

- [ ] **Step 3: Implement TraceWriter.__init__ and write_user_step**

```python
# src/klaude/core/trace.py
"""ATIF v1.4 trace writer — incremental trajectory output.

Holds an ATIF document in memory and rewrites the full JSON file
after each step. External consumers (nam-website) poll this file
for live progress during execution.

ATIF spec: https://www.harborframework.com/docs/agents/trajectory-format
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class TraceWriter:
    """Append-only ATIF v1.4 trace writer.

    Usage:
        tw = TraceWriter(Path("session.json"), model_name="openrouter/auto")
        tw.write_user_step("fix the bug")
        tw.write_agent_step("Let me look...", tool_calls=[...])
        tw.write_tool_result_step("call_1", "file contents")
        tw.finalize()
    """

    def __init__(self, path: Path, model_name: str) -> None:
        self._path = path
        self._model_name = model_name
        self._step_counter = 0
        self._doc: dict[str, Any] = {
            "schema_version": "ATIF-v1.4",
            "session_id": path.stem,
            "agent": {
                "name": "klaude",
                "version": "0.1.0",
                "model_name": model_name,
            },
            "steps": [],
        }

    def _next_step_id(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def _timestamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")

    def write_user_step(self, message: str) -> None:
        """Add a user step and flush to disk."""
        self._doc["steps"].append({
            "step_id": self._next_step_id(),
            "timestamp": self._timestamp(),
            "source": "user",
            "message": message,
        })
        self._flush()

    def _flush(self) -> None:
        """Rewrite the full JSON file atomically (write-to-temp + rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=self._path.parent, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._doc, f, indent=2)
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_trace.py::test_init_creates_atif_document -v`
Expected: PASS

- [ ] **Step 5: Write failing test for agent steps**

```python
# tests/test_trace.py (append)

def test_write_agent_step_text_only(tmp_path):
    """Agent step with text content, no tool calls."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("hello")
    tw.write_agent_step("Hi there!", tool_calls=None)

    data = json.loads(path.read_text())
    agent_step = data["steps"][1]
    assert agent_step["step_id"] == 2
    assert agent_step["source"] == "agent"
    assert agent_step["message"] == "Hi there!"
    assert agent_step["model_name"] == "test-model"
    assert "tool_calls" not in agent_step


def test_write_agent_step_with_tool_calls(tmp_path):
    """Agent step with tool calls."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("fix bug")
    tw.write_agent_step(None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "main.py"}'}},
    ])

    data = json.loads(path.read_text())
    agent_step = data["steps"][1]
    assert agent_step["source"] == "agent"
    assert agent_step["message"] is None
    assert len(agent_step["tool_calls"]) == 1
    tc = agent_step["tool_calls"][0]
    assert tc["tool_call_id"] == "call_1"
    assert tc["function_name"] == "read_file"
    assert tc["arguments"] == {"path": "main.py"}
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_trace.py -v -k "agent_step"`
Expected: FAIL — `AttributeError: 'TraceWriter' object has no attribute 'write_agent_step'`

- [ ] **Step 7: Implement write_agent_step**

Add to `TraceWriter` in `src/klaude/core/trace.py`:

```python
    def write_agent_step(self, content: str | None, tool_calls: list[dict] | None) -> None:
        """Add an agent step and flush to disk.

        Args:
            content: Text response (None if tool-call-only).
            tool_calls: OpenAI-format tool calls from StreamResult.to_message_dict().
                        Converted to ATIF format (tool_call_id, function_name, arguments).
        """
        step: dict[str, Any] = {
            "step_id": self._next_step_id(),
            "timestamp": self._timestamp(),
            "source": "agent",
            "message": content,
            "model_name": self._model_name,
        }
        if tool_calls:
            step["tool_calls"] = [
                self._convert_tool_call(tc) for tc in tool_calls
            ]
        self._doc["steps"].append(step)
        self._flush()

    @staticmethod
    def _convert_tool_call(tc: dict) -> dict:
        """Convert OpenAI tool call format to ATIF format."""
        args_raw = tc["function"]["arguments"]
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except (json.JSONDecodeError, TypeError):
            args = {"_raw": args_raw}
        return {
            "tool_call_id": tc["id"],
            "function_name": tc["function"]["name"],
            "arguments": args,
        }
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_trace.py -v -k "agent_step"`
Expected: PASS

- [ ] **Step 9: Write failing test for tool result steps**

```python
# tests/test_trace.py (append)

def test_write_tool_result_step(tmp_path):
    """System step with observation for a tool result."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("fix bug")
    tw.write_agent_step(None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}},
    ])
    tw.write_tool_result_step("call_1", "def main(): pass")

    data = json.loads(path.read_text())
    sys_step = data["steps"][2]
    assert sys_step["step_id"] == 3
    assert sys_step["source"] == "system"
    assert sys_step["message"] == "def main(): pass"
    assert sys_step["observation"]["results"][0]["tool_call_id"] == "call_1"
    assert sys_step["observation"]["results"][0]["content"] == "def main(): pass"
```

- [ ] **Step 10: Run test to verify it fails**

Run: `uv run pytest tests/test_trace.py::test_write_tool_result_step -v`
Expected: FAIL — `AttributeError: 'TraceWriter' object has no attribute 'write_tool_result_step'`

- [ ] **Step 11: Implement write_tool_result_step**

Add to `TraceWriter` in `src/klaude/core/trace.py`:

```python
    def write_tool_result_step(self, tool_call_id: str, content: str) -> None:
        """Add a system/observation step (tool result) and flush to disk."""
        self._doc["steps"].append({
            "step_id": self._next_step_id(),
            "timestamp": self._timestamp(),
            "source": "system",
            "message": content,
            "observation": {
                "results": [{"tool_call_id": tool_call_id, "content": content}],
            },
        })
        self._flush()
```

- [ ] **Step 12: Run test to verify it passes**

Run: `uv run pytest tests/test_trace.py::test_write_tool_result_step -v`
Expected: PASS

- [ ] **Step 13: Write failing test for finalize**

```python
# tests/test_trace.py (append)

def test_finalize_writes_final_metrics(tmp_path):
    """finalize() adds final_metrics to the document."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("hello")
    tw.write_agent_step("hi", tool_calls=None)
    tw.finalize()

    data = json.loads(path.read_text())
    fm = data["final_metrics"]
    assert fm["total_steps"] == 2
    assert fm["total_cost_usd"] == 0
    assert fm["total_prompt_tokens"] == 0
    assert fm["total_completion_tokens"] == 0
    assert fm["total_cached_tokens"] == 0
```

- [ ] **Step 14: Implement finalize**

Add to `TraceWriter` in `src/klaude/core/trace.py`:

```python
    def finalize(self) -> None:
        """Write final_metrics and flush. Called on session exit."""
        self._doc["final_metrics"] = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_cached_tokens": 0,
            "total_cost_usd": 0,
            "total_steps": len(self._doc["steps"]),
        }
        self._flush()
```

- [ ] **Step 15: Run all tests**

Run: `uv run pytest tests/test_trace.py -v`
Expected: All PASS

- [ ] **Step 16: Commit**

```bash
git add src/klaude/core/trace.py tests/test_trace.py
git commit -m "feat: add TraceWriter with ATIF v1.4 step writing"
```

---

### Task 2: TraceWriter — ATIF-to-Chat Conversion and Session Loading

**Files:**
- Modify: `src/klaude/core/trace.py`
- Modify: `tests/test_trace.py`

- [ ] **Step 1: Write failing test for to_chat_messages**

```python
# tests/test_trace.py (append)

def test_to_chat_messages_roundtrip(tmp_path):
    """ATIF steps convert back to OpenAI chat messages."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("fix bug")
    tw.write_agent_step(None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}},
    ])
    tw.write_tool_result_step("call_1", "contents")
    tw.write_agent_step("Done!", tool_calls=None)

    msgs = tw.to_chat_messages()
    assert len(msgs) == 4

    assert msgs[0] == {"role": "user", "content": "fix bug"}

    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] is None
    assert len(msgs[1]["tool_calls"]) == 1
    assert msgs[1]["tool_calls"][0]["id"] == "call_1"
    assert msgs[1]["tool_calls"][0]["type"] == "function"
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "read_file"
    assert msgs[1]["tool_calls"][0]["function"]["arguments"] == '{"path": "x.py"}'

    assert msgs[2] == {"role": "tool", "tool_call_id": "call_1", "content": "contents"}

    assert msgs[3] == {"role": "assistant", "content": "Done!"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_trace.py::test_to_chat_messages_roundtrip -v`
Expected: FAIL — `AttributeError: 'TraceWriter' object has no attribute 'to_chat_messages'`

- [ ] **Step 3: Implement to_chat_messages**

Add to `TraceWriter` in `src/klaude/core/trace.py`:

```python
    def to_chat_messages(self) -> list[dict[str, Any]]:
        """Convert ATIF steps to OpenAI chat message format.

        Used by session resume to reconstruct the message history
        the LLM expects.
        """
        messages: list[dict[str, Any]] = []
        for step in self._doc["steps"]:
            source = step["source"]
            if source == "user":
                messages.append({"role": "user", "content": step["message"]})
            elif source == "agent":
                msg: dict[str, Any] = {"role": "assistant", "content": step.get("message")}
                if step.get("tool_calls"):
                    msg["tool_calls"] = [
                        {
                            "id": tc["tool_call_id"],
                            "type": "function",
                            "function": {
                                "name": tc["function_name"],
                                "arguments": json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else tc["arguments"],
                            },
                        }
                        for tc in step["tool_calls"]
                    ]
                messages.append(msg)
            elif source == "system":
                results = step.get("observation", {}).get("results", [])
                if results:
                    for r in results:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": r["tool_call_id"],
                            "content": r["content"],
                        })
                else:
                    messages.append({"role": "user", "content": step["message"]})
        return messages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_trace.py::test_to_chat_messages_roundtrip -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for load and from_existing**

```python
# tests/test_trace.py (append)

def test_load_returns_chat_messages_and_turn_count(tmp_path):
    """load() reads an ATIF file and returns chat messages + turn count."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("first task")
    tw.write_agent_step("done", tool_calls=None)
    tw.write_user_step("second task")
    tw.write_agent_step("also done", tool_calls=None)
    tw.finalize()

    msgs, turn_count = TraceWriter.load(path)
    assert turn_count == 2  # two user steps = two turns
    assert len(msgs) == 4
    assert msgs[0]["content"] == "first task"
    assert msgs[3]["content"] == "also done"


def test_from_existing_continues_step_counter(tmp_path):
    """from_existing() loads an ATIF file and continues appending steps."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("first task")
    tw.write_agent_step("done", tool_calls=None)

    # Simulate new session picking up the trace
    tw2 = TraceWriter.from_existing(path)
    tw2.write_user_step("second task")
    tw2.write_agent_step("also done", tool_calls=None)

    data = json.loads(path.read_text())
    assert len(data["steps"]) == 4
    assert data["steps"][2]["step_id"] == 3  # continues from 2
    assert data["steps"][2]["source"] == "user"
    assert data["steps"][2]["message"] == "second task"
    assert data["agent"]["model_name"] == "test-model"  # preserved
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_trace.py -v -k "load_returns or from_existing"`
Expected: FAIL — `AttributeError`

- [ ] **Step 7: Implement load and from_existing**

Add to `TraceWriter` in `src/klaude/core/trace.py`:

```python
    @classmethod
    def load(cls, path: Path) -> tuple[list[dict[str, Any]], int]:
        """Load an ATIF file and return (chat_messages, turn_count).

        Used by session resume to reconstruct the conversation.
        turn_count = number of user steps in the trajectory.
        """
        data = json.loads(path.read_text())
        tw = cls.__new__(cls)
        tw._path = path
        tw._model_name = data.get("agent", {}).get("model_name", "")
        tw._doc = data
        tw._step_counter = len(data.get("steps", []))

        turn_count = sum(1 for s in data.get("steps", []) if s["source"] == "user")
        return tw.to_chat_messages(), turn_count

    @classmethod
    def from_existing(cls, path: Path) -> "TraceWriter":
        """Load an existing ATIF file and resume appending steps.

        Used when resuming a session (klaude -c). Preserves existing
        steps and continues the step counter.
        """
        data = json.loads(path.read_text())
        tw = cls.__new__(cls)
        tw._path = path
        tw._model_name = data.get("agent", {}).get("model_name", "")
        tw._doc = data
        tw._step_counter = max(
            (s["step_id"] for s in data.get("steps", [])),
            default=0,
        )
        return tw
```

- [ ] **Step 8: Run all tests**

Run: `uv run pytest tests/test_trace.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/klaude/core/trace.py tests/test_trace.py
git commit -m "feat: add ATIF-to-chat conversion and session loading"
```

---

### Task 3: TraceWriter — Atomic Flush Safety Test

**Files:**
- Modify: `tests/test_trace.py`

- [ ] **Step 1: Write test verifying atomic flush behavior**

```python
# tests/test_trace.py (append)

def test_flush_is_atomic_valid_json_at_all_times(tmp_path):
    """The trace file is always valid JSON — never a partial write."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")

    # After each write, the file should be valid JSON
    tw.write_user_step("step 1")
    data = json.loads(path.read_text())
    assert len(data["steps"]) == 1

    tw.write_agent_step("response", tool_calls=None)
    data = json.loads(path.read_text())
    assert len(data["steps"]) == 2

    tw.write_user_step("step 2")
    data = json.loads(path.read_text())
    assert len(data["steps"]) == 3


def test_no_temp_files_left_after_flush(tmp_path):
    """Atomic flush does not leave .tmp files behind."""
    path = tmp_path / "s.json"
    tw = TraceWriter(path, model_name="test-model")
    tw.write_user_step("hello")
    tw.write_agent_step("hi", tool_calls=None)

    remaining = list(tmp_path.glob("*.tmp"))
    assert remaining == []
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_trace.py -v -k "atomic or temp_files"`
Expected: PASS (these test existing behavior)

- [ ] **Step 3: Commit**

```bash
git add tests/test_trace.py
git commit -m "test: add atomic flush safety tests for TraceWriter"
```

---

### Task 4: Migrate Session Store to ATIF

**Files:**
- Modify: `src/klaude/core/session_store.py`
- Modify: `tests/test_session_store.py`

- [ ] **Step 1: Update test_session_store tests for ATIF format**

Replace the contents of `tests/test_session_store.py`:

```python
"""Test session_store with ATIF format."""

import json
from pathlib import Path

from klaude.core.session_store import save_session, load_session, list_sessions


def test_save_session_writes_atif(tmp_path):
    """save_session writes ATIF v1.4 format."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    sid = save_session(
        messages, turn_count=1, session_id="test-001",
        session_dir=tmp_path, model_name="test-model",
    )
    assert sid == "test-001"

    session_file = tmp_path / "test-001.json"
    assert session_file.exists()

    data = json.loads(session_file.read_text())
    assert data["schema_version"] == "ATIF-v1.4"
    assert data["session_id"] == "test-001"
    assert data["agent"]["model_name"] == "test-model"
    # system prompt is skipped, user + assistant = 2 steps
    assert len(data["steps"]) == 2
    assert data["steps"][0]["source"] == "user"
    assert data["steps"][1]["source"] == "agent"
    assert data["final_metrics"]["total_steps"] == 2


def test_load_session_reads_atif(tmp_path):
    """load_session reads ATIF and returns chat messages."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    save_session(
        messages, turn_count=1, session_id="load-test",
        session_dir=tmp_path, model_name="test-model",
    )
    result = load_session(session_id="load-test", session_dir=tmp_path)
    assert result is not None
    msgs, turns, saved_at, sid = result
    assert sid == "load-test"
    assert turns == 1
    assert len(msgs) == 2  # user + assistant (system skipped)
    assert msgs[0] == {"role": "user", "content": "hello"}
    assert msgs[1] == {"role": "assistant", "content": "hi"}


def test_list_sessions_reads_atif(tmp_path):
    """list_sessions extracts metadata from ATIF files."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "fix the bug"},
        {"role": "assistant", "content": "done"},
    ]
    save_session(
        messages, turn_count=1, session_id="list-test",
        session_dir=tmp_path, model_name="test-model",
    )
    sessions = list_sessions(session_dir=tmp_path)
    assert len(sessions) == 1
    assert sessions[0]["id"] == "list-test"
    assert sessions[0]["turn_count"] == 1
    assert sessions[0]["summary"] == "fix the bug"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_session_store.py -v`
Expected: FAIL — `save_session() got an unexpected keyword argument 'model_name'`

- [ ] **Step 3: Rewrite session_store.py to use TraceWriter**

Replace the contents of `src/klaude/core/session_store.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_session_store.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS. If other tests call `save_session` without `model_name`, they should still pass since it defaults to `""`.

- [ ] **Step 6: Commit**

```bash
git add src/klaude/core/session_store.py tests/test_session_store.py
git commit -m "feat: migrate session store to ATIF v1.4 format"
```

---

### Task 5: Wire TraceWriter into the Agentic Loop

**Files:**
- Modify: `src/klaude/core/loop.py`

- [ ] **Step 1: Add trace_path and model_name to Session.__init__**

In `src/klaude/core/loop.py`, add the import at the top:

```python
from klaude.core.trace import TraceWriter
```

Modify `Session.__init__` signature to accept `model_name`:

```python
    def __init__(
        self,
        client: LLMClient | None = None,
        context_window: int = 0,
        console: Console | None = None,
        auto_approve: bool = False,
        max_tokens: int = 0,
        config: KlaudeConfig | None = None,
        quiet: bool = False,
        model_name: str = "",
    ) -> None:
```

After `self.status_bar = StatusBar(quiet=self.quiet)`, add:

```python
        # ATIF trace writer (initialized when session dir is known)
        self.model_name = model_name
        self.trace: TraceWriter | None = None
```

- [ ] **Step 2: Add trace calls to Session.turn()**

In the `turn()` method of `src/klaude/core/loop.py`, add 4 trace write calls:

After `self.history.add_user(user_message)` (line 278):
```python
        if self.trace:
            self.trace.write_user_step(user_message)
```

After `self.history.add_assistant(result.to_message_dict())` in the no-tool-calls branch (line 315):
```python
                if self.trace:
                    self.trace.write_agent_step(
                        result.content, tool_calls=None,
                    )
```

After `self.history.add_assistant(result.to_message_dict())` in the tool-calls branch (line 325):
```python
            if self.trace:
                self.trace.write_agent_step(
                    result.content or None,
                    tool_calls=result.to_message_dict().get("tool_calls"),
                )
```

After `self.history.add_tool_result(tc.id, tool_result)` (line 367):
```python
                if self.trace:
                    self.trace.write_tool_result_step(tc.id, tool_result)
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS. The trace calls are guarded by `if self.trace:` so existing tests (where trace is None) are unaffected.

- [ ] **Step 4: Commit**

```bash
git add src/klaude/core/loop.py
git commit -m "feat: wire TraceWriter into the agentic loop"
```

---

### Task 6: Wire TraceWriter into CLI

**Files:**
- Modify: `src/klaude/ui/cli.py`

- [ ] **Step 1: Pass model_name to Session and initialize trace**

In `src/klaude/ui/cli.py`, in the `main()` function, modify the `Session()` creation (around line 256) to pass `model_name`:

```python
        session = Session(
            client=client,
            context_window=effective_context_window,
            console=active_console,
            auto_approve=effective_auto_approve,
            max_tokens=effective_max_tokens,
            config=cfg,
            quiet=json_mode,
            model_name=effective_model,
        )
```

After Session creation but before the resume block, initialize the trace writer. Add the import at the top of the file:

```python
from klaude.core.trace import TraceWriter
```

After `_active_session = session` (line 265), add:

```python
        # Initialize ATIF trace writer (unless resuming — that sets it below)
        from pathlib import Path as _Path
        _sd = _Path(session_dir) if session_dir else _Path(os.getcwd()) / ".klaude" / "sessions"
        _sd.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2: Update _save_and_summarize to use trace.finalize()**

Replace the `_save_and_summarize` function:

```python
def _save_and_summarize(
    session: Session,
    error: str | None = None,
) -> None:
    """Finalize trace and print JSON summary if in --json mode."""
    sid = None
    session_path = None

    if session.turn_count > 0 and session.trace:
        session.trace.finalize()
        sid = session.trace._doc.get("session_id")
        session_path = str(session.trace._path.resolve())

    _print_json_summary(session, sid, session_path, error=error)
```

- [ ] **Step 3: Update session resume to use TraceWriter.from_existing**

In the resume block (around line 268), after `session.restore(messages, turns)`, add:

```python
                # Resume ATIF trace from existing file
                session.trace = TraceWriter.from_existing(session_file_path)
```

To get `session_file_path`, update the resume block. Replace the resume section:

```python
        # --- Resume previous session ---
        if continue_session or resume_id:
            from pathlib import Path
            session_dir_path = Path(session_dir) if session_dir else None
            saved = load_session(resume_id, session_dir=session_dir_path)
            if saved:
                messages, turns, saved_at, sid = saved
                session.restore(messages, turns)
                # Point trace writer at the existing ATIF file
                if session_dir_path:
                    resume_trace_path = session_dir_path / f"{sid}.json"
                else:
                    resume_trace_path = Path(os.getcwd()) / ".klaude" / "sessions" / f"{sid}.json"
                if resume_trace_path.exists():
                    session.trace = TraceWriter.from_existing(resume_trace_path)
                if not json_mode:
                    active_console.print(
                        f"[dim]Resumed session {sid} ({turns} turns, "
                        f"{session.tracker.total_tokens:,} tokens, "
                        f"saved {saved_at})[/dim]"
                    )
            else:
                if not json_mode:
                    active_console.print("[yellow]No previous session found.[/yellow]")

        # Create fresh trace writer if not resuming
        if session.trace is None:
            import time as _time
            _trace_id = _time.strftime("%Y%m%d-%H%M%S")
            session.trace = TraceWriter(_sd / f"{_trace_id}.json", model_name=effective_model)
```

- [ ] **Step 4: Update SIGTERM handler**

Update `_sigterm_handler` to finalize the trace:

```python
def _sigterm_handler(signum: int, frame: object) -> None:
    """Handle SIGTERM: finalize trace and exit cleanly."""
    try:
        if _active_session is not None:
            _save_and_summarize(_active_session, error="SIGTERM")
        else:
            _print_json_summary(error="SIGTERM")
    except Exception:
        pass
    sys.exit(1)
```

(This already calls `_save_and_summarize` which now calls `trace.finalize()`, so no code change needed here — just verify the flow is correct.)

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/klaude/ui/cli.py
git commit -m "feat: wire TraceWriter into CLI entry point"
```

---

### Task 7: Update save_session Calls to Pass model_name

**Files:**
- Modify: `src/klaude/ui/cli.py`
- Modify: `src/klaude/ui/repl.py` (if it calls save_session)

- [ ] **Step 1: Check if repl.py calls save_session**

```bash
uv run grep -n "save_session" src/klaude/ui/repl.py
```

- [ ] **Step 2: Update any save_session calls that remain**

Since `_save_and_summarize` in cli.py now uses `trace.finalize()` instead of `save_session()`, check if `save_session` is still called anywhere. If the REPL calls `save_session` directly, update it to pass `model_name`. If not, no changes needed.

Search all files:
```bash
uv run grep -rn "save_session" src/klaude/
```

Update any remaining calls to include `model_name=session.model_name` (or equivalent).

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 4: Commit (if changes were made)**

```bash
git add -u
git commit -m "fix: pass model_name to remaining save_session calls"
```

---

### Task 8: Integration Test — Full Turn with Trace

**Files:**
- Create: `tests/test_trace_integration.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration test: a simulated turn writes correct ATIF trace."""

import json
from pathlib import Path

from klaude.core.trace import TraceWriter


def test_full_turn_trace(tmp_path):
    """Simulate a complete agentic turn and verify the ATIF output."""
    path = tmp_path / "integration.json"
    tw = TraceWriter(path, model_name="test-model")

    # User sends a message
    tw.write_user_step("read main.py and explain it")

    # Agent responds with a tool call
    tw.write_agent_step(None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "main.py"}'}},
    ])

    # Tool result
    tw.write_tool_result_step("call_1", "def main():\n    print('hello')")

    # Agent responds with text
    tw.write_agent_step("This is a simple Python script that prints 'hello'.", tool_calls=None)

    # Finalize
    tw.finalize()

    # Verify the complete ATIF document
    data = json.loads(path.read_text())
    assert data["schema_version"] == "ATIF-v1.4"
    assert data["session_id"] == "integration"
    assert len(data["steps"]) == 4
    assert data["final_metrics"]["total_steps"] == 4

    # Verify roundtrip: ATIF → chat messages → usable by LLM
    msgs = tw.to_chat_messages()
    assert len(msgs) == 4
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "read_file"
    assert msgs[2]["role"] == "tool"
    assert msgs[3]["role"] == "assistant"
    assert "hello" in msgs[3]["content"]

    # Verify resume: load from file, get same messages
    loaded_msgs, turn_count = TraceWriter.load(path)
    assert turn_count == 1
    assert loaded_msgs == msgs


def test_resume_appends_to_existing_trace(tmp_path):
    """Resuming a session appends new steps to the existing ATIF trace."""
    path = tmp_path / "resume.json"

    # First session
    tw1 = TraceWriter(path, model_name="test-model")
    tw1.write_user_step("first task")
    tw1.write_agent_step("done with first", tool_calls=None)
    tw1.finalize()

    # Resume
    tw2 = TraceWriter.from_existing(path)
    tw2.write_user_step("second task")
    tw2.write_agent_step("done with second", tool_calls=None)
    tw2.finalize()

    data = json.loads(path.read_text())
    assert len(data["steps"]) == 4
    assert data["steps"][0]["step_id"] == 1
    assert data["steps"][2]["step_id"] == 3
    assert data["final_metrics"]["total_steps"] == 4

    msgs, turns = TraceWriter.load(path)
    assert turns == 2
    assert len(msgs) == 4
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/test_trace_integration.py -v`
Expected: All PASS.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_trace_integration.py
git commit -m "test: add integration tests for ATIF trace roundtrip and resume"
```

---

### Task 9: Clean Up Handoff Document

**Files:**
- Delete: `docs/HANDOFF-trace-streaming.md`

- [ ] **Step 1: Remove the handoff document**

The handoff doc says "Delete after the feature is implemented." Now that the feature is implemented, remove it.

```bash
git rm docs/HANDOFF-trace-streaming.md
git commit -m "chore: remove handoff doc, trace streaming implemented"
```
