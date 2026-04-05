"""worktree tool — git worktree management for isolated agent work.

Git worktrees let you have multiple working directories from the same
repository. This is useful for isolating agent work: the agent can make
changes in a worktree without affecting the main working directory.

Operations:
- worktree_create: create a new worktree on a temp branch
- worktree_list: show active worktrees
- worktree_remove: clean up a worktree
"""

import os
import subprocess

from klaude.tools.registry import Tool


def _run_git(*args: str, cwd: str | None = None) -> tuple[bool, str]:
    """Run a git command and return (success, output)."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd or os.getcwd(),
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return False, "Error: git not found"
    except subprocess.TimeoutExpired:
        return False, "Error: git command timed out"


def handle_worktree(
    action: str,
    name: str | None = None,
    path: str | None = None,
    base_branch: str | None = None,
) -> str:
    """Manage git worktrees."""

    # Check we're in a git repo
    ok, _ = _run_git("rev-parse", "--git-dir")
    if not ok:
        return "Error: not in a git repository"

    if action == "create":
        if not name:
            return "Error: 'name' is required for worktree create"

        # Create worktree in a temp-ish location alongside the repo
        repo_root_ok, repo_root = _run_git("rev-parse", "--show-toplevel")
        if not repo_root_ok:
            return f"Error: could not find repo root: {repo_root}"

        wt_path = path or os.path.join(
            os.path.dirname(repo_root), f".klaude-worktree-{name}"
        )
        branch_name = f"klaude/{name}"
        base = base_branch or "HEAD"

        # Create a new branch and worktree
        ok, output = _run_git("worktree", "add", "-b", branch_name, wt_path, base)
        if not ok:
            # Branch might already exist
            if "already exists" in output:
                ok, output = _run_git("worktree", "add", wt_path, branch_name)
                if not ok:
                    return f"Error creating worktree: {output}"
            else:
                return f"Error creating worktree: {output}"

        return (
            f"Created worktree:\n"
            f"  Path: {wt_path}\n"
            f"  Branch: {branch_name}\n"
            f"  Base: {base}\n"
            f"Use this path for file operations in the isolated environment."
        )

    if action == "list":
        ok, output = _run_git("worktree", "list", "--porcelain")
        if not ok:
            return f"Error listing worktrees: {output}"

        if not output.strip():
            return "No worktrees found."

        # Parse porcelain format into readable output
        worktrees = []
        current: dict[str, str] = {}
        for line in output.split("\n"):
            if not line.strip():
                if current:
                    worktrees.append(current)
                    current = {}
                continue
            if line.startswith("worktree "):
                current["path"] = line[9:]
            elif line.startswith("branch "):
                current["branch"] = line[7:]
            elif line == "bare":
                current["bare"] = "true"
            elif line.startswith("HEAD "):
                current["head"] = line[5:13]  # short SHA
        if current:
            worktrees.append(current)

        lines = [f"Git worktrees ({len(worktrees)}):\n"]
        for wt in worktrees:
            p = wt.get("path", "?")
            b = wt.get("branch", "detached")
            h = wt.get("head", "")
            lines.append(f"  {p}")
            lines.append(f"    Branch: {b}  HEAD: {h}")
        return "\n".join(lines)

    if action == "remove":
        if not (name or path):
            return "Error: 'name' or 'path' is required for worktree remove"

        # If name given, construct the expected path
        if not path and name:
            repo_root_ok, repo_root = _run_git("rev-parse", "--show-toplevel")
            if repo_root_ok:
                path = os.path.join(
                    os.path.dirname(repo_root), f".klaude-worktree-{name}"
                )

        if not path:
            return "Error: could not determine worktree path"

        ok, output = _run_git("worktree", "remove", path, "--force")
        if not ok:
            return f"Error removing worktree: {output}"

        # Also try to delete the branch
        branch_name = f"klaude/{name}" if name else None
        if branch_name:
            _run_git("branch", "-D", branch_name)

        return f"Removed worktree: {path}"

    return f"Error: action must be 'create', 'list', or 'remove' (got '{action}')"


tool = Tool(
    name="worktree",
    description="Manage git worktrees. Actions: create, list, remove.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "remove"],
                "description": "Action: 'create', 'list', or 'remove'.",
            },
            "name": {
                "type": "string",
                "description": "Worktree name (used for branch klaude/<name> and path).",
            },
            "path": {
                "type": "string",
                "description": "Custom path for the worktree (optional, auto-generated if omitted).",
            },
            "base_branch": {
                "type": "string",
                "description": "Branch to base the worktree on (default: HEAD). For 'create' only.",
            },
        },
        "required": ["action"],
    },
    handler=handle_worktree,
)
