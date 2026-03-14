# Setting Up the LLM Model

klaude uses a local LLM served via an OpenAI-compatible API. The recommended model is **Qwen3-Coder-30B-A3B**.

## Model Overview

**Qwen3-Coder-30B-A3B**

- 30B total parameters, 3B active (Mixture-of-Experts architecture)
- 128K context window (native)
- MIT license
- Built for agentic coding: tool calling, file editing, bash execution
- HuggingFace: `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF`

## Quantization Options

| Quant | Size | RAM needed | Quality | Recommendation |
|-------|------|------------|---------|----------------|
| Q3_K_M | ~14GB | ~16GB | Good | Budget option |
| Q4_K_M | ~18.6GB | ~21GB | Best | **Recommended for 48GB Mac** |
| Q6_K | ~24GB | ~27GB | Great | Needs 32GB+ |
| Q8_0 | ~32GB | ~35GB | Excellent | Needs 48GB+ |

## Quick Setup (macOS with Homebrew)

```bash
# Install llama.cpp
brew install llama.cpp

# Download and start server (uses the included setup script)
./scripts/setup-model.sh           # downloads Q4_K_M by default
./scripts/setup-model.sh Q3_K_M   # or pick a different quantization

# Start the server
./scripts/setup-model.sh --serve
```

## Manual Server Start

```bash
llama-server \
  -m ~/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf \
  --port 8080 \
  -c 32768 \
  -ngl 99
```

## Context Size Tuning

The `-c` flag controls the server-side KV cache (how many tokens the model can hold in memory at once).

| `-c` value | Tokens | Notes |
|------------|--------|-------|
| `-c 8192` | 8K | Minimum, saves RAM |
| `-c 32768` | 32K | **Recommended** for 48GB Mac with Q4_K_M |
| `-c 65536` | 64K | Needs 48GB+ RAM headroom |

Larger context = more RAM consumed = slower generation. The default setup uses 32K (~24GB total RAM with Q4_K_M), leaving headroom on a 48GB machine.

## GPU Offloading

- `-ngl 60` is the default — partial GPU offload, avoids OOM at 32K context on 48GB Mac
- `-ngl 99` offloads all layers but may OOM with large context windows
- If you get out-of-memory errors, reduce `-ngl` (e.g. `-ngl 40`) or reduce `-c`
- Apple Silicon: Metal backend is used automatically, no extra flags needed

## Verification

```bash
# Check server is running
curl http://localhost:8080/v1/models

# Test a completion
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-coder-30b-a3b", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Alternative Models

klaude works with any OpenAI-compatible API endpoint. Other capable coding models:

- **Qwen3-Coder-Next** (80B MoE, Apache 2.0) — previous recommendation; 36GB Q3_K_M, tight fit on 48GB
- **Qwen2.5-Coder-32B** — smaller, still strong at coding, fits comfortably on 48GB
- **DeepSeek-Coder-V2** — another MoE model, similar memory profile
- Any model served via **vLLM**, **Ollama**, or other OpenAI-compatible servers

To point klaude at a different server or model, set the `base_url` and `model` in your config.
