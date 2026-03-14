"""notebook_edit tool — read, edit, and execute Jupyter notebook cells.

Parses .ipynb files (JSON format) directly. No dependency on jupyter or
nbformat — just standard json. Execution is optional and uses
`jupyter nbconvert --execute` if available.
"""

import json
import os
import subprocess

from klaude.tools.registry import Tool


def _read_notebook(path: str) -> dict:
    """Read and parse a .ipynb file."""
    with open(path) as f:
        return json.load(f)


def _write_notebook(path: str, nb: dict) -> None:
    """Write a notebook back to disk."""
    with open(path, "w") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")


def _format_cell(cell: dict, index: int) -> str:
    """Format a single cell for display."""
    cell_type = cell.get("cell_type", "unknown")
    source = "".join(cell.get("source", []))
    outputs = cell.get("outputs", [])

    lines = [f"--- Cell {index} [{cell_type}] ---"]
    lines.append(source)

    if outputs:
        lines.append("--- Output ---")
        for out in outputs:
            if "text" in out:
                lines.append("".join(out["text"]))
            elif "data" in out:
                data = out["data"]
                if "text/plain" in data:
                    lines.append("".join(data["text/plain"]))
                elif "text/html" in data:
                    lines.append("[HTML output]")
                elif "image/png" in data:
                    lines.append("[Image output (PNG)]")
            elif out.get("output_type") == "error":
                ename = out.get("ename", "Error")
                evalue = out.get("evalue", "")
                lines.append(f"{ename}: {evalue}")

    return "\n".join(lines)


def handle_notebook_edit(
    path: str,
    action: str,
    cell_index: int | None = None,
    content: str | None = None,
    cell_type: str | None = None,
) -> str:
    """Read, edit, or execute Jupyter notebook cells."""
    if not path.endswith(".ipynb"):
        return f"Error: expected .ipynb file (got {path})"

    # --- Read ---
    if action == "read":
        if not os.path.isfile(path):
            return f"Error: file not found: {path}"
        try:
            nb = _read_notebook(path)
        except (json.JSONDecodeError, KeyError) as e:
            return f"Error: invalid notebook format — {e}"

        cells = nb.get("cells", [])
        if not cells:
            return f"Notebook {path}: 0 cells (empty)"

        if cell_index is not None:
            if cell_index < 0 or cell_index >= len(cells):
                return f"Error: cell_index {cell_index} out of range (0-{len(cells)-1})"
            return _format_cell(cells[cell_index], cell_index)

        # Read all cells
        lines = [f"Notebook {path}: {len(cells)} cells\n"]
        for i, cell in enumerate(cells):
            lines.append(_format_cell(cell, i))
            lines.append("")
        return "\n".join(lines)

    # --- Edit ---
    if action == "edit":
        if cell_index is None:
            return "Error: 'cell_index' is required for edit"
        if content is None:
            return "Error: 'content' is required for edit"
        if not os.path.isfile(path):
            return f"Error: file not found: {path}"

        try:
            nb = _read_notebook(path)
        except (json.JSONDecodeError, KeyError) as e:
            return f"Error: invalid notebook format — {e}"

        cells = nb.get("cells", [])
        if cell_index < 0 or cell_index >= len(cells):
            return f"Error: cell_index {cell_index} out of range (0-{len(cells)-1})"

        # Update cell source (notebook format stores as list of lines)
        source_lines = [line + "\n" for line in content.split("\n")]
        if source_lines:
            source_lines[-1] = source_lines[-1].rstrip("\n")
        cells[cell_index]["source"] = source_lines

        if cell_type and cell_type in ("code", "markdown", "raw"):
            cells[cell_index]["cell_type"] = cell_type

        _write_notebook(path, nb)
        return f"Updated cell {cell_index} in {path}"

    # --- Insert ---
    if action == "insert":
        if content is None:
            return "Error: 'content' is required for insert"
        if not os.path.isfile(path):
            return f"Error: file not found: {path}"

        try:
            nb = _read_notebook(path)
        except (json.JSONDecodeError, KeyError) as e:
            return f"Error: invalid notebook format — {e}"

        cells = nb.get("cells", [])
        ct = cell_type or "code"
        source_lines = [line + "\n" for line in content.split("\n")]
        if source_lines:
            source_lines[-1] = source_lines[-1].rstrip("\n")

        new_cell = {
            "cell_type": ct,
            "metadata": {},
            "source": source_lines,
        }
        if ct == "code":
            new_cell["execution_count"] = None
            new_cell["outputs"] = []

        insert_at = cell_index if cell_index is not None else len(cells)
        insert_at = max(0, min(insert_at, len(cells)))
        cells.insert(insert_at, new_cell)
        nb["cells"] = cells

        _write_notebook(path, nb)
        return f"Inserted {ct} cell at index {insert_at} in {path}"

    # --- Execute ---
    if action == "execute":
        if not os.path.isfile(path):
            return f"Error: file not found: {path}"

        try:
            result = subprocess.run(
                ["jupyter", "nbconvert", "--to", "notebook",
                 "--execute", "--inplace", path],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                return f"Error executing notebook:\n{result.stderr}"
            # Re-read to show outputs
            nb = _read_notebook(path)
            cells = nb.get("cells", [])
            lines = [f"Executed {path} ({len(cells)} cells):\n"]
            for i, cell in enumerate(cells):
                if cell.get("cell_type") == "code" and cell.get("outputs"):
                    lines.append(_format_cell(cell, i))
                    lines.append("")
            return "\n".join(lines) or f"Executed {path} (no output)"
        except FileNotFoundError:
            return "Error: 'jupyter' not found — install with `pip install jupyter`"
        except subprocess.TimeoutExpired:
            return "Error: notebook execution timed out (120s)"

    return f"Error: action must be 'read', 'edit', 'insert', or 'execute' (got '{action}')"


tool = Tool(
    name="notebook_edit",
    description=(
        "Read, edit, insert, or execute Jupyter notebook (.ipynb) cells. "
        "Actions: 'read' (view cells and outputs), 'edit' (modify a cell's content), "
        "'insert' (add a new cell), 'execute' (run the notebook via jupyter nbconvert). "
        "Use cell_index (0-based) to target specific cells."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the .ipynb file.",
            },
            "action": {
                "type": "string",
                "enum": ["read", "edit", "insert", "execute"],
                "description": "Action: 'read', 'edit', 'insert', or 'execute'.",
            },
            "cell_index": {
                "type": "integer",
                "description": "0-based cell index (required for edit, optional for read/insert).",
            },
            "content": {
                "type": "string",
                "description": "New cell content (required for edit and insert).",
            },
            "cell_type": {
                "type": "string",
                "enum": ["code", "markdown", "raw"],
                "description": "Cell type (for edit/insert, default 'code').",
            },
        },
        "required": ["path", "action"],
    },
    handler=handle_notebook_edit,
)
