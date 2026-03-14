# AI Agent Guide

How klaude works from the model's perspective. Useful if you're swapping models, tuning prompts, or building on top of klaude.

## Architecture

klaude uses the standard agentic loop pattern:

```
User message → LLM → tool calls? → execute tools → feed results back → LLM → ...
                                                                         ↓
                                                                    text response → done
```

The loop continues until the LLM returns a text response with no tool calls. Max 50 iterations per turn (safety valve).

## Tool calling format

klaude uses the OpenAI function-calling API format. Tools are passed in the `tools` parameter:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file's contents.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "File path to read"}
      },
      "required": ["path"]
    }
  }
}
```

The LLM responds with tool calls:

```json
{
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "read_file",
        "arguments": "{\"path\": \"src/main.py\"}"
      }
    }
  ]
}
```

Arguments are a JSON string (not a parsed object). klaude parses it and calls the handler.

## Tool result format

Tool results are always strings. Sent back as tool messages:

```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": "     1→import sys\n     2→..."
}
```

Error results start with `"Error"`:
- `"Error: file not found: /path/to/file"`
- `"Error: permission denied by user"`
- `"Error: unknown tool 'foo'"`

## System prompt

The system prompt (`src/klaude/core/prompt.py`) tells the model:

1. **Who it is**: "You are klaude, an AI coding assistant..."
2. **What tools exist**: categorized list with usage guidance
3. **How to work**: understand first, plan multi-file changes, edit surgically, verify
4. **Guidelines**: read before editing, prefer edit_file over write_file, use git tools not bash
5. **Project memory**: contents of `KLAUDE.md` (if present)

## Tool usage patterns

### Effective patterns

**Read before write**: Always read a file before editing it. `edit_file` needs the exact text to match.

```
1. read_file("utils.py")           → see current contents
2. edit_file("utils.py", old, new) → surgical replacement
```

**Search before read**: Use glob/grep to find the right file first.

```
1. glob("**/*.py")                 → find Python files
2. grep("def parse_config")        → find the function
3. read_file("src/config.py")      → read the relevant file
```

**Plan before multi-file edits**: Use task_list for complex changes.

```
1. task_list(action="create", tasks=["update API", "update tests", "update docs"])
2. ... execute each task ...
3. task_list(action="update", task_id=1, status="done")
```

**Verify after changes**: Run tests or the program after editing.

```
1. edit_file(...)                   → make the change
2. bash("pytest tests/test_foo.py") → verify it works
```

### Anti-patterns

- **Guessing file contents** — always read first. edit_file fails if old_string doesn't match.
- **Using bash for file operations** — prefer read_file/write_file/edit_file over cat/sed/echo.
- **Using bash("git status")** — prefer git_status, git_diff, git_log tools (cleaner output).
- **Retrying the same failing approach** — if a tool call fails, try a different strategy.
- **Editing without understanding** — don't change code you haven't read and understood.

## Context management

klaude tracks token usage and compacts history when it gets too large:

- **Context window**: configurable (default 32768 tokens)
- **Warning threshold**: 80% of context window
- **Compaction**: when history exceeds threshold, older messages are summarized by the LLM into a compact form
- **Token counting**: estimated from message character count (rough but fast)

The model sees a status line each iteration:

```
Turn 3 | ~12,450 tokens (~19% of 32,768)
```

## Streaming

klaude uses streaming responses (`stream=True`). Text tokens are printed as they arrive. Tool calls are accumulated from delta chunks and executed after the stream completes.

The model should produce tool calls in the standard streaming format — partial function name and arguments across multiple chunks, assembled by the `ToolCallAccumulator` class.

## Model requirements

For best results, the model should support:

1. **Function calling** — must understand the OpenAI tool-calling format
2. **Multi-tool calls** — ability to call multiple tools in one response
3. **Following complex instructions** — the system prompt is ~2K tokens with detailed guidance
4. **JSON argument generation** — tool arguments must be valid JSON strings

Tested with Qwen3-Coder-30B-A3B. Should work with any model that has good tool-calling support via an OpenAI-compatible API.

## Extending with custom tools

A tool is three things:

```python
from klaude.tools.registry import Tool

tool = Tool(
    name="my_tool",                    # 1. Name (string)
    description="Does X.",             # 2. Description (for the LLM)
    parameters={                       # 3. JSON Schema
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "..."},
        },
        "required": ["query"],
    },
    handler=my_handler_function,       # 4. Handler (returns string)
)
```

The handler receives keyword arguments matching the schema and must return a string. Errors should be returned as strings starting with `"Error"`, not raised as exceptions (the registry catches exceptions, but explicit error strings give the LLM better context).

## Sub-agents vs teams

| Feature | sub_agent | teams |
|---------|-----------|-------|
| Agents | 1, anonymous | Named specialists |
| Tool access | Read-only (7 tools) | Configurable per member |
| Context sharing | None | Message board |
| Use case | Quick research | Complex multi-step tasks |
| Max iterations | 15 | 20 per member |

Use `sub_agent` for one-off questions. Use `team_create` + `team_delegate` when you need multiple specialists with different capabilities working on parts of a larger task.
