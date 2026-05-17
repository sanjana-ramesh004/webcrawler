# app/api/main.py
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import query, search, session
from app.config import get_settings
from app.graph.memory import close_pool, setup_checkpointer

cfg = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting up…")
    cfg.validate_required()
    setup_checkpointer()
    print("✅ All systems ready.")
    yield
    print("🛑 Shutting down…")
    close_pool()


app = FastAPI(
    title="AiR — Web RAG API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router,   prefix="/api")
app.include_router(search.router,  prefix="/api")
app.include_router(session.router, prefix="/api")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "model": cfg.mistral_model}