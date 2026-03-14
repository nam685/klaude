# Implementation Notes

Notes on real-world issues encountered while building klaude.

## Note 1: SOCKS Proxy and httpx (Checkpoint 2)

### What happened
When creating the `LLMClient`, the `openai` SDK (which uses `httpx` internally)
crashed with:
```
ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.
```

### What is a SOCKS proxy?

**Proxy basics:** A proxy is a server that sits between your computer and the
internet. Instead of connecting directly to a website, your traffic goes through
the proxy first.

```
Without proxy:  Your Mac ──────────────> website.com
With proxy:     Your Mac ───> Proxy ───> website.com
```

**SOCKS vs HTTP proxy:**
- **HTTP proxy** — understands HTTP. Can inspect/modify requests. Only works for HTTP/HTTPS.
- **SOCKS proxy** — works at a lower level (TCP). Doesn't understand HTTP — just
  forwards raw bytes. Works for ANY protocol (HTTP, SSH, FTP, etc.). SOCKS5 also
  supports authentication and DNS resolution through the proxy.

**Why you have one:** Your system has `ALL_PROXY=socks5h://localhost:64990` set,
likely from a VPN or privacy tool. The `h` in `socks5h` means "DNS resolution
happens on the proxy side" (vs `socks5` where DNS happens locally).

**The problem:** `httpx` (the HTTP library used by the `openai` SDK) auto-detects
proxy env vars (`ALL_PROXY`, `HTTPS_PROXY`, etc.) and tries to use them for ALL
connections — even `localhost`. Routing `localhost` through a SOCKS proxy is
pointless and requires an extra dependency (`socksio`).

### How we fixed it

Created an explicit `httpx.HTTPTransport()` that ignores proxy env vars:

```python
transport = httpx.HTTPTransport()          # No proxy, direct connection
http_client = httpx.Client(transport=transport)
client = OpenAI(base_url=..., http_client=http_client)
```

The `openai` SDK accepts a custom `http_client` parameter, letting us control
the transport layer.

### Lesson
Environment variables affect library behavior in non-obvious ways. When
something fails at the network level, always check `env | grep -i proxy`.

## Note 2: Tool System Design (Checkpoint 3)

### The Three Parts of a Tool

Every tool in our system (and in Claude Code, and in the OpenAI API) is three things:

```
1. Schema (JSON)  →  tells the LLM what the tool does and what params it takes
2. Handler (func) →  actually runs the tool (Python function)
3. Name (string)  →  connects schema to handler
```

### Why a Registry?

The registry pattern decouples tool definition from tool usage:

```python
# Each tool file defines itself:
tool = Tool(name="read_file", description="...", parameters={...}, handler=handle_read_file)

# The registry collects them:
registry.register(tool)

# The agentic loop uses the registry generically:
schemas = registry.get_schemas()    # → send to LLM
result = registry.execute(name, args)  # → run what LLM requested
```

The loop never needs to know which specific tools exist. It just asks the
registry. This means adding a new tool = writing one file, registering it.
No changes to the loop.

### Tool Execution Flow

```
LLM returns: {"name": "read_file", "arguments": "{\"path\": \"/foo/bar.py\"}"}
                                                    ↑ this is a JSON STRING
    ↓
registry.execute("read_file", '{"path": "/foo/bar.py"}')
    ↓
json.loads(arguments) → {"path": "/foo/bar.py"}  # parse JSON string to dict
    ↓
handler(**kwargs) → handle_read_file(path="/foo/bar.py")
    ↓
returns: "def main():\n    print('hello')\n"     # always returns a string
```

Key detail: the LLM returns arguments as a **JSON string** (not a dict). This
is because it's embedded in the API response JSON. We `json.loads()` it to get
the actual keyword arguments.

### Error Handling Strategy

Tools never raise exceptions to the caller. They always return error strings:

```python
"Error: file not found: /nonexistent/file.txt"
"Error: command timed out after 30s"
"Error: unknown tool 'foo'"
```

Why? Because the error message goes back to the LLM as a tool result. The LLM
can then read the error and decide what to do (try a different path, fix its
command, ask the user, etc.). If we raised exceptions, the agentic loop would
crash instead of letting the LLM recover.

### bash Tool Safety Note

The bash tool currently has NO sandboxing — it runs whatever the LLM asks for.
This is fine for Phase 1 (local development, we trust the model enough to test).
Phase 5 adds permission prompts and sandboxing.

## Note 3: The Agentic Loop (Checkpoint 4)

### What `loop.py` Actually Does

The entire loop is ~60 lines of real logic. Here's the skeleton:

```python
messages = [system_prompt, user_message]

for iteration in range(MAX_ITERATIONS):
    response = client.chat(messages, tools=tool_schemas)
    message = response.choices[0].message

    if not message.tool_calls:       # LLM is done — just text
        print(message.content)
        return

    messages.append(message)         # Add assistant message (with tool_calls)

    for tool_call in message.tool_calls:
        result = registry.execute(tool_call.function.name,
                                  tool_call.function.arguments)
        messages.append({"role": "tool", "tool_call_id": tool_call.id,
                         "content": result})
    # loop back — LLM sees tool results next iteration
```

### The Conversation as a Timeline

The `messages` list grows like this during a typical session:

```
[0] system    "You are klaude, an AI coding assistant..."
[1] user      "Fix the bug in main.py"
[2] assistant tool_calls=[read_file(path="main.py")]     ← LLM decides to read
[3] tool      "def main():\n    print(x)  # NameError"   ← file contents
[4] assistant tool_calls=[write_file(path="main.py", ..)] ← LLM decides to fix
[5] tool      "Successfully wrote 42 bytes to main.py"   ← confirmation
[6] assistant tool_calls=[bash(command="python main.py")] ← LLM verifies
[7] tool      "hello world"                              ← it works!
[8] assistant "Fixed the bug. The variable `x`..."       ← final text = done
```

Every message in this list is sent to the LLM on every turn. That's how it
"remembers" what it already did. This is also why context windows matter —
this list can get very long.

### Why `message.model_dump()`?

When the LLM returns a tool call, we need to add its response to the messages
list. The OpenAI SDK returns a Pydantic object, but the messages list needs
plain dicts. `model_dump()` converts it.

### The MAX_ITERATIONS Safety Valve

Without a limit, a confused model could loop forever (call tools that fail,
retry, fail again...). 50 iterations is generous — most real tasks finish in
5-15 turns. This is a simple safeguard; Claude Code uses token budgets instead.

### Why Non-Streaming First?

The loop uses `client.chat()` (non-streaming) instead of `client.chat_stream()`.
Streaming is better UX (you see tokens appear) but harder to implement because:

1. Tool calls arrive as **deltas** (partial JSON chunks) that must be reassembled
2. You need to accumulate text AND tool calls simultaneously
3. The response object shape is different (`ChatCompletionChunk` vs `ChatCompletion`)

We'll add streaming in a later checkpoint. Non-streaming is easier to
understand and debug — one request, one complete response.

## Note 4: CLI Wiring (Checkpoint 5)

### How `klaude "fix the bug"` Becomes a Python Function Call

The chain from terminal to code:

```
Terminal: klaude "fix the bug"
    ↓
pyproject.toml: [project.scripts] klaude = "klaude.cli:main"
    ↓
cli.py: main() — click parses args, creates LLMClient
    ↓
loop.py: run("fix the bug", client) — the agentic loop
    ↓
client.py: client.chat(messages, tools) — HTTP to llama-server
```

### `[project.scripts]` — How Python CLI Tools Work

In `pyproject.toml`:
```toml
[project.scripts]
klaude = "klaude.cli:main"
```

When you `uv sync`, this creates a small executable script in `.venv/bin/klaude`
that imports `klaude.cli` and calls `main()`. That's all a Python CLI tool is —
an entry point mapping.

### `nargs=-1` — Flexible Argument Handling

`click.argument("task", nargs=-1)` accepts any number of words:

```bash
klaude fix the bug in main.py     # task = ("fix", "the", "bug", "in", "main.py")
klaude "fix the bug in main.py"   # task = ("fix the bug in main.py",)
```

Both work because we `" ".join(task)` them into one string.

### Environment Variables for Config

```bash
KLAUDE_BASE_URL=http://some-server:8080/v1 klaude "do something"
KLAUDE_MODEL=qwen3-8b klaude "do something"
```

Click's `envvar` parameter makes this automatic — no extra code needed.
This lets you point klaude at different servers without changing code.

## Note 5: Local Model Serving (Checkpoint 6)

### What llama-server Actually Does

llama-server is a C++ program that:
1. Loads a GGUF model file into memory (RAM + GPU)
2. Starts an HTTP server
3. Exposes an OpenAI-compatible API at `/v1/chat/completions`

```
Your code (Python)              llama-server (C++)
─────────────────               ──────────────────
openai.Client(                  Loads 30GB model
  base_url="localhost:8080"     into unified memory
)                                     │
      │                               ▼
      ├── POST /v1/chat/completions ──→ Runs inference
      │                               │ (matrix math on Metal GPU)
      ◄── JSON response ◄────────────┘
```

Your Python code never touches the model weights directly. It's just HTTP.

### GGUF Format

GGUF (GPT-Generated Unified Format) is the file format llama.cpp uses.
A single `.gguf` file contains:
- Model weights (quantized to reduce size)
- Tokenizer
- Model metadata (architecture, context length, etc.)

One file = everything needed to run the model. No separate config files.

### Quantization Trade-offs (for 48GB Mac)

**Q3_K_M** (~28GB model, ~33GB with overhead) — **recommended start**
- Leaves ~15GB for context KV cache and OS
- Can use full 64K context comfortably
- Quality is "good" — noticeable vs Q8 but very usable

**Q4_K_M** (~38GB model, ~45GB with overhead) — **best quality that fits**
- Only ~3GB headroom — may need to reduce context to 32K
- Quality is "very good" — minimal loss from full precision
- Use this once you're comfortable with memory management

### The `-ngl 99` Flag

`-ngl` = number of GPU layers. On Apple Silicon, "GPU" means the Metal GPU
cores in the same chip. Setting it to 99 (higher than actual layer count)
tells llama.cpp to put ALL layers on GPU. This is fastest because Apple
Silicon's unified memory means there's no CPU↔GPU copy overhead.

### Why Not Ollama?

Ollama is easier (one command) but:
- Adds an abstraction layer between you and the model
- Harder to control quantization, context size, and GPU offloading precisely
- Tool calling support varies by model and Ollama version
- For learning, direct llama-server gives you more visibility into what's happening

## Note 6: Streaming (Checkpoint 7)

### Non-Streaming vs Streaming

**Non-streaming** (what we had before):
```
You wait 10 seconds ──────────→ entire response appears at once
```

**Streaming** (what we have now):
```
Token appears ─ token ─ token ─ token ─ token ─ done  (feels instant)
```

