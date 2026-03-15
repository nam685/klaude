# klaude

DIY Claude Code harness powered by open-source LLMs. An agentic coding CLI that runs locally on your hardware.

Built as an educational project to understand how tools like Claude Code work under the hood — then turned into something actually useful.

## What it does

klaude is a terminal-based AI coding assistant. You give it a task, and it reads your code, makes changes, runs commands, and verifies its work — all through an agentic loop that keeps going until the task is done.

```
$ klaude "add error handling to the parse function in utils.py"
```

Or use the interactive REPL for a back-and-forth conversation:

```
$ klaude
klaude> read main.py and explain it
... (reads files, explains) ...
klaude> now add input validation to the CLI arguments
... (edits files, runs tests) ...
klaude> /commit
... (analyzes changes, writes commit message, commits) ...
```

## Quick start

```bash
# 1. Install
uv tool install git+https://github.com/nam685/klaude.git

# 2. Download model and start server
./scripts/setup-model.sh            # downloads Qwen3-Coder-30B-A3B-Instruct-8bit
./scripts/setup-model.sh --serve    # starts mlx_lm.server on :8080

# 3. Run klaude (in another terminal)
klaude "your task here"
```

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), [mlx-lm](https://github.com/ml-explore/mlx-lm) (Apple Silicon). See [docs/INSTALL.md](docs/INSTALL.md) for detailed setup.

## Features

**23 built-in tools** — read/write/edit files, run bash commands, glob/grep search, git operations, task planning, sub-agents, web search & fetch, ask user, LSP code intelligence, notebook editing, background tasks, git worktrees, agent teams

**Interactive REPL** — multi-turn conversations with history, slash commands (`/commit`, `/review`, `/explain`), plan mode (`/plan`), cron scheduling (`/cron`), Esc to undo, Ctrl+C to interrupt

**Context management** — token counting, automatic history compaction, project memory via `KLAUDE.md`

**Safety** — permission prompts for writes/bash, command denylist, file path sandboxing, diff review for edits

**Extensible** — custom tool plugins (Python), MCP server integration, user-defined skills (markdown), pre/post hooks, config profiles

**Agent teams** — named specialists with configurable tool access (readonly/readwrite/full) and a shared message board for coordination

**Works with any OpenAI-compatible API** — mlx-lm, vLLM, Ollama, OpenAI, or any other provider

## Target model

**Qwen3-Coder-30B-A3B** — 30B MoE (3B active), 128K context, MIT. Purpose-built for agentic coding with tool calling. Runs on a Mac with 48GB RAM via mlx-lm (8-bit, ~30GB).

Model: `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit`

See [docs/SETUP-MODEL.md](docs/SETUP-MODEL.md) for model download and server configuration.

## Configuration

Create `.klaude.toml` in your project root:

```toml
[default]
model = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"
base_url = "http://localhost:8080/v1"
context_window = 32768

[profiles.remote]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
```

Switch profiles: `klaude --profile remote "your task"`

See [docs/examples/](docs/examples/) for more configs (MCP servers, hooks, plugins).

## Project structure

```
src/klaude/
  config.py        .klaude.toml loader + profiles
  permissions.py   Safety: prompts, denylist, sandboxing, plan mode
  memory.py        KLAUDE.md project memory
  core/
    loop.py        Core agentic loop + Session class
    client.py      LLM client (OpenAI SDK, retry logic)
    prompt.py      System prompt
    context.py     Token counting / context tracking
    history.py     Message history management
    compaction.py  Automatic context compaction
    stream.py      Streaming output + tool call accumulation
  ui/
    cli.py         CLI entry point (click)
    repl.py        Interactive REPL with readline
    render.py      Syntax-highlighted code blocks
  extensions/
    plugins.py     Custom tool plugin loader
    mcp.py         MCP server integration
    skills.py      Reusable prompt templates (/commit, /review)
    hooks.py       Pre/post tool execution hooks
    team.py        Agent teams (roles, message board)
    cron.py        Scheduled recurring tasks (/cron)
  tools/
    registry.py    Tool registry + dispatcher
    read_file.py   bash.py   glob_search.py   grep_search.py
    write_file.py  edit_file.py  list_directory.py
    git.py         task_list.py  sub_agent.py  web_fetch.py
    web_search.py  ask_user.py   lsp.py        notebook_edit.py
    background_task.py  worktree.py
    team.py        Team tools (create, delegate, message)
```

## Documentation

| Doc | Description |
|-----|-------------|
| [INSTALL.md](docs/INSTALL.md) | Installation (macOS, Linux, WSL) |
| [SETUP-MODEL.md](docs/SETUP-MODEL.md) | Model download + mlx-lm server setup |
| [USAGE.md](docs/USAGE.md) | Human usage guide (REPL, config, tools) |
| [AGENT-GUIDE.md](docs/AGENT-GUIDE.md) | AI agent guide (prompts, tool calling) |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | FAQ + common issues |

### Study materials (how it works)

| Doc | Description |
|-----|-------------|
| [00-project-overview.md](docs/00-project-overview.md) | Architecture overview |
| [01-how-agentic-loops-work.md](docs/01-how-agentic-loops-work.md) | Agentic loop concepts |
| [02-tool-calling-explained.md](docs/02-tool-calling-explained.md) | Tool calling deep dive |
| [03-claude-code-features.md](docs/03-claude-code-features.md) | Feature analysis + roadmap |
| [04-qwen3-coder-30b.md](docs/04-qwen3-coder-30b.md) | Model guide |
| [05-architecture-decisions.md](docs/05-architecture-decisions.md) | ADRs |
| [06-hardware-guide.md](docs/06-hardware-guide.md) | Hardware recommendations |
| [07-implementation-notes.md](docs/07-implementation-notes.md) | Implementation notes |

## License

Educational project. Not yet licensed — license TBD.

klaude was here!
