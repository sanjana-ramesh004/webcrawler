# app/api/schemas.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str  = Field(..., min_length=1, max_length=2000)
    image_url: Optional[str] = None
    thread_id: str = Field(..., description="Unique session identifier")


class SourceItem(BaseModel):
    index:   int
    url:     str
    title:   str
    snippet: str
    score:   float


class QueryResponse(BaseModel):
    answer:     str
    sources:    list[SourceItem]
    query_type: str
    thread_id:  str


class SearchRequest(BaseModel):
    url:       str  = Field(..., description="URL to search within")
    query:     str  = Field(..., min_length=1)
    image_b64: Optional[str] = None   # base64-encoded image from user


class SearchResponse(BaseModel):
    answer:  str
    url:     str
    title:   str


class SessionItem(BaseModel):
    thread_id:    str
    session_name: str
    created_at:   Optional[str]


class SessionMessage(BaseModel):
    role:    str
    content: str


class SessionDetail(BaseModel):
    thread_id:    str
    session_name: str
    messages:     list[SessionMessage]


class ClearResponse(BaseModel):
    thread_id: str
    message:   str