Same total time, but the user sees output immediately. This is critical UX
for slow local models (~15-25 tok/s).

### The Hard Part: Tool Calls Arrive in Pieces

With plain text streaming, it's trivial — just print each chunk's `delta.content`.
But tool calls arrive as fragmented deltas:

```
chunk 1: delta.tool_calls = [{index:0, id:"call_1", function:{name:"read"}}]
chunk 2: delta.tool_calls = [{index:0, function:{name:"_file"}}]
chunk 3: delta.tool_calls = [{index:0, function:{arguments:'{"p'}}]
chunk 4: delta.tool_calls = [{index:0, function:{arguments:'ath"'}}]
chunk 5: delta.tool_calls = [{index:0, function:{arguments:': "'}}]
chunk 6: delta.tool_calls = [{index:0, function:{arguments:'/foo"}'}}]
```

The name, id, and arguments are all split across multiple chunks. We need
to **accumulate** them using the `index` field to know which tool call
each fragment belongs to.

### The Solution: `ToolCallAccumulator`

```python
@dataclass
class ToolCallAccumulator:
    id: str = ""
    name: str = ""
    arguments: str = ""
```

For each chunk, we look at `delta.tool_calls[i].index` and append fragments
to the matching accumulator. When the stream ends, each accumulator has
the complete tool call.

### Why `index` Matters

The LLM can request **parallel tool calls** — e.g., read two files at once.
Each tool call gets a different index:

```
chunk: delta.tool_calls = [{index:0, name:"read_file"}, {index:1, name:"read_file"}]
chunk: delta.tool_calls = [{index:0, arguments:'{"path":"/a"}'}, {index:1, arguments:'{"path":"/b"}'}]
```

`tool_calls_by_index` dict keeps them separate.

### `StreamResult.to_message_dict()`

After consuming the stream, we need to add the assistant's response to the
message history. The OpenAI API expects a specific format for assistant
messages with tool calls:

```python
{
    "role": "assistant",
    "content": null,        # or text if the model also wrote text
    "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "...", "arguments": "..."}},
    ]
}
```

`to_message_dict()` builds this from our accumulators. This replaces the
`message.model_dump()` we used in the non-streaming version.

### Architecture: stream.py is Pure Accumulation

`stream.py` doesn't know about the agentic loop. It just:
1. Consumes chunks from a stream
2. Prints text deltas
3. Accumulates tool call fragments
4. Returns a `StreamResult`

The loop in `loop.py` decides what to do with the result (execute tools or finish).
This separation makes both modules easier to understand and test.

## Note 7: Phase 2 Tools (glob, grep, edit_file, list_directory)

### Why These Four Tools Matter

Phase 1 tools (read_file, write_file, bash) let the agent do things but
inefficiently. Imagine the LLM trying to find a bug without grep — it would
have to read every file manually. The Phase 2 tools make the agent *fast*:

| Tool | Without it, the LLM would... |
|------|-------------------------------|
| glob | `bash("find . -name '*.py'")` — works but fragile, OS-dependent |
| grep | read every file looking for a string — wastes tokens |
| edit_file | `write_file` the entire file to change one line — risky, token-heavy |
| list_directory | `bash("ls -la")` — works but output format varies |

### edit_file: The Most Important Phase 2 Tool

Claude Code's Edit tool uses the same pattern: provide `old_string` (exact match)
and `new_string` (replacement). Key design decisions:

1. **Must match exactly once** — if old_string appears 0 or 2+ times, it errors.
   This prevents ambiguous edits. The LLM must provide enough context to
   be unique.

2. **Returns an error string on failure, not an exception** — the LLM reads the
   error and can adjust (e.g., include more surrounding context).

3. **Why not line numbers?** Line numbers are fragile — if the LLM read the file
   10 turns ago and the file was edited since, line numbers are wrong. String
   matching works regardless of prior edits.

### grep: Skipping Non-Text Directories

`handle_grep` skips `.git`, `.venv`, `node_modules`, `__pycache__`, etc.
Without this, searching a Python project would waste time on thousands of
bytecode and git object files. The skip list matches what tools like `ripgrep`
do by default.

### System Prompt: Guiding Tool Choice

The improved system prompt organizes tools by purpose (reading vs writing vs
running) and gives explicit guidance:

