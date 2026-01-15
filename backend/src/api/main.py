"""
FastAPI application entrypoint.
"""
import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
import time

from ..core.config import settings

# Note: LangSmith environment variables are now set in config.py
# before any LangChain imports happen, ensuring tracing works correctly

from ..core.database import init_db, close_db, ensure_pgvector_extension
from ..core.cache import init_redis, close_redis
from ..core.telemetry import (
    get_logger,
    set_correlation_id,
    http_requests_total,
    http_request_duration_seconds,
)
from .routes import health, chat

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application."""
    # Startup
    logger.info("Starting DV360 Agent System", environment=settings.environment)

    try:
        # Log LangSmith tracing status (already set at module level)
        if settings.langchain_tracing_v2 and settings.langchain_api_key:
            logger.info(
                "LangSmith tracing enabled",
                project=settings.langchain_project,
                endpoint=getattr(settings, 'langsmith_endpoint', 'default'),
                tracing_v2=os.getenv("LANGCHAIN_TRACING_V2", "not set")
            )
        else:
            logger.info("LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY to enable)")

        # Initialize database
        await init_db()
        await ensure_pgvector_extension()

        # Initialize Redis
        await init_redis()

        logger.info("Application startup complete")
    except Exception as e:
        logger.error("Failed to initialize application", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("Shutting down application")
    await close_db()
    await close_redis()
    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="DV360 Multi-Agent System",
    description="AI-powered DV360 strategy and analysis platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all HTTP requests with correlation ID."""
    # Generate correlation ID
    correlation_id = str(uuid.uuid4())
    set_correlation_id(correlation_id)

    # Add to request state
    request.state.correlation_id = correlation_id

    # Start timer
    start_time = time.time()

    # Process request
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(
            "Request failed",
            method=request.method,
            path=request.url.path,
            correlation_id=correlation_id,
            error=str(e),
        )
        raise

    # Calculate duration
    duration = time.time() - start_time

    # Record metrics
    http_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
    ).inc()

    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)

    # Log request
    logger.info(
        "Request completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_seconds=round(duration, 3),
        correlation_id=correlation_id,
    )

    # Add correlation ID to response headers
    response.headers["X-Correlation-ID"] = correlation_id

    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    logger.error(
        "Unhandled exception",
        method=request.method,
        path=request.url.path,
        error=str(exc),
        correlation_id=correlation_id,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "correlation_id": correlation_id,
        },
    )


# Include routers
app.include_router(health.router)
app.include_router(chat.router)

# Mount Prometheus metrics endpoint
if settings.enable_prometheus:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "DV360 Multi-Agent System",
        "version": "0.1.0",
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
