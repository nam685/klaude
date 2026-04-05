"""lsp tool — code intelligence queries using jedi (Python) and ctags (general).

Provides go-to-definition, find-references, and diagnostics without
requiring a running LSP server. Uses jedi for Python files (accurate,
AST-based) and falls back to ctags-style grep for other languages.

Zero new dependencies — jedi is optional (graceful fallback if missing).
"""

import os
import re
import subprocess

from klaude.tools.registry import Tool

# Try to import jedi for Python intelligence
try:
    import jedi

    HAS_JEDI = True
except ImportError:
    HAS_JEDI = False


def _jedi_definitions(path: str, line: int, column: int) -> list[dict[str, str]]:
    """Use jedi to find definitions at a position."""
    script = jedi.Script(path=path)
    defs = script.goto(line=line, column=column)
    results = []
    for d in defs:
        if d.module_path:
            results.append(
                {
                    "name": d.name,
                    "path": str(d.module_path),
                    "line": d.line,
                    "type": d.type,
                }
            )
    return results


def _jedi_references(path: str, line: int, column: int) -> list[dict[str, str]]:
    """Use jedi to find references at a position."""
    script = jedi.Script(path=path)
    refs = script.get_references(line=line, column=column)
    results = []
    for r in refs:
        if r.module_path:
            results.append(
                {
                    "name": r.name,
                    "path": str(r.module_path),
                    "line": r.line,
                    "type": r.type,
                }
            )
    return results


def _jedi_diagnostics(path: str) -> list[dict[str, str]]:
    """Use jedi to get diagnostics (syntax errors, etc.) for a file."""
    script = jedi.Script(path=path)
    script.get_names(all_scopes=False, definitions=False)
    # Jedi doesn't have a direct diagnostics API — use syntax check
    results = []
    try:
        compile(open(path).read(), path, "exec")
    except SyntaxError as e:
        results.append(
            {
                "severity": "error",
                "message": str(e.msg),
                "line": e.lineno or 0,
                "path": path,
            }
        )
    return results


