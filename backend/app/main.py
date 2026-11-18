"""FastAPI main application entry point.

Configures application lifecycle, CORS middleware, global error handling,
and mounts API v1 modular routers.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import api_router
from app.schemas.health import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management for startup and shutdown events."""
    # Startup: logging and resource preparation
    print(f"[FairShare] Starting {settings.APP_NAME} in '{settings.ENVIRONMENT}' mode...")
    yield
    # Shutdown: clean up any remaining temp files or open pools
    print("[FairShare] Shutting down backend service.")


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Backend API for FairShare: A contribution analysis platform for team software projects "
        "using code-aware graph neural networks and gaming-resistant metric analysis."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure CORS Middleware
if settings.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)


# Top-level root health endpoint for monitoring convenience
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Root Health Check",
)
async def root_health() -> HealthResponse:
    """Convenience alias for /api/v1/health."""
    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        version="0.1.0",
        database_status="pending_database_team",
    )
