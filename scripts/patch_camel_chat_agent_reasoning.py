#!/usr/bin/env python3
"""
Patch CAMEL's chat_agent.py so OpenAI-compatible reasoning traces exposed as
`reasoning` work the same way as legacy `reasoning_content`.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


OLD_PARSE_BLOCK = """        output_messages: List[BaseMessage] = []\n        for choice in response.choices:\n            # Skip messages with no meaningful content\n            if (\n                choice.message.content is None\n                or choice.message.content.strip() == \"\"\n            ) and not choice.message.tool_calls:\n                continue\n\n            meta_dict = {}\n            if logprobs_info := handle_logprobs(choice):\n                meta_dict[\"logprobs_info\"] = logprobs_info\n\n            reasoning_content = getattr(\n                choice.message, \"reasoning_content\", None\n            )\n\n            chat_message = BaseMessage(\n                role_name=self.role_name,\n                role_type=self.role_type,\n                meta_dict=meta_dict,\n                content=choice.message.content or \"\",\n                parsed=getattr(choice.message, \"parsed\", None),\n                reasoning_content=reasoning_content,\n            )\n\n            output_messages.append(chat_message)\n"""

NEW_PARSE_BLOCK = """        output_messages: List[BaseMessage] = []\n        for choice in response.choices:\n            message_content = choice.message.content or \"\"\n            reasoning_content = self._extract_reasoning_content(\n                choice.message\n            )\n\n            # Keep reasoning-only responses from OpenAI-compatible providers.\n            if (\n                message_content.strip() == \"\"\n                and not choice.message.tool_calls\n                and not reasoning_content\n            ):\n                continue\n\n            meta_dict = {}\n            if logprobs_info := handle_logprobs(choice):\n                meta_dict[\"logprobs_info\"] = logprobs_info\n\n            chat_message = BaseMessage(\n                role_name=self.role_name,\n                role_type=self.role_type,\n                meta_dict=meta_dict,\n                content=message_content,\n                parsed=getattr(choice.message, \"parsed\", None),\n                reasoning_content=reasoning_content,\n            )\n\n            output_messages.append(chat_message)\n"""

INSERT_BEFORE_STEP_TERMINATE = """    @staticmethod\n    def _extract_reasoning_content(message: Any) -> Optional[str]:\n        r\"\"\"Extract reasoning content from provider-specific response fields.\n\n        OpenAI-compatible providers may expose the reasoning trace as either\n        ``reasoning`` or ``reasoning_content``. Keep both for compatibility.\n        \"\"\"\n        for attr_name in (\"reasoning\", \"reasoning_content\"):\n            value = getattr(message, attr_name, None)\n            if value:\n                return value\n        return None\n\n"""

OLD_STREAM_BLOCK = """                if delta.reasoning_content:\n                    content_accumulator.add_reasoning_content(\n                        delta.reasoning_content\n                    )\n                    # Yield partial response with reasoning content\n                    partial_response = (\n                        self._create_streaming_response_with_accumulator(\n                            content_accumulator,\n                            \"\",  # No regular content yet\n                            step_token_usage,\n                            getattr(chunk, 'id', ''),\n                            tool_call_records.copy(),\n                            reasoning_delta=delta.reasoning_content,\n                        )\n                    )\n                    yield partial_response\n"""

OLD_STREAM_BLOCK_DEEPSEEK = """                # Handle reasoning content streaming (for DeepSeek reasoner)\n                if (\n                    hasattr(delta, 'reasoning_content')\n                    and delta.reasoning_content\n                ):\n                    content_accumulator.add_reasoning_content(\n                        delta.reasoning_content\n                    )\n                    # Yield partial response with reasoning content\n                    partial_response = (\n                        self._create_streaming_response_with_accumulator(\n                            content_accumulator,\n                            \"\",  # No regular content yet\n                            step_token_usage,\n                            getattr(chunk, 'id', ''),\n                            tool_call_records.copy(),\n                            reasoning_delta=delta.reasoning_content,\n                        )\n                    )\n                    yield partial_response\n"""

NEW_STREAM_BLOCK = """                # Handle reasoning content streaming for providers that emit\n                # either `reasoning` or `reasoning_content`.\n                reasoning_delta = self._extract_reasoning_content(delta)\n                if reasoning_delta:\n                    content_accumulator.add_reasoning_content(\n                        reasoning_delta\n                    )\n                    # Yield partial response with reasoning content\n                    partial_response = (\n                        self._create_streaming_response_with_accumulator(\n                            content_accumulator,\n                            \"\",  # No regular content yet\n                            step_token_usage,\n                            getattr(chunk, 'id', ''),\n                            tool_call_records.copy(),\n                            reasoning_delta=reasoning_delta,\n                        )\n                    )\n                    yield partial_response\n"""


def patch_text(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    if OLD_PARSE_BLOCK in text:
      text = text.replace(OLD_PARSE_BLOCK, NEW_PARSE_BLOCK)
      changes.append("patched parse block")

    marker = "    def _step_terminate(\n"
    if "def _extract_reasoning_content(message: Any)" not in text:
        if marker not in text:
            raise RuntimeError("Could not find insertion marker for _extract_reasoning_content")
        text = text.replace(marker, INSERT_BEFORE_STEP_TERMINATE + marker, 1)
        changes.append("inserted _extract_reasoning_content")

    stream_replacements = text.count(OLD_STREAM_BLOCK)
    if stream_replacements:
        text = text.replace(OLD_STREAM_BLOCK, NEW_STREAM_BLOCK)
        changes.append(f"patched {stream_replacements} stream reasoning block(s)")

    deepseek_stream_replacements = text.count(OLD_STREAM_BLOCK_DEEPSEEK)
    if deepseek_stream_replacements:
        text = text.replace(OLD_STREAM_BLOCK_DEEPSEEK, NEW_STREAM_BLOCK)
        changes.append(
            f"patched {deepseek_stream_replacements} deepseek-style stream reasoning block(s)"
        )

    return text, changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default="/app/src/camel-ai/camel/agents/chat_agent.py",
        help="Path to CAMEL chat_agent.py",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise FileNotFoundError(f"Target file not found: {path}")

    original = path.read_text(encoding="utf-8")
    patched, changes = patch_text(original)

    if not changes:
        print(f"No patch needed for {path}")
        return 0

    path.write_text(patched, encoding="utf-8")
    print(f"Patched {path}")
    for change in changes:
        print(f"- {change}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Patch failed: {exc}", file=sys.stderr)
        raise
