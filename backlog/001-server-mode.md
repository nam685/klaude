---
status: done
priority: high
labels: [server, headless, nam-website]
---

# Server / headless mode for nam-website integration

klaude runs headless on a Hetzner VPS (8GB RAM, no GPU) as a sandboxed agent for nam685.de/slops. Visitors submit prompts, admin approves, klaude executes in a sandbox, trace is displayed publicly.

## Required

1. **OpenRouter support** — verify tool calling + streaming with `openrouter/free` meta-model (no GPU on server)
2. **Predictable session output** — `--session-dir` flag or print session path to stdout on exit
3. **Quiet/JSON output mode** — `--quiet` / `--json` flag that suppresses TUI and emits structured JSON summary
4. **SIGTERM graceful shutdown** — save session on kill signal (Celery enforces 600s timeout)

## Nice to have

5. **Token budget enforcement** — verify `--max-tokens` works with OpenRouter free tier
6. **`--cwd` flag** — change working directory before execution

## Context

- Sandbox: separate `klaude` Linux user, iptables (HTTPS-only outbound)
- Invocation: `sudo -u klaude /home/klaude/.local/bin/klaude "{prompt}" --auto-approve`
- Caller: Celery worker in nam-website (`website/tasks.py`)
- See `docs/feature-request-server-mode.md` for full spec
