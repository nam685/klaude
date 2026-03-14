# Architecture Decisions

Documenting key design choices and *why* we made them.

## ADR-1: OpenAI-Compatible API Only

**Decision:** Talk to models exclusively via the OpenAI chat completions API.
No custom inference code, no direct model loading.

**Why:**
- llama.cpp, vLLM, and SGLang all expose this API
- Qwen3-Coder-Next supports it natively
- Can swap local/remote models with one config change
- The `openai` Python SDK handles streaming, retries, etc.
- Zero coupling to any specific inference framework

**Trade-off:** Can't use model-specific features not in the OpenAI spec.
Acceptable — tool calling and streaming cover our needs.

## ADR-2: Single-Threaded Flat Loop (Like Claude Code)

**Decision:** One agent, one conversation, one flat message list. No swarms,
no competing personas, no multi-agent architectures in the core loop.

**Why:**
- Anthropic chose this deliberately for Claude Code — debuggability and reliability
- Easier to understand, easier to debug, easier to teach
- Sub-agents (Phase 6) are separate conversations, not threads in the main loop
- Complexity comes from tools and context management, not agent orchestration

## ADR-3: Python with Minimal Dependencies

**Decision:** Python 3.12+, managed with `uv`. Core deps: `openai`, `rich`, `click`.

**Why:**
- Python is the lingua franca of AI/ML tooling
- `uv` is fast and handles everything (venv, deps, scripts)
- `openai` SDK is well-maintained and handles the HTTP details
- `rich` gives us beautiful terminal output cheaply
- `click` is the standard for Python CLIs
- Avoid heavy frameworks (langchain, etc.) — we're learning by building

## ADR-4: Tools as Simple Python Functions

**Decision:** Each tool is a Python function with a JSON schema. No complex
tool framework, no abstract base classes.

**Why:**
- A tool is just: schema (JSON) + handler (function) + name (string)
- Registry is a dict mapping names to (schema, handler) tuples
- Adding a tool = writing one function + one schema dict
- No inheritance, no decorators, no magic

## ADR-5: Start Without Safety, Add It Later

**Decision:** Phase 1 has no permission system or sandboxing. We add safety
in Phase 5.

**Why:**
- Get something working first, understand the loop
- Safety is important but adds complexity that obscures the core concepts
- Running locally on your own machine reduces risk
- We'll document the risks clearly and add guardrails incrementally
