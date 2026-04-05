"""REPL mode — interactive multi-turn conversation with klaude.

Instead of one-shot `klaude "task"`, the REPL lets you have a
back-and-forth conversation:

    $ klaude
    klaude> read main.py and explain it
    ... (klaude responds) ...
    klaude> now add error handling to the parse function
    ... (klaude responds, remembering the previous context) ...
    klaude> /exit

The conversation history persists across turns within one session.
Context compaction kicks in automatically when the history gets large.

Slash commands:
    /exit, /quit  — exit the REPL
    /clear        — clear history and start fresh
    /context      — show current context usage
    /history      — show message history debug view
    /undo         — undo the last turn (Esc also works)
    /thinking     — toggle showing model's thinking (Ctrl+O)
    /plan         — toggle plan mode (read-only, no writes/bash)
    /cron         — manage scheduled tasks (/cron 5m <prompt>, /cron list, /cron stop <id>)
    /skills       — list available skills
    /sessions     — list saved sessions (resume with klaude -c or --resume <id>)
    /<name>       — run a skill (e.g., /commit, /review, /explain)
"""

import readline
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from klaude.core.loop import Session

# History file for readline (up-arrow recall across sessions)
HISTORY_FILE = Path.home() / ".klaude_history"
MAX_HISTORY_LENGTH = 500


def _setup_readline() -> None:
    """Configure readline for input editing and history, including Esc → /undo."""
    try:
        readline.read_history_file(HISTORY_FILE)
    except FileNotFoundError:
        pass
    readline.set_history_length(MAX_HISTORY_LENGTH)

    # Bind Esc key to insert "/undo" and accept the line.
    # This uses readline's key binding: Esc → clear line, type /undo, accept.
    # Works on both GNU readline and macOS libedit.
    try:
        if "libedit" in readline.__doc__:  # type: ignore[operator]
            # macOS libedit syntax
            readline.parse_and_bind('bind "\\e" "\\e[H\\e[2K/undo\\n"')
            readline.parse_and_bind('bind "\\x0f" "\\e[H\\e[2K/thinking\\n"')  # Ctrl+O
        else:
            # GNU readline syntax
            readline.parse_and_bind('"\\e": "\\C-a\\C-k/undo\\C-m"')
            readline.parse_and_bind('"\\C-o": "\\C-a\\C-k/thinking\\C-m"')
    except Exception:
        pass  # if binding fails, commands still work typed manually


def _save_readline() -> None:
    """Save readline history to disk."""
    try:
        readline.write_history_file(HISTORY_FILE)
    except OSError:
        pass


def _read_input(console: Console, session: Session | None = None) -> str | None:
    """Read user input, handling EOF (Ctrl+D) and keyboard interrupt.

    Returns the input string, or None if the user wants to exit.
    """
    try:
        prompt = (
            "klaude[plan]> "
            if session and session.permissions.plan_mode
            else "klaude> "
        )
        line = input(prompt)
        return line
    except EOFError:
        # Ctrl+D — exit
        console.print()
        return None
    except KeyboardInterrupt:
        # Ctrl+C at the prompt — clear line, don't exit
        console.print()
        return ""


