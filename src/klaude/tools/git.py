"""git tools — local git operations for status, diff, log, and commit."""

import subprocess
from typing import Optional

from klaude.tools.registry import Tool

TIMEOUT_SECONDS = 30


def _run_git(*args: str) -> tuple[str, str, int]:
    """Run a git command and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    return result.stdout, result.stderr, result.returncode


def handle_git_status() -> str:
    """Return current branch name and short working-tree status."""
    try:
        branch_out, branch_err, branch_rc = _run_git("branch", "--show-current")
        if branch_rc != 0:
            return f"Error: not a git repository or git not available.\n{branch_err.strip()}"

        branch = branch_out.strip() or "(detached HEAD)"

        status_out, status_err, status_rc = _run_git("status", "--short")
        if status_rc != 0:
            return f"Error running git status: {status_err.strip()}"

        status = status_out.strip() or "(clean)"
        return f"branch: {branch}\n{status}"
    except subprocess.TimeoutExpired:
        return f"Error: git status timed out after {TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"Error running git status: {e}"


def handle_git_diff(target: Optional[str] = None) -> str:
    """Return diff output for unstaged changes, staged changes, or against a ref."""
    try:
        # Quick check: are we in a git repo?
        _, _, check_rc = _run_git("rev-parse", "--git-dir")
        if check_rc != 0:
            return "Error: not a git repository."

        if target == "staged":
            args = ("diff", "--cached")
        elif target:
            args = ("diff", target)
        else:
            args = ("diff",)

        out, err, rc = _run_git(*args)
        if rc != 0:
            return f"Error running git diff: {err.strip()}"

        return out.strip() or "(no differences)"
    except subprocess.TimeoutExpired:
        return f"Error: git diff timed out after {TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"Error running git diff: {e}"


def handle_git_log(count: int = 10) -> str:
    """Return the last N commits as one-line summaries."""
    try:
        out, err, rc = _run_git("log", "--oneline", f"-n{count}")
        if rc != 0:
            return f"Error running git log: {err.strip()}"

        return out.strip() or "(no commits)"
    except subprocess.TimeoutExpired:
        return f"Error: git log timed out after {TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"Error running git log: {e}"


def handle_git_commit(message: str, files: Optional[list[str]] = None) -> str:
    """Stage files and create a commit with the given message."""
    if files is None:
        files = ["."]

    try:
        add_out, add_err, add_rc = _run_git("add", *files)
        if add_rc != 0:
            return f"Error staging files: {add_err.strip()}"

        commit_out, commit_err, commit_rc = _run_git("commit", "-m", message)
        output = commit_out.strip()
        if commit_err.strip():
            output += f"\n[stderr]\n{commit_err.strip()}"
        if commit_rc != 0:
            output += f"\n[exit code: {commit_rc}]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: git commit timed out after {TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"Error running git commit: {e}"


git_status_tool = Tool(
    name="git_status",
    description="Show current branch and working-tree status.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    handler=handle_git_status,
)

git_diff_tool = Tool(
    name="git_diff",
    description="Show git diff. target: 'staged', a ref, or omit for unstaged.",
    parameters={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "'staged' for staged changes, a branch name or commit hash "
                    "to diff against, or omit for unstaged changes."
                ),
            }
        },
        "required": [],
    },
    handler=handle_git_diff,
)

git_log_tool = Tool(
    name="git_log",
    description="Show recent commit history (one-line format).",
    parameters={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "Number of commits to show. Defaults to 10.",
            }
        },
        "required": [],
    },
    handler=handle_git_log,
)

git_commit_tool = Tool(
    name="git_commit",
    description="Stage files and create a git commit.",
    parameters={
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of file paths to stage. Defaults to ['.'] (stage everything)."
                ),
            },
        },
        "required": ["message"],
    },
    handler=handle_git_commit,
)
