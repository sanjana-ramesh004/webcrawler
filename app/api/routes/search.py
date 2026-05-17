# app/api/routes/search.py
"""
Live search against a specific URL.
Strategy:
  1. Try fetching the URL directly with httpx + BS4
  2. If content is too short (JS-rendered site), fall back to
     Tavily search scoped to that domain
  3. Caption image with Pixtral if provided
  4. Answer with Mistral
"""
from __future__ import annotations

import base64
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from mistralai.client.sdk import Mistral
from tavily import TavilyClient

from app.api.schemas import SearchRequest, SearchResponse
from app.config import get_settings
from app.tools.fetcher import fetch_single

cfg      = get_settings()
router   = APIRouter(prefix="/search", tags=["search"])
_mistral = Mistral(api_key=cfg.mistral_api_key)
_tavily  = TavilyClient(api_key=cfg.tavily_api_key)

MIN_CONTENT_LENGTH = 500   # chars — below this we assume JS-rendered


async def _get_page_content(url: str, query: str) -> tuple[str, str, str]:
    """
    Returns (title, content, method_used).
    Tries direct fetch first, falls back to Tavily site search.
    """
    # Try direct fetch first
    try:
        page = await fetch_single(url, query)
        content = page.get("content", "").strip()
        if len(content) >= MIN_CONTENT_LENGTH:
            return page.get("title", url), content, "direct"
    except Exception as e:
        print(f"[search] direct fetch failed: {e}")

    # Fallback — Tavily search scoped to the domain
    print(f"[search] content too short, using Tavily site search…")
    domain = urlparse(url).netloc.replace("www.", "")
    try:
        response = _tavily.search(
            query=f"site:{domain} {query}",
            max_results=8,
            search_depth="basic",
            include_raw_content=False,
        )
        results = response.get("results", []) if isinstance(response, dict) else []
        if results:
            # Aggregate content from all results on this domain
            domain_results = [r for r in results if domain in r.get("url", "")]
            if not domain_results:
                domain_results = results  # use all if none match domain

            combined = "\n\n---\n\n".join([
                f"Product page: {r.get('url', '')}\n{r.get('title', '')}\n{r.get('content', '')}"
                for r in domain_results[:6]
                if r.get("content")
            ])
            if combined:
                title = f"{domain} — search results for: {query}"
                return title, combined, "tavily"
    except Exception as e:
        print(f"[search] Tavily fallback failed: {e}")

    raise HTTPException(
        status_code=422,
        detail=f"Could not retrieve content from {url}. The site may block automated access. Try a more specific product page URL."
    )


@router.post("", response_model=SearchResponse)
async def search(req: SearchRequest):
    # ── Get page content ───────────────────────────────────────────────────────
    title, content, method = await _get_page_content(req.url, req.query)
    print(f"[search] got {len(content)} chars via {method}")

    # ── Caption image if provided ──────────────────────────────────────────────
    image_context = ""
    if req.image_b64:
        try:
            b64 = req.image_b64
            if b64.startswith("/9j"):       mime = "image/jpeg"
            elif b64.startswith("iVBOR"):   mime = "image/png"
            elif b64.startswith("UklG"):    mime = "image/webp"
            else:                           mime = "image/jpeg"

            print(f"[search] captioning image ({mime})…")
            cap_resp = _mistral.chat.complete(
                model="pixtral-12b-2409",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this clothing/fashion item in detail: "
                                "color, style, material, pattern, fit, and any distinctive features. "
                                "Be specific — someone will search a shopping site for something similar."
                            ),
                        },
                    ],
                }],
            )
            raw = cap_resp.choices[0].message.content
            caption = raw if isinstance(raw, str) else str(raw)
            print(f"[search] image caption: {caption[:120]}")
            image_context = (
                f"\n\nThe user is looking for items SIMILAR TO this image description:\n"
                f"{caption}\n"
                f"Prioritize results that match the color, style, and features above."
            )
        except Exception as e:
            print(f"[search] image caption failed: {e}")

    # ── Prompt ─────────────────────────────────────────────────────────────────
    prompt = f"""You are a shopping assistant helping find products on a website.
Use the product information below to answer the query.
Format your response with markdown:
- **Product name** as a bold heading for each item
- Price if shown
- Key features (color, material, style)
- Direct product URL as a clickable link if available
- Why it matches the query{image_context}

List ALL relevant items found. If no matching items exist in the content, say so clearly.

--- CONTENT FROM {req.url} ---
{content[:7000]}
--- END CONTENT ---

Query: {req.query}

Answer:"""

    try:
        response = _mistral.chat.complete(
            model=cfg.mistral_model,
            temperature=cfg.llm_temperature,
            messages=[{"role": "user", "content": prompt}],
            timeout_ms=60000,
        )
        raw = response.choices[0].message.content
        answer = (
            raw if isinstance(raw, str)
            else " ".join(getattr(c, "text", None) or str(c) for c in (raw or []))
        ).strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mistral error: {e}")

    # Append method note if Tavily was used
    if method == "tavily":
        answer += "\n\n---\n*Note: Product data retrieved via web search (site does not support direct page reading).*"

    return SearchResponse(answer=answer, url=req.url, title=title)