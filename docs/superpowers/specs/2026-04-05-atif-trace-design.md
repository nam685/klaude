# ATIF Trace Writer — Design Spec

> Replaces raw chat JSON with ATIF v1.4 as klaude's canonical session format.

## Problem

klaude saves session history as a single JSON dump of raw OpenAI chat messages on exit. nam-website's `/slops` page polls for traces during execution but gets nothing until the mission completes. The trace format is also a proprietary chat dump — not a standardized trajectory format.

## Goal

Write ATIF v1.4 trajectory files incrementally during execution. The file is rewritten after each step so external consumers (nam-website) can poll for live progress. ATIF becomes the single canonical format for both trace viewing and session resume.

## ATIF v1.4 Format

Reference: https://www.harborframework.com/docs/agents/trajectory-format

### Document structure

```json
{
  "schema_version": "ATIF-v1.4",
  "session_id": "20260405-143000",
  "agent": {
    "name": "klaude",
    "version": "0.1.0",
    "model_name": "openrouter/auto"
  },
  "steps": [ ... ],
  "final_metrics": {
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "total_cached_tokens": 0,
    "total_cost_usd": 0,
    "total_steps": 4
  }
}
```

### Step types

**User step** (`source: "user"`):
```json
{
  "step_id": 1,
  "timestamp": "2026-04-05T14:30:01",
  "source": "user",
  "message": "fix the bug in utils.py"
}
```

**Agent step** (`source: "agent"`) — text response or tool calls:
```json
{
  "step_id": 2,
  "timestamp": "2026-04-05T14:30:05",
  "source": "agent",
  "message": null,
  "model_name": "openrouter/auto",
  "tool_calls": [
    {
      "tool_call_id": "call_1",
      "function_name": "read_file",
      "arguments": {"path": "utils.py"}
    }
  ]
}
```

**System/observation step** (`source: "system"`) — tool result:
```json
{
  "step_id": 3,
  "timestamp": "2026-04-05T14:30:06",
  "source": "system",
  "message": "def foo():\n    ...",
  "observation": {
    "results": [{"tool_call_id": "call_1", "content": "def foo():\n    ..."}]
  }
}
```

### Mapping from current format

| Current (OpenAI chat) | ATIF step |
|---|---|
| `{"role": "user", "content": "..."}` | `source: "user"`, message = content |
| `{"role": "assistant", "content": "...", "tool_calls": [...]}` | `source: "agent"`, message = content, tool_calls mapped |
| `{"role": "tool", "tool_call_id": "...", "content": "..."}` | `source: "system"`, observation.results = [{tool_call_id, content}] |

One assistant message with multiple tool_calls stays as one step. Each tool result is its own step.

## Architecture

### New file: `src/klaude/core/trace.py`

```python
class TraceWriter:
    def __init__(self, path: Path, model_name: str) -> None:
        """Create a new ATIF trace. Holds doc in memory, rewrites file on each write."""

    def write_user_step(self, message: str) -> None:
        """Add a user step and flush to disk."""

    def write_agent_step(self, content: str | None, tool_calls: list | None) -> None:
        """Add an agent step (assistant response) and flush to disk."""

    def write_tool_result_step(self, tool_call_id: str, content: str) -> None:
        """Add a system/observation step (tool result) and flush to disk."""

    def finalize(self, metrics: dict | None = None) -> None:
        """Write final_metrics and flush. Called on session exit."""

    def _flush(self) -> None:
        """Rewrite the full JSON file. Atomic via write-to-temp + os.rename()."""

    @classmethod
    def from_existing(cls, path: Path) -> "TraceWriter":
        """Load an existing ATIF file and resume appending steps."""

    @classmethod
    def load(cls, path: Path) -> tuple[list[dict], int]:
        """Load ATIF, return (chat_messages, turn_count) for Session.restore()."""

    def to_chat_messages(self) -> list[dict]:
        """Convert ATIF steps back to OpenAI chat messages for the LLM."""
```

Key details:
- **Atomic writes:** `_flush()` writes to a temp file then `os.rename()` so a polling consumer never reads a half-written file.
- **`to_chat_messages()`:** Reverse mapping from ATIF steps to OpenAI chat format for session resume and LLM API calls.
- **Turn counting on load:** Count the number of `source: "user"` steps.

### Loop integration: `src/klaude/core/loop.py`

TraceWriter is created in `Session.__init__()` and called at 4 points in `Session.turn()`:

```
Session.turn(user_message):
    1. trace.write_user_step(user_message)              # after history.add_user

    for iteration in range(MAX_ITERATIONS):
        result = consume_stream(...)

        if not result.has_tool_calls:
            2. trace.write_agent_step(result)            # final text response
            return

        3. trace.write_agent_step(result)                # assistant + tool_calls

        for tc in result.tool_calls:
            ... execute tool ...
            4. trace.write_tool_result_step(tc.id, result)  # each tool result
```

### Session store migration: `src/klaude/core/session_store.py`

Becomes a thin wrapper around TraceWriter:
- `save_session()` → calls `trace.finalize(metrics)` (writes `final_metrics`, final flush)
- `load_session()` → calls `TraceWriter.load(path)` which parses ATIF and returns chat messages + turn count
- `list_sessions()` → scans directory, reads ATIF metadata (`session_id`, first user step for summary)

### Session resume flow

```
klaude -c:
    saved = load_session(resume_id)          # reads ATIF → chat messages
    session.restore(messages, turns)          # feeds chat messages to history
    session.trace = TraceWriter.from_existing(path)  # resumes ATIF doc
    # New steps append to existing trajectory, same session_id
```

On resume, the ATIF file grows with new steps appended. `final_metrics` updates on exit.

### CLI changes: `src/klaude/ui/cli.py`

- Pass `model_name` through to Session so TraceWriter can populate the `agent` block
- `--session-dir` continues to control where ATIF files are written
- `_build_json_summary` references the trace file path (same location, ATIF format now)

## What does NOT change

- `src/klaude/core/stream.py` — TraceWriter works with results after streaming
- `src/klaude/core/history.py` — still holds raw chat messages for the LLM
- `src/klaude/core/context.py` / `compaction.py` — compaction only affects LLM-side messages, trace is the full uncompacted record
- nam-website — separate follow-up (TraceViewer reads ATIF steps, tasks.py reads session_dir output directly)

## Scope exclusions

- Per-step token metrics: best-effort (populate if API returns usage, null otherwise). `cost_usd` is 0 (OpenRouter free tier).
- `reasoning_content` field: omit for now, add when thinking mode is relevant.
- ATIF validation: no validator on the write side. Structural correctness is enforced by TraceWriter's API.
- nam-website changes: separate task (TraceViewer update, mission→session rename, polling during execution).
