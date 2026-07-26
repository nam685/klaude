"""Tests for LLMClient's httpx transport/timeout configuration.

Regression tests for GitHub issue #19: remote (non-local) base_urls were
silently getting the same no-proxy-bypass transport used for local mlx-lm
servers, which (a) disabled env-based proxy resolution for every request,
and (b) dropped the OpenAI SDK's generous default timeout (600s read / 5s
connect) down to httpx's bare default of 5s for everything.
"""

from klaude.core.client import LLMClient
from openai import DEFAULT_TIMEOUT


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


def test_remote_base_url_forces_ipv4():
    """Remote connections bind to an IPv4 source address so httpcore skips
    IPv6 DNS candidates — some networks have flaky/broken IPv6 routes to
    specific providers (observed in production against Gemini's API) and
    httpx's sync backend has no Happy-Eyeballs fallback to recover from a
    bad first candidate."""
    client = LLMClient(base_url="https://api.example.com/v1", api_key="real-key")

    transport = client.client._client._transport
    assert transport._pool._local_address == "0.0.0.0"


def test_local_base_url_does_not_force_ipv4():
    """Local servers don't need the IPv4 pin — they're not affected by
    remote IPv6 routing issues, and forcing it would be an unnecessary
    behavior change for a code path issue #19/this fix isn't about."""
    client = LLMClient(base_url="http://localhost:8080/v1")

    transport = client.client._client._transport
    assert transport._pool._local_address is None
