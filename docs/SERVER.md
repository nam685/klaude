# Server / Headless Mode

klaude can run as a headless agent — no TUI, JSON output, machine-parseable results. This is how [nam685.de/slops](https://nam685.de/slops) uses it: a Celery worker calls klaude per sandbox job and reads the JSON result.

## Quick Start

```bash
klaude --json --session-dir /path/to/traces "your prompt here"
```

klaude runs, suppresses all TUI output, and prints one JSON object to stdout on completion.

## CLI Flags for Server Use

| Flag | Description |
|------|-------------|
| `--json` | Suppress TUI, print JSON summary to stdout |
| `--session-dir <path>` | Override where session files are saved |
| `--auto-approve` | Skip all permission prompts (implied by `--json`) |
| `--max-tokens N` | Cap token usage for the session (0 = unlimited) |

`--json` implies `--auto-approve` — headless runs don't have a human to approve tool calls.

## JSON Output Format

On completion (success or error), klaude prints exactly one JSON object:

```json
{
  "session_id": "20260405-143022",
  "session_path": "/path/to/traces/20260405-143022.json",
  "turn_count": 5,
  "token_count": 1234,
  "tool_calls": 8,
  "error": null
}
```

| Key | Type | Description |
|-----|------|-------------|
| `session_id` | string | Timestamp-based session identifier |
| `session_path` | string | Absolute path to the saved session file |
| `turn_count` | int | Number of model turns completed |
| `token_count` | int | Approximate tokens used |
| `tool_calls` | int | Number of tool calls made |
| `error` | string \| null | Error message, or `null` on success |

The JSON is always printed — even on error. Check `error` and the exit code together.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (model error, timeout, SIGTERM, etc.) |

## SIGTERM Handling

klaude installs a SIGTERM handler. When the process receives SIGTERM (e.g. from a subprocess timeout), it saves the session and prints the JSON with `error: "SIGTERM"` before exiting with code 1.

```json
{
  "session_id": "20260405-143022",
  "session_path": "/path/to/traces/20260405-143022.json",
  "turn_count": 3,
  "token_count": 890,
  "tool_calls": 4,
  "error": "SIGTERM"
}
```

## OpenRouter Config (no GPU)

For server deployments without a local GPU, use OpenRouter:

```toml
# .klaude.toml
[default]
model = "openrouter/auto"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
context_window = 32768
max_tokens = 8192
auto_approve = true
```

Set the key in the environment:

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

klaude uses the `openai` SDK, so any OpenAI-compatible endpoint works.

## Example Integration

Python subprocess pattern used by nam-website's Celery worker:

```python
import json
import subprocess

result = subprocess.run(
    ["klaude", "--json", "--session-dir", "/path/to/traces", "your prompt here"],
    capture_output=True, text=True, timeout=600,
    cwd="/path/to/workspace",
)
output = json.loads(result.stdout)
print(f"Session: {output['session_path']}")
print(f"Tools used: {output['tool_calls']}")
if output["error"]:
    print(f"Error: {output['error']}")
```

- `capture_output=True` — prevents klaude output from leaking to the worker's stdout
- `timeout=600` — sends SIGTERM after 10 minutes; klaude saves the session before dying
- `cwd` — sets the workspace directory klaude operates in
- Always check `result.returncode` in addition to `output["error"]`

## Sandbox Setup

The full sandbox setup (separate Linux user, iptables rules, deploy key, Celery integration) is documented in `nam-website/docs/server-setup-klaude.md`.
