"""edit_file tool — surgical text replacement in files.

Unlike write_file (which overwrites the entire file), edit_file replaces
a specific string within the file. This is how Claude Code's Edit tool works:
give it the exact text to find (old_string) and what to replace it with (new_string).

Why this approach?
- The LLM only needs to specify the changed portion, not the whole file
- Less likely to accidentally corrupt parts of the file it didn't mean to change
- Smaller tool call payloads = fewer tokens used
- Matches how developers think: "change X to Y"
"""

from pathlib import Path

from klaude.tools.registry import Tool


def handle_edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace old_string with new_string in a file."""
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"

    try:
        content = p.read_text()
    except Exception as e:
        return f"Error reading {path}: {e}"

    # Check that old_string exists in the file
    count = content.count(old_string)
    if count == 0:
        return (
            f"Error: old_string not found in {path}. "
            f"Make sure it matches exactly (including whitespace and indentation)."
        )
    if count > 1:
        return (
            f"Error: old_string appears {count} times in {path}. "
            f"Provide more surrounding context to make the match unique."
        )

    # Perform the replacement
    new_content = content.replace(old_string, new_string, 1)

    try:
        p.write_text(new_content)
    except Exception as e:
        return f"Error writing {path}: {e}"

    # Show what changed
    old_lines = old_string.count("\n") + 1
    new_lines = new_string.count("\n") + 1
    return (
        f"Successfully edited {path}: "
        f"replaced {old_lines} line(s) with {new_lines} line(s)"
    )


tool = Tool(
    name="edit_file",
    description="Replace an exact string match in a file. old_string must be unique.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to find (must appear exactly once in the file)",
            },
            "new_string": {
                "type": "string",
                "description": "The text to replace it with",
            },
        },
        "required": ["path", "old_string", "new_string"],
    },
    handler=handle_edit_file,
)
