# app/api/routes/session.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from app.api.schemas import ClearResponse, SessionDetail, SessionItem, SessionMessage
from app.graph.graph import rag_graph
from app.graph.memory import clear_session, get_all_sessions, get_session_messages

router = APIRouter(prefix="/session", tags=["session"])


@router.get("", response_model=list[SessionItem])
def list_sessions():
    """Return all stored sessions ordered by most recent."""
    return get_all_sessions()


@router.get("/{thread_id}", response_model=SessionDetail)
def get_session(thread_id: str):
    """Get full message history for a session."""
    try:
        raw = get_session_messages(thread_id, rag_graph)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    messages = []
    for msg in raw:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if isinstance(msg, HumanMessage):
            messages.append(SessionMessage(role="user", content=content))
        elif isinstance(msg, AIMessage):
            messages.append(SessionMessage(role="assistant", content=content))

    # Try to get session name from stored state
    try:
        snapshot = rag_graph.get_state({"configurable": {"thread_id": thread_id}})
        session_name = snapshot.values.get("session_name") or thread_id
    except Exception:
        session_name = thread_id

    return SessionDetail(
        thread_id=thread_id,
        session_name=session_name,
        messages=messages,
    )


@router.delete("/{thread_id}", response_model=ClearResponse)
def delete_session(thread_id: str):
    """Clear a session's chat history."""
    try:
        clear_session(thread_id, rag_graph)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ClearResponse(thread_id=thread_id, message=f"Session '{thread_id}' cleared.")