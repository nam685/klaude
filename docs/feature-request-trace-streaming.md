# Feature Request: Incremental Trace Output

## Context

nam-website's `/slops` page runs klaude missions and displays agent traces publicly. For running missions, the website polls and reads the trace file to show live progress.

Currently klaude only saves session history as a single JSON dump on exit (`session_store.py`). This means traces are only available after completion.

## Request

Add an option for klaude to write trace steps incrementally during execution, so external consumers can tail/poll the file for live progress.

## Options to investigate

1. **Post-tool hook** — use the existing `hooks.py` extension to append a step after each tool execution. Least invasive, but hooks are user-configured, not built-in.

2. **Trace writer in the agentic loop** — add a `TraceWriter` that `loop.py` calls after each assistant response and tool result. Writes one JSON object per step (JSONL). Most reliable.

3. **Periodic session dump** — re-save `session_store.py`'s full JSON after each turn. Simple but wasteful (rewrites entire file each time). External consumer must re-parse the whole file on each poll.

## Format considerations

- ATIF v1.4 (Harbor) is the target format for the final trace. Whether to write ATIF incrementally (one step per line as JSONL) or write klaude's native format and convert post-hoc is an open question.
- JSONL is simpler for append-only writes and tailing.
- A single ATIF JSON document is better for compatibility with Harbor tooling.
- Could do both: JSONL during execution, convert to ATIF on completion.

## Priority

Needed for nam-website `/slops` live trace rendering. Without this, running missions just show "running..." until completion.
