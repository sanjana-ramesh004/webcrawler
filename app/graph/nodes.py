# app/graph/nodes.py
from __future__ import annotations

import asyncio
import re
from typing import Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from mistralai.client.sdk import Mistral
from tavily import TavilyClient

from app.config import get_settings
from app.graph.memory import make_session_name
from app.graph.state import AgentState
from app.tools.fetcher import fetch_urls

cfg = get_settings()

_mistral = Mistral(api_key=cfg.mistral_api_key)
_tavily  = TavilyClient(api_key=cfg.tavily_api_key)


# ── 1. route_query ─────────────────────────────────────────────────────────────

def route_query(state: AgentState) -> dict:
    try:
        question = state["question"].strip()
        has_image = bool(state.get("image_url"))
        messages  = state.get("messages", [])

        query_type = "multimodal" if has_image and question else \
                     "image"     if has_image else "text"

        # Set session name from first human message
        session_name = state.get("session_name")
        if not session_name:
            human_msgs = [m for m in messages if isinstance(m, HumanMessage)]
            if not human_msgs:
                session_name = make_session_name(question)

        print(f"[route_query] type={query_type} session={session_name}")
        return {
            "query_type":   query_type,
            "session_name": session_name,
            "messages":     [HumanMessage(content=question)],
        }
    except Exception as e:
        print(f"[route_query] error: {e}")
        return {
            "query_type":   "text",
            "session_name": state.get("session_name"),
            "messages":     [],
        }


# ── 2. tavily_search ───────────────────────────────────────────────────────────

def tavily_search(state: AgentState) -> dict:
    """Search the web via Tavily and return top URLs + snippets."""
    try:
        question = state["question"]
        print(f"[tavily_search] searching: {question[:80]}")

        response = _tavily.search(
            query=question,
            max_results=cfg.tavily_max_results,
            search_depth="basic",
            include_answer=False,
            include_raw_content=False,
        )

        raw_results = response.get("results") if isinstance(response, dict) else []
        results = [
            {
                "url":     r.get("url", ""),
                "title":   r.get("title", ""),
                "snippet": r.get("content", ""),  # Tavily already returns content
                "score":   r.get("score", 0.0),
                "content": r.get("content", ""),  # store for direct use
            }
            for r in (raw_results or [])
            if r.get("url")
        ]

        print(f"[tavily_search] got {len(results)} results")
        return {"search_results": results}

    except Exception as e:
        print(f"[tavily_search] failed: {e}")
        return {"search_results": []}


# ── 3. fetch_and_extract ───────────────────────────────────────────────────────

def fetch_and_extract(state: AgentState) -> dict:
    """
    Build page content from Tavily snippets + live URL fetching.
    Always fetches ALL URLs that have no Tavily content.
    Uses a fresh event loop in a thread to avoid asyncio conflicts.
    """
    try:
        results = state.get("search_results", [])
        pages = []
        urls_to_fetch = []

        for r in results:
            content_text = (r.get("content") or r.get("snippet") or "").strip()
            if len(content_text) > 100:
                pages.append({
                    "url":     r["url"],
                    "title":   r.get("title", ""),
                    "content": content_text,
                })
            else:
                # Always try to fetch — even if snippet exists but is short
                urls_to_fetch.append((r["url"], r.get("title", "")))

        # Fetch missing URLs using a fresh thread with its own event loop
        if urls_to_fetch:
            print(f"[fetch_and_extract] live-fetching {len(urls_to_fetch)} URLs…")
            import threading

            fetched_results = []
            errors = []

            def run_fetch():
                import asyncio as _asyncio
                loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(loop)
                try:
                    urls = [u for u, _ in urls_to_fetch]
                    result = loop.run_until_complete(fetch_urls(urls))
                    fetched_results.extend(result)
                except Exception as e:
                    errors.append(str(e))
                finally:
                    loop.close()

            t = threading.Thread(target=run_fetch)
            t.start()
            t.join(timeout=30)  # max 30s for all fetches

            if errors:
                print(f"[fetch_and_extract] fetch errors: {errors}")
            pages.extend(fetched_results)

        print(f"[fetch_and_extract] total pages with content: {len(pages)}")
        return {"fetched_pages": pages}

    except Exception as e:
        print(f"[fetch_and_extract] failed: {e}")
        return {"fetched_pages": []}


# ── 4. generate_answer ─────────────────────────────────────────────────────────

def generate_answer(state: AgentState) -> dict:
    """Build context from fetched pages + chat history, call Mistral."""
    try:
        pages    = state.get("fetched_pages", [])
        results  = state.get("search_results", [])
        question = state["question"]

        # Build snippet map for source scores
        score_map = {r["url"]: r.get("score", 0.0) for r in results}

        # Build context
        ctx_parts: list[str] = []
        if pages:
            for i, page in enumerate(pages, 1):
                ctx_parts.append(
                    f"[{i}] {page['title']} ({page['url']})\n{page['content'][:3000]}\n"
                )
        else:
            # Fallback to Tavily snippets if fetching failed
            for i, r in enumerate(results, 1):
                ctx_parts.append(f"[{i}] {r['title']} ({r['url']})\n{r['snippet']}\n")

        context = "\n---\n".join(ctx_parts) if ctx_parts else "No content retrieved."

        # Chat history
        history = _format_history(state.get("messages", []))

        prompt = f"""You are a precise research assistant that synthesizes information from multiple web sources.

INSTRUCTIONS:
- Synthesize information from ALL provided sources, not just one
- Structure your answer with clear sections using markdown (## headings, bullet points, bold text)
- After each key fact or claim, cite the source like [1], [2], [3] etc.
- Include a brief intro paragraph, then organized sections, then a summary if helpful
- Draw on multiple sources to give a complete, well-rounded answer
- Be comprehensive but concise

--- CONVERSATION HISTORY ---
{history if history else "No previous messages."}
--- END HISTORY ---

--- WEB SOURCES ---
{context}
--- END WEB SOURCES ---

Question: {question}

Write a well-structured, markdown-formatted answer synthesizing ALL the sources above:"""

        print(f"[generate_answer] calling {cfg.mistral_model}…")
        response = _mistral.chat.complete(
            model=cfg.mistral_model,
            temperature=cfg.llm_temperature,
            messages=[{"role": "user", "content": prompt}],
            timeout_ms=60000,
        )

        raw = response.choices[0].message.content
        answer_text = (
            raw if isinstance(raw, str)
            else " ".join(getattr(c, "text", None) or str(c) for c in (raw or []))
        ).strip()

        # Build sources list — include ALL results so user sees every site used
        sources = []
        for i, r in enumerate(results, 1):
            sources.append({
                "index":   i,
                "url":     r["url"],
                "title":   r["title"],
                "snippet": r["snippet"][:200],
                "score":   round(float(score_map.get(r["url"], 0)), 4),
            })

        return {
            "answer":   answer_text,
            "sources":  sources,
            "messages": [AIMessage(content=answer_text)],
        }

    except Exception as e:
        print(f"[generate_answer] failed: {e}")
        return {
            "answer":   "Sorry, I encountered an error generating a response.",
            "sources":  [],
            "messages": [AIMessage(content="Error generating response.")],
        }


def _format_history(messages: list[BaseMessage]) -> str:
    if not messages:
        return ""
    lines = []
    for msg in messages[:-1]:
        if isinstance(msg, HumanMessage):
            lines.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"Assistant: {msg.content}")
    return "\n".join(lines)