def _handle_slash_command(
    command: str, session: Session, console: Console
) -> bool | str:
    """Handle a slash command.

    Returns:
        True  — REPL should continue (command handled)
        False — REPL should exit
        str   — a rendered skill prompt to run through session.turn()
    """
    # Split into command and arguments (e.g., "/commit fix auth bug")
    parts = command.strip().split(None, 1)
    cmd = parts[0].lower()
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd in ("/exit", "/quit"):
        return False

    if cmd == "/clear":
        from klaude.core.prompt import SYSTEM_PROMPT
        from klaude.core.history import MessageHistory

        session.history = MessageHistory(SYSTEM_PROMPT)
        session.turn_count = 0
        session.tracker.update(session.history.messages)
        console.print("[dim]History cleared.[/dim]")
        return True

    if cmd == "/context":
        session.tracker.update(session.history.messages)
        console.print(f"[dim]{session.tracker.format_status()}[/dim]")
        console.print(f"[dim]Messages: {len(session.history)}[/dim]")
        start, end = session.history.compactable_range()
        if end > start:
            console.print(f"[dim]Compactable: {end - start} messages[/dim]")
        return True

    if cmd == "/history":
        console.print(f"[dim]{session.history.format_debug()}[/dim]")
        return True

    if cmd == "/undo":
        if session.undo():
            console.print("[dim]Undid last turn.[/dim]")
        else:
            console.print("[yellow]Nothing to undo.[/yellow]")
        return True

    if cmd == "/thinking":
        from klaude.core import stream as _stream_mod

        _stream_mod.show_thinking = not _stream_mod.show_thinking
        state = "ON" if _stream_mod.show_thinking else "OFF"
        color = "cyan" if _stream_mod.show_thinking else "dim"
        console.print(f"[{color}]Show thinking: {state}[/{color}]  (Ctrl+O to toggle)")
        return True

    if cmd == "/plan":
        session.permissions.plan_mode = not session.permissions.plan_mode
        state = (
            "ON (read-only)" if session.permissions.plan_mode else "OFF (full access)"
        )
        color = "yellow" if session.permissions.plan_mode else "green"
        console.print(f"[{color}]Plan mode: {state}[/{color}]")
        return True

    if cmd == "/cron":
        from klaude.extensions.cron import create_job, list_jobs, stop_job, stop_all

        if not cmd_args:
            console.print(f"[dim]{list_jobs()}[/dim]")
            return True
        if cmd_args == "list":
            console.print(f"[dim]{list_jobs()}[/dim]")
            return True
        if cmd_args.startswith("stop "):
            job_id = cmd_args[5:].strip()
            if job_id == "all":
                console.print(f"[dim]{stop_all()}[/dim]")
            else:
                console.print(f"[dim]{stop_job(job_id)}[/dim]")
            return True
        # /cron <interval> <prompt>
        cron_parts = cmd_args.split(None, 1)
        if len(cron_parts) < 2:
            console.print(
                "[yellow]Usage: /cron <interval> <prompt>  (e.g., /cron 5m /review)[/yellow]"
            )
            return True
        interval, prompt = cron_parts
        msg = create_job(interval, prompt)
        console.print(f"[dim]{msg}[/dim]")
        return True

    if cmd == "/skills":
        from klaude.extensions.skills import format_skill_list

        console.print(f"[dim]{format_skill_list(session.skills)}[/dim]")
        return True

    if cmd == "/sessions":
        from klaude.core.session_store import list_sessions, format_session_list

        console.print(f"[dim]{format_session_list(list_sessions())}[/dim]")
        return True

    # Check if it's a skill name (e.g., /commit, /review)
    skill_name = cmd.lstrip("/")
    if skill_name in session.skills:
        skill = session.skills[skill_name]
        console.print(f"[dim]Running skill: {skill.name} — {skill.description}[/dim]")
        return skill.render(cmd_args)

    console.print(f"[red]Unknown command: {cmd}[/red]")
    console.print(
        "[dim]Commands: /exit /clear /context /history /undo /plan /thinking /cron /skills /sessions[/dim]"
    )
    if session.skills:
        names = ", ".join(f"/{n}" for n in sorted(session.skills))
        console.print(f"[dim]Skills: {names}[/dim]")
    return True


def repl(session: Session) -> None:
    """Run the interactive REPL loop."""
    console = session.console

    console.print(
        Panel(
            f"[bold]klaude[/bold] — interactive mode\n"
            f"[dim]Model: {session.client.model}\n"
            f"Type your message, or /exit to quit.[/dim]",
            border_style="blue",
        )
    )

    _setup_readline()
    session.status_bar.start()

    # Set up cron callback so scheduled jobs can run turns
    from klaude.extensions.cron import set_run_callback, stop_all as _cron_stop_all

    def _cron_turn(prompt: str) -> None:
        """Run a prompt through the session (called by cron timer thread)."""
        try:
            console.print(
                f"\n[dim italic]  (cron job running: {prompt[:60]})[/dim italic]"
            )
            session.turn(prompt)
        except Exception:
            pass  # don't crash the cron thread

    set_run_callback(_cron_turn)

    try:
        while True:
            line = _read_input(console, session)

            # None = exit signal (Ctrl+D)
            if line is None:
                break

            # Empty input (e.g., just pressed Enter, or Ctrl+C at prompt)
            stripped = line.strip()
            if not stripped:
                continue

            # Slash commands
            if stripped.startswith("/"):
                result = _handle_slash_command(stripped, session, console)
                if result is False:
                    break
                if isinstance(result, str):
                    # Skill returned a prompt — run it through the agentic loop
                    try:
                        session.turn(result)
                    except KeyboardInterrupt:
                        console.print("\n[yellow]Interrupted.[/yellow]")
                continue

            # Regular message — run through the agentic loop
            try:
                session.turn(stripped)
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted.[/yellow]")
                continue

    finally:
        session.status_bar.stop()
        _cron_stop_all()  # stop all cron jobs on exit
        _save_readline()
        console.print("[dim]Goodbye.[/dim]")
