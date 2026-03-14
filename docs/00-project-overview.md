# klaude — DIY Claude Code Harness

**Goal:** Build a Claude Code-like agentic coding CLI from scratch, powered by open-source LLMs (starting with Qwen3-Coder-Next). Educational project — learn by building.

## Why?

- Understand how agentic coding tools actually work under the hood
- Run locally on your own hardware — no API costs, full privacy
- Learn the architecture patterns: tool calling, agentic loops, context management
- Have a hackable base to experiment with different models and features

## Target Model

**Qwen3-Coder-Next** (Feb 2026)
- 80B total params, 3B active (Mixture-of-Experts)
- 256K context window
- Apache 2.0 license
- Trained specifically for agentic coding (tool calling, file editing, bash execution)
- 44.3% on SWE-Bench Pro
- Runs on consumer hardware via llama.cpp

## Hardware

**Current:** Apple M4 Pro, 48GB unified memory
- Can run Q4_K_M (4-bit) quantization (~45GB)
- Context may need limiting to ~64K-100K tokens
- Perfectly usable for development and testing

**Future:** Dedicated hardware (see docs/06-hardware-guide.md)

## Tech Stack

- Python 3.12+ with `uv`
- `openai` SDK — talks to any OpenAI-compatible server
- `rich` — terminal formatting and streaming
- `click` — CLI
- `llama.cpp` (llama-server) — local model serving

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
│   └── setup-model.sh       # Download & serve Qwen3-Coder-Next
├── pyproject.toml
└── README.md
```
