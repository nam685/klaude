"""Stream consumer — reassembles streaming chunks into complete messages.

When streaming, the LLM sends many small chunks (deltas). Each chunk may contain:
- A text fragment (content delta)
- A tool call fragment (partial function name or arguments)
- A finish_reason indicating the response is complete

The challenge: tool calls arrive in pieces across many chunks:

    chunk 1: tool_calls=[{index=0, id="call_1", function={name="read_f"}}]
    chunk 2: tool_calls=[{index=0, function={name="ile"}}]
    chunk 3: tool_calls=[{index=0, function={arguments='{"pa'}}]
    chunk 4: tool_calls=[{index=0, function={arguments='th":'}}]
    chunk 5: tool_calls=[{index=0, function={arguments=' "/foo'}}]
    chunk 6: tool_calls=[{index=0, function={arguments='"}'}}]

We must accumulate these fragments into a complete tool call:
    {id="call_1", name="read_file", arguments='{"path": "/foo"}'}

This module handles that reassembly.
"""

from dataclasses import dataclass, field

import httpx
from openai import APIConnectionError, Stream
from openai.types.chat import ChatCompletionChunk
from rich.console import Console
from rich.status import Status

from klaude.ui.render import StreamPrinter

console = Console()


@dataclass
class ToolCallAccumulator:
    """Accumulates streaming fragments for a single tool call."""

    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class StreamResult:
    """The complete result of consuming a stream.

    After the stream ends, this contains either:
    - text content (a plain text response, model is done)
    - tool_calls (the model wants to call tools, loop should continue)
    - or both (text + tool calls in the same response)
    """

    content: str = ""
    tool_calls: list[ToolCallAccumulator] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        """Whether the response contains any tool calls."""
        return len(self.tool_calls) > 0

    def to_message_dict(self) -> dict:
        """Convert to a message dict for the conversation history.

        This matches the format that the OpenAI API expects when you
        append an assistant message with tool calls.
        """
        msg: dict = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        return msg


def consume_stream(
    stream: Stream[ChatCompletionChunk],
    print_text: bool = True,
) -> StreamResult:
    """Consume a streaming response, printing text as it arrives.

    This is the core streaming logic:
    1. Iterate over chunks from the LLM
    2. Print text deltas immediately (real-time output)
    3. Accumulate tool call fragments silently
    4. Return the complete result when the stream ends

    Args:
        stream: The streaming response from client.chat_stream()
        print_text: Whether to print text deltas to the console

    Returns:
        StreamResult with accumulated content and/or tool calls
    """
    result = StreamResult()
    # Tool calls indexed by position (the LLM can call multiple tools)
    tool_calls_by_index: dict[int, ToolCallAccumulator] = {}

    # Show a spinner until the first token arrives
    spinner: Status | None = Status("Thinking...", console=console, spinner="dots")
    spinner.start()

    # Rich rendering for code blocks in streaming output
    printer = StreamPrinter(console) if print_text else None

    # Text-based tool call suppression: buffer content near '<' to detect
    # model-native tool call markup before printing it.
    _TOOL_MARKERS = ("<function=", "<tool_call>")
    _print_pending = ""
    _suppressing_tool_text = False

    interrupted = False
    disconnected = False
    try:
        for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Stop spinner only for text content.  For tool-call-only
            # responses the spinner stays alive with a progress label,
            # eliminating the visual gap + blank lines before execution.
            if delta.content and spinner and not _suppressing_tool_text:
                spinner.stop()
                spinner = None

            # --- Text content delta ---
            if delta.content:
                result.content += delta.content

                if _suppressing_tool_text:
                    pass  # Already detected tool call markup, skip printing
                elif printer:
                    _print_pending += delta.content

                    # Check for complete tool call marker
                    _marker_found = False
                    for _marker in _TOOL_MARKERS:
                        _idx = _print_pending.find(_marker)
                        if _idx != -1:
                            # Print text before the marker, suppress the rest
                            if _idx > 0:
                                printer.feed(_print_pending[:_idx])
                            _suppressing_tool_text = True
                            _print_pending = ""
                            _marker_found = True
                            # Show spinner for tool call progress
                            if not spinner:
                                spinner = Status(
                                    "Calling tools...",
                                    console=console,
                                    spinner="dots",
                                )
                                spinner.start()
                            break

                    if not _marker_found:
                        # Check if buffer might still form a marker
                        # (ends with a prefix of "<function=" or "<tool_call>")
                        _lt = _print_pending.rfind("<")
                        if _lt >= 0 and any(
                            m.startswith(_print_pending[_lt:])
                            for m in _TOOL_MARKERS
                        ):
                            # Hold text from '<' onward, print everything before
                            if _lt > 0:
                                printer.feed(_print_pending[:_lt])
                            _print_pending = _print_pending[_lt:]
                        else:
                            # No match possible, flush to printer
                            printer.feed(_print_pending)
                            _print_pending = ""

            # --- Tool call deltas ---
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index

                    # First time seeing this index? Create accumulator.
                    if idx not in tool_calls_by_index:
                        tool_calls_by_index[idx] = ToolCallAccumulator()

                    acc = tool_calls_by_index[idx]

                    # Accumulate fragments
                    if tc_delta.id:
                        acc.id = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc.name += tc_delta.function.name
                        if tc_delta.function.arguments:
                            acc.arguments += tc_delta.function.arguments

                # Update spinner to show tool call progress
                if spinner:
                    n = len(tool_calls_by_index)
                    spinner.update(
                        f"Calling {n} tool{'s' if n != 1 else ''}..."
                    )
    except KeyboardInterrupt:
        # Ctrl+C during streaming — stop gracefully, return what we have so far.
        # We discard incomplete tool calls (they'd fail to execute anyway)
        # and keep any text content that was already streamed.
        interrupted = True
        tool_calls_by_index.clear()
    except (APIConnectionError, httpx.RemoteProtocolError, httpx.ReadError) as e:
        # Server dropped connection mid-stream (OOM crash, timeout, etc.)
        # Keep whatever content was already received and report the disconnect.
        disconnected = True
        tool_calls_by_index.clear()
        console.print(f"\n[red]Server disconnected: {e}[/red]")
    finally:
        if spinner is not None:
            spinner.stop()

    # Flush pending print buffer (only if we didn't detect tool call markup)
    if printer and _print_pending and not _suppressing_tool_text:
        printer.feed(_print_pending)

    # Flush any remaining buffered text (e.g., partial lines, unclosed code blocks)
    if printer:
        printer.flush()

    if interrupted:
        if result.content:
            result.content += "\n\n[interrupted]"
        else:
            result.content = "[interrupted]"

    if disconnected:
        if result.content:
            result.content += "\n\n[server disconnected]"
        else:
            result.content = "[server disconnected]"

    # Collect accumulated tool calls in order
    for idx in sorted(tool_calls_by_index):
        result.tool_calls.append(tool_calls_by_index[idx])

    # Fallback: if no API-level tool calls were detected, check text content
    # for model-native tool call markup (e.g., Qwen3-Coder's <function=...>
    # format).  This happens when the LLM server doesn't convert text-based
    # tool calls to the OpenAI tool_calls API format.
    if not result.has_tool_calls and result.content:
        from klaude.core.tool_call_parser import parse_tool_calls_from_text

        cleaned, text_tool_calls = parse_tool_calls_from_text(result.content)
        if text_tool_calls:
            result.content = cleaned
            result.tool_calls = text_tool_calls

    return result
