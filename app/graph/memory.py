# app/graph/memory.py
"""
In-process session memory using LangGraph's MemorySaver.
Sessions are stored in RAM — they reset when the server restarts.
No database required.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

# Single in-process checkpointer
checkpointer = MemorySaver()


def setup_checkpointer() -> None:
    """No setup needed for MemorySaver."""
    print("✅ Checkpointer ready (MemorySaver — in-process).")


def make_session_name(question: str) -> str:
    clean = question.strip().replace("\n", " ")
    return clean[:60] + ("…" if len(clean) > 60 else "")


def get_thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def get_all_sessions() -> list[dict]:
    """
    MemorySaver doesn't support listing sessions.
    Returns empty list — Sessions panel will show nothing.
    """
    return []


def get_session_messages(thread_id: str, graph) -> list:
    try:
        snapshot = graph.get_state(get_thread_config(thread_id))
        return snapshot.values.get("messages", [])
    except Exception:
        return []


def clear_session(thread_id: str, graph) -> None:
    try:
        graph.update_state(
            get_thread_config(thread_id),
            {"messages": [], "answer": "", "sources": []},
        )
    except Exception as e:
        print(f"[memory] clear_session failed for {thread_id}: {e}")


def close_pool() -> None:
    """No pool to close with MemorySaver."""
    pass