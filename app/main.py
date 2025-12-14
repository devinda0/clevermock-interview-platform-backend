from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.api import api_router

from contextlib import asynccontextmanager
from app.db.mongodb import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database connection on startup."""
    await init_db()
    yield
    # Note: LiveKit agent should be run separately using:
    # python -m livekit.agents dev app.livekit.agent:entrypoint

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    print(f"Allowed CORS Origins: {settings.BACKEND_CORS_ORIGINS}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {"message": "Welcome to Interview Assistant Backend"}