def _grep_definitions(symbol: str, directory: str) -> list[dict[str, str]]:
    """Fallback: grep for definition patterns across common languages."""
    patterns = [
        rf"(def|func|function|fn)\s+{re.escape(symbol)}\b",  # Python, Go, JS, Rust
        rf"class\s+{re.escape(symbol)}\b",  # class definitions
        rf"(const|let|var|val)\s+{re.escape(symbol)}\b",  # variable declarations
        rf"type\s+{re.escape(symbol)}\b",  # type definitions
        rf"interface\s+{re.escape(symbol)}\b",  # interface definitions
    ]
    combined = "|".join(f"({p})" for p in patterns)

    try:
        result = subprocess.run(
            [
                "grep",
                "-rnE",
                combined,
                directory,
                "--include=*.py",
                "--include=*.js",
                "--include=*.ts",
                "--include=*.go",
                "--include=*.rs",
                "--include=*.java",
                "--include=*.rb",
                "--include=*.c",
                "--include=*.cpp",
                "--include=*.h",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    results = []
    for line in result.stdout.strip().split("\n")[:20]:
        if not line:
            continue
        match = re.match(r"^(.+?):(\d+):(.*)", line)
        if match:
            results.append(
                {
                    "path": match.group(1),
                    "line": int(match.group(2)),
                    "text": match.group(3).strip(),
                }
            )
    return results


def _grep_references(symbol: str, directory: str) -> list[dict[str, str]]:
    """Fallback: grep for all usages of a symbol."""
    try:
        result = subprocess.run(
            [
                "grep",
                "-rnw",
                symbol,
                directory,
                "--include=*.py",
                "--include=*.js",
                "--include=*.ts",
                "--include=*.go",
                "--include=*.rs",
                "--include=*.java",
                "--include=*.rb",
                "--include=*.c",
                "--include=*.cpp",
                "--include=*.h",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    results = []
    for line in result.stdout.strip().split("\n")[:30]:
        if not line:
            continue
        match = re.match(r"^(.+?):(\d+):(.*)", line)
        if match:
            results.append(
                {
                    "path": match.group(1),
                    "line": int(match.group(2)),
                    "text": match.group(3).strip(),
                }
            )
    return results


def handle_lsp(
    action: str,
    path: str | None = None,
    line: int | None = None,
    column: int | None = None,
    symbol: str | None = None,
) -> str:
    """Perform a code intelligence query."""
    if action not in ("definition", "references", "diagnostics"):
        return f"Error: action must be 'definition', 'references', or 'diagnostics' (got '{action}')"

    # --- Diagnostics ---
    if action == "diagnostics":
        if not path:
            return "Error: 'path' is required for diagnostics"
        if not os.path.isfile(path):
            return f"Error: file not found: {path}"

        if path.endswith(".py"):
            if HAS_JEDI:
                results = _jedi_diagnostics(path)
            else:
                # Basic syntax check without jedi
                results = []
                try:
                    compile(open(path).read(), path, "exec")
                except SyntaxError as e:
                    results.append(
                        {
                            "severity": "error",
                            "message": str(e.msg),
                            "line": e.lineno or 0,
                            "path": path,
                        }
                    )
            if not results:
                return f"No diagnostics for {path} (clean)"
            lines = [f"Diagnostics for {path}:\n"]
            for d in results:
                lines.append(f"  Line {d['line']}: [{d['severity']}] {d['message']}")
            return "\n".join(lines)
        else:
            return f"Diagnostics only supported for Python files (got {path})"

    # --- Definition / References with jedi (Python) ---
    if path and path.endswith(".py") and line is not None and HAS_JEDI:
        col = column if column is not None else 0
        try:
            if action == "definition":
                results = _jedi_definitions(path, line, col)
            else:
                results = _jedi_references(path, line, col)
        except Exception as e:
            return f"Error: jedi failed — {e}"

        if not results:
            return f"No {action}s found at {path}:{line}:{col}"

        lines = [f"{action.title()}s for position {path}:{line}:{col}:\n"]
        for r in results:
            loc = f"{r.get('path', '?')}:{r.get('line', '?')}"
            name = r.get("name", "?")
            rtype = r.get("type", "")
            lines.append(f"  {name} ({rtype}) → {loc}")
        return "\n".join(lines)

    # --- Fallback: grep-based search (any language) ---
    if not symbol:
        # Try to extract symbol from file + line
        if path and line is not None and os.path.isfile(path):
            try:
                with open(path) as f:
                    file_lines = f.readlines()
                if 0 < line <= len(file_lines):
                    text = file_lines[line - 1]
                    col = column or 0
                    # Extract word at column
                    match = re.search(r"\b\w+\b", text[col:])
                    if match:
                        symbol = match.group()
            except Exception:
                pass
        if not symbol:
            return "Error: 'symbol' is required when not using a Python file with line/column"

    directory = os.getcwd()
    if action == "definition":
        results = _grep_definitions(symbol, directory)
    else:
        results = _grep_references(symbol, directory)

    if not results:
        return f"No {action}s found for '{symbol}'"

    lines = [f"{action.title()}s for '{symbol}':\n"]
    for r in results:
        loc = f"{r['path']}:{r['line']}"
        text = r.get("text", "")
        lines.append(f"  {loc}  {text}")
    return "\n".join(lines)


tool = Tool(
    name="lsp",
    description="Code intelligence: go-to-definition, find-references, diagnostics.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["definition", "references", "diagnostics"],
                "description": "The query type: 'definition', 'references', or 'diagnostics'.",
            },
            "path": {
                "type": "string",
                "description": "Absolute file path (required for diagnostics, optional for def/refs).",
            },
            "line": {
                "type": "integer",
                "description": "1-based line number (for Python jedi queries).",
            },
            "column": {
                "type": "integer",
                "description": "0-based column offset (for Python jedi queries, default 0).",
            },
            "symbol": {
                "type": "string",
                "description": "Symbol name to search for (used for grep fallback when path/line not given).",
            },
        },
        "required": ["action"],
    },
    handler=handle_lsp,
)
