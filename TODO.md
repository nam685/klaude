# klaude — TODO / Roadmap

## Phase 1: Working Demo (MVP)
- [x] Set up Python project → `pyproject.toml`
- [x] LLM client → `src/klaude/core/client.py`
- [x] Tool registry + executor → `src/klaude/tools/registry.py`
- [x] Tool: `read_file` → `src/klaude/tools/read_file.py`
- [x] Tool: `write_file` → `src/klaude/tools/write_file.py`
- [x] Tool: `bash` → `src/klaude/tools/bash.py`
- [x] Core agentic loop → `src/klaude/core/loop.py`
- [x] System prompt → `src/klaude/core/prompt.py`
- [x] CLI entry point → `src/klaude/ui/cli.py`
- [x] Streaming text output → `src/klaude/core/stream.py`
- [x] Script to download & serve model → `scripts/setup-model.sh`

## Phase 2: Essential Tools
- [x] Tool: `glob` → `src/klaude/tools/glob_search.py`
- [x] Tool: `grep` → `src/klaude/tools/grep_search.py`
- [x] Tool: `edit_file` → `src/klaude/tools/edit_file.py`
- [x] Tool: `list_directory` → `src/klaude/tools/list_directory.py`
- [x] Improved system prompt → `src/klaude/core/prompt.py`

## Phase 3: Context Management
- [x] Token counting / context tracking → `src/klaude/core/context.py` (Note 8)
- [x] Message history management → `src/klaude/core/history.py` (Note 9)
- [x] Context compaction → `src/klaude/core/compaction.py` (Note 10)
- [x] Long-term memory → `src/klaude/memory.py` (Note 11)

## Phase 4: User Experience
- [x] Multi-turn REPL mode → `src/klaude/ui/repl.py`, `core/loop.py` Session class (Note 12)
- [x] Interrupt handling → `src/klaude/core/stream.py` KeyboardInterrupt (Note 13)
- [x] Spinner/progress indicator → `src/klaude/core/stream.py` Status spinner (Note 14)
- [x] Input editing / history → `src/klaude/ui/repl.py` readline (Note 15)
- [x] Syntax-highlighted code blocks → `src/klaude/ui/render.py` StreamPrinter (Note 16)

## Phase 5: Safety & Control
- [x] Permission system → `src/klaude/permissions.py` PermissionManager (Note 17)
- [x] Command denylist → `src/klaude/permissions.py` DENIED_COMMANDS (Note 18)
- [x] Diff review for edits → `src/klaude/permissions.py` format_diff() (Note 19)
- [x] File system sandboxing → `src/klaude/permissions.py` is_path_allowed() (Note 20)
- [x] Token budgets → `src/klaude/core/loop.py` max_tokens check (Note 21)

## Phase 6: Advanced Agentic
- [x] Error recovery / retry logic → `src/klaude/core/client.py` _retry(), `core/loop.py` try/except (Note 22)
- [x] Git integration → `src/klaude/tools/git.py` git_status, git_diff, git_log, git_commit (Note 23)
- [x] Task planning (structured TODO lists) → `src/klaude/tools/task_list.py` (Note 24)
- [x] Multi-file coordinated edits → `src/klaude/core/prompt.py` system prompt guidance (Note 25)
- [x] Sub-agents (separate conversations) → `src/klaude/tools/sub_agent.py` (Note 26)
- [x] Web fetch tool → `src/klaude/tools/web_fetch.py` (Note 27)

