# Setting Up the LLM Model

klaude uses a local LLM served via an OpenAI-compatible API.

## Recommended: Qwen3-Coder-30B-A3B on mlx-lm

**Model:** `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit` (~30GB)

- 30B total parameters, 3B active (MoE) — fast inference
- 128K native context, 32K practical with 48GB RAM
- MIT license, strong coding benchmarks, native tool calling
- Served via mlx-lm (Apple's ML framework for Apple Silicon)

### Quick Setup

```bash
# Install mlx-lm + download model (~30GB)
./scripts/setup-model.sh

# Start the server
./scripts/setup-model.sh --serve
```

### Manual Setup

```bash
# Install mlx-lm
uv tool install mlx-lm

# Download model
hf download mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit

# Start server
mlx_lm.server \
  --model mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit \
  --port 8080
```

### Verify

```bash
# Check server is running
curl http://localhost:8080/v1/models

# Test a completion
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Memory Usage

| Component | RAM |
|-----------|-----|
| Model (8-bit) | ~30GB |
| KV cache (32K context) | ~5GB |
| **Total** | **~35GB** |

Fits on a 48GB Mac with ~13GB left for macOS and apps.

## Alternative Models

klaude works with any OpenAI-compatible API. Set `base_url` and `model`
in `.klaude.toml` or via CLI flags:

```bash
klaude --base-url https://api.openai.com/v1 --model gpt-4o "your task"
```

Other local options:
- **Ollama** — `ollama serve`, set `--base-url http://localhost:11434/v1`
- **vLLM** — for NVIDIA GPUs
- **llama.cpp** — `llama-server` (note: has grammar crash issues with tool calling, see Note 46)

## Proxy Issues

If downloads fail with SOCKS proxy errors, unset proxy vars first:

```bash
unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy
./scripts/setup-model.sh
```

## Config File

Instead of CLI flags, put your model settings in `.klaude.toml`:

```toml
[default]
model = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"
base_url = "http://localhost:8080/v1"
context_window = 32768
```

See `docs/examples/` for more config examples.
