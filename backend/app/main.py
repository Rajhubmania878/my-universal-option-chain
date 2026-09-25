import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.api.routes import api_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.status import router as status_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown routines."""
    logger.info(f"Starting {settings.PROJECT_NAME} in [{settings.APP_ENV}] mode...")
    logger.info(f"Timezone: {settings.TIMEZONE}, Snapshot interval: {settings.SNAPSHOT_INTERVAL_SECONDS}s")
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Derivatives market-data and analytics engine with Angel One SmartAPI, Redis, PostgreSQL, and Google Sheets integration.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration to allow Google Apps Script and modern Web frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root-level health & status probes (convenient for container liveness/readiness probes)
app.include_router(health_router)
app.include_router(status_router)

# Versioned API routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Track request latency and attach X-Process-Time header."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000.0
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler to ensure clean JSON responses without leaking traces."""
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please refer to system status or logs.",
            "path": request.url.path,
        },
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=(settings.APP_ENV == "development"),
    )
