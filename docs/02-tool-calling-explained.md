# Tool Calling (Function Calling) Explained

## What is Tool Calling?

Tool calling is how LLMs interact with the real world. Instead of just generating
text, the model can output structured function calls that your code executes.

## The Flow

```
You define tools (JSON schemas)
    ↓
Send tools + messages to LLM API
    ↓
LLM responds with tool_calls (structured JSON)
    ↓
Your code parses and executes them
    ↓
You send results back to the LLM
    ↓
LLM uses results to continue reasoning
```

## OpenAI-Compatible Tool Format

This is the standard format used by OpenAI, and supported by mlx-lm, llama.cpp,
vLLM, SGLang, and Qwen3-Coder-30B-A3B:

### Defining a Tool

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file"
                    }
                },
                "required": ["path"]
            }
        }
    }
]
```

### LLM Response with Tool Calls

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "read_file",
          "arguments": "{\"path\": \"/Users/nam/project/main.py\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

### Sending Tool Results Back

```python
messages.append({
    "role": "tool",
    "tool_call_id": "call_abc123",
    "content": "# contents of main.py\ndef main():\n    print('hello')\n"
})
```

## Why OpenAI-Compatible?

We use the OpenAI SDK format because:
1. **mlx-lm** serves models with an OpenAI-compatible API (`/v1/chat/completions`)
2. **llama.cpp, vLLM, and SGLang** do the same
3. **Qwen3-Coder-30B-A3B** was trained on this tool calling format
4. We can swap between local and remote models without code changes
5. The `openai` Python SDK handles all the HTTP/streaming details

## Qwen3-Coder-30B-A3B Tool Calling Notes

- Uses the standard Qwen3 special tokens for tool parsing
- Supports parallel tool calls (multiple tools in one response)
- Trained on agentic coding tools specifically — it knows patterns like
  "read file → edit → run tests"

## What We Build

Our tool system needs:
1. **Registry** — map tool names to Python functions + JSON schemas
2. **Executor** — parse tool calls, run functions, format results
3. **Individual tools** — read_file, write_file, bash, glob, grep
