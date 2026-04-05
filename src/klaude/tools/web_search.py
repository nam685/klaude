"""web_search tool — keyword search via DuckDuckGo HTML.

Unlike web_fetch (which requires a URL), this performs a keyword search
and returns summarized results. Uses DuckDuckGo's HTML-only endpoint
which requires no API key and returns structured results.

Uses httpx (already a dependency via openai) — no extra packages.
"""

import re
from html import unescape
from urllib.parse import quote_plus

import httpx

from klaude.tools.registry import Tool

TIMEOUT_SECONDS = 15
MAX_RESULTS = 8


def _extract_results(html: str) -> list[dict[str, str]]:
    """Extract search results from DuckDuckGo HTML response.

    DuckDuckGo's HTML lite page has a predictable structure:
    result links in <a class="result-link"> or similar, with snippets in
    adjacent elements. We parse the simplified HTML page.
    """
    results: list[dict[str, str]] = []

    # DuckDuckGo HTML lite format: results are in <a> tags with class containing "result"
    # Each result block has a link and a snippet
    # Pattern: find result links and their snippets
    result_blocks = re.findall(
        r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>'
        r'.*?<(?:td|div|span)[^>]*class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</(?:td|div|span)>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    if result_blocks:
        for url, title_html, snippet_html in result_blocks[:MAX_RESULTS]:
            title = _strip_tags(title_html).strip()
            snippet = _strip_tags(snippet_html).strip()
            if title and url.startswith("http"):
                results.append({"title": title, "url": url, "snippet": snippet})

    # Fallback: simpler pattern for regular DuckDuckGo HTML
    if not results:
        # Look for <a rel="nofollow" ...> links which are search results
        links = re.findall(
            r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        # Look for snippets that follow
        snippets = re.findall(
            r'<(?:td|div|span)[^>]*class="[^"]*snippet[^"]*"[^>]*>(.*?)</(?:td|div|span)>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        for i, (url, title_html) in enumerate(links[:MAX_RESULTS]):
            title = _strip_tags(title_html).strip()
            snippet = (
                _strip_tags(snippets[i][0] if i < len(snippets) else "").strip()
                if snippets
                else ""
            )
            if title and url.startswith("http"):
                results.append({"title": title, "url": url, "snippet": snippet})

    # Final fallback: just grab all http links with surrounding text
    if not results:
        for match in re.finditer(r'href="(https?://[^"]+)"[^>]*>([^<]+)</a>', html):
            url, title = match.group(1), match.group(2).strip()
            if title and len(title) > 5 and "duckduckgo" not in url.lower():
                results.append({"title": title, "url": url, "snippet": ""})
                if len(results) >= MAX_RESULTS:
                    break

    return results


def _strip_tags(html: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", html)
    return unescape(text)


def handle_web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return summarized results."""
    if not query.strip():
        return "Error: search query cannot be empty"

    num_results = min(max(num_results, 1), MAX_RESULTS)
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        with httpx.Client(follow_redirects=True, timeout=TIMEOUT_SECONDS) as client:
            response = client.get(
                url,
                headers={
                    "User-Agent": "klaude/0.1 (AI coding assistant)",
                    "Accept": "text/html",
                },
            )
            response.raise_for_status()
            html = response.text

        results = _extract_results(html)

        if not results:
            return f"No results found for: {query}"

        # Format results
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results[:num_results], 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet']}")
            lines.append("")

        lines.append("Use web_fetch to read any of these URLs in full.")
        return "\n".join(lines)

    except httpx.TimeoutException:
        return f"Error: search timed out after {TIMEOUT_SECONDS}s"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} from search"
    except httpx.RequestError as e:
        return f"Error: search request failed — {e}"
    except Exception as e:
        return f"Error performing search: {e}"


tool = Tool(
    name="web_search",
    description="Search the web by keyword. Returns titles, URLs, snippets.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (1-8, default 5).",
            },
        },
        "required": ["query"],
    },
    handler=handle_web_search,
)
