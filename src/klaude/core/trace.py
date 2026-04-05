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
