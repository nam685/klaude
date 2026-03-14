# Usage Guide

## Modes

### One-shot mode

Pass a task as arguments — klaude processes it and exits:

```bash
uv run klaude "fix the bug in utils.py"
uv run klaude read main.py and explain it
uv run klaude "add tests for the parse module"
```

Quotes are optional. Multiple words are joined into one message.

### Interactive REPL

Run with no arguments for a multi-turn conversation:

```bash
uv run klaude
```

The conversation persists across turns — klaude remembers what you discussed. Context compaction kicks in automatically when history gets large.

## REPL commands

| Command | Description |
|---------|-------------|
| `/exit`, `/quit` | Exit the REPL |
| `/clear` | Clear conversation history |
| `/context` | Show token usage and context stats |
| `/history` | Debug view of message history |
| `/undo` | Undo the last turn (Esc key also works) |
| `/skills` | List available skills |
| `/<name>` | Run a skill (see Skills section) |

- **Ctrl+C** at the prompt clears the line. During generation, interrupts the current response.
- **Ctrl+D** exits the REPL.
- **Up/Down arrows** recall previous inputs (persisted in `~/.klaude_history`).

## Tools

klaude has 17 built-in tools, organized by category:

### Reading & searching
| Tool | Description |
|------|-------------|
| `list_directory` | See what files exist in a directory |
| `glob` | Find files by pattern (`**/*.py`, `src/**/*.ts`) |
| `grep` | Search file contents with regex |
| `read_file` | Read a file's contents |

### Writing & editing
| Tool | Description |
|------|-------------|
| `edit_file` | Surgical string replacement in a file (preferred) |
| `write_file` | Create new files or complete rewrites |

### Running commands
| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands |

### Git
| Tool | Description |
|------|-------------|
| `git_status` | Current branch and working tree status |
| `git_diff` | Show diffs (unstaged, staged, or against a ref) |
| `git_log` | Recent commit history |
| `git_commit` | Stage files and commit (requires permission) |

### Planning & research
| Tool | Description |
|------|-------------|
| `task_list` | Create and manage structured TODO lists |
| `sub_agent` | Spawn a separate conversation for research |
| `web_fetch` | Fetch a URL and extract readable text |

### Agent teams
| Tool | Description |
|------|-------------|
| `team_create` | Define a team with named agents and roles |
| `team_delegate` | Assign a task to a team member |
| `team_message` | Read/post on the team's shared message board |

## Permissions

Tools are classified into safety tiers:

- **Safe** (no prompt): `read_file`, `glob`, `grep`, `list_directory`, `git_status`, `git_diff`, `git_log`, `task_list`, `sub_agent`, `web_fetch`
- **Dangerous** (requires approval): `bash`, `write_file`, `edit_file`, `git_commit`

When a dangerous tool is called, you'll see a prompt:

```
  Permission required: bash
  Command: pytest tests/
  Allow? [y/n]
```

To skip all prompts: `uv run klaude --auto-approve "task"` or set `auto_approve = true` in `.klaude.toml`.

### Hard blocks

Some operations are always blocked, even with `--auto-approve`:

- **Command denylist**: `sudo`, `rm -rf /`, `chmod 777`, `curl | bash`, `dd of=/dev/`, etc.
- **Path sandboxing**: file tools can only access files within the working directory. Blocked paths include `~/.ssh`, `~/.aws`, `~/.gnupg`, `/etc/shadow`.

## Configuration

klaude loads `.klaude.toml` from the project root (or any parent directory).

**Resolution order** (highest wins):
1. CLI flags (`--model`, `--base-url`, etc.)
2. Environment variables (`KLAUDE_MODEL`, `KLAUDE_BASE_URL`, etc.)
3. `.klaude.toml`
4. Built-in defaults

### Minimal config

```toml
[default]
model = "qwen3-coder-30b-a3b"
base_url = "http://localhost:8080/v1"
```

### All options

