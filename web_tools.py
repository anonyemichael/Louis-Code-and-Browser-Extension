"""
web_tools.py — multi-provider web access for Louis CLI.

Providers (tried in order):
  1. Tavily API    – structured search results (set TAVILY_API_KEY, free 1k/month)
  2. DuckDuckGo    – scrapes DDG HTML endpoint (no key, fragile but free)
  3. Google CSE    – Google Custom Search (set GOOGLE_API_KEY + GOOGLE_CSE_ID)

Functions:
  web_search(query)        -> search across providers with automatic fallback
  web_search_deep(query)   -> search + fetch & extract top 3 results
  fetch_url(url)           -> download page, return cleaned readable text
  extract_page_text(url)   -> enhanced text extraction with readability heuristics
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DDG_HTML_URL = "https://duckduckgo.com/html/"
TAVILY_API_URL = "https://api.tavily.com/search"
GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")

# DuckDuckGo result parsing patterns
_RESULT_ANCHOR_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_RESULT_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>',
    re.IGNORECASE | re.DOTALL,
)

# Content density scoring patterns for readability
_BLOCK_TAGS = re.compile(
    r"<(script|style|nav|footer|header|aside|iframe|noscript|svg|form)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_ARTICLE_RE = re.compile(
    r"<(article|main|div[^>]+(?:content|article|post|entry|text|body)[^>]*)>(.*?)</(?:article|main|div)>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(fragment: str) -> str:
    """Remove HTML tags but keep a space where they were, then unescape entities."""
    text = _TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _unwrap_ddg_redirect(href: str) -> str:
    """DuckDuckGo's HTML results wrap real URLs as /l/?uddg=<urlencoded-url>&..."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    if parsed.path == "/l/" or parsed.netloc.endswith("duckduckgo.com"):
        qs = urllib.parse.parse_qs(parsed.query)
        target = qs.get("uddg")
        if target:
            return urllib.parse.unquote(target[0])
    return href


def _error(message: str, hint: bool = True) -> str:
    payload: dict[str, Any] = {"status": "error", "message": message}
    if hint:
        payload["hint"] = (
            "DuckDuckGo scraping can break or get rate-limited without warning. "
            "For a more reliable backend, get a free key at tavily.com "
            "(1,000 searches/month, no card) and set TAVILY_API_KEY."
        )
    return json.dumps(payload)


def _get_env(name: str) -> str | None:
    """Get env var, checking both os.environ and Windows registry."""
    value = os.environ.get(name)
    if value:
        return value
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                v, _ = winreg.QueryValueEx(key, name)
                if v:
                    return str(v)
        except Exception:
            pass
    return None


# ── Provider: Tavily ──────────────────────────────────────────────────────────

def _search_tavily(query: str, max_results: int = 5) -> list[dict] | None:
    """Search via Tavily API. Returns list of results or None if unavailable."""
    api_key = _get_env("TAVILY_API_KEY")
    if not api_key:
        return None

    payload = json.dumps({
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "search_depth": "basic",
    }).encode("utf-8")

    request = urllib.request.Request(
        TAVILY_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    results = []
    for item in data.get("results", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", "")[:300],
        })
    return results if results else None


# ── Provider: Google Custom Search ────────────────────────────────────────────

def _search_google_cse(query: str, max_results: int = 5) -> list[dict] | None:
    """Search via Google Custom Search. Returns list of results or None."""
    api_key = _get_env("GOOGLE_API_KEY")
    cse_id = _get_env("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        return None

    params = urllib.parse.urlencode({
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "num": min(max_results, 10),
    })

    request = urllib.request.Request(
        f"{GOOGLE_CSE_URL}?{params}",
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    results = []
    for item in data.get("items", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })
    return results if results else None


# ── Provider: DuckDuckGo (HTML scrape) ────────────────────────────────────────

def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict] | None:
    """Search via DuckDuckGo HTML scraping. Returns list or None."""
    params = urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(
        f"{DDG_HTML_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.5"},
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw_html = response.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    anchors = list(_RESULT_ANCHOR_RE.finditer(raw_html))
    snippets = list(_RESULT_SNIPPET_RE.finditer(raw_html))

    if not anchors:
        return None

    results = []
    for i, match in enumerate(anchors[:max_results]):
        href, raw_title = match.group(1), match.group(2)
        title = _strip_tags(raw_title)
        url = _unwrap_ddg_redirect(href)
        snippet = _strip_tags(snippets[i].group(1)) if i < len(snippets) else ""
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})

    return results if results else None


# ── Public API ────────────────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> str:
    """Search the web with automatic provider fallback.

    Order: Google CSE → Tavily → DuckDuckGo
    """
    query = (query or "").strip()
    if not query:
        return _error("No search query provided.", hint=False)

    max_results = max(1, min(int(max_results or 5), 10))
    provider_used = "unknown"

    # Try Google CSE first (Dedicated API Key)
    results = _search_google_cse(query, max_results)
    if results:
        provider_used = "google"
    else:
        # Try Tavily
        results = _search_tavily(query, max_results)
        if results:
            provider_used = "tavily"
        else:
            # Try DuckDuckGo as final fallback
            results = _search_duckduckgo(query, max_results)
            if results:
                provider_used = "duckduckgo"

    if not results:
        return _error(
            "All search providers failed. DuckDuckGo may be rate-limiting, "
            "and no Tavily/Google API keys are configured."
        )

    return json.dumps({
        "status": "success",
        "query": query,
        "provider": provider_used,
        "results": results,
    })


