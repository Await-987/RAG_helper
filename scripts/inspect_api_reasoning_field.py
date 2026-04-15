#!/usr/bin/env python3
"""
Inspect raw OpenAI-compatible API responses and report the exact reasoning field.

This script reads the current project `.env` through backend settings and sends
both non-streaming and streaming chat-completions requests to the configured
API. It recursively scans returned JSON payloads for keys such as:

  - reasoning
  - reasoning_content
  - thought
  - thinking

Usage:
    python scripts/inspect_api_reasoning_field.py
    python scripts/inspect_api_reasoning_field.py --query "Explain transformers simply."
    python scripts/inspect_api_reasoning_field.py --extra-body '{"chat_template_kwargs":{"enable_thinking":true}}'
    python scripts/inspect_api_reasoning_field.py --sync-only
    python scripts/inspect_api_reasoning_field.py --stream-only
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings


CANDIDATE_KEYWORDS = (
    "reasoning",
    "reasoning_content",
    "thought",
    "thinking",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect which reasoning field the configured OpenAI-compatible API returns.",
    )
    parser.add_argument(
        "--query",
        default="List the steps you use to answer, then answer: what is 2 + 2?",
        help="User prompt sent to the model.",
    )
    parser.add_argument(
        "--model",
        default=settings.MODEL_NAME,
        help="Model name. Defaults to MODEL_NAME from .env.",
    )
    parser.add_argument(
        "--base-url",
        default=settings.OPENAI_API_URL,
        help="OpenAI-compatible base URL. Defaults to `url` from .env.",
    )
    parser.add_argument(
        "--api-key",
        default=settings.OPENAI_API_KEY,
        help="API key. Defaults to OPENAI_API_KEY from .env.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=0.9,
        help="Top-p sampling value.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="Maximum output tokens.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Request timeout in seconds.",
    )
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Only run the non-streaming request.",
    )
    parser.add_argument(
        "--stream-only",
        action="store_true",
        help="Only run the streaming request.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="",
        help="Optional reasoning_effort request field.",
    )
    parser.add_argument(
        "--extra-body",
        default="",
        help="Optional JSON object merged into the request body.",
    )
    parser.add_argument(
        "--stream-preview-limit",
        type=int,
        default=20,
        help="How many matching stream chunks to print in detail. Use -1 to print all.",
    )
    return parser.parse_args()


def setup_logger() -> tuple[Path, callable]:
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"inspect_api_reasoning_field_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    handle = log_file.open("w", encoding="utf-8")

    def log(message: str = "") -> None:
        print(message)
        handle.write(message + "\n")
        handle.flush()

    def close() -> None:
        handle.close()

    return log_file, log, close


def mask_secret(value: str | None) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def build_endpoint(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        raise ValueError("Missing base URL. Set `url` in .env or pass --base-url.")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def parse_extra_body(extra_body: str) -> dict[str, Any]:
    if not extra_body.strip():
        return {}
    try:
        parsed = json.loads(extra_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--extra-body is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("--extra-body must decode to a JSON object.")
    return parsed


def summarize_value(value: Any, limit: int = 240) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    text = text.replace("\n", "\\n")
    if len(text) > limit:
        return text[:limit] + "...(truncated)"
    return text


def find_candidate_fields(obj: Any, path: str = "$") -> list[tuple[str, str, str]]:
    matches: list[tuple[str, str, str]] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}"
            lower_key = key.lower()
            if any(keyword in lower_key for keyword in CANDIDATE_KEYWORDS):
                matches.append((child_path, type(value).__name__, summarize_value(value)))
            matches.extend(find_candidate_fields(value, child_path))
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            matches.extend(find_candidate_fields(item, f"{path}[{index}]"))

    return matches


def print_matches(log, matches: Iterable[tuple[str, str, str]], prefix: str = "") -> None:
    matches = list(matches)
    if not matches:
        log(f"{prefix}No candidate reasoning field found.")
        return
    for path, value_type, summary in matches:
        log(f"{prefix}{path} ({value_type}) = {summary}")


def build_payload(args: argparse.Namespace, stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.query}],
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "stream": stream,
    }
    if args.reasoning_effort.strip():
        payload["reasoning_effort"] = args.reasoning_effort.strip()
    payload.update(parse_extra_body(args.extra_body))
    return payload


def post_json(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: int,
    stream: bool,
) -> requests.Response:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=timeout,
        stream=stream,
    )


def inspect_sync(log, response: requests.Response) -> None:
    log("")
    log("=" * 80)
    log("SYNC RESPONSE")
    log("=" * 80)
    log(f"HTTP {response.status_code}")

    if not response.ok:
        log(response.text[:4000])
        response.raise_for_status()

    data = response.json()
    log(f"Top-level keys: {list(data.keys())}")
    if isinstance(data.get("choices"), list) and data["choices"]:
        first_choice = data["choices"][0]
        log(f"choices[0] keys: {list(first_choice.keys())}")
        if isinstance(first_choice.get("message"), dict):
            log(f"choices[0].message keys: {list(first_choice['message'].keys())}")

    matches = find_candidate_fields(data)
    log("Candidate reasoning fields:")
    print_matches(log, matches, prefix="  ")

    log("")
    log("Raw JSON preview:")
    log(json.dumps(data, ensure_ascii=False, indent=2)[:6000])


def inspect_stream(log, response: requests.Response, preview_limit: int) -> None:
    log("")
    log("=" * 80)
    log("STREAM RESPONSE")
    log("=" * 80)
    log(f"HTTP {response.status_code}")

    if not response.ok:
        log(response.text[:4000])
        response.raise_for_status()

    seen_counts: dict[str, int] = defaultdict(int)
    sample_by_path: dict[str, tuple[str, str]] = {}
    chunk_count = 0
    done_seen = False
    detailed_match_chunks = 0
    suppression_logged = False

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            log(f"Non-data stream line: {line[:500]}")
            continue

        data_str = line[5:].strip()
        if data_str == "[DONE]":
            done_seen = True
            log("Stream ended with [DONE].")
            continue

        chunk_count += 1
        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            log(f"[chunk {chunk_count}] Non-JSON payload: {data_str[:500]}")
            continue

        show_chunk_shape = preview_limit < 0 or chunk_count <= max(preview_limit, 5)
        if show_chunk_shape:
            log(f"[chunk {chunk_count}] top-level keys: {list(payload.keys())}")

        if isinstance(payload.get("choices"), list) and payload["choices"]:
            choice = payload["choices"][0]
            if show_chunk_shape:
                log(f"[chunk {chunk_count}] choices[0] keys: {list(choice.keys())}")
            if isinstance(choice.get("delta"), dict) and show_chunk_shape:
                log(f"[chunk {chunk_count}] delta keys: {list(choice['delta'].keys())}")

        matches = find_candidate_fields(payload)
        if matches:
            should_print_detail = (
                preview_limit < 0
                or detailed_match_chunks < preview_limit
            )
            if should_print_detail:
                log(f"[chunk {chunk_count}] candidate reasoning fields:")
                print_matches(log, matches, prefix="  ")
                detailed_match_chunks += 1
            elif not suppression_logged:
                log(
                    f"Further matching chunks suppressed after "
                    f"{preview_limit} previews. Summary will continue."
                )
                suppression_logged = True
            for path, value_type, summary in matches:
                seen_counts[path] += 1
                sample_by_path[path] = (value_type, summary)

    log("")
    log(f"Total stream chunks: {chunk_count}")
    log(f"DONE received: {done_seen}")
    log("Summary of candidate reasoning fields across stream:")
    if not seen_counts:
        log("  No candidate reasoning field found in stream chunks.")
        return

    for path, count in sorted(seen_counts.items(), key=lambda item: (-item[1], item[0])):
        value_type, summary = sample_by_path[path]
        log(f"  {path}: seen {count} chunk(s), last value ({value_type}) = {summary}")


def validate_args(args: argparse.Namespace) -> None:
    if args.sync_only and args.stream_only:
        raise ValueError("--sync-only and --stream-only cannot be used together.")
    if not args.api_key:
        raise ValueError("Missing API key. Set OPENAI_API_KEY in .env or pass --api-key.")
    if not args.model:
        raise ValueError("Missing model name. Set MODEL_NAME in .env or pass --model.")


def main() -> int:
    args = parse_args()
    validate_args(args)
    endpoint = build_endpoint(args.base_url)
    log_file, log, close_log = setup_logger()

    try:
        log("Inspecting configured OpenAI-compatible API")
        log(f"Endpoint: {endpoint}")
        log(f"Model: {args.model}")
        log(f"API key: {mask_secret(args.api_key)}")
        log(f"Query: {args.query}")
        if args.reasoning_effort.strip():
            log(f"reasoning_effort: {args.reasoning_effort.strip()}")
        if args.extra_body.strip():
            log(f"extra_body: {args.extra_body}")

        if not args.stream_only:
            sync_payload = build_payload(args, stream=False)
            response = post_json(
                url=endpoint,
                api_key=args.api_key,
                payload=sync_payload,
                timeout=args.timeout,
                stream=False,
            )
            inspect_sync(log, response)

        if not args.sync_only:
            stream_payload = build_payload(args, stream=True)
            response = post_json(
                url=endpoint,
                api_key=args.api_key,
                payload=stream_payload,
                timeout=args.timeout,
                stream=True,
            )
            inspect_stream(log, response, args.stream_preview_limit)

        log("")
        log(f"Log saved to: {log_file}")
        return 0
    except Exception as exc:
        log("")
        log(f"ERROR: {exc}")
        log(f"Log saved to: {log_file}")
        return 1
    finally:
        close_log()


if __name__ == "__main__":
    raise SystemExit(main())
