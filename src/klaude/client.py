"""LLM client — talks to any OpenAI-compatible API (llama-server, vLLM, etc.).

Includes retry logic with exponential backoff for transient failures
(connection errors, HTTP 5xx, timeouts). See Note 22 in docs.
"""

import time
from collections.abc import Callable

import httpx
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, Stream
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)


# Default to local llama-server
DEFAULT_BASE_URL = "http://localhost:8080/v1"
DEFAULT_MODEL = "qwen3-coder-next"

# Retry config
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds — doubles each retry (1s, 2s, 4s)
RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, InternalServerError)


class LLMClient:
    """Thin wrapper around the OpenAI SDK for chat completions with tool calling."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str = "not-needed",
    ):
        self.model = model
        # Explicit httpx client that bypasses proxy env vars (ALL_PROXY, etc.).
        # Without this, httpx tries to route localhost through a SOCKS proxy.
        transport = httpx.HTTPTransport()
        http_client = httpx.Client(transport=transport)
        self.client = OpenAI(base_url=base_url, api_key=api_key, http_client=http_client)

    def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[ChatCompletionToolParam] | None = None,
    ) -> ChatCompletion:
        """Send a chat completion request. Returns the full response.

        Retries on transient failures with exponential backoff.
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        return self._retry(lambda: self.client.chat.completions.create(**kwargs))

    def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[ChatCompletionToolParam] | None = None,
    ) -> Stream[ChatCompletionChunk]:
        """Send a streaming chat completion request. Yields delta chunks.

        Retries the initial connection on transient failures.
        Once streaming starts, failures are not retried (partial data exists).
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        return self._retry(lambda: self.client.chat.completions.create(**kwargs))

    def _retry[T](self, fn: Callable[[], T]) -> T:
        """Execute fn with exponential backoff on transient errors."""
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return fn()
            except RETRYABLE_EXCEPTIONS as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    time.sleep(delay)
        raise last_error  # type: ignore[misc]