- "Use list_directory to orient yourself"
- "Prefer edit_file over write_file for existing files"
- "Read files before editing them" (needed for edit_file's exact match)
- "Try grep first, fall back to reading whole files"

This guidance matters because the LLM chooses tools based on the system prompt.
Without it, a model might always use write_file (simpler but wasteful) instead
of edit_file (surgical but requires reading first). The prompt shapes behavior
more than the tool descriptions alone.

### Dynamic System Prompt

The system prompt includes `os.getcwd()` via f-string — the LLM sees the
actual working directory. This helps it construct absolute paths for tools.
Claude Code does the same thing — its system prompt contains environment
context like the current directory, git branch, and recent commits.

## Note 8: Token Counting & Context Tracking (Phase 3)

### The Problem

Every LLM has a context window — a maximum number of tokens it can process
in one request. For Qwen3-Coder-Next with our llama-server config, that's
65,536 tokens. The conversation (system prompt + all messages + tool schemas)
must fit within this limit. If it doesn't, the server will either truncate
silently or error out.

In an agentic loop, the conversation grows fast:
- System prompt: ~500 tokens
- Tool schemas (sent every request): ~500 tokens
- Each tool result (e.g., reading a file): 100-5000+ tokens
- Each assistant response: 50-500 tokens

After 10-15 tool calls, you can easily be at 20,000+ tokens. Without tracking,
you have no idea how close you are to the cliff.

### Why Estimation, Not Exact Counting?

Three options for counting tokens:

| Approach | Accuracy | Dependencies | Notes |
|----------|----------|-------------|-------|
| `tiktoken` (OpenAI) | ~85% for Qwen | `tiktoken` package | Wrong tokenizer |
| HuggingFace tokenizer | ~99% | `transformers` + `torch` (~2GB) | Way too heavy |
| llama-server `/tokenize` | 100% | Requires server running | Non-standard endpoint |
| **chars ÷ 4 heuristic** | **~75-80%** | **None** | **Good enough** |

We chose the heuristic because:
1. **Zero dependencies** — no extra packages to install
2. **Always available** — works even without the server running
3. **Good enough** — we need to know "am I at 50% or 90%?", not the exact count
4. **Simple to understand** — one line of code

The ~4 chars/token ratio comes from empirical measurement across English text
and code. Some tokens are 1 char (`(`, `{`), some are 10+ chars (`function`
as a single token). It averages to ~4.

### What Gets Counted

Every API request sends:
```
┌──────────────────────────────────────┐
│ Tool schemas (JSON, ~500 tokens)     │  ← constant overhead every turn
├──────────────────────────────────────┤
│ System prompt message                │  ← constant
│ User message                         │  ← constant
│ Assistant message (tool calls)       │  ← grows each turn
│ Tool result message                  │  ← grows each turn
│ Assistant message (tool calls)       │  ← grows each turn
│ Tool result message                  │  ← grows each turn
│ ...                                  │
└──────────────────────────────────────┘
```

The tracker counts all of these. The tool schema overhead is easy to forget
because it's not in the message list — it's a separate `tools` parameter.
But it eats into the context window just the same.

### Per-Message Overhead

Each message has ~4 tokens of overhead beyond its content: the role label
(`system`, `user`, `assistant`, `tool`), message delimiters, and formatting
tokens that the model's chat template adds. This varies by model but 4 is
a reasonable estimate.

### Why Recalculate From Scratch?

```python
def update(self, messages):
    self.message_tokens = [estimate_message_tokens(m) for m in messages]
```

We recalculate all message tokens on every turn instead of incrementally
adding new ones. This is simpler and avoids drift from accumulated rounding
errors. With at most ~100 messages in a typical session, the cost is
negligible.

### Warning Thresholds

- **80%** — "approaching limit" warning. Time to think about compaction.
- **95%** — "CRITICAL" warning. Next turn will likely fail or get truncated.

These thresholds set up for the next feature: context compaction (summarizing
old messages to free up space). The tracker tells you *when* to compact;
the compactor (Phase 3, next checkpoint) will handle *how*.

## Note 9: Message History Management (Phase 3)

### Why Wrap the Message List?

The agentic loop used to manage messages as a raw `list[dict]`:

```python
messages: list[dict] = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": user_message},
]
messages.append(result.to_message_dict())
messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
```

This works but has no structure. For compaction, we need to answer questions
like "which messages are safe to summarize?" and "replace these messages with
a summary." A raw list can't express these concepts.

`MessageHistory` wraps the list and adds:
- Typed methods: `add_user()`, `add_assistant()`, `add_tool_result()`
- `compactable_range()` — identifies which messages can be summarized
- `replace_range()` — swaps old messages for a summary

### Protected vs Compactable Messages

```
[0] system prompt           ← PROTECTED (always needed)
[1] user: "Fix the bug"     ← PROTECTED (the task definition)
[2] assistant: read_file    ← compactable (old exchange)
[3] tool: file contents     ← compactable (old exchange)
[4] assistant: edit_file    ← compactable (old exchange)
[5] tool: success           ← PROTECTED (recent, keep_recent=6)
[6] assistant: read_file    ← PROTECTED (recent)
[7] tool: new contents      ← PROTECTED (recent)
...
```

The `keep_recent` parameter (default 6) controls how many recent messages
stay visible. This prevents the LLM from repeating actions it just took.
The older exchanges in the middle are safe to summarize — they're already
"done" and the LLM just needs a high-level record of what happened.

### Summary Messages Use the "system" Role

When we replace old messages with a summary, we insert it as a `system`
message, not `user` or `assistant`:

```python
{"role": "system", "content": "[Conversation summary]\nRead main.py, edited..."}
```

Why? The `assistant` role would confuse the model — it would think it
previously said that text. The `user` role would look like the user said it.
The `system` role signals "this is authoritative context" without being
part of the conversation flow.

## Note 10: Context Compaction (Phase 3)

### The Compaction Loop

Compaction happens at the end of each tool-call turn in the agentic loop:

```
while tool_calls:
    execute tools
    add results to history
    ─── COMPACT HERE ───  ← if context > 75% full
    next LLM call
```

This placement means we compact *before* the next LLM call, ensuring the
request fits within the context window.

### Using the LLM to Summarize

The key insight: we already have an LLM available — use it to summarize.

```python
summary_messages = [
    {"role": "system", "content": SUMMARIZE_PROMPT},
    {"role": "user", "content": f"Summarize this:\n{transcript}"},
]
response = client.chat(summary_messages)  # non-streaming, no tools
```

This is a separate, simple request — no tools, no streaming. The LLM reads
the old exchanges and returns a concise summary. We then replace the originals
with this summary.

### Truncating Tool Results in the Summary Request

A single `read_file` result can be thousands of characters. If we include
all of those in the summarization request, the summary request itself could
be huge. So we truncate tool results to 2000 chars in the transcript:

```python
if role == "tool" and len(content) > 2000:
    content = content[:2000] + "\n... (truncated)"
```

The summary doesn't need the full file contents — just enough to know what
was read and what was in it.

### Why 75% Threshold?

Compaction kicks in at 75% context usage. Why not higher?

- The compaction request itself uses tokens (the transcript + summary)
- After compaction, the LLM still needs room to generate its next response
- Tool results from the next turn need space too
- 75% gives a comfortable buffer while not compacting too aggressively

If compaction doesn't free enough space (the compactable range is small),
the 80% warning and 95% critical alerts from the tracker still kick in.

## Note 11: Long-Term Memory (Phase 3)

### The KLAUDE.md Convention

Claude Code uses `CLAUDE.md` for per-project memory. We do the same with
`KLAUDE.md`. When klaude starts, it searches for this file starting from
the current directory, walking up to the root (like how git finds `.git/`).

The file's contents are injected into the system prompt:

```
System prompt:
├── Identity and instructions (hardcoded)
├── Current directory (dynamic)
├── Tool descriptions (hardcoded)
├── Work guidelines (hardcoded)
└── Project memory from KLAUDE.md (loaded at startup)
```

### Why Read-Only (For Now)?

The LLM can read KLAUDE.md via the system prompt but can't write to it
through a dedicated tool. This is intentional:

1. **Safety** — auto-writing memory could accumulate incorrect information
2. **Simplicity** — the user manually curates what's important
3. **Transparency** — the user always knows exactly what's in memory

The LLM *can* still edit KLAUDE.md using `edit_file` or `write_file` if
asked — it's just a regular file. But there's no special "save to memory"
tool that would encourage the LLM to write to it autonomously.

A future improvement could add a `save_memory` tool with user confirmation.

### Search Path (Walk Up)

```python
def find_memory_file(start_dir):
    current = Path(start_dir or os.getcwd()).resolve()
    while True:
        candidate = current / MEMORY_FILE
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break  # reached root
        current = parent
    return None
```

Walking upward means you can run `klaude` from any subdirectory and it'll
still find the project root's KLAUDE.md. This matches git's behavior —
you don't need to be in the root to use it.

### Size Limit

We cap loaded memory at 8KB to prevent a huge KLAUDE.md from eating the
context window. At ~4 chars/token, 8KB ≈ 2000 tokens — a reasonable amount
for project context without dominating the prompt.

## Note 12: Session Refactor & Multi-Turn REPL (Phase 4)

### The Problem With One-Shot

Before this change, `run()` in loop.py created everything fresh:

```python
def run(user_message, client, context_window):
    registry = create_registry()
    tracker = ContextTracker(...)
    history = MessageHistory(...)
    history.add_user(user_message)
    # ... loop ...
```

Each invocation was independent. No way to have a follow-up conversation.
For multi-turn REPL, the history must persist across user messages.

### The Session Class

The fix: extract a `Session` class that holds all persistent state:

```python
class Session:
    def __init__(self, client, context_window, console):
        self.client = client
        self.registry = create_registry()
        self.tracker = ContextTracker(context_window=context_window)
        self.history = MessageHistory(SYSTEM_PROMPT)

    def turn(self, user_message: str) -> str:
        self.history.add_user(user_message)
        # ... same agentic loop, but using self.history ...
```

Now the REPL can call `session.turn()` repeatedly, and the conversation
accumulates in `session.history`. The one-shot `run()` function still
exists as a convenience wrapper.

### REPL Design

The REPL is a simple input loop:

```
klaude> [user types here]
  ... (agentic loop runs) ...
klaude> [user types again, same session]
```

Key features:
- **Slash commands**: `/exit`, `/clear`, `/context`, `/history`
- **Ctrl+C at prompt**: clears the line, doesn't exit
- **Ctrl+C during LLM**: stops streaming, returns to prompt
- **Ctrl+D**: exits (standard Unix convention)
- **readline**: up-arrow history, line editing, persisted to `~/.klaude_history`

### Two Modes via CLI

```
klaude                  → REPL mode (interactive)
klaude "fix the bug"    → one-shot mode (process and exit)
```

Click's `nargs=-1` gives us a tuple. Empty tuple = no args = REPL.

## Note 13: Interrupt Handling (Phase 4)

### Where Ctrl+C Can Hit

There are three places Ctrl+C can happen:

1. **At the REPL prompt** — user is typing input
2. **During LLM streaming** — waiting for/receiving tokens
3. **During tool execution** — a tool (e.g., bash) is running

Each needs different handling:

| Location | Behavior |
|----------|----------|
| REPL prompt | Clear input line, show new prompt |
| LLM streaming | Stop stream, keep partial text, return to prompt |
| Tool execution | Bubble up to REPL, show "Interrupted", return to prompt |

### Graceful Stream Interruption

The stream consumer catches `KeyboardInterrupt` inside the chunk loop:

```python
try:
    for chunk in stream:
        # ... accumulate ...
except KeyboardInterrupt:
    interrupted = True
    tool_calls_by_index.clear()  # discard incomplete tool calls
```

Why discard tool calls? If the LLM was mid-way through emitting a tool call
(e.g., only half the arguments JSON arrived), executing it would fail. But
any text content already printed is kept — the user saw it on screen.

## Note 14: Spinner & Waiting UX (Phase 4)

### The Silent Wait Problem

With streaming, text appears token-by-token — great UX. But there's a gap
between sending the request and receiving the first token. With a local
model, this can be 1-10+ seconds (model loading, prompt processing). During
this time, the terminal is completely silent. The user wonders: is it working?
Did it crash?

### Rich Status Spinner

We use `rich.status.Status` to show an animated spinner:

```python
spinner = Status("Thinking...", console=console, spinner="dots")
spinner.start()
# ... on first real content:
spinner.stop()
```

The spinner runs on a background thread (Rich handles this). It stops the
moment the first content or tool call delta arrives. The spinner is also
cleaned up in a `finally` block and on `KeyboardInterrupt`.

## Note 15: Readline Input History (Phase 4)

### Why readline?

Python's built-in `readline` module (actually `libedit` on macOS) gives us:
- **Line editing**: arrow keys, Ctrl+A/E (home/end), Ctrl+W (delete word)
- **History**: up/down arrows recall previous inputs
- **Persistence**: history saved to `~/.klaude_history` across sessions

This is zero extra dependencies — `readline` is in Python's standard library.
The alternative (`prompt_toolkit`) is more powerful but adds ~300KB of deps
for features we don't need yet.

### History Persistence

```python
def _setup_readline():
    readline.read_history_file(HISTORY_FILE)  # load on start

def _save_readline():
    readline.write_history_file(HISTORY_FILE)  # save on exit
```

The save happens in a `finally` block, so history is preserved even on
crashes. We cap at 500 entries to prevent the file from growing forever.

## Note 16: Syntax-Highlighted Code Blocks in Streaming (Phase 4)

### The Challenge

LLM responses often contain code blocks:

    Here's how to fix it:
    ```python
    def hello():
        print("hello world")
    ```

But tokens arrive one-by-one: `"``"`, `"` "`, `"py"`, `"th"`, ... We can't
syntax-highlight half a function. We need the complete code block before
we can colorize it.

### The State Machine

`StreamPrinter` uses a simple two-state machine:

```
State NORMAL:
  - Print text lines as they arrive (real-time streaming feel)
  - If line matches ```<lang> → switch to CODE, start buffering

State CODE:
  - Accumulate lines silently (user sees nothing yet)
  - If line matches ``` → render buffer with Syntax(), switch to NORMAL
```

This means:
- **Regular text** streams in real-time (no change from before)
- **Code blocks** appear all at once, with full syntax highlighting

### Line Buffering

The key trick: we buffer at the **line level**, not the token level.

```python
def feed(self, text: str) -> None:
    self._buffer += text
    while "\n" in self._buffer:
        line, self._buffer = self._buffer.split("\n", 1)
        self._process_line(line)
```

Each delta might be a single character or a whole paragraph. We accumulate
in `_buffer` and only process when we have a complete line (contains `\n`).
This means code fence detection (```` ``` ````) works correctly even when the
fence characters arrive across multiple deltas.

### Rich Syntax Rendering

We use `rich.syntax.Syntax` (backed by Pygments) to render code blocks:

```python
syntax = Syntax(code, lang, theme="monokai", line_numbers=False, word_wrap=True)
console.print(syntax)
```

Pygments supports 500+ languages. We also maintain a small alias map
(`py` → `python`, `js` → `javascript`, etc.) for common shorthand.

### Edge Cases

- **Unclosed code block** (stream interrupted or LLM forgot to close):
  `flush()` renders whatever was accumulated
- **Empty code block**: silently skipped
- **Unknown language**: falls back to plain text (no highlighting)
- **Nested backticks** inside code: not an issue because we only match
  ```` ``` ```` at the start of a line (the regex anchors with `^`)

### Why Not Full Markdown Rendering?

Rich has a `Markdown` class that renders full markdown (headers, bold,
lists, etc.). We don't use it because:

1. **Streaming** — `Markdown()` needs the complete text upfront
2. **Overhead** — most LLM output is plain text + code blocks; full markdown
   rendering adds complexity for little visual gain
3. **Readability** — `# Header` and `**bold**` are perfectly readable as
   raw text in a terminal; code blocks are the one thing that genuinely
   benefits from syntax highlighting

## Note 17: Permission System (Phase 5)

### The Interception Point

Permissions are checked in the agentic loop, between the LLM deciding to
call a tool and actually executing it:

```
LLM says: call bash("rm -rf /tmp/junk")
    │
    ├── 1. Hard check (denylist, path sandbox) → block or continue
    ├── 2. Permission prompt (dangerous tools) → approve or deny
    └── 3. Execute tool
```

If denied at any step, the tool result is an error message. The LLM sees
the denial and can try a different approach — this is better than crashing
or silently blocking.

### Tool Classification

```
SAFE (no prompt):       read_file, glob, grep, list_directory
DANGEROUS (prompt):     bash, write_file, edit_file
```

Safe tools are read-only — they can't modify the filesystem or execute
commands. Dangerous tools can. This mirrors Claude Code's approach: reads
are free, writes need approval.

### Three Layers of Safety

1. **Command denylist** — regex patterns that always block, regardless of
   user approval. `rm -rf /`, `sudo`, `curl | bash`, `dd of=/dev/`, etc.
   These are catastrophic operations that no reasonable coding task needs.

2. **Path sandbox** — file tools are restricted to the working directory
   tree. Blocked paths include `~/.ssh`, `~/.aws`, `/etc/shadow`, etc.
   This prevents the LLM from reading SSH keys or credentials.

3. **Permission prompt** — for everything else, the user decides.
   Shows what's about to happen (command, file path, diff) and asks y/n.

### Auto-Approve Mode

`--auto-approve` skips the user prompt (layers 1 and 2 still apply).
Useful for:
- Testing (don't want to approve 50 tool calls)
- Scripted/CI usage
- Trusting the model on safe tasks

## Note 18: Command Denylist (Phase 5)

### Why Regex?

Commands are strings. The simplest way to pattern-match dangerous commands
is regex. Each pattern catches a class of danger:

```python
DENIED_COMMANDS = [
    re.compile(r"\brm\s+(-\w*f\w*\s+)*\s*/\s*$"),  # rm -rf /
    re.compile(r"\bsudo\b"),                          # any sudo
    re.compile(r"\bcurl\b.*\|\s*\bbash\b"),           # curl | bash
    ...
]
```

The `\b` word boundaries prevent false positives (`customer` matching `rm`).

### Limitations

Regex denylist is **defense in depth**, not a complete sandbox. A clever
LLM could bypass it (e.g., `$(echo rm) -rf /`). But combined with the
permission prompt and path sandbox, it catches the obvious dangers.

For a production tool, you'd want a proper command parser or seccomp/landlock
sandbox at the OS level. For an educational project, regex + permission
prompt is a good balance.

## Note 19: Diff Review for edit_file (Phase 5)

### Why Show a Diff?

When the LLM calls `edit_file`, the user needs to know exactly what's
changing before approving. A diff is the standard way to show this:

```diff
--- a/main.py
+++ b/main.py
@@ -1 +1 @@
-print("hello")
+print("world")
```

We generate the diff using Python's `difflib.unified_diff` from old_string
and new_string. Then render it with `rich.syntax.Syntax` using the "diff"
lexer, which colorizes additions (green) and deletions (red).

### Integration with Permission Prompt

The diff is shown as part of the permission prompt:

```
  Permission required: edit_file
  File: main.py
  --- a/main.py
  +++ b/main.py
  @@ -1 +1 @@
  -print("hello")
  +print("world")
  Allow? [y/n]
```

The user sees the exact change before deciding. This is like `git diff`
before `git add` — you review before committing.

## Note 20: File System Sandbox (Phase 5)

### Two Rules

1. **Working directory restriction**: file paths must resolve to within
   `os.getcwd()` (or below it). This prevents the LLM from reading/writing
   arbitrary files on the system.

2. **Blocked sensitive paths**: even within the home directory, certain
   paths are always blocked: `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.env`,
   `~/.netrc`, `~/.kube`, `/etc/shadow`, `/etc/passwd`.

### Path Resolution

We use `Path.resolve()` to handle symlinks and `..` components:

```python
path = Path(path_str).resolve()
cwd = Path(os.getcwd()).resolve()
if cwd not in path.parents and path != cwd:
    return "Blocked: outside working directory"
```

This prevents tricks like `/home/user/project/../../.ssh/id_rsa` — it
resolves to `/home/user/.ssh/id_rsa` which is outside the working directory.

## Note 21: Token Budgets (Phase 5)

### Simple Threshold

Token budgets are a simple guard: if estimated token usage exceeds the
budget, stop the session gracefully.

```python
if self.max_tokens > 0 and self.tracker.total_tokens > self.max_tokens:
    return "Stopped: token budget exceeded."
```

Checked at the top of each loop iteration, before calling the LLM. The
default is 0 (unlimited).

### Use Cases

- **Cost control**: on paid APIs, limit spend per session
- **Resource management**: on local hardware, prevent very long sessions
  that keep the GPU busy
- **Testing**: run with a small budget to verify the loop stops gracefully

The token budget is separate from the context window. The context window
is the model's limit (65K tokens). The budget is the user's limit
("don't spend more than 10K tokens on this task").

## Note 22: Error Recovery & Retry Logic (Phase 6)

### The Problem

Local LLMs are flaky. llama-server can:
- Refuse connections during model loading (cold start)
- Return 500 errors under memory pressure
- Time out on long prompts

Without retry logic, a single transient failure kills the whole session.

### Exponential Backoff in client.py

```python
RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, InternalServerError)

def _retry[T](self, fn: Callable[[], T]) -> T:
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except RETRYABLE_EXCEPTIONS as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)  # 1s, 2s, 4s
                time.sleep(delay)
    raise last_error
```

Both `chat()` and `chat_stream()` use `_retry()`. For streaming, only the
initial connection is retried — once tokens start flowing, failures aren't
retried (you'd lose partial data).

### Which Exceptions to Retry

| Exception | Meaning | Retry? |
|-----------|---------|--------|
| `APIConnectionError` | Server unreachable | Yes — might be starting up |
| `APITimeoutError` | Request took too long | Yes — might be temporary load |
| `InternalServerError` | HTTP 500 | Yes — often transient |
| `BadRequestError` | HTTP 400 | No — our request is wrong |
| `AuthenticationError` | HTTP 401/403 | No — won't fix itself |

### Error Recovery in the Loop

The agentic loop wraps the LLM call in a try/except. If all retries fail,
it shows the error and stops gracefully:

```python
try:
    stream = self.client.chat_stream(...)
except (APIConnectionError, APITimeoutError, InternalServerError) as e:
    return f"Stopped: LLM API error — {e}"
```

Tool execution errors were already handled — the registry catches exceptions
and returns error strings. The LLM reads these and can self-correct.

## Note 23: Git Integration (Phase 6)

### Why Dedicated Git Tools?

The LLM could do `bash("git status")`, but dedicated tools are better:

1. **Cleaner output** — `git status --short` vs the full status output
2. **Structured parameters** — `git_diff(target="staged")` vs remembering flags
3. **Permission gating** — `git_commit` is DANGEROUS, `git_status` is SAFE
4. **Error handling** — clear "not a git repository" message vs raw git errors

### The Four Tools

| Tool | Command | Safety |
|------|---------|--------|
| `git_status` | `git branch --show-current` + `git status --short` | SAFE |
| `git_diff` | `git diff`, `git diff --cached`, `git diff <ref>` | SAFE |
| `git_log` | `git log --oneline -n <count>` | SAFE |
| `git_commit` | `git add <files>` + `git commit -m <msg>` | DANGEROUS |

### subprocess.run, Not bash -c

All git tools use `subprocess.run(["git", ...])` directly. This avoids
shell injection — the arguments are passed as a list, not interpolated
into a shell command string.

### GitHub = MCP Later

These tools only do **local** git operations. GitHub (PRs, issues, code search)
will be handled via MCP integration in Phase 7, not custom tools.

## Note 24: Task Planning Tool (Phase 6)

### Why the LLM Needs a Task List

For complex tasks (e.g., "refactor the auth module into 3 files"), the LLM
can lose track of what it's done and what's left. A task list:

1. **Forces planning** — the model breaks down the task before starting
2. **Tracks progress** — marks steps as done/in-progress/skipped
3. **Shows the user** — transparency about what the agent is doing

### Single Tool, Multiple Actions

Rather than 3 separate tools (create, update, list), we use one tool with
an `action` parameter. This keeps the tool schema list shorter — with 14
tools already, every slot counts for context overhead.

### Module-Level State

```python
_tasks: list[dict] = []

def handle_task_list(action, tasks=None, task_index=None, status=None):
    global _tasks
    ...
```

The task list is a module-level list. It resets when `action="create"` is
called. This means:
- One task list per session (REPL mode: persists across turns)
- No persistence to disk (ephemeral, per-session planning)
- Sub-agents don't see the parent's task list (separate imports)

### Display Format

```
Task plan (2/5 done):
[x] 0. Read the config file
[x] 1. Find the bug
[~] 2. Fix the validation logic
[ ] 3. Add test
[ ] 4. Run tests
```

Status symbols: `[ ]` pending, `[~]` in progress, `[x]` done, `[-]` skipped.
Familiar from any TODO list. The counter at top gives a quick progress summary.

## Note 25: Multi-File Coordinated Edits (Phase 6)

### Not a New Tool — Prompt Guidance

The LLM can already edit multiple files (call `edit_file` repeatedly). The
problem is *strategy*: without guidance, it might edit a consumer before the
provider, or forget to update an import.

The fix is system prompt guidance:

```
When a task requires changes across multiple files, use task_list to plan
the steps first. Execute edits in dependency order — change the foundation
before the code that depends on it.
```

Combined with the task_list tool, this gives the LLM a structured workflow:

1. Create a task plan listing all files to change
2. Edit foundation files first (e.g., the module being imported)
3. Edit dependent files (e.g., the module doing the importing)
4. Mark each step done as you go

This is prompt engineering, not a new tool. The right instruction can be
more effective than a complex tool.

## Note 26: Sub-Agents (Phase 6)

### The Concept

A sub-agent is a separate, isolated LLM conversation spawned by the main
agent. Think of it as a research assistant:

```
Main conversation:
  User: "Refactor the auth module"
  Agent: I'll research the current structure first.
         → sub_agent("Find all files that import from auth.py and list the
                       functions they use")
  Sub-agent: (reads files, searches, returns findings)
  Agent: Based on the research, here are the files that need changes...
```

### Why Isolation?

1. **Context protection** — reading 10 files for research would flood the
   main context. The sub-agent's context is separate and discarded after.
2. **Focused reasoning** — the sub-agent has a clear, narrow task. No
   distraction from the broader conversation.
3. **Reuse** — the sub-agent reuses the same LLM client (connection, config).

### Read-Only Access

Sub-agents only get SAFE tools: `read_file`, `glob`, `grep`, `list_directory`,
`git_status`, `git_diff`, `git_log`. They cannot:
- Write files
- Run bash commands
- Make git commits
- Spawn their own sub-agents (no recursion)

This is a deliberate safety choice. A sub-agent that can write files could
make unreviewed changes. Read-only ensures the main agent stays in control.

### Non-Streaming

Sub-agents use `client.chat()` (non-streaming), not `client.chat_stream()`.
Their output goes back to the parent as a tool result, not streamed to the
user. The parent decides what to show.

### Client Sharing

The sub-agent shares the parent's `LLMClient` via a module-level setter:

```python
# sub_agent.py
_client: LLMClient | None = None

def set_client(client: LLMClient) -> None:
    global _client
    _client = client
```

Called once in `Session.__init__()`. This avoids creating duplicate HTTP
connections and ensures the sub-agent uses the same model/endpoint.

### Iteration Limit

Sub-agents are capped at 15 iterations (vs 50 for the main loop). Research
tasks should complete quickly — if a sub-agent needs 15+ tool calls, the
task was probably too broad.

## Note 27: Web Fetch Tool (Phase 6)

### URL Fetching, Not Web Search

`web_fetch` takes a specific URL and returns its text content. It does NOT
search the web. The LLM needs to already know the URL (e.g., from a README,
documentation link, or user message).

Web *search* (finding URLs by query) requires an external search engine API
(Brave, SearXNG, etc.) and will be added later via MCP.

### HTML-to-Text Extraction

Most web pages are HTML. We do a simple conversion:

1. Remove `<script>` and `<style>` blocks entirely
2. Replace block-level tags (`<p>`, `<div>`, `<h1>`, `<br>`) with newlines
3. Strip all remaining HTML tags
4. Decode HTML entities (`&amp;` → `&`, `&#39;` → `'`)
5. Collapse whitespace

This is naive but effective for documentation pages, READMEs, and API docs.
It fails on JavaScript-heavy SPAs (content is in JS, not HTML), but those
would need a full browser engine anyway.

### Why Not BeautifulSoup?

`beautifulsoup4` is the standard Python HTML parser, but it's an extra
dependency. Our regex-based approach handles the common cases. The tradeoff:

| Approach | Accuracy | Dependencies | Code |
|----------|----------|-------------|------|
| BeautifulSoup | High | `beautifulsoup4` + parser | ~20 lines |
| **Regex strip** | **Medium** | **None (stdlib only)** | **~10 lines** |
| Readability algorithms | Very high | `readability-lxml` | ~5 lines |

For an AI assistant fetching docs, medium accuracy is fine. If the text
extraction is poor for a specific page, the LLM can try a different URL
or fall back to `bash("curl ...")` for the raw content.

### Safety Limits

- **URL validation**: must start with `http://` or `https://`
- **Timeout**: 15 seconds
- **Max response size**: 512KB (prevents downloading huge files)
- **Max output chars**: 20,000 (truncated to avoid flooding context)

The output limit is important — a single large web page could consume
5000+ tokens. At 20K chars ÷ 4 ≈ 5000 tokens, this is a reasonable cap
for a single tool call result.

### httpx, Not requests

We use `httpx` (already a dependency via the openai SDK) instead of
`requests`. No new dependency needed. `httpx` also has better timeout
handling and async support if we need it later.

## Note 28: Per-Project Config & Model Profiles (Phase 7)

### The Problem

Before config files, all settings were CLI flags or env vars:

```bash
klaude --model gpt-4o --base-url https://api.openai.com/v1 --context-window 128000
```

This is tedious to type repeatedly and doesn't persist per-project.

### .klaude.toml

We use TOML (Python 3.11+ has `tomllib` in stdlib — zero dependencies).
The config file lives at the project root, found by walking upward from cwd
(same as KLAUDE.md and `.git`).

```toml
[default]
model = "qwen3-coder-next"
base_url = "http://localhost:8080/v1"
context_window = 65536

[profiles.remote]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
context_window = 128000
```

### Resolution Order

Settings are resolved highest-priority-first:

```
CLI flags  >  Environment variables  >  .klaude.toml  >  Built-in defaults
```

In code, Click's defaults are set to `None` instead of hardcoded values.
This lets us distinguish "user didn't pass this flag" from "user passed the
default value". Then we merge: `effective = cli_value or config_value`.

### Model Profiles

The `--profile` flag selects a named profile:

```bash
klaude --profile remote "explain this code"
```

Profiles override the `[default]` section. Use cases:
- `local`: Qwen3-Coder on localhost
- `remote`: GPT-4o on OpenAI API
- `fast`: smaller/faster model for simple tasks

### api_key_env: Indirection for Secrets

Rather than putting API keys directly in config files:

```toml
api_key_env = "OPENAI_API_KEY"  # reads from environment variable
```

The `env:` prefix also works in MCP server environment variables:

```toml
[mcp.servers.github]
env = { GITHUB_TOKEN = "env:GITHUB_TOKEN" }
```

This way `.klaude.toml` can be committed to git safely.

## Note 29: Hooks (Phase 7)

### Pre/Post Tool Execution

Hooks are shell commands that run before and/or after every tool call:

```toml
[hooks]
pre_tool = "echo '[$(date)] Tool: {tool_name}' >> ~/.klaude/tool.log"
post_tool = ""
```

Placeholders `{tool_name}` and `{arguments}` are substituted before execution.

### Design: Best-Effort, Non-Blocking

Hooks are "fire and forget":
- 5-second timeout (won't block the agentic loop)
- Errors are silently ignored (hooks shouldn't crash the main app)
- Run via `subprocess.run(["bash", "-c", cmd])`

This is intentionally simple. Hooks are for logging, notifications, or
simple validation — not for complex transformations. A future enhancement
could add hook return values that block tool execution (like Claude Code's
PreToolUse hooks).

## Note 30: Custom Tool Plugins (Phase 7)

### How Plugins Work

klaude scans a directory (default: `.klaude/tools/`) for Python files.
Each file that exports a `tool` variable (a `Tool` instance) gets its
tool registered alongside the built-in tools.

```python
# .klaude/tools/jira_lookup.py
from klaude.tools.registry import Tool

def handle_jira(ticket_id: str) -> str:
    import subprocess
    result = subprocess.run(["jira", "view", ticket_id], capture_output=True, text=True)
    return result.stdout

tool = Tool(
    name="jira_lookup",
    description="Look up a JIRA ticket by ID.",
    parameters={
        "type": "object",
        "properties": {"ticket_id": {"type": "string"}},
        "required": ["ticket_id"],
    },
    handler=handle_jira,
)
```

### Dynamic Import

We use `importlib.util.spec_from_file_location()` to import plugin files
without them being on the Python path. Each file gets a unique module name
(`klaude_plugin_<stem>`) to avoid collisions.

Files starting with `_` are skipped (convention for helper modules).
Import errors are caught and silently skipped — one broken plugin shouldn't
prevent klaude from starting.

### Security Note

Plugins run with the same privileges as klaude itself. There's no sandboxing
of plugin code. This is acceptable because:
1. Users install plugins themselves (from their own `.klaude/tools/`)
2. The permission system still applies to plugin tools
3. This matches how Claude Code's custom tools work

## Note 31: MCP — Model Context Protocol (Phase 7)

### What Is MCP?

MCP (Model Context Protocol) is a standard created by Anthropic for
connecting AI assistants to external tool servers. Think of it as a
**universal plugin protocol**: instead of building a custom GitHub
integration, Slack integration, database integration, etc., you connect
to MCP servers that already exist for those services.

```
┌──────────┐         MCP Protocol         ┌──────────────┐
│  klaude  │ ◄══════════════════════════► │  MCP Server  │
│ (client) │    JSON-RPC over stdio       │  (e.g. GitHub)│
└──────────┘                               └──────────────┘
```

### The Protocol (JSON-RPC)

MCP uses JSON-RPC 2.0 — a simple request/response protocol. Messages are
JSON objects sent over a transport (usually stdio pipes or HTTP).

A client (klaude) sends requests like:

```json
{"jsonrpc": "2.0", "method": "tools/list", "id": 1}
```

And the server responds:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "search_code",
        "description": "Search code in a GitHub repository",
        "inputSchema": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "repo": {"type": "string"}
          },
          "required": ["query"]
        }
      }
    ]
  }
}
```

To call a tool:

```json
{"jsonrpc": "2.0", "method": "tools/call", "id": 2,
 "params": {"name": "search_code", "arguments": {"query": "auth bug"}}}
