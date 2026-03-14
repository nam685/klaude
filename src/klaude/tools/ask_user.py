"""ask_user tool — structured user interaction.

Instead of the LLM just emitting text and hoping the user responds,
this tool explicitly asks a question and waits for the user's response.
The model gets the user's answer back as a tool result.

This is the equivalent of Claude Code's AskUserQuestion tool.
"""

from rich.console import Console
from rich.panel import Panel

from klaude.tools.registry import Tool

# Module-level console — set by the session at init time
_console: Console | None = None


def set_console(console: Console) -> None:
    """Set the console instance (called by Session.__init__)."""
    global _console
    _console = console


def handle_ask_user(question: str) -> str:
    """Ask the user a question and return their response."""
    if not question.strip():
        return "Error: question cannot be empty"

    console = _console or Console()

    console.print()
    console.print(Panel(question, title="[bold yellow]Question[/bold yellow]", border_style="yellow"))

    try:
        response = input("Your answer: ").strip()
        if not response:
            return "(user gave no response)"
        return response
    except EOFError:
        return "(user ended input)"
    except KeyboardInterrupt:
        console.print()
        return "(user cancelled)"


tool = Tool(
    name="ask_user",
    description=(
        "Ask the user a question and wait for their response. "
        "Use when you need clarification, confirmation, or a choice from the user. "
        "Prefer this over just stating a question in your text output, because "
        "this tool guarantees you receive the user's answer as a tool result."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user.",
            },
        },
        "required": ["question"],
    },
    handler=handle_ask_user,
)
