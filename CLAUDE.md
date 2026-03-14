# klaude — Project Instructions

## Code Style
- All functions must have return type annotations
- Use `uv run` for all Python commands
- Minimal dependencies — no heavy frameworks
- Tools are simple functions + JSON schemas, no abstract base classes

## Project Structure
- `src/klaude/` — main package
  - `core/` — loop, client, context, compaction, history, stream, prompt
  - `ui/` — cli, repl, render
  - `extensions/` — plugins, mcp, skills, hooks, team, cron
  - `tools/` — 18 tool files + registry
  - Top-level: config, permissions, memory
- `docs/` — study materials and implementation notes
- `scripts/` — helper scripts (model setup, etc.)

## Running
- `uv sync` to install deps
- `uv run klaude "task"` to run the CLI
- LLM backend: mlx-lm (mlx_lm.server) on localhost:8080