```

Response:

```json
{"jsonrpc": "2.0", "id": 2,
 "result": {"content": [{"type": "text", "text": "Found 3 matches..."}]}}
```

You don't need to implement any of this yourself — the `mcp` Python SDK
handles all the JSON-RPC encoding, framing, and transport.

### Transport: stdio

The most common MCP transport is **stdio**: the client spawns the server
as a subprocess and communicates via stdin/stdout.

```
klaude                          MCP server process
  │                                  │
  │── spawn subprocess ──────────────│
  │                                  │
  │── write JSON-RPC to stdin ──────►│
  │                                  │── process request
  │◄── read JSON-RPC from stdout ────│
  │                                  │
```

This is how most MCP servers work: `npx @modelcontextprotocol/server-github`,
`python -m mcp_server_sqlite`, etc. The server runs as a child process
and dies when the client disconnects.

HTTP/SSE transport also exists for remote servers, but stdio is simpler
and more common for local use.

### Our Implementation: MCPBridge

The challenge: the `mcp` SDK is fully async (asyncio), but klaude's
agentic loop is synchronous. We bridge this with a background event loop:

```
Main thread (sync)              Background thread (async)
─────────────────               ─────────────────────────
Session.__init__()
  │
  ├─ MCPBridge()
  │   └─ starts background       asyncio event loop running
  │      thread with             ◄────────────────────────
  │      asyncio loop
  │
  ├─ bridge.connect_all()
  │   └─ run_coroutine_         → stdio_client(params)
  │      threadsafe()           → session.initialize()
  │                             → session.list_tools()
  │   ◄─ returns tools ─────────
  │
  ...later, during tool call...
  │
  ├─ handler(**kwargs)
  │   └─ run_coroutine_         → session.call_tool(name, args)
  │      threadsafe()
  │   ◄─ returns result ────────
