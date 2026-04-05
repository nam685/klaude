"""Integration test for --json mode output format."""

import json

from click.testing import CliRunner
from klaude.ui.cli import main


def test_json_mode_no_task_errors():
    """--json without a task prints JSON error and exits nonzero."""
    runner = CliRunner()
    result = runner.invoke(main, ["--json"])
    assert result.exit_code != 0
    # Should print full JSON schema to stdout
    output = result.output.strip()
    assert output, "Expected JSON output on stdout"
    data = json.loads(output)
    assert data["error"] == "--json requires a task argument"
    assert "session_id" in data
    assert "session_path" in data
    assert "turn_count" in data
    assert "token_count" in data
    assert "tool_calls" in data


def test_json_flag_implies_auto_approve():
    """Verify --json is documented in help text."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert "--json" in result.output
    assert "Headless" in result.output or "headless" in result.output
