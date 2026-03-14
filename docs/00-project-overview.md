# klaude — DIY Claude Code Harness

**Goal:** Build a Claude Code-like agentic coding CLI from scratch, powered by open-source LLMs (starting with Qwen3-Coder-30B-A3B). Educational project — learn by building.

## Why?

- Understand how agentic coding tools actually work under the hood
- Run locally on your own hardware — no API costs, full privacy
- Learn the architecture patterns: tool calling, agentic loops, context management
- Have a hackable base to experiment with different models and features

## Target Model

**Qwen3-Coder-30B-A3B** (mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit)
- 30B total params, 3B active (Mixture-of-Experts)
- 128K context window
- MIT license
- Trained specifically for agentic coding (tool calling, file editing, bash execution)
- Served via mlx-lm on Apple Silicon

## Hardware

**Current:** Apple M4 Pro, 48GB unified memory
- Runs Qwen3-Coder-30B-A3B 8-bit (~30GB) — fits comfortably
- Context limited to 32K tokens (default)
- Perfectly usable for development and testing

**Future:** Dedicated hardware (see docs/06-hardware-guide.md)

## Tech Stack

- Python 3.12+ with `uv`
- `openai` SDK — talks to any OpenAI-compatible server
- `rich` — terminal formatting and streaming
- `click` — CLI
- `mlx-lm` (mlx_lm.server) — local model serving on Apple Silicon

## Project Structure

```
klaude/
├── docs/                    # Study materials & planning (you are here)
├── src/klaude/
│   ├── __init__.py
│   ├── cli.py               # CLI entry point
│   ├── loop.py              # Core agentic loop
│   ├── client.py            # LLM client (OpenAI-compatible)
│   ├── tools/               # Tool implementations
│   │   ├── __init__.py
│   │   ├── registry.py      # Tool registry & dispatcher
│   │   ├── read_file.py
│   │   ├── write_file.py
│   │   ├── bash.py
│   │   ├── glob_search.py
│   │   └── grep_search.py
│   ├── context.py           # Context window management
│   └── prompt.py            # System prompt
├── scripts/
│   └── setup-model.sh       # Download & serve Qwen3-Coder-30B-A3B
├── pyproject.toml
└── README.md
```
