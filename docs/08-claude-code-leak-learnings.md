# Learnings from Claude Code Source Leak (March 2026)

Notes from the Claude Code npm source map leak. The full TypeScript source
(512k lines) was exposed via a `.map` file shipped in `@anthropic-ai/claude-code@2.1.88`
due to a missing `.npmignore` entry combined with a Bun bug that serves source
maps in production.

## Permission System — "Critic" Pattern

Claude Code does NOT use allowlists for bash commands. Each command goes through
a separate model call (Sonnet 4.6 classifier) that evaluates: "Is this command
safe given the user's stated intent, the working directory, and the current
context?"

This is more robust than regex/denylist approaches because it adapts to context.
A `rm -rf` in a temp build directory is fine; the same command in `~` is not.

**Takeaway for klaude:** The manual approval queue is v1's "critic." For v2+,
consider a lightweight classifier check before execution (could be a separate
prompt to the same model with a yes/no schema).

## Bash Validation — 23 Security Checks

The bash validation module spans 2,592 lines with 23 numbered security checks.
Each check maps to a real attack vector discovered in production:

- Path traversal (`../../etc/passwd`)
- Credential file reads (`~/.ssh/*`, `.env`, `.git/config`)
- Network exfiltration (`curl`, `wget` to external hosts)
- Process manipulation (`kill`, signals)
- Symlink attacks
- Environment variable injection

**Takeaway for klaude:** OS-level isolation (separate user) handles most of
these. But klaude should still have a command denylist for the obvious ones
(`ssh`, `scp`, reading outside workspace). Defense in depth.

## System Prompt — Stable/Dynamic Boundary

Claude Code splits the system prompt with a `SYSTEM_PROMPT_DYNAMIC_BOUNDARY`
marker:

- **Before boundary (stable):** Tool definitions, personality, safety rules.
  This part is identical across turns → enables aggressive prompt caching.
- **After boundary (dynamic):** Current file context, git status, user
  instructions. Changes every turn.

Sections marked `DANGEROUS_uncachedSystemPromptSection` signal to engineers
that modifications will break the cache.

**Takeaway for klaude:** Split system prompt into cached (tools, rules) and
uncached (workspace state, task description) sections. With OpenRouter, prompt
caching depends on the provider, but the architecture prepares you for it.

## Memory — 3-Layer Index

1. **Index (always loaded):** Pointers only, ~150 chars per line. This is the
   equivalent of klaude's `KLAUDE.md`.
2. **Topic files (loaded on demand):** Actual knowledge, loaded when the index
   suggests relevance.
3. **Transcripts (grep-only):** Never loaded into context directly. Only
   searched via grep when specific history is needed.

An `autoDream` process consolidates daily learnings in a forked subagent with
limited tool access, preventing corruption of main context.

**Takeaway for klaude:** Already doing layer 1 well. Consider structured topic
files for layer 2 (e.g., per-project knowledge that gets loaded when working
on that project).

## KAIROS — Proactive Agent Infrastructure

Hidden feature flags reveal autonomous background agents:

- Heartbeat prompts: "anything worth doing right now?"
- Push notifications to the user
- GitHub PR subscriptions (auto-review)
- File delivery (agent produces artifacts)
- **Append-only logging** — prevents history erasure

**Takeaway for klaude:** The append-only logging pattern is critical for the
nam-website trace recording feature. Traces should be write-only from klaude's
perspective — the agent can append to its trace log but never delete or modify
past entries. This prevents prompt injection from covering its tracks.

## Anti-Distillation Defense

Requests include `anti_distillation: ['fake_tools']` flags that inject decoy
tool definitions into prompts, poisoning competitor training data scraping.

A `CONNECTOR_TEXT` layer summarizes assistant reasoning with cryptographic
signatures, blocking full reasoning chain extraction.

**Takeaway for klaude:** Not relevant for klaude's use case, but interesting
to know about when calling Claude's API.

## Subagent Execution Model

Three patterns: **fork**, **teammate**, **worktree**.

- Forked subagents inherit parent context as byte-identical copies, so spawning
  five agents costs barely more than one (prompt cache hit).
- Worktree agents get a git worktree for isolated file changes.
- Teammate agents share a message board for coordination.

**Takeaway for klaude:** klaude's team.py already implements the teammate
pattern. The fork optimization (shared prompt cache) is worth pursuing when
using providers that support it.

## Sources

- [Engineer's Codex — Diving into Claude Code's Source Code](https://read.engineerscodex.com/p/diving-into-claude-codes-source-code)
- [Kilo Blog — Claude Code Source Leak Timeline](https://blog.kilo.ai/p/claude-code-source-leak-a-timeline)
- [Layer5 — 512,000 Lines](https://layer5.io/blog/engineering/the-claude-code-source-leak-512000-lines-a-missing-npmignore-and-the-fastest-growing-repo-in-github-history/)
- [SecurityWeek — Critical Vulnerability](https://www.securityweek.com/critical-vulnerability-in-claude-code-emerges-days-after-source-leak/)
