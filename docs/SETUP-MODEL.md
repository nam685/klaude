# Setting Up the LLM Model

klaude uses a local LLM served via an OpenAI-compatible API. The recommended model is **Qwen3-Coder-Next**.

## Model Overview

**Qwen3-Coder-Next**

- 80B total parameters, 3B active (Mixture-of-Experts architecture)
- 256K context window (native)
- Apache 2.0 license
- Built for agentic coding: tool calling, file editing, bash execution
- HuggingFace: `unsloth/Qwen3-Coder-Next-GGUF`

## Quantization Options

| Quant | Size | RAM needed | Quality | Recommendation |
|-------|------|------------|---------|----------------|
| Q3_K_M | ~36GB | ~38GB | Good | Best for 48GB Mac |
| Q4_K_M | ~45GB | ~48GB | Better | Tight fit on 48GB |
| Q4_K_S | ~42GB | ~44GB | Good | Middle ground |
| Q6_K | ~55GB | ~58GB | Great | Needs 64GB+ |
| Q8_0 | ~72GB | ~75GB | Excellent | Needs 80GB+ |

## Quick Setup (macOS with Homebrew)

```bash
# Install llama.cpp
brew install llama.cpp

# Download and start server (uses the included setup script)
./scripts/setup-model.sh           # downloads Q3_K_M by default
./scripts/setup-model.sh Q4_K_M   # or pick a different quantization

# Start the server
./scripts/setup-model.sh --serve
```

## Manual Server Start

```bash
llama-server \
  -hf unsloth/Qwen3-Coder-Next-GGUF:Q3_K_M \
  --port 8080 \
  -c 8192 \
  -ngl 99
```

## Context Size Tuning

The `-c` flag controls the server-side KV cache (how many tokens the model can hold in memory at once). This is separate from klaude's software-side `context_window` setting (default: 65536 tokens used for tracking/truncation logic).

| `-c` value | Tokens | Notes |
|------------|--------|-------|
| `-c 8192` | 8K | Safe for 48GB Mac with Q3_K_M |
| `-c 16384` | 16K | Needs more RAM headroom |
| `-c 32768` | 32K | Needs 64GB+ for Q3_K_M |

Larger context = more RAM consumed = slower generation. Start at 8192 and increase if needed.

## GPU Offloading

- `-ngl 99` offloads all layers to GPU (Apple Silicon unified memory or CUDA)
- If you get out-of-memory errors, reduce the value: `-ngl 50` keeps some layers on CPU
- Apple Silicon: Metal backend is used automatically, no extra flags needed

## Verification

```bash
# Check server is running
curl http://localhost:8080/v1/models

# Test a completion
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-coder-next", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Alternative Models

klaude works with any OpenAI-compatible API endpoint. Other capable coding models:

- **Qwen2.5-Coder-32B** — smaller, still strong at coding, fits comfortably on 48GB
- **DeepSeek-Coder-V2** — another MoE model, similar memory profile
- Any model served via **vLLM**, **Ollama**, or other OpenAI-compatible servers

To point klaude at a different server or model, set the `base_url` and `model` in your config.
