"""Regression test for GitHub issue #19.

openai's SDK wraps *any* exception raised while sending a request in
APIConnectionError with the generic message "Connection error." — discarding
whatever the real underlying problem was. That made the reported bug
undiagnosable: users only ever saw "Stopped: LLM API error — Connection
error." with no way to tell a real TCP failure from an SSL error, a proxy
misconfiguration, or something else entirely.

klaude's own error formatting must surface the chained cause when present.
"""

import httpx
from openai import APIConnectionError

from klaude.core.loop import _describe_llm_error


def test_describes_chained_cause():
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")

    try:
        try:
            raise ConnectionResetError("boom")
        except Exception as err:
            raise APIConnectionError(request=request) from err
    except APIConnectionError as e:
        message = _describe_llm_error(e)

    assert "Connection error." in message
    assert "ConnectionResetError" in message
    assert "boom" in message


def test_no_cause_falls_back_to_plain_message():
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    e = APIConnectionError(request=request)

    assert _describe_llm_error(e) == "Connection error."
