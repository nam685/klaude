# Troubleshooting & FAQ

## Connection Issues

**Q: "Connection refused" when running klaude**

mlx_lm.server isn't running. Start it:

```
mlx_lm.server --model mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit --port 8080
```

---

**Q: "APIConnectionError" or timeout**

The server may still be loading the model (can take 30-60s). Wait and retry. Verify the server is up:

```
curl http://localhost:8080/v1/models
```

---

**Q: klaude connects but responses are garbage or empty**

The model may not support tool calling. Use Qwen3-Coder-Next or another model explicitly trained for tool use.

---

## Memory & Performance

**Q: mlx_lm.server crashes or gets OOM killed**

The model is too large for available RAM. Options:

- Switch to a smaller mlx model (e.g. a lower-bit quantization on Hugging Face)
- Reduce context window in `.klaude.toml`: set `context_window = 16384`
- Close other memory-intensive apps to free unified memory

---

**Q: Responses are very slow**

This is normal for local LLMs. The 4-bit mlx model on M4 Pro generates roughly 20-40 tok/s. To speed things up:

- Reduce context window (faster generation with smaller KV cache)
- Use a smaller model for rapid iteration

---

**Q: "Token budget exceeded" error**

klaude hit the `max_tokens` limit. Increase it in `.klaude.toml`:

```toml
max_tokens = 8192
```

Or disable the limit at runtime:

```
klaude --max-tokens 0 "task"
```

---

## Tool Errors

**Q: "Permission denied by user" — tool keeps getting blocked**

klaude prompts before running dangerous tools (bash, write_file, edit_file, git_commit). Press `y` to allow. To skip all prompts:

```
klaude --auto-approve "task"
```

---

**Q: "Blocked: path is outside the working directory"**

The file sandbox restricts access to the current working directory. Run klaude from the project root:

```
cd /path/to/project && klaude "task"
```

---

**Q: "Blocked: matches safety rule"**

The command matched the denylist (e.g., `sudo`, `rm -rf /`). These are always blocked. Rephrase the task to avoid them.

---

## Config Issues

**Q: .klaude.toml changes aren't taking effect**

Config is loaded at startup. Restart klaude. Also check:

- The file is in the project root or a parent directory
- The TOML syntax is valid (`uv run python3 -c "import tomllib; tomllib.load(open('.klaude.toml','rb'))"`)

---

**Q: How do I use a remote API (OpenAI, Anthropic, etc.)?**

Set `base_url` and `api_key` in `.klaude.toml`:

```toml
base_url = "https://api.openai.com/v1"
api_key  = "sk-..."
model    = "gpt-4o"
```

Or pass them as CLI flags. See `docs/examples/` for sample configs.

---

**Q: MCP server fails to connect**

Check that:

- The command exists (e.g., `npx` is on PATH for npm-based servers)
- Required environment variables are set
- MCP servers are started as child processes — inspect their stderr for errors

---

## REPL Issues

**Q: Up-arrow history not working**

readline/libedit should work by default. History is saved to `~/.klaude_history`. On macOS, libedit is used instead of GNU readline — behavior is mostly identical.

---

**Q: Esc key doesn't undo**

The Esc-based undo binding depends on libedit configuration. Use the slash command instead:

```
/undo
```

---

**Q: How do I exit?**

Any of these work:

```
/exit
/quit
Ctrl+D
```

---

## General

**Q: Where are the model files stored?**

mlx-lm uses the Hugging Face cache:

- macOS/Linux: `~/.cache/huggingface/hub/`

---

**Q: Can I use klaude with Ollama?**

Yes. Ollama exposes an OpenAI-compatible API. In `.klaude.toml`:

```toml
base_url = "http://localhost:11434/v1"
api_key  = "ollama"
model    = "qwen2.5-coder:32b"
```

---

**Q: Can I use klaude with vLLM?**

Yes. vLLM has an OpenAI-compatible server. Set `base_url` to your vLLM endpoint:

```toml
base_url = "http://localhost:8000/v1"
api_key  = "token-abc"
model    = "Qwen/Qwen2.5-Coder-32B-Instruct"
```
