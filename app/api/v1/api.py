from fastapi import APIRouter
from app.api.v1.endpoints import health, chat, prepare, auth, livekit, review

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(livekit.router, prefix="/livekit", tags=["livekit"])
api_router.include_router(prepare.router, prefix="/prepare", tags=["prepare"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
