"""Test CLI flag parsing for --json and --session-dir."""

from click.testing import CliRunner
from klaude.ui.cli import main


def test_json_flag_recognized():
    """--json flag is accepted by the CLI."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--json" in result.output


def test_session_dir_flag_recognized():
    """--session-dir flag is accepted by the CLI."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--session-dir" in result.output