## Phase 7: Extensibility
- [x] Per-project config + model profiles → `src/klaude/config.py` .klaude.toml loader (Note 28)
- [x] Hooks (pre/post tool execution) → `src/klaude/extensions/hooks.py` shell command hooks (Note 29)
- [x] Custom tool plugins → `src/klaude/extensions/plugins.py` dynamic .py loader (Note 30)
- [x] MCP (Model Context Protocol) support → `src/klaude/extensions/mcp.py` using official `mcp` SDK (Note 31)
- [x] Undo / time travel (Esc key) → `src/klaude/core/loop.py` snapshots, `ui/repl.py` /undo (Note 32)
- [x] Config-driven architecture → `src/klaude/ui/cli.py` --profile flag (Note 33)
- [x] Skills (reusable prompt templates invoked via /skill_name) → `src/klaude/extensions/skills.py` (Note 34)
    - Skill files: `.klaude/skills/*.md` — markdown with YAML frontmatter (name, description)
    - Skill body = prompt text injected into conversation when invoked
    - Skill discovery: `/skills` lists available, `/skill_name` runs one
    - Built-in skills: `/commit` (smart git commit), `/review` (code review), `/explain` (explain codebase)
    - User-defined skills: drop a .md file in `.klaude/skills/`
    - Skill parameters: `{input}`, `{cwd}` placeholders filled at invocation

## Phase 8: Team (Stretch)
- [x] Agent teams → `src/klaude/extensions/team.py` AgentRole, `tools/team.py` team_create (Note 35)
- [x] Task delegation → `src/klaude/tools/team.py` team_delegate, `extensions/team.py` run_agent (Note 35)
- [x] Inter-agent messaging → `src/klaude/extensions/team.py` MessageBoard, `tools/team.py` team_message (Note 35)

## Phase 9: Customer Care
- [x] Push to GitHub (private repo) → `.gitignore`, `README.md`, git init (Note 36)
- [x] Installation guide (macOS, Linux, Windows/WSL) → `docs/INSTALL.md` (Note 36)
- [x] Setup guide for mlx-lm + model download → `docs/SETUP-MODEL.md` (Note 36)
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
- [x] Plan mode → `src/klaude/permissions.py` PLAN_MODE_BLOCKED, `ui/repl.py` /plan command (Note 38)
- [x] Git worktrees → `src/klaude/tools/worktree.py` — create/list/remove isolated worktrees (Note 42)
- [x] Cron / scheduled tasks → `src/klaude/extensions/cron.py`, `ui/repl.py` /cron command (Note 43)

## Phase 11: Context Optimization + Model Switch
- [x] Trim tool schema descriptions → `src/klaude/tools/*.py` (Note 44)
- [x] Compact system prompt → `src/klaude/core/prompt.py` (Note 44)
- [x] Dynamic tool loading (3 tiers: core/git/extended) → `src/klaude/tools/registry.py`, `core/loop.py` (Note 44)
- [x] Fix default context_window (32768) → `src/klaude/config.py` (Note 44)
- [x] Adaptive compaction thresholds → `src/klaude/core/compaction.py` (Note 45)
- [x] Auto-detect context window from server → `src/klaude/core/client.py` detect_context_window() (Note 45)
- [x] Exact tokenization via /tokenize → `src/klaude/core/context.py` exact_token_count() (Note 45)
- [x] Model switch to Qwen3-Coder-30B-A3B → `src/klaude/config.py`, `scripts/setup-model.sh` (Note 46)
- [x] Switch from llama.cpp to mlx-lm → `scripts/setup-model.sh` (Note 46)

## Phase 12: Restructure
- [x] Subpackage reorganization → `src/klaude/core/`, `ui/`, `extensions/` (Note 47)
    - `core/` — loop, client, context, compaction, history, stream, prompt, session_store
    - `ui/` — cli, repl, render, status_bar
    - `extensions/` — plugins, mcp, skills, hooks, team, cron

## Phase 13: CLI Polish (Note 48)
- [x] Persistent status bar → `src/klaude/ui/status_bar.py` — ANSI scroll region, single bottom line
- [x] Tool call spinner → `src/klaude/core/stream.py` — spinner stays alive during tool call streaming ("Calling N tools...")
- [x] Trailing newline after responses → `src/klaude/core/loop.py` — prompt no longer runs into model output
- [x] Session persistence → `src/klaude/core/session_store.py` — auto-save on exit, keep last 10 sessions
- [x] Session resume → `src/klaude/ui/cli.py` — `klaude -c` (latest) or `--resume <id>` (specific)
- [x] /sessions command → `src/klaude/ui/repl.py` — list saved sessions with IDs, turns, summaries
