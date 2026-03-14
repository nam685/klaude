"""CLI entry point — the `klaude` command.

Modes:
    klaude                    -> interactive REPL
    klaude "fix the bug"      -> one-shot task
    klaude -c                 -> resume last session (REPL)
    klaude --resume <id>      -> resume specific session (REPL)
    klaude -c "more work"     -> resume last session + one-shot task

Config resolution: CLI flags > env vars > .klaude.toml > defaults.
"""

import click
from rich.console import Console

from klaude.config import load_config
from klaude.core.client import LLMClient
from klaude.core.loop import Session
from klaude.core.session_store import load_session, save_session

console = Console()


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
) -> None:
    """klaude — DIY Claude Code harness powered by open-source LLMs.

    With no arguments, starts an interactive REPL:

        klaude

    Or pass a task for one-shot mode:

        klaude read main.py and explain it

        klaude "fix the bug in utils.py"

    Resume the last session:

        klaude -c
    """
    # Load config from .klaude.toml (CLI flags override)
    cfg = load_config(profile=profile)

    # CLI flags override config file values
    effective_model = model or cfg.model
    effective_base_url = base_url or cfg.base_url
    effective_context_window = context_window or cfg.context_window
    effective_max_tokens = max_tokens if max_tokens is not None else cfg.max_tokens
    effective_auto_approve = auto_approve or cfg.auto_approve

    client = LLMClient(
        base_url=effective_base_url,
        model=effective_model,
        api_key=cfg.api_key,
    )
    session = Session(
        client=client,
        context_window=effective_context_window,
        console=console,
        auto_approve=effective_auto_approve,
        max_tokens=effective_max_tokens,
        config=cfg,
    )

    # --- Resume previous session ---
    if continue_session or resume_id:
        saved = load_session(resume_id)
        if saved:
            messages, turns, saved_at, sid = saved
            session.restore(messages, turns)
            console.print(
                f"[dim]Resumed session {sid} ({turns} turns, "
                f"{session.tracker.total_tokens:,} tokens, "
                f"saved {saved_at})[/dim]"
            )
        else:
            console.print("[yellow]No previous session found.[/yellow]")

    if not task:
        # --- REPL mode ---
        from klaude.ui.repl import repl

        try:
            repl(session)
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            if session.turn_count > 0:
                save_session(session.history.messages, session.turn_count)
    else:
        # --- One-shot mode ---
        user_message = " ".join(task)
        console.print(f"[dim]Model: {effective_model} @ {effective_base_url}[/dim]")
        console.print()

        session.status_bar.start()
        try:
            session.turn(user_message)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            session.status_bar.stop()
            if session.turn_count > 0:
                save_session(session.history.messages, session.turn_count)
