# klaude — TODO / Roadmap

## Phase 1: Working Demo (MVP)
- [x] Set up Python project → `pyproject.toml`
- [x] LLM client → `src/klaude/client.py`
- [x] Tool registry + executor → `src/klaude/tools/registry.py`
- [x] Tool: `read_file` → `src/klaude/tools/read_file.py`
- [x] Tool: `write_file` → `src/klaude/tools/write_file.py`
- [x] Tool: `bash` → `src/klaude/tools/bash.py`
- [x] Core agentic loop → `src/klaude/loop.py`
- [x] System prompt → `src/klaude/prompt.py`
- [x] CLI entry point → `src/klaude/cli.py`
- [x] Streaming text output → `src/klaude/stream.py`
- [x] Script to download & serve Qwen3-Coder-Next → `scripts/setup-model.sh`

## Phase 2: Essential Tools
- [x] Tool: `glob` → `src/klaude/tools/glob_search.py`
- [x] Tool: `grep` → `src/klaude/tools/grep_search.py`
- [x] Tool: `edit_file` → `src/klaude/tools/edit_file.py`
- [x] Tool: `list_directory` → `src/klaude/tools/list_directory.py`
- [x] Improved system prompt → `src/klaude/prompt.py`

## Phase 3: Context Management
- [x] Token counting / context tracking → `src/klaude/context.py` (Note 8)
- [x] Message history management → `src/klaude/history.py` (Note 9)
- [x] Context compaction → `src/klaude/compaction.py` (Note 10)
- [x] Long-term memory → `src/klaude/memory.py` (Note 11)

## Phase 4: User Experience
- [x] Multi-turn REPL mode → `src/klaude/repl.py`, `loop.py` Session class (Note 12)
- [x] Interrupt handling → `src/klaude/stream.py` KeyboardInterrupt (Note 13)
- [x] Spinner/progress indicator → `src/klaude/stream.py` Status spinner (Note 14)
- [x] Input editing / history → `src/klaude/repl.py` readline (Note 15)
- [x] Syntax-highlighted code blocks → `src/klaude/render.py` StreamPrinter (Note 16)

## Phase 5: Safety & Control
- [x] Permission system → `src/klaude/permissions.py` PermissionManager (Note 17)
- [x] Command denylist → `src/klaude/permissions.py` DENIED_COMMANDS (Note 18)
- [x] Diff review for edits → `src/klaude/permissions.py` format_diff() (Note 19)
- [x] File system sandboxing → `src/klaude/permissions.py` is_path_allowed() (Note 20)
- [x] Token budgets → `src/klaude/loop.py` max_tokens check (Note 21)

## Phase 6: Advanced Agentic
- [x] Error recovery / retry logic → `src/klaude/client.py` _retry(), `src/klaude/loop.py` try/except (Note 22)
- [x] Git integration → `src/klaude/tools/git.py` git_status, git_diff, git_log, git_commit (Note 23)
- [x] Task planning (structured TODO lists) → `src/klaude/tools/task_list.py` (Note 24)
- [x] Multi-file coordinated edits → `src/klaude/prompt.py` system prompt guidance (Note 25)
- [x] Sub-agents (separate conversations) → `src/klaude/tools/sub_agent.py` (Note 26)
- [x] Web fetch tool → `src/klaude/tools/web_fetch.py` (Note 27)

## Phase 7: Extensibility
- [x] Per-project config + model profiles → `src/klaude/config.py` .klaude.toml loader (Note 28)
- [x] Hooks (pre/post tool execution) → `src/klaude/hooks.py` shell command hooks (Note 29)
- [x] Custom tool plugins → `src/klaude/plugins.py` dynamic .py loader (Note 30)
- [x] MCP (Model Context Protocol) support → `src/klaude/mcp.py` using official `mcp` SDK (Note 31)
- [x] Undo / time travel (Esc key) → `src/klaude/loop.py` snapshots, `src/klaude/repl.py` /undo (Note 32)
- [x] Config-driven architecture → `src/klaude/cli.py` --profile flag (Note 33)
- [x] Skills (reusable prompt templates invoked via /skill_name) → `src/klaude/skills.py` (Note 34)
    - Skill files: `.klaude/skills/*.md` — markdown with YAML frontmatter (name, description)
    - Skill body = prompt text injected into conversation when invoked
    - Skill discovery: `/skills` lists available, `/skill_name` runs one
    - Built-in skills: `/commit` (smart git commit), `/review` (code review), `/explain` (explain codebase)
    - User-defined skills: drop a .md file in `.klaude/skills/`
    - Skill parameters: `{input}`, `{cwd}` placeholders filled at invocation

## Phase 8: Team (Stretch)
- [x] Agent teams → `src/klaude/team.py` AgentRole, `src/klaude/tools/team.py` team_create (Note 35)
- [x] Task delegation → `src/klaude/tools/team.py` team_delegate, `src/klaude/team.py` run_agent (Note 35)
- [x] Inter-agent messaging → `src/klaude/team.py` MessageBoard, `src/klaude/tools/team.py` team_message (Note 35)

## Phase 9: Customer Care
- [x] Push to GitHub (private repo) → `.gitignore`, `README.md`, git init (Note 36)
- [x] Installation guide (macOS, Linux, Windows/WSL) → `docs/INSTALL.md` (Note 36)
- [x] Setup guide for llama-server + model download → `docs/SETUP-MODEL.md` (Note 36)
- [x] Usage guide for humans (getting started, REPL, config, tools) → `docs/USAGE.md` (Note 36)
- [x] Usage guide for AI agents (system prompt patterns, tool calling tips) → `docs/AGENT-GUIDE.md` (Note 36)
- [x] Example .klaude.toml configs (local, remote API, MCP servers) → `docs/examples/` (Note 36)
- [x] Troubleshooting / FAQ → `docs/TROUBLESHOOTING.md` (Note 36)

## Phase 10: Feature Parity with Claude Code
- [x] Tool: `web_search` → `src/klaude/tools/web_search.py` — keyword search via DuckDuckGo HTML
- [x] Tool: `ask_user` → `src/klaude/tools/ask_user.py` — structured question with answer as tool result
- [x] Tool: `lsp` → `src/klaude/tools/lsp.py` — jedi (Python) + grep fallback (Note 39)
- [x] Tool: `notebook_edit` → `src/klaude/tools/notebook_edit.py` — .ipynb JSON read/edit/insert/execute (Note 40)
- [x] Background tasks → `src/klaude/tools/background_task.py` — threaded sub-agents with start/status/result (Note 41)
- [x] Plan mode → `src/klaude/permissions.py` PLAN_MODE_BLOCKED, `src/klaude/repl.py` /plan command (Note 38)
- [x] Git worktrees → `src/klaude/tools/worktree.py` — create/list/remove isolated worktrees (Note 42)
- [x] Cron / scheduled tasks → `src/klaude/cron.py`, `src/klaude/repl.py` /cron command (Note 43)
