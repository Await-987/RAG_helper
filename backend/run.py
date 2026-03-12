#!/usr/bin/env python3
"""
Backend server runner script.

Usage:
    python run.py [--host HOST] [--port PORT] [--reload]

Examples:
    python run.py                    # Run on 0.0.0.0:8000
    python run.py --port 8080        # Run on 0.0.0.0:8080
    python run.py --reload           # Run with auto-reload for development
"""
import sys
import os
import argparse
from pathlib import Path

# Add the current directory to path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

# Load environment variables from parent directory .env
parent_env = backend_dir.parent / ".env"
if parent_env.exists():
    from dotenv import load_dotenv
    load_dotenv(parent_env)
    print(f"Loaded environment from: {parent_env}")


def main():
    parser = argparse.ArgumentParser(description="Run the RAG Backend API server")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)"
    )

    args = parser.parse_args()

    import uvicorn

    print(f"\n{'='*60}")
    print(f"  RAG Backend API Server")
    print(f"  Host: {args.host}")
    print(f"  Port: {args.port}")
    print(f"  Reload: {args.reload}")
    print(f"  Workers: {args.workers}")
    print(f"  Docs: http://{args.host}:{args.port}/docs")
    print(f"{'='*60}\n")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1  # reload doesn't work with multiple workers
    )


if __name__ == "__main__":
    main()
