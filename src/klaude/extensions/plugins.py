"""Plugin loader — load custom Tool definitions from Python files.

Plugins are Python files in a configured directory (default: .klaude/tools/).
Each file should export a `tool` variable that is a Tool instance:

    # .klaude/tools/my_tool.py
    from klaude.tools.registry import Tool

    def handle_my_tool(query: str) -> str:
        return f"Result for: {query}"

    tool = Tool(
        name="my_tool",
        description="Does something custom.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The query"},
            },
            "required": ["query"],
        },
        handler=handle_my_tool,
    )

See Note 30 in docs/07-implementation-notes.md.
"""

import importlib.util
import sys
from pathlib import Path

from klaude.tools.registry import Tool


def load_plugin_tools(tools_dir: str) -> list[Tool]:
    """Load Tool instances from Python files in the given directory.

    Scans for .py files, imports each, and looks for a `tool` attribute.
    Returns a list of Tool objects found. Silently skips files that don't
    export a `tool` or fail to import.
    """
    dir_path = Path(tools_dir)
    if not dir_path.is_dir():
        return []

    tools: list[Tool] = []
    for py_file in sorted(dir_path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            # Dynamic import: create a module spec from the file path
            module_name = f"klaude_plugin_{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Look for a `tool` attribute
            tool = getattr(module, "tool", None)
            if isinstance(tool, Tool):
                tools.append(tool)
        except Exception:
            # Skip broken plugins silently — don't crash the main app
            continue

    return tools
