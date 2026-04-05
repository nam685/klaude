# Server Mode Design

Make klaude work as a headless agent on a VPS for nam685.de/slops integration.

## Context

klaude is deployed on a Hetzner VPS (8GB RAM, no GPU) as a sandboxed agent. Visitors submit prompts on the website, admin approves, a Celery worker invokes klaude as a separate Linux user, and the trace is displayed publicly.

**Current invocation:**
```bash
sudo -u klaude /home/klaude/.local/bin/klaude "{prompt}" --auto-approve
```

**Problems:**
1. No structured output — caller must scan `.klaude/sessions/` and guess which file is the right one
2. Rich TUI output (spinners, colors, status bar) is noise in headless mode
3. If klaude is killed mid-execution (600s Celery timeout), the session file may not be saved
4. OpenRouter compatibility is unverified

## Changes

### 1. `--json` flag

New CLI flag in `cli.py`. When set:

- Suppresses all TUI output: no Rich console, no spinners, no streamed text, no status bar
- Implies `--auto-approve` (headless can't prompt for input)
- On exit, prints a single JSON object to stdout:

```json
{
  "session_id": "20260405-143022",
  "session_path": "/home/klaude/workspace/playground/.klaude/sessions/20260405-143022.json",
  "turn_count": 5,
  "token_count": 1234,
  "tool_calls": 8,
  "error": null
}
```

- On failure, same structure with `error` populated. JSON is always printed, even on crash (wrap in try/finally).
- Errors and warnings go to stderr.
- `session_path` is the absolute path to the saved session file.

**Implementation:** Pass a `quiet=True` flag (derived from `--json`) through to `Session`, `StatusBar`, and `consume_stream`. Each component skips output when quiet. The JSON summary is assembled in `cli.py` after the session completes.

### 2. `--session-dir <path>` flag

New CLI flag in `cli.py`. Overrides where session files are saved.

- Default: `.klaude/sessions/` in cwd (unchanged)
- When set: `save_session()` and `_sessions_dir()` in `session_store.py` accept an optional `session_dir: Path | None` parameter
- The `--json` output's `session_path` reflects the actual save location
- Directory is created if it doesn't exist (existing behavior of `_sessions_dir()`)

**Why:** Lets the caller control where sessions land. `tasks.py` passes `--session-dir /home/klaude/traces/task-42/` so it knows exactly where to read the result, and sessions don't pile up in the workspace.

### 3. SIGTERM graceful shutdown

Register `signal.signal(signal.SIGTERM, handler)` early in `main()`.

The handler:
1. Calls `save_session()` with the current session state
2. If `--json`, prints the JSON summary to stdout (with `error: "SIGTERM"`)
3. Calls `sys.exit(0)` to trigger normal cleanup

**Access to session state:** Store a module-level reference to the active `Session` object in `cli.py` so the signal handler can reach it. Set it after session creation, clear it on exit.

**Edge cases:**
- If SIGTERM arrives before the session starts (during setup), handler exits without saving
- If SIGTERM arrives during `save_session()` itself, the file may be partial — acceptable, the caller checks for valid JSON
- SIGKILL (sent if SIGTERM handler takes too long) cannot be caught — this is expected

### 4. OpenRouter verification

No code changes expected. klaude uses the `openai` SDK and OpenRouter is OpenAI-compatible. Verify:

- Tool calls work with `openrouter/free` meta-model
- Streaming works
- Context window is respected
- If routed to a model without tool calling support, klaude's text-based `tool_call_parser.py` handles the fallback

Document any quirks in `docs/TROUBLESHOOTING.md`.

## Files to change

| File | Change |
|------|--------|
| `src/klaude/ui/cli.py` | `--json` and `--session-dir` flags, SIGTERM handler, quiet console, JSON summary output |
| `src/klaude/core/session_store.py` | Optional `session_dir` parameter on `save_session()` and `_sessions_dir()` |
| `src/klaude/core/loop.py` | Expose `total_tool_calls` counter on `Session` for JSON summary |
| `src/klaude/ui/status_bar.py` | No-op `start()`/`stop()`/`update()` when `quiet=True` |
| `src/klaude/core/stream.py` | Skip streaming print when `quiet=True` |

## Caller changes (nam-website)

After klaude ships server mode, `website/tasks.py` simplifies to:

```python
result = subprocess.run(
    ["sudo", "-u", KLAUDE_USER, KLAUDE_BIN, mission.prompt,
     "--json", "--session-dir", trace_dir],
    capture_output=True, text=True, timeout=600, cwd=workspace_dir,
)
output = json.loads(result.stdout)
# output: {session_id, session_path, turn_count, token_count, tool_calls, error}
```

No more scanning session directories or estimating token counts.

## Out of scope

- `--cwd` flag — caller handles via `subprocess.run(cwd=...)`
- Trace streaming / incremental output — separate spec (backlog #002)
- Token budget changes — existing `--max-tokens` should work, verify during OpenRouter testing
