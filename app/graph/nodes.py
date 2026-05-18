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
            include_raw_content=True,   # get full page content from Tavily
        )

        raw_results = response.get("results") if isinstance(response, dict) else []
        results = [
            {
                "url":     r.get("url", ""),
                "title":   r.get("title", ""),
                # prefer raw_content (full page) over content (snippet)
                "snippet": r.get("raw_content") or r.get("content") or "",
                "score":   r.get("score", 0.0),
                "content": r.get("raw_content") or r.get("content") or "",
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
    Use Tavily content directly — no live fetching needed since
    we now use include_raw_content=True in tavily_search.
    Falls back to snippet if raw_content is empty.
    """
    try:
        results = state.get("search_results", [])
        pages = []

        for r in results:
            text = (r.get("content") or r.get("snippet") or "").strip()
            if text:
                pages.append({
                    "url":     r["url"],
                    "title":   r.get("title", ""),
                    "content": text[:4000],
                })

        print(f"[fetch_and_extract] total pages with content: {len(pages)}")

        # If still nothing, try live fetch as last resort
        if not pages:
            print("[fetch_and_extract] no Tavily content — trying live fetch…")
            import threading
            urls = [r["url"] for r in results[:5]]  # only fetch top 5
            fetched = []

            def run():
                import asyncio as _asyncio
                loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(loop)
                try:
                    fetched.extend(loop.run_until_complete(fetch_urls(urls)))
                except Exception as e:
                    print(f"[fetch_and_extract] live fetch error: {e}")
                finally:
                    loop.close()

            t = threading.Thread(target=run)
            t.start()
            t.join(timeout=20)
            pages.extend(fetched)
            print(f"[fetch_and_extract] live fetched {len(fetched)} pages")

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