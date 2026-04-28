"""Main FastAPI application for Nave backend.

Wires core config, security middleware, and API routers.
Serves as central data layer for indicators, COT, signals.
"""

from app.core.security import setup_security_middleware
from app.core.config import settings
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import sys
from pathlib import Path

# Ensure imports work when run from project root (backend/app structure)
root_path = Path(__file__).parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))


from app.api.indicators import router as indicators_router  # noqa: E402
from app.api.cot import router as cot_router  # noqa: E402

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Nave Macro Data & Trading Signals API",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware (before security)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=settings.allow_credentials,
    allow_methods=settings.allow_methods,
    allow_headers=settings.allow_headers,
)

# Security, rate limiting, logging
setup_security_middleware(app)

# Include routers
app.include_router(indicators_router, prefix="/api/v1", tags=["indicators"])
app.include_router(cot_router, prefix="/api/v1", tags=["cot"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": settings.app_version,
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "message": "Welcome to Nave API",
        "docs": "/docs",
        "version": settings.app_version,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
