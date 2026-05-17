# app/api/routes/query.py
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, cast, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig

from app.api.schemas import QueryRequest, QueryResponse
from app.graph.graph import rag_graph
from app.graph.memory import get_thread_config
from app.graph.state import AgentState

router = APIRouter(prefix="/query", tags=["query"])


def _initial_state(req: QueryRequest) -> dict:
    """Return plain dict — avoids TypedDict constructor issues."""
    return {
        "question":       req.question,
        "image_url":      req.image_url,
        "query_type":     "text",
        "session_name":   None,
        "search_results": [],
        "fetched_pages":  [],
        "answer":         "",
        "sources":        [],
        "messages":       [],
    }


def _run_graph(state: dict, config: dict) -> dict:
    """Run graph synchronously — called in a thread from async context."""
    result = rag_graph.invoke(cast(Any, state), cast(Any, config))
    return dict(result)


@router.post("", response_model=QueryResponse)
async def query(req: QueryRequest):
    config = get_thread_config(req.thread_id)
    state  = _initial_state(req)
    try:
        final = await asyncio.to_thread(_run_graph, state, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return QueryResponse(
        answer=final.get("answer", ""),
        sources=final.get("sources", []),
        query_type=final.get("query_type", "text"),
        thread_id=req.thread_id,
    )


@router.post("/stream")
async def query_stream(req: QueryRequest):
    """
    SSE stream.
    Runs the graph in a thread, then streams the answer word by word.

    Events:
      data: {"event": "node",    "node": "tavily_search"}
      data: {"event": "answer",  "token": "..."}
      data: {"event": "sources", "sources": [...]}
      data: {"event": "done",    "thread_id": "..."}
      data: {"event": "error",   "detail": "..."}
    """
    config = get_thread_config(req.thread_id)
    state  = _initial_state(req)

    # Queues for cross-thread communication
    node_queue: asyncio.Queue = asyncio.Queue()
    result_holder: list[dict] = []
    error_holder:  list[str]  = []

    def run_graph_with_events():
        """Runs in a thread — pushes node events then final result."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            final_state: dict = {}
            for event in rag_graph.stream(cast(Any, state), cast(Any, config), stream_mode="updates"):
                node_name = list(event.keys())[0]
                node_data = event[node_name]
                # Thread-safe put into queue
                import concurrent.futures
                asyncio.get_event_loop().call_soon_threadsafe(
                    node_queue.put_nowait,
                    {"event": "node", "node": node_name}
                )
                if isinstance(node_data, dict):
                    final_state.update(node_data)

            result_holder.append(final_state)
        except Exception as exc:
            error_holder.append(str(exc))
        finally:
            # Signal done
            asyncio.get_event_loop().call_soon_threadsafe(
                node_queue.put_nowait, {"event": "__done__"}
            )

    async def generator() -> AsyncGenerator[str, None]:
        try:
            # Run graph in executor (its own thread + event loop)
            loop = asyncio.get_event_loop()

            # Use a simpler approach: run graph in thread, collect events via list
            node_events: list[str] = []
            final_state: dict = {}

            def run():
                try:
                    fs: dict = {}
                    for event in rag_graph.stream(cast(Any, state), cast(Any, config), stream_mode="updates"):
                        node_name = list(event.keys())[0]
                        node_data = event[node_name]
                        node_events.append(node_name)
                        if isinstance(node_data, dict):
                            fs.update(node_data)
                    final_state.update(fs)
                except Exception as exc:
                    error_holder.append(str(exc))

            await asyncio.to_thread(run)

            # Check for errors
            if error_holder:
                yield f"data: {json.dumps({'event': 'error', 'detail': error_holder[0]})}\n\n"
                return

            # Emit node events
            for node_name in node_events:
                yield f"data: {json.dumps({'event': 'node', 'node': node_name})}\n\n"
                await asyncio.sleep(0)

            # Stream answer word by word
            answer = final_state.get("answer", "")
            if answer:
                words = answer.split(" ")
                for i, word in enumerate(words):
                    token = word + ("" if i == len(words) - 1 else " ")
                    yield f"data: {json.dumps({'event': 'answer', 'token': token})}\n\n"
                    await asyncio.sleep(0.02)

            # Send sources
            sources = final_state.get("sources", [])
            yield f"data: {json.dumps({'event': 'sources', 'sources': sources})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'thread_id': req.thread_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )