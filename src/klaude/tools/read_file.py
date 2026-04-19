"""read_file tool — reads a file and returns its contents.

For plain-text files, returns the text verbatim. For known binary formats
(PDF, Office, images, HTML) it dispatches to `_document.extract`, which
wraps the result in a prompt-injection-safety envelope. For unknown binary
data it returns a clear error asking the agent to use `read_document`.
"""

from pathlib import Path

from klaude.tools.registry import Tool

_BINARY_EXTS = frozenset(
    {
        ".pdf",
        ".docx",
        ".xlsx",
        ".pptx",
        ".html",
        ".htm",
        ".png",
        ".jpg",
        ".jpeg",
        ".tiff",
        ".bmp",
        ".gif",
        ".webp",
    }
)


def handle_read_file(path: str) -> str:
    """Read the contents of a file at the given path."""
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"

    if p.suffix.lower() in _BINARY_EXTS:
        from klaude.tools._document import extract  # lazy import

        return extract(p)

    try:
        return p.read_text()
    except UnicodeDecodeError:
        return (
            f"Error: {path} is binary. Use read_document if it's a "
            f"supported format (PDF, docx, xlsx, pptx, html, image), or "
            f"convert it to text first."
        )
    except Exception as e:
        return f"Error reading {path}: {e}"


tool = Tool(
    name="read_file",
    description=(
        "Read file contents at the given path. Source code, JSON, CSV, MD, "
        "YAML and other text files are returned verbatim. PDFs, Office docs "
        "(.docx/.xlsx/.pptx), images (.png/.jpg/...), and .html files are "
        "auto-dispatched through read_document and wrapped as untrusted."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
            }
        },
        "required": ["path"],
    },
    handler=handle_read_file,
)
