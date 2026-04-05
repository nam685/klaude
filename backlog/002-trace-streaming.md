---
status: todo
priority: high
labels: [server, nam-website, traces]
---

# Incremental trace output for live progress

nam-website's `/slops` page shows agent traces publicly. Currently klaude only saves session history as a single JSON dump on exit, so running missions just show "running..." until completion.

## What to do

Add a `TraceWriter` in `loop.py` that appends one JSON object per step (JSONL) during execution. External consumers (nam-website) can tail/poll the file for live progress.

## Options

1. **TraceWriter in the agentic loop** (preferred) — `loop.py` calls it after each assistant response and tool result
2. **Post-tool hook** — use existing `hooks.py` to append a step after each tool execution
3. **Periodic session dump** — re-save full JSON after each turn (wasteful)

## Format

- JSONL during execution (append-only, easy to tail)
- Convert to ATIF v1.4 on completion (Harbor compatibility)
- Or: write ATIF incrementally (one step per line)

## Context

- Consumer: nam-website `GET /api/slops/<id>/trace/` endpoint
- See `docs/feature-request-trace-streaming.md` for full spec
