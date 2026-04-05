# nam-website Changes for ATIF Trace Format

> Required changes to nam-website to consume klaude's new ATIF v1.4 trace format.
> Companion to `2026-04-05-atif-trace-design.md` (klaude side).

## Context

After the klaude ATIF change, the trace file at `{trace_dir}/trace.json` changes from:

```json
{"id": "...", "messages": [{"role": "user", "content": "..."}, ...]}
```

to ATIF v1.4:

```json
{
  "schema_version": "ATIF-v1.4",
  "session_id": "...",
  "agent": {"name": "klaude", "version": "0.1.0", "model_name": "..."},
  "steps": [
    {"step_id": 1, "timestamp": "...", "source": "user", "message": "..."},
    {"step_id": 2, "timestamp": "...", "source": "agent", "message": null, "tool_calls": [...]},
    {"step_id": 3, "timestamp": "...", "source": "system", "message": "...", "observation": {...}},
    ...
  ],
  "final_metrics": {...}
}
```

The file is rewritten after each step during execution, so polling works for live progress.

## File-by-file changes

### 1. `website/tasks.py` — `_execute_klaude()`

**Current behavior:** Runs klaude, reads the raw session file from `.klaude/sessions/`, copies it to traces dir, manually counts tokens/tool_calls from chat messages.

**New behavior:** Pass `--session-dir` pointing directly at the trace dir. klaude writes the ATIF file there — no copy step needed. Read metrics from ATIF's `final_metrics` instead of counting manually.

```python
def _execute_klaude(mission):
    workspace_dir = os.path.join(WORKSPACE_BASE, mission.workspace)
    trace_dir = os.path.join(TRACES_BASE, mission.workspace)
    os.makedirs(trace_dir, exist_ok=True)

    result = subprocess.run(
        [
            "sudo", "-u", KLAUDE_USER, KLAUDE_BIN,
            mission.prompt,
            "--auto-approve",
            "--session-dir", trace_dir,  # klaude writes ATIF here directly
        ],
        capture_output=True, text=True, timeout=600,
        cwd=workspace_dir,
    )

    # Read ATIF trace (newest file in trace_dir)
    atif = {}
    trace_files = sorted(Path(trace_dir).glob("*.json"), key=lambda f: f.stat().st_mtime)
    if trace_files:
        with open(trace_files[-1]) as f:
            atif = json.load(f)

    # Metrics from ATIF final_metrics
    fm = atif.get("final_metrics", {})
    token_count = fm.get("total_prompt_tokens", 0) + fm.get("total_completion_tokens", 0)
    tool_calls_count = sum(
        len(s.get("tool_calls", []))
        for s in atif.get("steps", [])
        if s.get("source") == "agent"
    )

    # Summary from last agent step with content
    summary = ""
    for step in reversed(atif.get("steps", [])):
        if step.get("source") == "agent" and step.get("message"):
            summary = step["message"][:500]
            break

    return {
        "summary": summary,
        "token_count": token_count,
        "tool_calls": tool_calls_count,
        "error": result.stderr if result.returncode != 0 else "",
        "trace_dir": trace_dir,
    }
```

**Key change:** No more reading from `.klaude/sessions/` and copying. klaude writes directly to `trace_dir` via `--session-dir`.

### 2. `website/views/slops.py` — `slops_trace()`

**Current behavior:** Reads `trace.json`, returns `{"trace": content}` where content is the raw session JSON.

**New behavior:** Same read logic, but the content is now ATIF. The endpoint doesn't need to transform anything — it passes the ATIF document through. The frontend handles it.

```python
def slops_trace(request, mission_id):
    # ... same fetch logic ...

    # Find the trace file (ATIF format now)
    trace_files = sorted(Path(m.trace_path).glob("*.json"), key=lambda f: f.stat().st_mtime)
    if not trace_files:
        return JsonResponse({"trace": None})

    try:
        with open(trace_files[-1]) as f:
            content = json.load(f)
    except (OSError, json.JSONDecodeError):
        return JsonResponse({"error": "Failed to read trace file"}, status=500)

    return JsonResponse({"trace": content})
```

**Key change:** Reads newest `*.json` in trace_path instead of hardcoded `trace.json`, since klaude names files by session ID (e.g. `20260405-143000.json`).

### 3. `frontend/src/lib/api.ts` — Types

Update `MissionTrace` to reflect that `trace` is now an ATIF document:

