"""
ERIS FastAPI Application Server Base.
Configures FastAPI routes, CORS policy, and root health check endpoints.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.api.routes.chat import router as chat_router

settings = get_settings()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
async def health_check():
    """System health check endpoint."""
    return {
        "status": "online",
        "system": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
    }
    