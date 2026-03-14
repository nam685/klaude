"""task_list tool — create and manage a structured task plan during complex work."""

from klaude.tools.registry import Tool

_tasks: list[dict] = []

_STATUS_SYMBOLS: dict[str, str] = {
    "pending": "[ ]",
    "in_progress": "[~]",
    "done": "[x]",
    "skipped": "[-]",
}


def _render_tasks() -> str:
    """Render the current task list as a formatted string."""
    if not _tasks:
        return "No tasks."

    done_count = sum(1 for t in _tasks if t["status"] == "done")
    total = len(_tasks)
    lines = [f"Task plan ({done_count}/{total} done):"]
    for i, task in enumerate(_tasks):
        symbol = _STATUS_SYMBOLS.get(task["status"], "[ ]")
        lines.append(f"{symbol} {i}. {task['description']}")
    return "\n".join(lines)


def handle_task_list(
    action: str,
    tasks: list[str] | None = None,
    task_index: int | None = None,
    status: str | None = None,
) -> str:
    """Create and manage a task plan."""
    global _tasks

    if action == "create":
        if not tasks:
            return "Error: 'tasks' parameter is required for action 'create'."
        _tasks = [{"description": desc, "status": "pending"} for desc in tasks]
        return _render_tasks()

    elif action == "update":
        if task_index is None:
            return "Error: 'task_index' parameter is required for action 'update'."
        if status is None:
            return "Error: 'status' parameter is required for action 'update'."
        if status not in ("done", "in_progress", "skipped"):
            return f"Error: invalid status '{status}'. Must be one of: done, in_progress, skipped."
        if not _tasks:
            return "Error: no task list exists. Use action 'create' first."
        if task_index < 0 or task_index >= len(_tasks):
            return f"Error: task_index {task_index} is out of range (0–{len(_tasks) - 1})."
        _tasks[task_index]["status"] = status
        return _render_tasks()

    elif action == "list":
        return _render_tasks()

    else:
        return f"Error: unknown action '{action}'. Must be one of: create, update, list."


tool = Tool(
    name="task_list",
    description="Create/update a task plan. Actions: create, update, list.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "update", "list"],
                "description": "The operation to perform on the task list.",
            },
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of task descriptions to create. Required for action 'create'.",
            },
            "task_index": {
                "type": "integer",
                "description": "0-based index of the task to update. Required for action 'update'.",
            },
            "status": {
                "type": "string",
                "enum": ["done", "in_progress", "skipped"],
                "description": "New status for the task. Required for action 'update'.",
            },
        },
        "required": ["action"],
    },
    handler=handle_task_list,
)
