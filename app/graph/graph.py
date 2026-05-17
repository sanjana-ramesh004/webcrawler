# app/graph/graph.py
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph.memory import checkpointer
from app.graph.state import AgentState
from app.graph.nodes import (
    fetch_and_extract as _fetch_and_extract,
    generate_answer   as _generate_answer,
    route_query       as _route_query,
    tavily_search     as _tavily_search,
)


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("route_query",       _route_query)
    g.add_node("tavily_search",     _tavily_search)
    g.add_node("fetch_and_extract", _fetch_and_extract)
    g.add_node("generate_answer",   _generate_answer)

    g.add_edge(START,              "route_query")
    g.add_edge("route_query",      "tavily_search")
    g.add_edge("tavily_search",    "fetch_and_extract")
    g.add_edge("fetch_and_extract","generate_answer")
    g.add_edge("generate_answer",  END)

    return g.compile(checkpointer=checkpointer)


rag_graph = build_graph()

if __name__ == "__main__":
    print(rag_graph.get_graph().draw_ascii())