def fetch_url(url: str, max_chars: int = 6000) -> str:
    """Download a URL and return cleaned, readable text content (best-effort)."""
    url = (url or "").strip()
    if not url:
        return _error("No URL provided.", hint=False)

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return _error(f"Unsupported or missing URL scheme: '{parsed.scheme or '(none)'}'. Use http(s).", hint=False)

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            raw_bytes = response.read(2_000_000)  # cap at ~2MB read
    except urllib.error.HTTPError as exc:
        return _error(f"Server returned HTTP {exc.code} for {url}.", hint=False)
    except urllib.error.URLError as exc:
        return _error(f"Network error fetching {url}: {exc.reason}", hint=False)
    except Exception as exc:  # noqa: BLE001
        return _error(f"Unexpected error fetching {url}: {exc}", hint=False)

    if "text" not in content_type and "html" not in content_type and content_type:
        return _error(
            f"Content-Type '{content_type}' is not text/HTML — fetch_url only reads readable pages.",
            hint=False,
        )

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1", errors="replace")

    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    title = _strip_tags(title_match.group(1)) if title_match else ""

    # Drop the whole <head> (title/meta/etc. are not body content) plus
    # script/style/nav/footer blocks before flattening tags, so menus, JS,
    # and the page <title> don't get duplicated into the extracted body text.
    cleaned = re.sub(r"<head[^>]*>.*?</head>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    body = _strip_tags(cleaned)
    body = _BLANKLINES_RE.sub("\n\n", body)

    truncated = False
    if len(body) > max_chars:
        body = body[:max_chars]
        truncated = True

    return json.dumps({
        "status": "success",
        "url": url,
        "title": title,
        "content": body,
        "truncated": truncated,
    })


def extract_page_text(url: str, max_chars: int = 12000) -> str:
    """Enhanced text extraction with readability heuristics.

    Tries to find <article> or <main> content first, then falls back
    to full body extraction. Returns more content than fetch_url.
    """
    url = (url or "").strip()
    if not url:
        return _error("No URL provided.", hint=False)

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return _error(f"Unsupported URL scheme: '{parsed.scheme}'.", hint=False)

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            content_type = response.headers.get("Content-Type", "")
            raw_bytes = response.read(4_000_000)
    except urllib.error.HTTPError as exc:
        return _error(f"HTTP {exc.code} for {url}.", hint=False)
    except urllib.error.URLError as exc:
        return _error(f"Network error: {exc.reason}", hint=False)
    except Exception as exc:
        return _error(f"Error fetching {url}: {exc}", hint=False)

    if "text" not in content_type and "html" not in content_type and content_type:
        return _error(f"Not an HTML page: '{content_type}'.", hint=False)

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = raw_bytes.decode("latin-1", errors="replace")

    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_text, re.IGNORECASE | re.DOTALL)
    title = _strip_tags(title_match.group(1)) if title_match else ""

    # Try to find article/main content first (readability heuristic)
    article_match = _ARTICLE_RE.search(raw_text)
    if article_match:
        content_html = article_match.group(2)
        # Strip block-level noise from the article
        content_html = _BLOCK_TAGS.sub(" ", content_html)
        body = _strip_tags(content_html)
    else:
        # Fallback: full page extraction (same as fetch_url but larger)
        cleaned = re.sub(r"<head[^>]*>.*?</head>", " ", raw_text, flags=re.IGNORECASE | re.DOTALL)
        cleaned = _BLOCK_TAGS.sub(" ", cleaned)
        body = _strip_tags(cleaned)

    body = _BLANKLINES_RE.sub("\n\n", body).strip()

    # Extract links for context
    link_pattern = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    links = []
    for m in link_pattern.finditer(raw_text):
        link_text = _strip_tags(m.group(2)).strip()
        if link_text and len(link_text) > 3:
            links.append({"text": link_text[:80], "url": m.group(1)})
    links = links[:20]  # Cap at 20 links

    truncated = False
    if len(body) > max_chars:
        body = body[:max_chars]
        truncated = True

    return json.dumps({
        "status": "success",
        "url": url,
        "title": title,
        "content": body,
        "links": links,
        "truncated": truncated,
    })


def web_search_deep(query: str, max_results: int = 3) -> str:
    """Search + fetch top results for comprehensive content extraction.

    Performs a web search, then fetches and extracts text from the top results.
    Useful when Louis needs in-depth information, not just snippets.
    """
    query = (query or "").strip()
    if not query:
        return _error("No search query provided.", hint=False)

    # First, do a regular search
    search_raw = web_search(query, max_results=max_results)
    try:
        search_data = json.loads(search_raw)
    except Exception:
        return search_raw  # Return the error as-is

    if search_data.get("status") != "success":
        return search_raw

    results = search_data.get("results", [])
    enriched = []

    for result in results[:max_results]:
        url = result.get("url", "")
        entry: dict[str, Any] = {
            "title": result.get("title", ""),
            "url": url,
            "snippet": result.get("snippet", ""),
            "full_content": None,
        }

        if url:
            try:
                page_raw = extract_page_text(url, max_chars=4000)
                page_data = json.loads(page_raw)
                if page_data.get("status") == "success":
                    entry["full_content"] = page_data.get("content", "")[:4000]
            except Exception:
                pass  # Keep snippet only

        enriched.append(entry)

    return json.dumps({
        "status": "success",
        "query": query,
        "provider": search_data.get("provider", "unknown"),
        "results": enriched,
    })
