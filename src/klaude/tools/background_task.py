"""background_task tool — run sub-agents as background threads.

Instead of blocking while a sub-agent works, background tasks let the
model launch work, continue doing other things, and check back later.

Three operations:
- background_start: launch a sub-agent in a thread
- background_status: check if a task is running/done
- background_result: get the output of a completed task

Uses threading (not multiprocessing) — sub-agents share the LLM client
connection pool, which is more efficient than spawning processes.
"""

import threading
import time
from dataclasses import dataclass, field

from klaude.tools.registry import Tool

# Import sub_agent internals for reuse
from klaude.tools.sub_agent import handle_sub_agent


@dataclass
class BackgroundJob:
    """A background sub-agent job."""
    task_id: str
    prompt: str
    status: str = "running"  # running, completed, error
    result: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None


# Module-level job store
_jobs: dict[str, BackgroundJob] = {}
_lock = threading.Lock()
_next_id = 1


def _run_job(job: BackgroundJob) -> None:
    """Execute a sub-agent in a background thread."""
    try:
        result = handle_sub_agent(job.prompt)
        with _lock:
            job.result = result
            job.status = "completed"
            job.finished_at = time.time()
    except Exception as e:
        with _lock:
            job.result = f"Error: {e}"
            job.status = "error"
            job.finished_at = time.time()


def handle_background_task(
    action: str,
    task: str | None = None,
    task_id: str | None = None,
) -> str:
    """Manage background sub-agent tasks."""
    global _next_id

    if action == "start":
        if not task:
            return "Error: 'task' is required for action 'start'"

        with _lock:
            tid = f"bg-{_next_id}"
            _next_id += 1

        job = BackgroundJob(task_id=tid, prompt=task)
        with _lock:
            _jobs[tid] = job

        thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
        thread.start()

        return f"Started background task {tid}: {task[:100]}"

    if action == "status":
        with _lock:
            if task_id and task_id in _jobs:
                job = _jobs[task_id]
                elapsed = (job.finished_at or time.time()) - job.started_at
                return f"Task {task_id}: {job.status} ({elapsed:.1f}s)"

            # List all jobs
            if not _jobs:
                return "No background tasks."
            lines = ["Background tasks:\n"]
            for tid, job in _jobs.items():
                elapsed = (job.finished_at or time.time()) - job.started_at
                lines.append(f"  {tid}: {job.status} ({elapsed:.1f}s) — {job.prompt[:60]}")
            return "\n".join(lines)

    if action == "result":
        if not task_id:
            return "Error: 'task_id' is required for action 'result'"
        with _lock:
            if task_id not in _jobs:
                return f"Error: unknown task_id '{task_id}'"
            job = _jobs[task_id]
            if job.status == "running":
                return f"Task {task_id} is still running (started {time.time() - job.started_at:.1f}s ago)"
            return f"Task {task_id} [{job.status}]:\n\n{job.result}"

    return f"Error: action must be 'start', 'status', or 'result' (got '{action}')"


tool = Tool(
    name="background_task",
    description=(
        "Run sub-agents in the background without blocking. "
        "Actions: 'start' (launch a task, returns task_id), "
        "'status' (check progress of one or all tasks), "
        "'result' (get the output of a completed task). "
        "Background tasks have the same read-only tools as sub_agent. "
        "Use for: parallel research, long-running exploration, or tasks you "
        "want to check on later."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "status", "result"],
                "description": "Action: 'start', 'status', or 'result'.",
            },
            "task": {
                "type": "string",
                "description": "Task prompt for the sub-agent (required for 'start').",
            },
            "task_id": {
                "type": "string",
                "description": "Task ID to check (for 'status' of a specific task, or 'result').",
            },
        },
        "required": ["action"],
    },
    handler=handle_background_task,
)
