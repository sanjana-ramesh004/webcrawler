# app/graph/state.py
"""
AgentState — single source of truth passed through every node.

Key change from earlier version:
  image_b64 removed — images are now passed as image_url (string).
  The actual image is fetched in retrieve_node only when needed,
  keeping state lightweight and checkpoint storage small.
"""
from __future__ import annotations

from typing import Annotated, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    question: str
    image_url: Optional[str]          # URL of user-attached image (not base64)

    # ── Routing ───────────────────────────────────────────────────────────────
    query_type: str                   # "text" | "image" | "multimodal"
    needs_crawl: bool
    crawl_url: Optional[str]
    crawl_stats: Optional[dict]

    # ── Retrieval ─────────────────────────────────────────────────────────────
    raw_chunks: list[dict]
    raw_images: list[dict]

    # ── Reranked ──────────────────────────────────────────────────────────────
    chunks: list[dict]
    images: list[dict]

    # ── Output ────────────────────────────────────────────────────────────────
    answer: str
    sources: list[dict]
    image_sources: list[dict]

    # ── Chat history (persisted by PostgresSaver across turns) ─────────────────
    messages: Annotated[list[BaseMessage], add_messages]