```

`asyncio.run_coroutine_threadsafe()` is the key function — it submits
a coroutine to the background loop and returns a `Future` that we can
`.result()` on from the sync main thread.

### Tool Name Namespacing

MCP tools are prefixed with `mcp_<server_name>_` to avoid collisions:

```
MCP server "github" tool "search_code"  →  klaude tool "mcp_github_search_code"
```

The LLM sees all tools (built-in + MCP) in a flat list. The prefix
tells it (and us) where a tool comes from.

### Configuration in .klaude.toml

```toml
[mcp.servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_TOKEN = "env:GITHUB_TOKEN" }

[mcp.servers.sqlite]
command = "python"
args = ["-m", "mcp_server_sqlite", "--db", "mydb.sqlite"]
```

Each `[mcp.servers.<name>]` entry defines:
- `command`: the executable to run
- `args`: command-line arguments
- `env`: environment variables (with `env:` indirection for secrets)

### Error Handling

MCP server failures don't crash klaude:
- Connection failure → warning printed, server skipped
- Tool call failure → error string returned to LLM (it can try another approach)
- Server crash mid-session → next tool call returns an error

### What MCP Unlocks

With MCP support, klaude can now use any MCP server:
- **GitHub**: PRs, issues, code search, file contents
- **Slack**: read/send messages, search channels
- **Databases**: SQLite, PostgreSQL queries
- **File systems**: remote file access
- **Custom tools**: any server that speaks MCP

No custom code needed per service — just a config entry.

## Note 32: Undo / Time Travel (Phase 7)

### The Problem

In a multi-turn REPL session, the LLM might make a mistake: edit the
wrong file, go down a wrong path, or produce an unhelpful response. Without
undo, the user's options are:
1. `/clear` — loses ALL context, starts from scratch
2. Keep going — the mistake pollutes the conversation history
3. Manually fix it — tedious

### Snapshots

Before each turn, Session saves a snapshot of the conversation state:

```python
def snapshot(self) -> None:
    snap = (self.turn_count, copy.deepcopy(self.history.messages))
    self._snapshots.append(snap)