```toml
[default]
model = "qwen3-coder-30b-a3b"
base_url = "http://localhost:8080/v1"
api_key = "not-needed"              # or api_key_env = "OPENAI_API_KEY"
context_window = 32768
max_tokens = 0                      # 0 = unlimited
auto_approve = false
undo_depth = 10

[profiles.remote]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
context_window = 128000

[hooks]
pre_tool = ""                       # shell command before each tool call
post_tool = ""                      # shell command after each tool call

[plugins]
tools_dir = ".klaude/tools"         # custom tool plugins
skills_dir = ".klaude/skills"       # custom skills

[mcp]
[mcp.servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_TOKEN = "env:GITHUB_TOKEN" }
```

### CLI flags

```
--base-url URL          LLM API base URL
--model NAME            Model name
--context-window N      Context window size in tokens
--auto-approve          Skip permission prompts
--max-tokens N          Max tokens per session (0 = unlimited)
--profile NAME          Config profile from .klaude.toml
```

All flags have corresponding env vars: `KLAUDE_BASE_URL`, `KLAUDE_MODEL`, etc.

### Profiles

Switch between local and remote models:

```bash
uv run klaude --profile remote "explain this code"
```

## Skills

Skills are reusable prompt templates invoked via `/skill_name` in the REPL.

### Built-in skills

| Skill | Description |
|-------|-------------|
| `/commit` | Analyze changes and make a smart git commit |
| `/review` | Review code changes for bugs and style |
| `/explain` | Explain the codebase structure |

Usage with arguments:

```
klaude> /commit fix authentication timeout
klaude> /review focus on security issues
klaude> /explain just the database layer
```

### Custom skills

Create `.klaude/skills/your_skill.md`:

```markdown
---
name: test
description: Run tests and fix failures
---
Run the test suite with `bash("pytest -v")`.
If any tests fail, read the failing test and the tested code,
then fix the issue.

{input}
```

Parameters:
- `{input}` — text after the skill name (e.g., `/test only auth tests` → `"only auth tests"`)
- `{cwd}` — current working directory

## Project memory

Create `KLAUDE.md` in your project root to give klaude persistent context:

```markdown
# Project conventions

- Use ruff for linting
- Tests go in tests/ directory
- All functions need type annotations
- Use pydantic for data models
```

This is loaded into the system prompt at startup. Max 8KB. The LLM reads it but doesn't modify it — you maintain it manually.

## Custom tool plugins

Create Python files in `.klaude/tools/`:

```python
# .klaude/tools/my_tool.py
from klaude.tools.registry import Tool

def handle_my_tool(query: str) -> str:
    return f"Result for: {query}"

tool = Tool(
    name="my_tool",
    description="Does something custom.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The query"},
        },
        "required": ["query"],
    },
    handler=handle_my_tool,
)
```

Export a `tool` variable of type `Tool`. It's automatically loaded at startup.

## MCP servers

Connect to external tool servers via [Model Context Protocol](https://modelcontextprotocol.io):

```toml
# .klaude.toml
[mcp.servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_TOKEN = "env:GITHUB_TOKEN" }

[mcp.servers.filesystem]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
```

MCP tools appear as `mcp_<server>_<tool>` in the tool list. They're called through stdio communication with the server process.

`env:VAR_NAME` references are resolved from environment variables at startup.

## Hooks

Run shell commands before/after tool execution:

```toml
[hooks]
pre_tool = "echo 'Running: {tool_name}'"
post_tool = "echo 'Done: {tool_name}'"
```

Placeholders: `{tool_name}`, `{arguments}`. Hooks have a 5-second timeout and never block the main loop.

## Agent teams

For complex multi-step tasks, create a team of specialists:

```
klaude> Create a team to refactor the auth module:
        - researcher (readonly): map all auth dependencies
        - coder (readwrite): perform the refactor
        - reviewer (readonly): verify correctness
```

Each team member:
- Gets an isolated conversation with tools matching their access level
- Can see previous members' results via the shared message board
- Auto-posts their findings when done

Tool access levels:
- **readonly**: search, read files, git status/diff/log (7 tools)
- **readwrite**: + write_file, edit_file (9 tools)
- **full**: + bash, git_commit, web_fetch (12 tools)

## Undo

Type `/undo` or press **Esc** to revert the last turn. This restores the conversation history to its state before that turn. Up to 10 snapshots are kept (configurable via `undo_depth`).
