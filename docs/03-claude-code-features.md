# Claude Code Features — What We'll Build (and in What Order)

A complete breakdown of Claude Code's capabilities, organized by implementation
priority. Each feature is a learning opportunity.

## Phase 1: Working Demo (MVP)

The minimum to have something useful. Get the loop running end-to-end.

- [ ] **1.1 LLM Client** — OpenAI-compatible client, talks to mlx_lm.server
- [ ] **1.2 Basic Tool System** — registry, executor, JSON schema definitions
- [ ] **1.3 read_file tool** — read file contents, return to LLM
- [ ] **1.4 write_file tool** — create/overwrite files
- [ ] **1.5 bash tool** — execute shell commands, return stdout/stderr
- [ ] **1.6 Agentic Loop** — the core while(tool_calls) loop
- [ ] **1.7 System Prompt** — basic prompt telling the model what tools it has
- [ ] **1.8 CLI Entry Point** — `klaude "do something"` runs the loop
- [ ] **1.9 Streaming Output** — stream text tokens as they arrive

## Phase 2: Essential Tools

Make it actually useful for coding tasks.

- [ ] **2.1 glob tool** — find files by pattern (like `**/*.py`)
- [ ] **2.2 grep tool** — search file contents
- [ ] **2.3 edit_file tool** — surgical edits (not full file rewrites)
- [ ] **2.4 list_directory tool** — ls equivalent
- [ ] **2.5 Improved system prompt** — coding-focused instructions, tool usage guidelines

## Phase 3: Context Management

The hard part. Context windows are finite; real projects are not.

- [ ] **3.1 Token counting** — track how much context we're using
- [ ] **3.2 Message history management** — store and replay conversation
- [ ] **3.3 Context compaction** — summarize old messages when nearing limit
      (Claude Code triggers at ~92% usage)
- [ ] **3.4 Long-term memory** — persist key info to a markdown file (like CLAUDE.md)

## Phase 4: User Experience

Make it pleasant to use in a terminal.

- [ ] **4.1 Rich terminal output** — syntax highlighting, markdown rendering
- [ ] **4.2 Interrupt handling** — Ctrl+C to stop the current action, not kill the app
- [ ] **4.3 Tool call display** — show what tools are being called and their results
- [ ] **4.4 Spinner/progress** — show activity while LLM is thinking
- [ ] **4.5 Multi-turn conversation** — REPL mode, keep chatting
- [ ] **4.6 Input editing** — multi-line input, history

## Phase 5: Safety & Control

The human-in-the-loop parts.

- [ ] **5.1 Permission system** — ask before running destructive commands
- [ ] **5.2 Sandboxing** — restrict file system access, network access
- [ ] **5.3 Command allowlist/denylist** — block dangerous commands by default
- [ ] **5.4 Cost/token budgets** — limit how many tokens a single task can use
- [ ] **5.5 Diff review** — show file changes as diffs before applying

## Phase 6: Advanced Agentic Features

What makes Claude Code powerful beyond basic tool use.

- [ ] **6.1 Task planning (TODO lists)** — model creates structured task lists
- [ ] **6.2 Sub-agents** — spawn separate conversations for exploration
- [ ] **6.3 Git integration** — understand branches, diffs, commit history
- [ ] **6.4 Web search tool** — search the web for docs/answers
- [ ] **6.5 Retry/error recovery** — detect failures and retry with different approach
- [ ] **6.6 Multi-file edits** — coordinate changes across multiple files
- [ ] **6.7 LSP integration** — go-to-definition, find-references, hover/type info via language servers

## Phase 7: Extensibility

Make it hackable and configurable.

- [ ] **7.1 Custom tools** — plugin system to add new tools
- [ ] **7.2 MCP support** — connect to Model Context Protocol servers
- [ ] **7.3 Hooks** — run custom code before/after tool calls
- [ ] **7.4 Project config** — per-project settings (like CLAUDE.md)
- [ ] **7.5 Model switching** — easy config to swap between models/providers

## Phase 8: Team & Collaboration (Stretch)

Advanced orchestration.

- [ ] **8.1 Agent teams** — multiple agents working on a shared project
- [ ] **8.2 Task delegation** — lead agent assigns work to teammates
- [ ] **8.3 Inter-agent messaging** — agents communicate with each other

---

## Feature Comparison: Claude Code vs Our MVP

| Feature              | Claude Code | Our Phase 1 | Notes                           |
|----------------------|-------------|-------------|---------------------------------|
| Agentic loop         | Yes         | Yes         | Core architecture               |
| Tool calling         | Yes         | Yes         | OpenAI-compatible format        |
| File read/write      | Yes         | Yes         | Basic but functional            |
| Bash execution       | Yes         | Yes         | No sandboxing initially         |
| Streaming            | Yes         | Yes         | Via openai SDK                  |
| Context compaction   | Yes         | Phase 3     | Critical for long tasks         |
| Sub-agents           | Yes         | Phase 6     | Separate conversations          |
| Permission system    | Yes         | Phase 5     | Safety feature                  |
| MCP support          | Yes         | Phase 7     | Extensibility                   |
| Agent teams          | Yes         | Phase 8     | Advanced orchestration          |
| Model                | Claude      | Qwen3-Coder-30B-A3B | Open source, local         |
