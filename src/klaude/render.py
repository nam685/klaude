"""Rich rendering — syntax highlighting for code blocks in streaming output.

The problem: LLM responses arrive token-by-token, but syntax highlighting
needs complete code blocks. We can't highlight half a function.

The solution: a line-buffered state machine.

    State NORMAL: print text as it arrives (line-at-a-time)
    Detect "```" at start of a line → switch to CODE state, start buffering
    State CODE: accumulate lines silently
    Detect "```" closing → render buffered code with syntax highlighting
    Switch back to NORMAL

Text outside code blocks streams normally (the user sees it in real-time).
Code blocks appear all at once when complete, with syntax highlighting.
"""

import re

from rich.console import Console
from rich.syntax import Syntax

# Map common language aliases to Pygments lexer names
LANG_ALIASES: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "yml": "yaml",
    "md": "markdown",
    "rb": "ruby",
    "rs": "rust",
    "": "text",
}

# Pattern to detect opening code fence (``` or ```python etc.)
CODE_FENCE_OPEN = re.compile(r"^```(\w*)$")
CODE_FENCE_CLOSE = re.compile(r"^```$")


class StreamPrinter:
    """Prints streaming LLM output with syntax-highlighted code blocks.

    Usage:
        printer = StreamPrinter(console)
        for token in stream:
            printer.feed(token)
        printer.flush()
    """

    def __init__(self, console: Console) -> None:
        self.console = console
        self._buffer = ""          # accumulates partial lines
        self._in_code = False      # inside a code fence?
        self._code_lang = ""       # language of current code block
        self._code_lines: list[str] = []  # accumulated code lines

    def feed(self, text: str) -> None:
        """Feed a text delta from the stream."""
        self._buffer += text

        # Process complete lines (keeping any trailing incomplete line in buffer)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._process_line(line)

    def flush(self) -> None:
        """Flush any remaining buffered text (call at end of stream)."""
        if self._in_code:
            # Stream ended mid-code-block — render what we have
            self._render_code_block()
        if self._buffer:
            self.console.print(self._buffer, end="", highlight=False)
            self._buffer = ""

    def _process_line(self, line: str) -> None:
        """Process a complete line."""
        if self._in_code:
            # Inside a code block — check for closing fence
            if CODE_FENCE_CLOSE.match(line):
                self._render_code_block()
            else:
                self._code_lines.append(line)
        else:
            # Outside code block — check for opening fence
            match = CODE_FENCE_OPEN.match(line)
            if match:
                self._in_code = True
                self._code_lang = match.group(1)
                self._code_lines = []
            else:
                # Regular text — print immediately
                self.console.print(line, highlight=False)

    def _render_code_block(self) -> None:
        """Render the accumulated code block with syntax highlighting."""
        code = "\n".join(self._code_lines)
        lang = LANG_ALIASES.get(self._code_lang, self._code_lang) or "text"

        if code.strip():
            syntax = Syntax(
                code,
                lang,
                theme="monokai",
                line_numbers=False,
                word_wrap=True,
            )
            self.console.print(syntax)
        else:
            # Empty code block — just skip it
            pass

        self._in_code = False
        self._code_lang = ""
        self._code_lines = []
