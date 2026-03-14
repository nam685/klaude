# Qwen3-Coder-Next — Model Guide

> **Note:** This doc covers the original model choice. klaude now uses Qwen3-Coder-30B-A3B via mlx-lm — see SETUP-MODEL.md. The content below is kept as historical reference.

## Overview

| Property          | Value                                    |
|-------------------|------------------------------------------|
| Developer         | Alibaba Qwen Team                        |
| Release           | February 2026                            |
| Architecture      | Mixture-of-Experts (MoE)                 |
| Total params      | 80B                                      |
| Active params     | 3B (only these run per token)            |
| Context window    | 256K tokens                              |
| License           | Apache 2.0                               |
| SWE-Bench Pro     | 44.3%                                    |
| Attention         | Gated DeltaNet (75% linear, 25% full)    |
| Training focus    | Agentic coding, tool calling, file edits |

## Why This Model?

1. **Cheap to run** — only 3B active params despite 80B total
2. **Built for agents** — trained on Claude Code-style tool schemas
3. **Runs on consumer hardware** — single GPU or Apple Silicon
4. **Open source** — Apache 2.0, full weights available
5. **256K context** — enough for large codebases

## Memory Requirements by Quantization

| Quantization | Model Size | RAM Needed | Quality     | Your Mac (48GB) |
|-------------|------------|------------|-------------|-----------------|
| Q2_K        | ~20GB      | ~25GB      | Usable      | Comfortable     |
| Q3_K_M      | ~28GB      | ~33GB      | Good        | Comfortable     |
| Q4_K_M      | ~38GB      | ~45GB      | Very good   | Tight but works |
| Q4_K_XL     | ~40GB      | ~46GB      | Best 4-bit  | Very tight      |
| Q8_0        | ~70GB      | ~85GB      | Near native | Won't fit       |

**Recommendation for 48GB Mac:** Start with Q3_K_M for comfortable headroom,
or Q4_K_M for best quality (but limit context to ~64K tokens).

## How to Download and Run

### Option 1: llama.cpp (Recommended for Mac)

```bash
# Install llama.cpp
brew install llama.cpp

# Run directly from HuggingFace (auto-downloads)
llama-server \
  -hf unsloth/Qwen3-Coder-Next-GGUF:Q3_K_M \
  --port 8080 \
  -c 65536 \
  --n-gpu-layers 99

# The model will be cached in ~/.cache/llama.cpp/
```

This starts an OpenAI-compatible API at `http://localhost:8080/v1/`.

### Option 2: Download First, Then Run

```bash
# Install huggingface-hub CLI
uv tool install huggingface-hub

# Download specific quantization
huggingface-cli download unsloth/Qwen3-Coder-Next-GGUF \
  Qwen3-Coder-Next-Q3_K_M.gguf \
  --local-dir ~/models/

# Run with llama-server
llama-server \
  -m ~/models/Qwen3-Coder-Next-Q3_K_M.gguf \
  --port 8080 \
  -c 65536 \
  --n-gpu-layers 99
```

### Key llama-server Flags

| Flag | Purpose |
|------|---------|
| `-c 65536` | Context size (tokens). Reduce if tight on RAM |
| `--n-gpu-layers 99` | Offload all layers to GPU (Apple Silicon unified memory) |
| `--port 8080` | API port |
| `-ngl 99` | Short form of --n-gpu-layers |
| `--chat-template chatml` | Force chat template (usually auto-detected) |

## Connecting Our Harness

Once llama-server is running, our code talks to it like any OpenAI API:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed"  # local server doesn't check
)

response = client.chat.completions.create(
    model="qwen3-coder-next",
    messages=[{"role": "user", "content": "Hello!"}],
    tools=[...],
)
```

## Important Notes

- **Update llama.cpp regularly** — Qwen3-Coder-Next needs a Feb 2026+ build
  for correct tool parsing (fixed key_gdiff calculation bug)
- **Unsloth Dynamic 2.0 GGUFs** perform better than standard quantizations
  at the same size — always prefer these
- MoE models efficiently split: dense layers → GPU, sparse experts → CPU RAM.
  llama.cpp handles this automatically on Apple Silicon.

## References

- [Qwen3-Coder-Next on HuggingFace](https://huggingface.co/Qwen/Qwen3-Coder-Next)
- [Unsloth GGUF Downloads](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF)
- [Running Locally Guide (Unsloth)](https://unsloth.ai/docs/models/qwen3-coder-next)
- [llama.cpp Qwen Guide](https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html)
- [Run Qwen3-Coder-Next Locally (CoderSera)](https://ghost.codersera.com/blog/run-qwen3-coder-next-locally-2026/)
