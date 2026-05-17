# app/tools/fetcher.py
"""
Fetches a list of URLs in parallel using httpx async,
extracts clean text with BeautifulSoup.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

cfg = get_settings()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _extract_text(html: str, max_chars: int) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text[:max_chars]


def _get_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    return (soup.title.string or "").strip() if soup.title else ""


async def _fetch_one(
    client: httpx.AsyncClient,
    url: str,
    max_chars: int,
) -> dict | None:
    try:
        r = await client.get(url, headers=_HEADERS, timeout=10, follow_redirects=True)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "text/html" not in ct:
            return None
        html  = r.text
        title = _get_title(html)
        text  = _extract_text(html, max_chars)
        return {"url": url, "title": title, "content": text}
    except Exception as exc:
        print(f"[fetcher] failed {url}: {exc}")
        return None


async def fetch_urls(urls: list[str], max_chars: int | None = None) -> list[dict]:
    """Fetch all URLs in parallel. Returns list of {url, title, content}."""
    max_chars = max_chars or cfg.search_max_chars
    async with httpx.AsyncClient(verify=False) as client:
        tasks = [_fetch_one(client, url, max_chars) for url in urls]
        results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def fetch_single(url: str, query: str, max_chars: int | None = None) -> dict:
    """
    Fetch a single URL for the live Search panel.
    Returns {url, title, content, query}.
    """
    max_chars = max_chars or cfg.search_max_chars
    async with httpx.AsyncClient(verify=False) as client:
        result = await _fetch_one(client, url, max_chars)
    if not result:
        raise ValueError(f"Could not fetch content from {url}")
    result["query"] = query
    return result