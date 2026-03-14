# How Agentic Loops Work

This is the core concept behind Claude Code and every agentic coding tool.

## The Basic Pattern

```
User message
    ↓
┌─────────────────────┐
│   Send to LLM       │ ← conversation history + system prompt + tools
│   (chat completion)  │
└─────────┬───────────┘
          ↓
    Does response contain
    tool_calls?
     /          \
   YES           NO
    ↓             ↓
Execute tool    Display text
    ↓           response to user
Append tool     (loop ends)
result to
conversation
    ↓
  (loop back to "Send to LLM")
```

## In Code (Pseudocode)

```python
messages = [system_prompt, user_message]

while True:
    response = llm.chat(messages, tools=tool_definitions)

    # If the LLM just wants to talk, we're done
    if not response.tool_calls:
        print(response.content)
        break

    # Otherwise, execute each tool call
    for tool_call in response.tool_calls:
        result = execute_tool(tool_call.name, tool_call.arguments)
        messages.append(tool_result(tool_call.id, result))

    # Loop back — LLM sees the tool results and decides next action
```

## Key Insights

### 1. The LLM Decides When to Stop
There's no hardcoded "do 5 steps then stop." The model itself decides whether to
call another tool or return a text response. This is what makes it "agentic" —
the model plans and acts autonomously.

### 2. Tools Are Just JSON Schemas
Tools are described to the LLM as JSON schemas in the system prompt / API call.
The LLM outputs structured JSON to "call" them. Your code parses that JSON and
executes the actual function. Example:

```json
{
  "name": "read_file",
  "description": "Read the contents of a file",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Absolute file path"}
    },
    "required": ["path"]
  }
}
```

### 3. The Conversation IS the Memory
The full message history (user messages, assistant responses, tool calls, tool
results) is sent to the LLM on every turn. This is how it "remembers" what it
already did. This is also why context window management matters.

### 4. Claude Code's Loop is Flat
Anthropic explicitly chose a single-threaded, flat message list — no swarms,
no competing agent personas. One agent, one conversation, tools as capabilities.
Sub-agents are separate conversations that report back results.

## How Claude Code Specifically Works

1. **Gather context** — reads files, searches codebase, understands the task
2. **Take action** — edits files, runs commands, creates code
3. **Verify** — runs tests, checks output, confirms changes work

These phases blend together naturally. The model might read a file, edit it,
run tests, see a failure, read the error, edit again — all in one loop.

## What We're Building

Our `loop.py` will implement exactly this pattern:
- Maintain a message list
- Call the LLM with tool definitions
- Parse tool calls from the response
- Execute tools and append results
- Repeat until the LLM responds with plain text

## References

- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- [How the agent loop works (Agent SDK)](https://platform.claude.com/docs/en/agent-sdk/agent-loop)
- [Tracing Claude Code's LLM Traffic](https://medium.com/@georgesung/tracing-claude-codes-llm-traffic-agentic-loop-sub-agents-tool-use-prompts-7796941806f5)
- [Claude Code: Behind the scenes of the master agent loop](https://blog.promptlayer.com/claude-code-behind-the-scenes-of-the-master-agent-loop/)