```

`copy.deepcopy` is important — we need an independent copy of the message
list, not a reference to the same list. Messages are dicts of strings and
lists, so deepcopy handles them correctly.

### Undo

`/undo` (or pressing Esc) pops the most recent snapshot and restores it:

```python
def undo(self) -> bool:
    if not self._snapshots:
        return False
    turn_count, messages = self._snapshots.pop()
    self.turn_count = turn_count
    self.history._messages = messages
    return True
```

This restores the history to exactly what it was before the last turn.
The LLM's response and any tool calls from that turn are erased.

### Depth Limit

Snapshots are capped at `undo_depth` (default 10). Each snapshot is a full
copy of the message history, which can be large after many turns. The cap
prevents memory from growing unboundedly.

### Esc Key Binding

The Esc key is bound in readline to type `/undo` and submit:
- On GNU readline: `"\\e": "\\C-a\\C-k/undo\\C-m"` (clear line, type /undo, enter)
- On macOS libedit: `bind "\\e" "\\e[H\\e[2K/undo\\n"` (similar)

This gives the user a one-key "go back" that feels like undo in an editor.

### What Undo Does NOT Do

Undo restores the **conversation state** — it does not reverse file changes.
If the LLM edited a file in the undone turn, the file stays modified on
disk. This is intentional: file changes should be managed with git
(`git_diff`, `git checkout`), not a conversation-level undo.

A future enhancement could integrate with git to also revert file changes.

## Note 33: Config-Driven Architecture (Phase 7)

### The Shift

Before Phase 7, klaude's behavior was determined by:
1. Hardcoded defaults in Python files
2. CLI flags
3. Environment variables

After Phase 7, there's a new layer: the `.klaude.toml` config file.
This moves klaude from a "one-size-fits-all" tool to a configurable
platform:

```
┌─────────────────────────────────────────┐
│ CLI flags (highest priority)            │
├─────────────────────────────────────────┤
│ Environment variables                   │
├─────────────────────────────────────────┤
│ .klaude.toml config file                │
│  ├── [default] settings                 │
│  ├── [profiles.*] model profiles        │
│  ├── [hooks] pre/post tool hooks        │
│  ├── [plugins] custom tools directory   │
│  └── [mcp.servers.*] MCP connections    │
├─────────────────────────────────────────┤
│ Built-in defaults (lowest priority)     │
└─────────────────────────────────────────┘
```

### Why TOML?

| Format | Stdlib support | Human-readable | Comments | Nested |
|--------|---------------|----------------|----------|--------|
| JSON | Yes | OK | No | Yes |
| YAML | No (PyYAML) | Good | Yes | Yes |
| INI | Yes (configparser) | Good | Yes | Limited |
| **TOML** | **Yes (3.11+)** | **Great** | **Yes** | **Yes** |

TOML is the best fit: it's in Python's stdlib (3.11+), very readable,
supports comments and nested sections, and is the standard for Python
project config (`pyproject.toml`).

## Note 34: Skills — Reusable Prompt Templates (Phase 7)

### What Skills Are

A skill is a reusable prompt template invoked from the REPL with a slash
command: `/commit`, `/review`, `/explain`, or any custom name you define.
When you run `/commit fix auth bug`, klaude renders the skill's body into
a complete user message and feeds it through the normal agentic loop —
the same path as typing a message directly. The LLM then follows those
instructions, using whatever tools it needs.

Skills are not tools. They don't have JSON schemas. They don't get called
by the LLM. They are instructions *for* the LLM, written in plain markdown.

### Two Sources of Skills

Skills are loaded from two places, with user skills winning on name conflicts:

```
Built-in skills (hardcoded in skills.py)
    commit   — analyze git diff and write a meaningful commit message
    review   — code review of recent changes
    explain  — orient a new reader to the codebase

