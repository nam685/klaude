# Hardware Guide — Running LLMs Locally

## Your Current Setup

**Apple M4 Pro, 48GB unified memory**

| What works                          | What doesn't fit              |
|-------------------------------------|-------------------------------|
| Qwen3-Coder-Next Q2_K (~25GB)      | Q8_0 quantization (~85GB)     |
| Qwen3-Coder-Next Q3_K_M (~33GB)    | Full FP16 model               |
| Qwen3-Coder-Next Q4_K_M (~45GB)*   | Multiple models simultaneously |

*Tight — leaves ~3GB for context KV cache. Limit context to 64K tokens.

### Apple Silicon Advantage

Apple Silicon uses **unified memory** — CPU and GPU share the same RAM pool.
This means all 48GB is available for model inference. No separate "VRAM" like
NVIDIA GPUs. llama.cpp supports this natively via Metal.

### Practical Tips for Your Mac

```bash
# Check current memory pressure
memory_pressure

# Monitor during inference
# Activity Monitor → Memory tab → watch "Memory Used"

# If tight, reduce context
llama-server -c 32768   # 32K context instead of 64K
```

## Future Hardware Options

### Option A: Mac Studio / Mac Pro (Apple Silicon)

| Model           | RAM    | Price (approx) | Can Run                    |
|-----------------|--------|-----------------|----------------------------|
| Mac Studio M4 Ultra | 192GB | ~$5,000-8,000 | Q8_0, full context, multiple models |
| Mac Studio M4 Max   | 128GB | ~$3,000-5,000 | Q4_K_M with full 256K context      |

**Pros:** Silent, low power, macOS ecosystem, great for development
**Cons:** Expensive per GB, can't upgrade RAM later

### Option B: NVIDIA GPU Server (Best Performance/$)

| Setup                     | VRAM  | Price (approx) | Can Run                    |
|---------------------------|-------|-----------------|----------------------------|
| 1x RTX 4090              | 24GB  | ~$2,000         | Q2_K with limited context  |
| 2x RTX 3090              | 48GB  | ~$1,600         | Q4_K_M, good context       |
| 1x RTX 5090              | 32GB  | ~$2,000         | Q3_K_M, decent context     |
| 2x RTX 4090 (NVLink)     | 48GB  | ~$4,000         | Q4_K_M, full experience    |
| Used server w/ A100 80GB  | 80GB  | ~$3,000-5,000   | Q8_0, production quality   |

**Pros:** Best tok/s, CUDA ecosystem, can add more GPUs
**Cons:** Loud, power hungry, Linux preferred, separate from dev machine

### Option C: Cloud GPU (Pay As You Go)

| Provider      | GPU         | Cost/hr  | Best For                    |
|---------------|-------------|----------|-----------------------------|
| RunPod        | A100 80GB   | ~$1.50   | Testing larger quants       |
| Vast.ai       | A100 80GB   | ~$1.00   | Cheapest spot instances     |
| Lambda        | H100 80GB   | ~$2.50   | Maximum performance         |

**Pros:** No upfront cost, try before you buy
**Cons:** Ongoing cost, latency, data leaves your machine

## Recommendation Path

1. **Now:** Use your M4 Pro 48GB with Q3_K_M. Perfectly good for development.
2. **When you want more:** Try a cloud GPU for a few hours to test Q8_0 quality.
3. **If you're serious:** A used dual-3090 system or Mac Studio M4 Max 128GB
   gives the best balance of cost, performance, and usability.

## Performance Expectations (M4 Pro 48GB, Q3_K_M)

- **Prompt processing:** ~50-100 tok/s (reading your codebase)
- **Token generation:** ~15-25 tok/s (model's response)
- **First token latency:** 1-3 seconds (depending on prompt length)
- **Practical feel:** Usable but noticeably slower than cloud APIs

These numbers are approximate — actual performance varies with context length
and system load.
