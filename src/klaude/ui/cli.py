"""CLI entry point — the `klaude` command.

Modes:
    klaude                    -> interactive REPL
    klaude "fix the bug"      -> one-shot task
    klaude -c                 -> resume last session (REPL)
    klaude --resume <id>      -> resume specific session (REPL)
    klaude -c "more work"     -> resume last session + one-shot task
    klaude --json "task"      -> headless mode (structured JSON output)

Config resolution: CLI flags > env vars > .klaude.toml > defaults.
"""

import json
import os
import signal
import sys
import time
from pathlib import Path

import click
from rich.console import Console

from klaude.config import load_config
from klaude.core.client import LLMClient
from klaude.core.loop import Session
from klaude.core.session_store import load_session
from klaude.core.trace import TraceWriter

console = Console()

# Module-level reference for SIGTERM handler to access
_active_session: Session | None = None
_json_mode: bool = False
_session_dir_override: str | None = None
_json_printed: bool = False  # prevent double-printing on SIGTERM


def _build_json_summary(
    session: Session,
    session_id: str,
    session_path: str,
    error: str | None = None,
) -> dict:
    """Build the JSON summary dict for --json output."""
    return {
        "session_id": session_id,
        "session_path": session_path,
        "turn_count": session.turn_count,
        "token_count": session.tracker.total_tokens,
        "tool_calls": session.total_tool_calls,
        "error": error,
    }


def _print_json_summary(
    session: Session | None = None,
    session_id: str | None = None,
    session_path: str | None = None,
    error: str | None = None,
) -> None:
    """Print a JSON summary to stdout. Always prints in --json mode (once)."""
    global _json_printed
    if not _json_mode or _json_printed:
        return
    _json_printed = True
    if session is not None:
        summary = _build_json_summary(session, session_id or "", session_path or "", error=error)
    else:
        summary = {
            "session_id": None,
            "session_path": None,
            "turn_count": 0,
            "token_count": 0,
            "tool_calls": 0,
            "error": error,
        }
    print(json.dumps(summary), flush=True)


def _save_and_summarize(
    session: Session,
    error: str | None = None,
) -> None:
    """Finalize trace and print JSON summary if in --json mode."""
    sid = None
    session_path = None

    if session.turn_count > 0 and session.trace:
        session.trace.finalize()
        sid = session.trace.session_id
        session_path = str(session.trace.path.resolve())
        # Prune old sessions to keep directory bounded
        from klaude.core.session_store import _prune_old_sessions
        _prune_old_sessions(session.trace.path.parent)

    _print_json_summary(session, sid, session_path, error=error)


def _sigterm_handler(signum: int, frame: object) -> None:
    """Handle SIGTERM: save session and exit cleanly."""
    try:
        if _active_session is not None:
            _save_and_summarize(_active_session, error="SIGTERM")
        else:
            _print_json_summary(error="SIGTERM")
    except Exception:
        pass
    sys.exit(1)


