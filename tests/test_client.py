"""Tests for LLMClient's httpx transport/timeout configuration.

Regression tests for GitHub issue #19: remote (non-local) base_urls were
silently getting the same no-proxy-bypass transport used for local mlx-lm
servers, which (a) disabled env-based proxy resolution for every request,
and (b) dropped the OpenAI SDK's generous default timeout (600s read / 5s
connect) down to httpx's bare default of 5s for everything.
"""

from openai import DEFAULT_TIMEOUT

from klaude.core.client import LLMClient


def test_remote_base_url_keeps_openai_default_timeout():
    """A remote base_url must not be silently downgraded to httpx's 5s default."""
    client = LLMClient(base_url="https://api.example.com/v1", api_key="real-key")

    assert client.client._client.timeout == DEFAULT_TIMEOUT


def test_local_base_url_still_bypasses_proxy_transport():
    """Local servers (mlx-lm etc.) keep the explicit no-proxy transport."""
    client = LLMClient(base_url="http://localhost:8080/v1")

    import httpx

    assert isinstance(client.client._client._transport, httpx.HTTPTransport)
    # Legacy behavior preserved: local client uses httpx's bare 5s default.
    assert client.client._client.timeout == httpx.Timeout(timeout=5.0)
