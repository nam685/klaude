"""LLM client — talks to any OpenAI-compatible API (mlx-lm, vLLM, etc.).

Includes retry logic with exponential backoff for transient failures
(connection errors, HTTP 5xx, timeouts). See Note 22 in docs.
"""

import time
from collections.abc import Callable

import httpx
from openai import (
    DEFAULT_TIMEOUT,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    Stream,
)
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
        # Fail fast if remote API has no real API key
        _is_local = "localhost" in base_url or "127.0.0.1" in base_url
        if not _is_local and api_key in ("not-needed", ""):
            raise ValueError(
                f"API key required for remote server {base_url}. "
                f"Set api_key or api_key_env in .klaude.toml, "
                f"or export the env var."
            )
        # Disable Qwen3 thinking by default for faster responses.
        # chat_template_kwargs is mlx-lm specific — only send to local servers.
        self.extra_body: dict | None = (
            {"chat_template_kwargs": {"enable_thinking": False}}
            if (not thinking and _is_local)
            else None
        )
        if _is_local:
            # Explicit httpx client that bypasses proxy env vars (ALL_PROXY, etc.).
            # Without this, httpx tries to route localhost through a SOCKS proxy.
            transport = httpx.HTTPTransport()
            http_client = httpx.Client(transport=transport)
            self.client = OpenAI(
                base_url=base_url, api_key=api_key, http_client=http_client
            )
        else:
            # Remote APIs prefer IPv4. Some networks have flaky/partially-broken
            # IPv6 routes to specific providers (observed in production: several
            # of Google's round-robined IPv6 addresses refused connections while
            # IPv4 worked fine) and httpx's sync backend has no Happy-Eyeballs
            # fallback — it just fails on whichever address family it tries
            # first. Binding to the IPv4 "any" source address makes
            # socket.create_connection() skip IPv6 candidates (bind() raises on
            # a family mismatch) without disabling IPv6 system-wide.
            #
            # Passing a custom http_client bypasses the OpenAI SDK's own client
            # construction — including its generous default timeout (600s
            # read/write/pool, 5s connect) — so it's replicated explicitly here;
            # otherwise this would silently fall back to httpx's bare Client
            # default of 5s for everything, the exact bug fixed for remote
            # clients previously by *not* passing a custom http_client at all.
            transport = httpx.HTTPTransport(local_address="0.0.0.0")
            http_client = httpx.Client(transport=transport, timeout=DEFAULT_TIMEOUT)
            self.client = OpenAI(
                base_url=base_url, api_key=api_key, http_client=http_client
            )

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
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    time.sleep(delay)
        raise last_error  # type: ignore[misc]
