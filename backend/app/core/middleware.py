"""
Middleware configuration for the FastAPI backend.
"""
import time
import sys
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from loguru import logger

from app.config import settings


def setup_logging():
    """Configure loguru logging"""
    logger.remove()
    logger.add(
        sys.stdout,
        level="DEBUG" if settings.DEBUG else "INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )


def setup_cors(app: FastAPI):
    """Setup CORS middleware"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )


async def request_logging_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware to log all requests and responses.
    """
    start_time = time.time()

    # Log request
    logger.info(f"Request: {request.method} {request.url.path}")

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration = time.time() - start_time

    # Log response
    logger.info(
        f"Response: {request.method} {request.url.path} - "
        f"Status: {response.status_code} - Duration: {duration:.3f}s"
    )

    return response


async def exception_handler_middleware(request: Request, call_next: Callable) -> Response:
    """
    Global exception handler middleware.
    """
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error": str(e) if settings.DEBUG else None
            }
        )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    HTTP exception handler.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


def setup_middleware(app: FastAPI):
    """Setup all middleware for the application"""
    # Setup CORS
    setup_cors(app)

    # Add request logging
    app.middleware("http")(request_logging_middleware)

    # Add exception handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Setup logging
    setup_logging()
