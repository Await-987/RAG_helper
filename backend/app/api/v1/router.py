"""
API v1 router aggregation.
"""
from fastapi import APIRouter

from app.api.v1 import auth, chat, files, users, rag, knowledge_graph

api_router = APIRouter()

# Include all sub-routers
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(files.router)
api_router.include_router(users.router)
api_router.include_router(rag.router)
api_router.include_router(knowledge_graph.router)
