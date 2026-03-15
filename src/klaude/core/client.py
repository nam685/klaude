"""LLM client — talks to any OpenAI-compatible API (mlx-lm, vLLM, etc.).

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


# Default to local mlx-lm server
DEFAULT_BASE_URL = "http://localhost:8080/v1"
DEFAULT_MODEL = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"

# mlx-lm server defaults to --max-tokens 512 which truncates responses.
# Override per-request so the model can generate full responses.
DEFAULT_MAX_COMPLETION_TOKENS = 8192

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
        thinking: bool = False,
    ):
        self.model = model
        self.base_url = base_url
        # Disable Qwen3 thinking by default for faster responses.
        # mlx-lm passes chat_template_kwargs through to the Jinja template.
        self.extra_body: dict | None = (
            None if thinking else {"chat_template_kwargs": {"enable_thinking": False}}
        )
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
            "max_tokens": DEFAULT_MAX_COMPLETION_TOKENS,
        }
        if tools:
            kwargs["tools"] = tools
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body

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
            "max_tokens": DEFAULT_MAX_COMPLETION_TOKENS,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body

        return self._retry(lambda: self.client.chat.completions.create(**kwargs))

    def detect_context_window(self) -> int | None:
        """Query the server for the actual context window size.

        Tries /props first (llama-server/llama.cpp native), falls back to None.
        Returns the context size in tokens, or None if detection fails.
        """
        # Strip /v1 suffix to get the base server URL
        server_url = self.base_url.rstrip("/")
        if server_url.endswith("/v1"):
            server_url = server_url[:-3]

        try:
            transport = httpx.HTTPTransport()
            with httpx.Client(transport=transport, timeout=5.0) as client:
                resp = client.get(f"{server_url}/props")
                if resp.status_code == 200:
                    data = resp.json()
                    n_ctx = data.get("default_generation_settings", {}).get("n_ctx")
                    if n_ctx and isinstance(n_ctx, int) and n_ctx > 0:
                        return n_ctx
        except Exception:
            pass
        return None

    def tokenize(self, text: str) -> list[int] | None:
        """Get exact token IDs using the server's /tokenize endpoint.

        Returns list of token IDs, or None if endpoint unavailable.
        """
        server_url = self.base_url.rstrip("/")
        if server_url.endswith("/v1"):
            server_url = server_url[:-3]

        try:
            transport = httpx.HTTPTransport()
            with httpx.Client(transport=transport, timeout=5.0) as client:
                resp = client.post(
                    f"{server_url}/tokenize",
                    json={"content": text},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tokens = data.get("tokens")
                    if isinstance(tokens, list):
                        return tokens
        except Exception:
            pass
        return None

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