User skills (.klaude/skills/*.md)
    deploy   — your own deploy workflow
    commit   — override the built-in with your team's conventions
    ...
```

`load_all_skills()` builds a `dict[str, Skill]` by loading built-ins first,
then user skills — later entries overwrite earlier ones with the same name.
Files prefixed with `_` are skipped (good for drafts or disabled skills).

### Skill File Format

A user skill is a plain `.md` file with YAML frontmatter:

```markdown
---
name: deploy
description: Deploy to production with safety checks
---
Check git status is clean, run tests with bash, then deploy.

{input}
```

The frontmatter provides the name and description. The body is the prompt
text. If no `name` key is present, the filename stem is used as the name.

### Parameter Substitution

Two placeholders are available in the body:

| Placeholder | Replaced with |
|-------------|---------------|
| `{input}`   | Everything the user typed after the skill name (e.g., `/commit fix auth` → `"fix auth"`) |
| `{cwd}`     | The current working directory at invocation time |

When `{input}` is empty (user typed just `/commit` with nothing after),
the substitution leaves a blank string. Repeated `\n\n\n` sequences are
collapsed to `\n\n` to avoid awkward blank lines in the rendered prompt.

```python
def render(self, user_input: str = "") -> str:
    text = self.body.replace("{input}", user_input).replace("{cwd}", os.getcwd())
    if not user_input:
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
    return text.strip()
```

### Frontmatter Parsing Without PyYAML

We parse the frontmatter ourselves instead of adding a PyYAML dependency:

```python
def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)      # find closing ---
    fm_text = text[3:end].strip()
    body = text[end + 3:].strip()
    metadata: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()
    return metadata, body
```

This handles only flat `key: value` pairs — no lists, no nesting, no
multi-line values. That's all we need for `name` and `description`.
The trade-off is intentional: zero new dependencies, 15 lines of code,
and skill files stay simple by design. If a skill file is broken, it's
silently skipped rather than crashing the session.

### REPL Integration — Three Return Types

`_handle_slash_command()` in `repl.py` has an unusual but elegant signature:

```python
def _handle_slash_command(command: str, session: Session, console: Console) -> bool | str:
```

The three return values mean:

| Return value | Meaning |
|--------------|---------|
| `False`      | Exit the REPL (`/exit`, `/quit`) |
| `True`       | Command handled, continue the loop (e.g., `/clear`, `/history`) |
| `str`        | A rendered skill prompt — pass it to `session.turn()` |

The REPL dispatch is then just:

```python
result = _handle_slash_command(stripped, session, console)
if result is False:
    break
if isinstance(result, str):
    session.turn(result)   # run the rendered prompt through the agentic loop
# True falls through — continue
```

This keeps skills out of the REPL's control flow entirely. A skill is just
a string that arrives at the same place as a typed message. No special code
path, no extra loop, no flag to check.

### Why Prompt Injection, Not a New Tool?

An alternative design would make each skill a tool the LLM could call:
`use_skill("commit")`. We rejected this for several reasons:

1. **No schema overhead.** Tools need JSON schemas, input validation, and
   a handler function. A skill is just markdown — zero boilerplate.

2. **User intent, not LLM intent.** The user invokes a skill; the LLM
   doesn't decide to. Skills are a user shortcut, not an LLM capability.

3. **Works with any model.** Skills don't depend on tool-calling support.
   They're ordinary user messages — every chat model understands them.

4. **Easy to author.** A user can create a skill with a text editor and
   zero Python knowledge. No need to understand schemas or registries.

### Configuration

`skills_dir` lives in `KlaudeConfig` (default `.klaude/skills`):

```toml
# .klaude.toml
[plugins]
skills_dir = "team-skills"   # load skills from a custom directory
```

The `[plugins]` section groups extensibility settings together — the same
section that holds `tools_dir` for custom Python tools. This makes it easy
to version-control a project's skills alongside its custom tools and check
them into the repository so the whole team shares them.

## Note 35: Agent Teams — Collaborative Task Execution (Phase 8)

### What Teams Are

Teams extend the sub_agent concept from one anonymous researcher to a named
group of specialists, each with a defined role and configurable tool access.
The distinction is worth stating clearly:

```
sub_agent  — one call, one anonymous read-only agent, results returned inline
teams      — named specialists, varying tool access, shared message board,
             sequential execution with context chaining between members
```

A team is created by the lead agent (the main Session's LLM), populated with
role definitions, and then driven by delegating tasks to each member in turn.
Members can see one another's results through a shared message board, so later
members build on earlier ones without the lead having to manually relay findings.

### Architecture

Three new files, two updated files.

**`src/klaude/team.py`** — core types and execution engine:
- `AgentRole` dataclass: name, description, system_prompt, tool_access
- `TeamMessage` dataclass: sender, content, recipient, timestamp
- `MessageBoard` class: thread-safe shared context
- `_create_registry(tool_access)` — builds the right `ToolRegistry` per level
- `_build_member_system_prompt()` — injects board messages into the system prompt
- `run_agent()` — runs one member's isolated agentic loop

**`src/klaude/tools/team.py`** — three tools the LLM can call:
- `team_create` — define the team and its members
- `team_delegate` — run one member on a task
- `team_message` — read from or post to the shared board

**`loop.py`** — registers the three team tools in the main `ToolRegistry` and
calls `tools.team.set_client(client)` alongside the existing
`tools.sub_agent.set_client(client)` call.

**`prompt.py`** — adds a guidance section explaining when and how to use teams
(complex multi-step tasks, not for simple single-agent work).

### Tool Access Levels

`_create_registry(tool_access)` builds the right set of tools for each tier:

```python
def _create_registry(tool_access: str) -> ToolRegistry:
    registry = ToolRegistry()

    # Always: read-only exploration (same as sub_agent)
    registry.register(read_file_tool)
    registry.register(glob_tool)
    registry.register(grep_tool)
    registry.register(list_directory_tool)
    registry.register(git_status_tool)
    registry.register(git_diff_tool)
    registry.register(git_log_tool)

    if tool_access in ("readwrite", "full"):
        registry.register(write_file_tool)
        registry.register(edit_file_tool)

    if tool_access == "full":
        registry.register(bash_tool)
        registry.register(git_commit_tool)
        registry.register(web_fetch_tool)

    return registry
```

The three tiers map to natural roles:

| Level | Extra tools | Typical role |
|-------|-------------|--------------|
| `readonly` | — | Researcher, analyst, reviewer |
| `readwrite` | write_file, edit_file | Coder, refactorer |
| `full` | + bash, git_commit, web_fetch | Builder, deployer |

`readonly` is the default and matches sub_agent exactly — safe exploration with
no side effects. Each tier adds strictly more tools, so a `full` member can do
everything a `readonly` member can.

### Message Board

`MessageBoard` is a thread-safe container for inter-agent messages. The design
is simple: messages are either broadcasts (no recipient) or addressed to a
specific agent.

```python
def get_for(self, agent_name: str) -> list[TeamMessage]:
    """Get messages visible to a specific agent (broadcasts + direct messages)."""
    with self._lock:
        return [
            m for m in self._messages
            if m.recipient is None or m.recipient == agent_name
        ]
```

This single method drives context chaining: when `_build_member_system_prompt()`
constructs a member's system prompt, it calls `board.get_for(role.name)` to
include all messages they're allowed to see. Since `run_agent()` auto-posts the
result when a member finishes, the next member's system prompt automatically
contains all previous results:

```
# Automatically at end of run_agent():
board.post(role.name, result)
```

The board exposes `post(sender, content, recipient=None)` for explicit messages
(the lead can post context before delegating), and `format()` for the
`team_message` tool to display the board in a human-readable form.

The `_lock` is a `threading.Lock()`. Sequential execution doesn't strictly
require it, but it costs nothing and leaves the door open for parallel execution
in a future where llama-server can handle concurrent requests.

### Sequential Execution

Members run one at a time. This is an explicit design decision, not a
limitation we plan to fix:

1. **llama.cpp constraint** — `llama-server` typically processes one request at
   a time. Parallel calls would queue anyway, giving no speedup.
2. **Context chaining is natural** — sequential execution means member N always
   sees member N-1's results. With parallel execution you'd need an explicit
   aggregation step to share results.
3. **Simpler error handling** — if a member fails, the lead sees the error
   immediately and can adjust the next delegation accordingly.

The thread-safety in `MessageBoard` is future-proofing, not current necessity.

### How a Team Run Looks

Here's a concrete walkthrough of the full flow for "refactor the auth module":

```
1. LLM calls team_create:
   members = [
     {name: "researcher",  tool_access: "readonly",  description: "Map auth dependencies"},
     {name: "coder",       tool_access: "readwrite", description: "Perform the refactor"},
     {name: "reviewer",    tool_access: "readonly",  description: "Check correctness"},
   ]

2. LLM calls team_delegate(member_name="researcher", task="Find all files that
   import from auth.py and list the functions they use")
   → run_agent() runs researcher's isolated loop (up to 20 iterations)
   → researcher reads files, greps for imports, builds a map
   → auto-posts findings to the board
   → returns: "[researcher] auth.py exports 3 functions, imported by 5 files..."

3. LLM calls team_delegate(member_name="coder", task="Split auth.py into
   auth/core.py and auth/tokens.py, updating all imports")
   → coder's system prompt includes researcher's findings (from board.get_for)
   → coder edits files with full context of what needs updating
   → auto-posts "Refactor complete, updated 5 files" to the board

4. LLM calls team_delegate(member_name="reviewer", task="Verify the refactor
   is correct and all imports resolve")
   → reviewer sees both researcher and coder messages in system prompt
   → reviewer reads files, checks imports, confirms correctness
   → auto-posts verdict

5. LLM calls team_message(action="read") to see the full board
   → synthesizes all three results into a final summary for the user
```

The lead agent orchestrates the whole flow through tool calls, never leaving
the agentic loop. From the lead's perspective, each delegation is just a tool
call that returns a string.

### Module-Level State Pattern

Like other stateful tools in klaude, team tools use module-level variables:

```python
# src/klaude/tools/team.py
_client: LLMClient | None = None
_team_name: str = ""
_members: dict[str, AgentRole] = {}
_board: MessageBoard = MessageBoard()

def set_client(client: LLMClient) -> None:
    global _client
    _client = client
```

`set_client()` is called once in `Session.__init__()`, sharing the same
`LLMClient` instance used by the main loop and sub_agent. This means:
- No duplicate HTTP connections to llama-server
- Team members use the same model and endpoint as the lead
- The pattern is identical to `tools.sub_agent.set_client(client)`

`team_create` resets `_members` and clears the board — creating a new team
replaces the old one. There's one active team per session at any time.

### Stats

- **17 tools total**: 14 existing + 3 team tools (team_create, team_delegate,
  team_message)
- **2 new files**: `src/klaude/team.py` (~240 lines), `src/klaude/tools/team.py`
  (~260 lines)
- **Max iterations per member**: 20 (vs 50 for the main loop, 15 for sub_agent)

## Note 36: Customer Care — Documentation (Phase 9)

### Overview

Phase 9 is about making klaude usable by people who weren't there while it was
built. The code is solid, but without documentation it is a black box. The goal:
someone who just cloned the repo should be able to download a model, start the
server, and run their first task within 15 minutes.

### Doc Structure

Seven new files, organized by audience and purpose:

| File | Audience | Purpose |
|------|----------|---------|
| `README.md` | Everyone | Project overview, quick start, feature summary, links to all docs |
| `docs/INSTALL.md` | New users | Installation for macOS, Linux, Windows/WSL |
| `docs/SETUP-MODEL.md` | New users | Qwen3-Coder-Next download, quantization options, llama-server config |
| `docs/USAGE.md` | Human operators | REPL, tools, permissions, config, skills, plugins, MCP, teams |
| `docs/AGENT-GUIDE.md` | Model developers | Tool schemas, agentic loop details, patterns, anti-patterns |
| `docs/TROUBLESHOOTING.md` | Anyone stuck | Q&A format, common issues and fixes |
| `docs/examples/*.klaude.toml` | All users | 5 copy-paste-ready config examples |

### Design Decisions

**Concise, not comprehensive.** Every doc favors short copy-paste commands over
lengthy explanations. If you can show it in a code block, do not explain it in
a paragraph. A user who can copy-paste a working command learns faster than one
who reads a page of prose.

**Q&A format for troubleshooting.** Pattern matching is fast. Users scan for
their exact error message, find the answer immediately. Prose paragraphs require
reading; a `### Problem: <error text>` header requires one eye movement.

**Example configs as separate files.** The five files under `docs/examples/`
are complete, valid `.klaude.toml` configs that a user can literally copy to
their project root. No need to extract snippets from prose, no risk of missing
a required key.

**Two audience tracks.** `USAGE.md` covers the human workflow: launching the
REPL, approving tool calls, setting up config, working with skills and plugins.
`AGENT-GUIDE.md` covers the model's perspective: tool schema format, how the
agentic loop processes responses, which patterns work and which cause loops or
stalls. Keeping these separate avoids a single document that is too abstract for
humans and too shallow for model developers.

**README as table of contents.** The README links to every doc and gives a
one-paragraph summary of each. No information lives in the README that is not
covered in detail elsewhere. This keeps the README short enough to read in
two minutes and ensures deep information is findable without scrolling.

**Study materials preserved.** The existing `docs/00-07` files are educational
deep dives written while the code was being built. The new docs are practical
how-to guides. They complement each other: a contributor reads the study
materials to understand why something was built a certain way; a new user reads
the how-to guides to get running fast.

### Example Config Coverage

The five example configs under `docs/examples/` cover the most common setups:

- `local.klaude.toml` — minimal config for llama-server on localhost:8080
- `remote-openai.klaude.toml` — remote OpenAI API with API key from env var
- `multi-profile.klaude.toml` — multiple named profiles switchable via --profile
- `mcp-servers.klaude.toml` — MCP server integration (GitHub, filesystem, Postgres)
- `full.klaude.toml` — all supported keys, useful as a reference/template

Each file includes inline comments explaining every key. A user new to TOML can
read any of them without consulting a separate config reference.

### Git Setup

Also initialized the git repo as part of Phase 9. Steps taken:

1. Created `.gitignore` covering Python artifacts (`.venv`, `__pycache__`,
   `*.pyc`), model files (`*.gguf`, `*.bin`), history (`.klaude_history`),
   and session temporaries (`tmp/`).
2. Ran `git init` and staged all 47 tracked files.
3. The initial staging excludes the model cache under
   `~/Library/Caches/llama.cpp/` — that path is outside the repo, so it
   never appears in `git status`.

### Stats

- 5 new documentation files (`INSTALL.md`, `SETUP-MODEL.md`, `USAGE.md`,
  `AGENT-GUIDE.md`, `TROUBLESHOOTING.md`)
- 5 example config files under `docs/examples/`
- 1 `README.md`
- 1 `.gitignore`
- 47 files tracked in initial git staging
- Approximately 900 lines of new documentation total

## Note 37: Web Search & Ask User — New Tools (Phase 10)

### Overview

Phase 10 adds Claude Code parity features. The first batch: `web_search`
(keyword search, not just URL fetch) and `ask_user` (structured question
with guaranteed response). Both are classified as SAFE tools — no
permission prompt needed.

### web_search — DuckDuckGo HTML Scraping

The key design question: how to do keyword search without an API key?

**Options considered:**
1. Google Custom Search API — requires API key + project setup
2. Bing Search API — requires Azure subscription
3. SearXNG — self-hosted, but requires running another service
4. DuckDuckGo HTML endpoint — no API key, returns parseable HTML

We chose option 4. DuckDuckGo's `html.duckduckgo.com/html/` endpoint
returns a simplified HTML page with search results. No JavaScript
rendering, no API key, no rate limiting (within reason).

**Parsing strategy:** Three-tier regex extraction with progressive fallback:

```
Tier 1: result-link + result-snippet class patterns
Tier 2: rel="nofollow" links + snippet classes
Tier 3: raw href extraction (any http link with text > 5 chars)
```

Each tier catches a different HTML structure DuckDuckGo might serve.
The fallback chain means the tool degrades gracefully rather than
returning "no results" when the HTML format changes slightly.

**Output format:** Numbered list with title, URL, and snippet for each
result. Ends with a hint to use `web_fetch` to read the full page. This
creates a natural two-step workflow: search → fetch.

```
1. Python subprocess — Real Python
   URL: https://realpython.com/python-subprocess/
   The subprocess module allows you to spawn new processes...
```

**Uses httpx** (already a transitive dependency via openai) — zero new
packages added.

### ask_user — Structured User Interaction

Without `ask_user`, the model's only way to ask a question is to emit
text and hope the user reads it and responds on the next turn. This is
fragile: the model might emit a question buried in a long response, or
the user might not realize a response is expected.

`ask_user` makes the interaction explicit:
1. Model calls `ask_user(question="Which database?")`
2. Tool renders the question in a yellow `rich.Panel`
3. User types their answer at the `Your answer: ` prompt
4. Answer returns as the tool result — model sees it immediately

**Console sharing:** The tool needs a `rich.Console` for styled output.
We use the same module-level pattern as `sub_agent` — `set_console()` is
called by `Session.__init__()` so the tool shares the session's console.

**Edge cases:** EOF (Ctrl+D) returns "(user ended input)". Ctrl+C returns
"(user cancelled)". Empty response returns "(user gave no response)".
All three are distinguishable by the model so it can react appropriately.

### Safety Classification

Both tools are in `SAFE_TOOLS` — no permission prompt:
- `web_search`: read-only, outbound HTTP only, no file system access
- `ask_user`: only reads from stdin, no side effects

## Note 38: Plan Mode — Read-Only Toggle (Phase 10)

### Overview

Plan mode restricts the agent to read-only tools. When active, the model
can explore code, search, discuss plans, and ask questions — but cannot
write files, run commands, or commit. This is useful for:

- **Safe exploration**: let the model investigate before you approve changes
- **Architecture discussion**: plan multi-file changes without risk
- **Code review**: read and analyze without accidental modifications

### Implementation

Plan mode is a boolean flag on `PermissionManager`:

```python
self.plan_mode = False  # toggled by /plan REPL command
```

When active, `check_tool()` blocks any tool in `PLAN_MODE_BLOCKED` before
the permission prompt even fires:

```python
PLAN_MODE_BLOCKED = {"bash", "write_file", "edit_file", "git_commit", "team_delegate"}
```

The block happens at the same level as command denylist and path sandboxing —
the model receives an error message explaining why the tool was blocked, and
it can adapt (e.g., describe what it would do instead of doing it).

**Why block `team_delegate`?** Team members can have `readwrite` or `full`
access tiers. Delegating to them would bypass plan mode's restrictions.

**What stays allowed:** All read tools (`read_file`, `glob`, `grep`,
`list_directory`, `git_status`, `git_diff`, `git_log`), research tools
(`sub_agent`, `web_search`, `web_fetch`), planning tools (`task_list`),
interaction tools (`ask_user`), and team coordination (`team_create`,
`team_message`). The model can do everything except modify state.

### REPL Integration

- `/plan` toggles the flag on/off
- Prompt changes: `klaude>` → `klaude[plan]>` — visual indicator
- The toggle is instant — no history clearing, no session restart
- Switching off restores full access immediately

### Comparison with Claude Code

Claude Code's plan mode (`EnterPlanMode`/`ExitPlanMode`) is a tool the
model calls itself. klaude's is user-controlled via `/plan`. The user
decides when to restrict the model, not the other way around. This is
a deliberate choice: the user is the trust boundary.

## Note 39: LSP Tool — Code Intelligence (Phase 10)

### Overview

The `lsp` tool provides go-to-definition, find-references, and diagnostics
without requiring a running language server process. It uses a two-tier
approach: jedi for Python (accurate, AST-based), grep for everything else.

### Why Not a Real LSP Client?

A proper LSP client would need to:
1. Start a language server process (pyright, tsserver, gopls, etc.)
2. Send `initialize`, wait for capabilities
3. Open documents, wait for diagnostics
4. Send `textDocument/definition` requests
5. Keep the server alive for the session

That's a lot of complexity for a tool that the model calls occasionally.
Instead, we use two approaches that give 80% of the value:

**Python (jedi):** The `jedi` library does static analysis directly —
no server process needed. One function call gives you definitions,
references, or completions. It understands imports, class hierarchies,
decorators, and most Python patterns. jedi is optional — if not installed,
Python falls back to grep.

**Everything else (grep):** We search for common definition patterns:
```
(def|func|function|fn)\s+SYMBOL\b    # function definitions
class\s+SYMBOL\b                      # class definitions
(const|let|var|val)\s+SYMBOL\b        # variable declarations
type\s+SYMBOL\b                       # type definitions
interface\s+SYMBOL\b                  # interface definitions
```

This catches most definitions in Python, JavaScript, TypeScript, Go, Rust,
Java, Ruby, C, and C++. For references, we use word-boundary grep (`-w`).

### Parameter Design

The tool accepts flexible parameters to handle both tiers:

- **Python with jedi:** `action="definition" path="foo.py" line=42 column=10`
  — precise cursor-position query
- **Grep fallback:** `action="definition" symbol="MyClass"` — searches the
  working directory for definition patterns
- **Diagnostics:** `action="diagnostics" path="foo.py"` — syntax check
  (Python compile() or jedi)

If `path` + `line` are given for a Python file and jedi is available, we
use jedi. Otherwise, we extract the symbol at the given position and fall
back to grep. If only `symbol` is given, we go straight to grep.

### Safety Classification

`lsp` is a SAFE tool — it only reads files and runs grep (never modifies
anything). No permission prompt needed.

## Note 40: Notebook Edit — Jupyter Integration (Phase 10)

### Overview

The `notebook_edit` tool reads, edits, inserts cells into, and executes
Jupyter notebooks (.ipynb files). It works directly with the JSON format
— no dependency on `jupyter` or `nbformat` for read/edit/insert.
Execution optionally uses `jupyter nbconvert` if available.

### .ipynb Format

A Jupyter notebook is just a JSON file:

```json
{
  "cells": [
    {
      "cell_type": "code",
      "source": ["import os\n", "print(os.getcwd())"],
      "metadata": {},
      "execution_count": 1,
      "outputs": [{"output_type": "stream", "text": ["/home/user"]}]
    },
    {
      "cell_type": "markdown",
      "source": ["# Hello"],
      "metadata": {}
    }
  ],
  "metadata": { "kernelspec": {...}, "language_info": {...} },
  "nbformat": 4,
  "nbformat_minor": 5
}
```

Key detail: `source` is a **list of lines** (each ending with `\n`),
not a single string. We handle this conversion transparently — the model
provides content as a plain string, and we split it into the list format
that notebooks expect.

### Four Actions

1. **read**: Parse the notebook and display cells with their outputs.
   Can read all cells or a specific cell by index. Output includes cell
   type, source, and any execution outputs (text, errors, images).

2. **edit**: Modify a cell's source content and optionally change its
   type. Requires `cell_index` and `content`.

3. **insert**: Add a new cell at a specific position (or at the end).
   Creates proper cell structure with metadata and empty outputs.

4. **execute**: Run the notebook via `jupyter nbconvert --execute --inplace`.
   This requires jupyter to be installed. After execution, re-reads the
   notebook to show outputs. Timeout: 120 seconds.

### Safety Classification

`notebook_edit` is classified as DANGEROUS — it writes to .ipynb files
and can execute code. Requires user approval.

## Note 41: Background Tasks — Non-Blocking Sub-Agents (Phase 10)

### Overview

Background tasks let the model launch sub-agents that run in parallel
without blocking the main conversation. The model can start multiple
research tasks, continue talking with the user, and check results later.

### Architecture

```
Main thread (agentic loop)
  │
  ├─ background_task(action="start", task="explore auth code")
  │     └─ spawns Thread-1 → runs handle_sub_agent()
  │
  ├─ background_task(action="start", task="read all test files")
  │     └─ spawns Thread-2 → runs handle_sub_agent()
  │
  ├─ (continues working on other things...)
  │
  ├─ background_task(action="status")
  │     └─ returns: "bg-1: completed (4.2s), bg-2: running (2.1s)"
  │
  └─ background_task(action="result", task_id="bg-1")
        └─ returns the sub-agent's findings
```

### Why Threads, Not Processes?

Sub-agents share the `LLMClient` connection pool. With threads, this
sharing is free — all threads use the same httpx client. With processes,
we'd need to either serialize the client (not possible) or create new
connections per process (wasteful).

The GIL isn't a problem because sub-agents are I/O-bound (waiting for
LLM API responses, reading files). Python releases the GIL during I/O.

### Thread Safety

The job store (`_jobs`) is protected by a `threading.Lock`. Each job is
a `BackgroundJob` dataclass with `status`, `result`, `started_at`, and
`finished_at`. The lock is held only for brief dict operations — no risk
of contention.

Threads are daemonic (`daemon=True`) so they don't prevent the process
from exiting when the user quits the REPL.

### Safety Classification

`background_task` is SAFE — it delegates to `handle_sub_agent`, which
only has read-only tools. A background task cannot write files, run
commands, or commit.

## Note 42: Git Worktrees — Isolated Working Directories (Phase 10)

### Overview

Git worktrees let you have multiple working directories from a single
repository. Each worktree has its own branch and working copy, but they
share the same `.git` directory (object store, refs, config).

```
repo/                          # main worktree (your work)
../.klaude-worktree-refactor/  # agent worktree (klaude/refactor branch)
../.klaude-worktree-fix-bug/   # agent worktree (klaude/fix-bug branch)
```

### Operations

1. **create**: Creates a new worktree alongside the repo directory.
   - Branch: `klaude/<name>` (auto-created from HEAD or specified base)
   - Path: `../.klaude-worktree-<name>` (adjacent to repo root)
   - If the branch already exists, attaches to it instead of creating

2. **list**: Shows all worktrees with their paths, branches, and HEAD SHAs.
   Uses `git worktree list --porcelain` for machine-parseable output.

3. **remove**: Removes a worktree and deletes its branch.
   Uses `--force` to handle unclean worktrees. Branch deletion is
   best-effort (may fail if it's the current branch elsewhere).

### Naming Convention

All klaude worktrees use the `klaude/` branch prefix and
`.klaude-worktree-` path prefix. This makes them easy to identify and
clean up — you can `git worktree list | grep klaude` to find them all.

### Safety Classification

`worktree` is DANGEROUS — it creates branches and directories, and
`remove` deletes them. Requires user approval. This is appropriate
because worktrees affect shared git state.

## Note 43: Cron — Scheduled Recurring Tasks (Phase 10)

### Overview

The cron system runs prompts or skills on a recurring interval within a
REPL session. It's not a system-level cron — it starts and stops with
the session.

### Usage

```
/cron 5m /review          # run /review every 5 minutes
/cron 30s git_status      # check git status every 30 seconds
/cron list                # show active jobs
/cron stop cron-1         # stop a specific job
/cron stop all            # stop all jobs
```

### Architecture

Each cron job uses a `threading.Timer` chain:

```python
def _schedule_next(job):
    def _tick():
        job.run_count += 1
        _run_callback(job.prompt)   # runs session.turn()
        _schedule_next(job)         # schedule next tick
    timer = Timer(job.interval_seconds, _tick)
    timer.daemon = True
    timer.start()
```

This is a "self-rescheduling timer" pattern. After each tick, the callback
schedules the next one. This avoids the complexity of a scheduler thread
and handles variable execution times naturally (the interval is measured
from the end of one execution to the start of the next).

### REPL Integration

The REPL sets a callback function (`session.turn`) that cron jobs use to
run prompts. This decouples cron from the session — cron.py doesn't import
loop.py, and the callback is injected at REPL startup.

On REPL exit, `stop_all()` is called to cancel all pending timers. Since
timers are daemonic, they'd be killed on process exit anyway, but explicit
cleanup is cleaner.

### Interval Parsing

Supports `30s`, `5m`, `1h`, or plain numbers (treated as minutes).
Minimum interval: 10 seconds (prevents accidental flooding).

### Thread Safety Concern

Cron callbacks run `session.turn()` from a timer thread, while the main
thread might also be running `session.turn()` from user input. The session
is not thread-safe — concurrent turns could corrupt message history.

In practice, this is acceptable because:
1. Cron intervals are typically minutes, not seconds
2. The user is usually idle when a cron job fires
3. The worst case is garbled output, not data loss

A production system would need a mutex or message queue, but for an
educational project this trade-off is reasonable.
