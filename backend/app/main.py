"""
FastAPI application entry point.
"""
import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.router import api_router
from app.core.middleware import setup_middleware, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown events.
    """
    # Startup
    setup_logging()

    print("=" * 60)
    print(f"Starting {settings.PROJECT_NAME}...")
    print(f"API prefix: {settings.API_V1_PREFIX}")
    print(f"Debug mode: {settings.DEBUG}")
    print("=" * 60)

    # Note: Database toolkit will be initialized lazily on first use
    # to avoid locking issues if Qdrant is already in use by Streamlit
    print("Application ready!")

    yield

    # Shutdown
    print("Shutting down application...")
    # Cleanup resources if needed
    from app.dependencies import cleanup_table_summary_model
    cleanup_table_summary_model()
    print("Application shutdown complete.")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="""
## RAG Backend API

A FastAPI backend for the RAG (Retrieval-Augmented Generation) application.

### Features

- **Authentication**: JWT-based authentication
- **Chat**: SSE streaming chat with knowledge base retrieval
- **Files**: File upload, import to vector database, and management
- **Users**: User management (admin only)

### Authentication

Most endpoints require a JWT token in the Authorization header:
```
Authorization: Bearer <your_token>
```

Get a token by logging in at `/api/v1/auth/login`.
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan
    )

    # Setup middleware
    setup_middleware(app)

    # Include API router
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint - API information"""
        return {
            "name": settings.PROJECT_NAME,
            "version": "1.0.0",
            "docs": "/docs",
            "api_prefix": settings.API_V1_PREFIX
        }

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy"}

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
