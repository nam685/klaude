"""web_fetch tool — fetch a URL and extract readable text.

Uses httpx (already a dependency via openai) for HTTP requests and a simple
HTML-to-text approach: strip tags, decode entities, collapse whitespace.
No external dependencies like beautifulsoup — keeps things minimal.

See Note 27 in docs/07-implementation-notes.md for design rationale.
"""

import re
from html import unescape

import httpx

from klaude.tools.registry import Tool

TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 512 * 1024  # 512KB — don't download huge pages
MAX_OUTPUT_CHARS = 20_000  # Truncate output to avoid flooding context


def _html_to_text(html: str) -> str:
    """Naive but effective HTML-to-text conversion.

    Removes script/style blocks, strips tags, decodes entities, collapses whitespace.
    Good enough for documentation pages, READMEs, and API docs.
    """
    # Remove script and style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block-level elements with newlines
    text = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*/?>", "\n", text, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = unescape(text)
    # Collapse whitespace (but preserve newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def handle_web_fetch(url: str) -> str:
    """Fetch a URL and return its text content."""
    if not url.startswith(("http://", "https://")):
        return f"Error: URL must start with http:// or https:// (got: {url})"

    try:
        with httpx.Client(follow_redirects=True, timeout=TIMEOUT_SECONDS) as client:
            response = client.get(url, headers={"User-Agent": "klaude/0.1 (AI coding assistant)"})
            response.raise_for_status()

            # Check size before reading full body
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                return f"Error: response too large ({int(content_length):,} bytes, max {MAX_RESPONSE_BYTES:,})"

            content_type = response.headers.get("content-type", "")
            body = response.text

            # Convert HTML to text
            if "html" in content_type:
                body = _html_to_text(body)

            # Truncate if too long
            if len(body) > MAX_OUTPUT_CHARS:
                body = body[:MAX_OUTPUT_CHARS] + f"\n\n[truncated — {len(response.text):,} chars total]"

            return body or "(empty response)"

    except httpx.TimeoutException:
        return f"Error: request timed out after {TIMEOUT_SECONDS}s"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} for {url}"
    except httpx.RequestError as e:
        return f"Error: request failed — {e}"
    except Exception as e:
        return f"Error fetching URL: {e}"


tool = Tool(
    name="web_fetch",
    description="Fetch a URL and return readable text content.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
            }
        },
        "required": ["url"],
    },
    handler=handle_web_fetch,
)
