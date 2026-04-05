# Feature Request: Server / Headless Mode

klaude is deployed on a VPS (Hetzner, 8GB RAM, no GPU) as a sandboxed agent for [nam685.de/slops](https://nam685.de/slops). It runs headless via Celery: visitors submit prompts, admin approves, klaude executes in a sandbox, trace is displayed publicly.

## Invocation

```bash
sudo -u klaude /home/klaude/.local/bin/klaude "{prompt}" --auto-approve
```

Working directory set by the caller via `subprocess.run(cwd=workspace_dir)`.

## Required Changes

### 1. OpenRouter support

The server has no GPU — klaude must use a remote API. Config:

```toml
[default]
model = "openrouter/free"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
context_window = 32768
```

klaude uses the `openai` SDK so OpenRouter should work out of the box. But `openrouter/free` is a meta-model that routes to whatever's free — tool calling support may vary. Things to verify:
- Tool calls work reliably (or degrade gracefully if the routed model doesn't support them)
- Streaming works
- Context window is respected

### 2. Predictable session output

The caller (nam-website `tasks.py`) reads the session file after execution from `.klaude/sessions/` in the working directory. Currently it grabs the latest file by sort order — fragile if a workspace has old sessions.

Options (pick one):
- **`--session-dir <path>`** flag to override where sessions are saved
- **Print session file path to stdout** on exit so the caller can parse it
- **Return session ID** so the caller can construct the path

### 3. Quiet/JSON output mode

In one-shot headless mode, rich console output (spinners, colors, status bars) is noise. Add a `--quiet` or `--json` flag that:
- Suppresses all TUI output
- On completion, prints a single JSON object to stdout:

```json
{
  "session_id": "20260405-143022",
  "session_path": ".klaude/sessions/20260405-143022.json",
  "turn_count": 5,
  "token_count": 1234,
  "tool_calls": 8,
  "error": null
}
```

This replaces the caller's need to parse session files and estimate tokens.

### 4. SIGTERM graceful shutdown

nam-website's Celery task kills klaude after 600s via subprocess timeout (SIGTERM). Currently the session file may not be saved if klaude is mid-execution. Add:
- Signal handler for SIGTERM that saves the session before exit
- Or periodic session checkpointing during long runs

## Nice to Have

### 5. Token budget enforcement

`--max-tokens` exists. Verify it works with OpenRouter free tier. The server should cap missions to prevent runaway usage.

### 6. `--cwd` flag

Add `--cwd <path>` to change working directory before execution. Currently the caller sets this via `subprocess.run(cwd=...)` which works, but an explicit flag is cleaner and matches Claude Code's behavior.

## Context

- Sandbox: separate `klaude` Linux user, iptables (HTTPS-only outbound), no access to `/home/nam`
- Caller: Celery worker in nam-website (`website/tasks.py`)
- Playground repo: `github.com/nam685/klaude-playground` (deploy key, SSH over port 443)
- See `nam-website/docs/server-setup-klaude.md` for full setup
