#!/usr/bin/env python
"""
完整 RAG Agent 交互式对话测试

使用 chat_agent_factory() 创建带完整 RAG 工具链的 ChatAgent。
用途：
  - 端到端验证 Agent + DatabaseToolkit + 向量检索是否正常
  - 调试多轮对话、工具调用、记忆管理等业务逻辑

用法:
    python scripts/chat_agent_interactive.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.agent_factory import chat_agent_factory


def main():
    print("=" * 60)
    print("RAG Agent 交互式对话（含 DatabaseToolkit 工具链）")
    print("输入 exit 或按 Ctrl+C 退出")
    print("=" * 60)

    agent = chat_agent_factory()

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
