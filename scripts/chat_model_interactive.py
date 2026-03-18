#!/usr/bin/env python
"""
裸模型交互式对话测试

直接使用 stream_model() 构建 ChatAgent，不加载任何 RAG 工具。
用途：
  - 验证模型 API 连通性与流式输出是否正常
  - 排查与 RAG/工具链无关的模型层问题

用法:
    python scripts/chat_model_interactive.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from camel.agents.chat_agent import ChatAgent
from camel.messages.base import BaseMessage
from backend.app.core.model_runtime import stream_model


def main():
    system_message = """你是一个聊天助手。随便聊天。"""

    agent = ChatAgent(
        system_message=BaseMessage.make_assistant_message(
            role_name="Chat Agent",
            content=system_message,
        ),
        model=stream_model(),
        stream_accumulate=False,
    )

    print("=" * 60)
    print("裸模型交互式对话（不含 RAG 工具）")
    print("输入 exit 或按 Ctrl+C 退出")
    print("=" * 60)

    while True:
        try:
            question = input("\n问题：").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n退出。")
            break

        if question.lower() in ("exit", "quit", "q"):
            print("退出。")
            break

        if not question:
            continue

        response = agent.step(question)
        for chunk_response in response:
            message = chunk_response.msgs[0]
            content_text = message.content
            if content_text:
                print(content_text, end="", flush=True)

        print("\n")
        print("-" * 100)
        print(agent.memory.get_context())
        print("-" * 100)


if __name__ == "__main__":
    main()