@click.command()
@click.argument("task", nargs=-1)
@click.option(
    "--base-url",
    default=None,
    envvar="KLAUDE_BASE_URL",
    help="LLM API base URL",
)
@click.option(
    "--model",
    default=None,
    envvar="KLAUDE_MODEL",
    help="Model name to use",
)
@click.option(
    "--context-window",
    default=None,
    envvar="KLAUDE_CONTEXT_WINDOW",
    type=int,
    help="Context window size in tokens",
)
@click.option(
    "--auto-approve",
    is_flag=True,
    default=False,
    envvar="KLAUDE_AUTO_APPROVE",
    help="Skip permission prompts for dangerous tools",
)
@click.option(
    "--max-tokens",
    default=None,
    envvar="KLAUDE_MAX_TOKENS",
    type=int,
    help="Max tokens per session (0 = unlimited)",
)
@click.option(
    "--profile",
    default=None,
    envvar="KLAUDE_PROFILE",
    help="Config profile to use (from .klaude.toml [profiles.<name>])",
)
@click.option(
    "-c",
    "--continue",
    "continue_session",
    is_flag=True,
    default=False,
    help="Resume the last session",
)
@click.option(
    "--resume",
    "resume_id",
    default=None,
    help="Resume a specific session by ID (see /sessions)",
)
@click.option(
    "--json",
    "json_mode",
    is_flag=True,
    default=False,
    envvar="KLAUDE_JSON",
    help="Headless mode: suppress TUI, print JSON summary on exit",
)
@click.option(
    "--session-dir",
    default=None,
    envvar="KLAUDE_SESSION_DIR",
    help="Override directory for session files",
)
def main(
    task: tuple[str, ...],
    base_url: str | None,
    model: str | None,
    context_window: int | None,
    auto_approve: bool,
    max_tokens: int | None,
    profile: str | None,
    continue_session: bool,
    resume_id: str | None,
    json_mode: bool,
    session_dir: str | None,
) -> None:
    """klaude — DIY Claude Code harness powered by open-source LLMs.

    With no arguments, starts an interactive REPL:

        klaude

    Or pass a task for one-shot mode:

        klaude read main.py and explain it

        klaude "fix the bug in utils.py"

    Resume the last session:

        klaude -c

    Headless mode (for server integration):

        klaude --json "fix the bug"
    """
    global _active_session, _json_mode, _session_dir_override
    _json_mode = json_mode
    _session_dir_override = session_dir

    # --json implies --auto-approve (headless can't prompt)
    if json_mode:
        auto_approve = True

    # --json without a task is an error (check before setup)
    if not task and json_mode:
        _print_json_summary(error="--json requires a task argument")
        raise SystemExit(1)

    # Register SIGTERM handler
    signal.signal(signal.SIGTERM, _sigterm_handler)

    # Top-level try/finally ensures JSON is always printed, even on setup crash
    try:
        # Load config from .klaude.toml (CLI flags override)
        cfg = load_config(profile=profile)

        # CLI flags override config file values
        effective_model = model or cfg.model
        effective_base_url = base_url or cfg.base_url
        effective_context_window = context_window or cfg.context_window
        effective_max_tokens = max_tokens if max_tokens is not None else cfg.max_tokens
        effective_auto_approve = auto_approve or cfg.auto_approve

        # In --json mode, use a quiet console that discards output
        active_console = Console(file=open(os.devnull, "w")) if json_mode else console

        client = LLMClient(
            base_url=effective_base_url,
            model=effective_model,
            api_key=cfg.api_key,
            thinking=cfg.thinking,
        )
        session = Session(
            client=client,
            context_window=effective_context_window,
            console=active_console,
            auto_approve=effective_auto_approve,
            max_tokens=effective_max_tokens,
            config=cfg,
            quiet=json_mode,
            model_name=effective_model,
        )
        _active_session = session

        # Set up session directory for ATIF trace files
        _sd = Path(session_dir) if session_dir else Path(os.getcwd()) / ".klaude" / "sessions"
        _sd.mkdir(parents=True, exist_ok=True)

        # --- Resume previous session ---
        if continue_session or resume_id:
            session_dir_path = Path(session_dir) if session_dir else None
            saved = load_session(resume_id, session_dir=session_dir_path)
            if saved:
                messages, turns, saved_at, sid = saved
                session.restore(messages, turns)
                # Point trace writer at the existing ATIF file
                if session_dir_path:
                    resume_trace_path = session_dir_path / f"{sid}.json"
                else:
                    resume_trace_path = Path(os.getcwd()) / ".klaude" / "sessions" / f"{sid}.json"
                if resume_trace_path.exists():
                    session.trace = TraceWriter.from_existing(resume_trace_path)
                if not json_mode:
                    active_console.print(
                        f"[dim]Resumed session {sid} ({turns} turns, "
                        f"{session.tracker.total_tokens:,} tokens, "
                        f"saved {saved_at})[/dim]"
                    )
            else:
                if not json_mode:
                    active_console.print("[yellow]No previous session found.[/yellow]")

        # Create fresh trace writer if not resuming
        if session.trace is None:
            _trace_id = time.strftime("%Y%m%d-%H%M%S")
            session.trace = TraceWriter(_sd / f"{_trace_id}.json", model_name=effective_model)

        if not task:
            # --- REPL mode (never --json, that case is handled above) ---
            from klaude.ui.repl import repl

            try:
                repl(session)
            except Exception as e:
                active_console.print(f"\n[red]Error: {e}[/red]")
                raise SystemExit(1)
            finally:
                _active_session = None
                _save_and_summarize(session)
        else:
            # --- One-shot mode (normal or --json) ---
            user_message = " ".join(task)
            if not json_mode:
                active_console.print(
                    f"[dim]Model: {effective_model} @ {effective_base_url}[/dim]"
                )
                active_console.print()

            session.status_bar.start()
            error = None
            try:
                session.turn(user_message)
            except KeyboardInterrupt:
                error = "interrupted"
                if not json_mode:
                    active_console.print("\n[yellow]Interrupted.[/yellow]")
            except Exception as e:
                error = str(e)
                if not json_mode:
                    active_console.print(f"\n[red]Error: {e}[/red]")
            finally:
                session.status_bar.stop()
                _active_session = None
                _save_and_summarize(session, error=error)

            if error:
                raise SystemExit(1)

    except SystemExit:
        raise  # let SystemExit propagate
    except Exception as e:
        # Crash during setup — still print JSON if in --json mode
        _print_json_summary(error=str(e))
        if not json_mode:
            console.print(f"\n[red]Error: {e}[/red]")
        raise SystemExit(1)
