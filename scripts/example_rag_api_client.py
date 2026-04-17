#!/usr/bin/env python3
"""
Example client for RAG API.

This script demonstrates how to call the RAG query API externally,
bypassing the web UI authentication using API Key.

Two endpoints available:
- /rag/query: Full RAG pipeline (retrieval + AI generation)
- /rag/search: Pure retrieval (returns original document chunks)

Usage:
    # Full RAG query (AI-generated answer)
    python scripts/example_rag_api_client.py query --query "变压器绝缘等级要求" --api-key YOUR_KEY

    # Pure retrieval (original document chunks)
    python scripts/example_rag_api_client.py search --query "变压器绝缘" --top-k 5 --api-key YOUR_KEY

Environment variables (alternative to --api-key):
    RAG_API_KEY: API key for authentication
    RAG_API_URL: Base URL for the API (default: http://localhost:8000)
"""
import argparse
import os
import sys
import json
from pathlib import Path

# Add project root to path for imports if running from project directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def query_rag(
    query: str,
    api_key: str,
    base_url: str = "http://localhost:8000",
) -> dict:
    """
    Full RAG query: retrieval + AI generation.

    Returns AI-generated answer with source references.
    """
    import requests

    url = f"{base_url}/api/v1/rag/query"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {"query": query}

    response = requests.post(url, headers=headers, json=payload, timeout=120)

    if response.status_code == 200:
        return response.json()
    elif response.status_code == 401:
        raise Exception("Authentication failed: Invalid API Key")
    elif response.status_code == 503:
        raise Exception("Service unavailable: RAG API not configured")
    else:
        raise Exception(f"API error: {response.status_code} - {response.text}")


def search_rag(
    query: str,
    api_key: str,
    base_url: str = "http://localhost:8000",
    top_k: int = 5,
) -> dict:
    """
    Pure retrieval: returns original document chunks without AI processing.

    Returns raw search results from vector database.
    """
    import requests

    url = f"{base_url}/api/v1/rag/search"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {"query": query, "top_k": top_k}

    response = requests.post(url, headers=headers, json=payload, timeout=60)

    if response.status_code == 200:
        return response.json()
    elif response.status_code == 401:
        raise Exception("Authentication failed: Invalid API Key")
    elif response.status_code == 503:
        raise Exception("Service unavailable: RAG API not configured")
    else:
        raise Exception(f"API error: {response.status_code} - {response.text}")


def print_query_result(result: dict):
    """Pretty print query result."""
    print("\n" + "=" * 60)
    print("【AI 生成的答案】")
    print("=" * 60)
    print(result["answer"])
    print("\n【参考文件】")
    for src in result["sources"]:
        print(f"  - {src['file_name']}")
        print(f"    路径: {src['absolute_path']}")
    if not result["sources"]:
        print("  (无参考文件)")


def print_search_result(result: dict):
    """Pretty print search result."""
    print("\n" + "=" * 60)
    print(f"【检索结果】共 {result['total']} 条")
    print("=" * 60)

    for i, item in enumerate(result["results"], 1):
        print(f"\n--- 结果 {i} ---")
        print(f"文件: {item['file_name']}")
        print(f"路径: {item['absolute_path']}")
        print(f"类型: {item.get('chunk_type', 'text')}")
        print(f"相关度: {item['score']:.4f}")
        print(f"内容:\n{item['content'][:500]}...")
        if len(item['content']) > 500:
            print(f"  ...(共 {len(item['content'])} 字符)")


def main():
    parser = argparse.ArgumentParser(
        description="RAG API Client Example",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Query subcommand (full RAG)
    query_parser = subparsers.add_parser("query", help="Full RAG query (AI-generated answer)")
    query_parser.add_argument("--query", required=True, help="Question to ask")
    query_parser.add_argument("--api-key", default=os.getenv("RAG_API_KEY", ""), help="API key")
    query_parser.add_argument("--url", default=os.getenv("RAG_API_URL", "http://localhost:8000"), help="Base URL")
    query_parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format")

    # Search subcommand (pure retrieval)
    search_parser = subparsers.add_parser("search", help="Pure retrieval (original chunks)")
    search_parser.add_argument("--query", required=True, help="Search query")
    search_parser.add_argument("--top-k", type=int, default=5, help="Number of results (1-20)")
    search_parser.add_argument("--api-key", default=os.getenv("RAG_API_KEY", ""), help="API key")
    search_parser.add_argument("--url", default=os.getenv("RAG_API_URL", "http://localhost:8000"), help="Base URL")
    search_parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if not args.api_key:
        print("Error: API key required. Use --api-key or set RAG_API_KEY environment variable.")
        sys.exit(1)

    print(f"URL: {args.url}/api/v1/rag/{args.command}")
    print(f"Query: {args.query}")

    try:
        if args.command == "query":
            result = query_rag(args.query, args.api_key, args.url)
            if args.output == "json":
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print_query_result(result)

        elif args.command == "search":
            result = search_rag(args.query, args.api_key, args.url, args.top_k)
            if args.output == "json":
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print_search_result(result)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()