```typescript
export interface ATIFStep {
  step_id: number;
  timestamp: string;
  source: "user" | "agent" | "system";
  message: string | null;
  model_name?: string;
  tool_calls?: {
    tool_call_id: string;
    function_name: string;
    arguments: Record<string, unknown>;
  }[];
  observation?: {
    results: { tool_call_id: string; content: string }[];
  };
  metrics?: {
    prompt_tokens?: number;
    completion_tokens?: number;
  };
}

export interface ATIFDocument {
  schema_version: string;
  session_id: string;
  agent: { name: string; version: string; model_name: string };
  steps: ATIFStep[];
  final_metrics?: {
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_cached_tokens: number;
    total_cost_usd: number;
    total_steps: number;
  };
}

export interface MissionTrace {
  trace: ATIFDocument | null;
  status: MissionStatus;
}
```

### 4. `frontend/src/app/slops/components/TraceViewer.tsx`

**Current behavior:** Reads `trace.trace.messages[]` — array of `{role, content, tool_calls, tool_call_id}` in OpenAI chat format.

**New behavior:** Reads `trace.trace.steps[]` — array of ATIF steps with `{step_id, source, message, tool_calls, observation}`.

Mapping for the renderer:

| Current (chat messages) | New (ATIF steps) |
|---|---|
| `msg.role === "user"` | `step.source === "user"` |
| `msg.role === "assistant"` | `step.source === "agent"` |
| `msg.role === "tool"` | `step.source === "system"` |
| `msg.content` | `step.message` |
| `msg.tool_calls[].function.name` | `step.tool_calls[].function_name` |
| `msg.tool_calls[].function.arguments` (JSON string) | `step.tool_calls[].arguments` (object) |
| `msg.tool_calls[].id` | `step.tool_calls[].tool_call_id` |
| `msg.tool_call_id` (on tool result) | `step.observation.results[].tool_call_id` |
| `msg.content` (on tool result) | `step.observation.results[].content` |

Specific changes to each sub-component:

**`ToolCallBlock`:**
- `call.function.name` → `call.function_name`
- `call.function.arguments` (JSON string, needs `JSON.parse`) → `call.arguments` (already an object)
- `call.id` → `call.tool_call_id`

**`ToolResult`:**
- Currently receives `content` string from `msg.content` on a `role: "tool"` message
- Now receives content from `step.observation.results[0].content`

**Main `TraceViewer` render loop:**
- `trace.trace.messages` → `trace.trace.steps`
- Switch on `step.source` instead of `step.role`
- `"user"` / `"agent"` / `"system"` instead of `"user"` / `"assistant"` / `"tool"`

**New capability — timestamps:** Each step has a `timestamp` field. Can optionally render timestamps in the trace UI (e.g. relative time between steps to show how long tool calls took).

### 5. `frontend/src/app/slops/page.tsx` — Trace fetching

**Current behavior:** `fetchTrace()` calls `/api/slops/<id>/` (the detail endpoint, not the trace endpoint), then sets `trace` from `data.trace`.

**Problem:** Looking at line 108, it fetches the mission detail endpoint, not the trace endpoint. The detail endpoint returns mission metadata (no trace). The trace field comes from `data.trace` which doesn't exist on the detail response — it would always be undefined.

**Fix:** Fetch from `/api/slops/<id>/trace/` instead:

```typescript
const fetchTrace = useCallback(async (id: number) => {
  setTraceLoading(true);
  try {
    // Fetch mission detail (for status)
    const detailRes = await fetch(`${API}/api/slops/${id}/`);
    if (!detailRes.ok) { setTrace(null); return; }
    const detail = await detailRes.json();

    // Fetch trace (ATIF document)
    const traceRes = await fetch(`${API}/api/slops/${id}/trace/`);
    const traceData = traceRes.ok ? await traceRes.json() : { trace: null };

    setTrace({ trace: traceData.trace, status: detail.status });
  } catch {
    setTrace(null);
  } finally {
    setTraceLoading(false);
  }
}, []);
```

### 6. `website/models/mission.py` — No changes required

The model stores `trace_path` as a string path to the directory. This still works — the directory now contains ATIF files instead of raw session JSON. The `token_count` and `tool_calls` fields are populated from ATIF metrics in `tasks.py`.

The mission→session rename is a separate, optional follow-up (model rename, migration, API endpoint rename, frontend copy changes).

## Change order

1. **Backend first** (`tasks.py`, `slops.py`) — pass `--session-dir`, read ATIF format
2. **Types** (`api.ts`) — add ATIF types
3. **Frontend** (`TraceViewer.tsx`, `page.tsx`) — render ATIF steps, fix trace endpoint URL
4. **Deploy both** klaude and nam-website together (the format change is breaking)

## Scope exclusions

- Mission → session rename (separate follow-up)
- Session resume from nam-website UI (future feature)
- ATIF validation on the consumer side
- Streaming/SSE (polling is sufficient for now)
