"""Aggregate API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import agent, auth, chat, documents, metrics

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(agent.router)
api_router.include_router(metrics.router)
