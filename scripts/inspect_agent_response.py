#!/usr/bin/env python
"""
ChatAgent 响应结构诊断工具

检查 CAMEL 框架在流式模式下的 response 对象结构，
包括 msgs、content、reasoning_content 等字段的传递情况。

用途：
  - 排查流式响应结构变化（CAMEL 版本升级后）
  - 确认 reasoning_content 是否被正确传递
  - 诊断 agent.step() 返回值的实际类型和属性

结果同时输出到终端和 logs/ 目录下的日志文件。

用法:
    python scripts/inspect_agent_response.py
    python scripts/inspect_agent_response.py --query "你好"
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.agent_factory import chat_agent_factory


def setup_log(log_dir: Path) -> Path:
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"inspect_agent_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return log_file


def make_logger(log_file: Path):
    f = open(log_file, "w", encoding="utf-8")

    def log(msg: str = ""):
        print(msg)
        f.write(msg + "\n")
        f.flush()

    def close():
        f.close()

    return log, close


def inspect_sync_response(agent, query: str, log):
    """检查同步调用时 response 的对象结构"""
    log("\n" + "=" * 80)
    log("【同步响应结构检查】")
    log("=" * 80)
    log(f"查询: {query}")
    log("-" * 80)

    response = agent.step(query)

    log(f"\nResponse 类型: {type(response)}")
    log(f"Response 属性: {[a for a in dir(response) if not a.startswith('_')]}")

    if hasattr(response, "msg"):
        msg = response.msg
        log(f"\nresponse.msg 类型: {type(msg)}")
        if hasattr(msg, "content"):
            content = str(msg.content)
            log(f"response.msg.content 长度: {len(content)}")
            log(f"response.msg.content (前500字符):\n{content[:500]}")

    if hasattr(response, "msgs"):
        msgs = response.msgs
        log(f"\nresponse.msgs 数量: {len(msgs)}")
        for i, msg in enumerate(msgs):
            log(f"\n[msgs[{i}]]")
            log(f"  类型: {type(msg)}")
            if hasattr(msg, "content"):
                content = str(msg.content)
                log(f"  content 长度: {len(content)}")
                log(f"  content (前300字符): {content[:300]}")
            for attr in dir(msg):
                if attr.startswith("_") or attr in ("content", "role", "role_name"):
                    continue
                try:
                    value = getattr(msg, attr)
                    if not callable(value):
                        log(f"  {attr}: {str(value)[:200]}")
                except Exception:
                    pass


def inspect_stream_response(agent, query: str, log):
    """检查流式调用时每个 chunk 的结构"""
    log("\n" + "=" * 80)
    log("【流式响应结构检查】")
    log("=" * 80)
    log(f"查询: {query}")
    log("-" * 80)

    response = agent.step(query)
    chunk_count = 0

    for chunk in response:
        chunk_count += 1
        if chunk_count > 5:  # 只详细打印前5个块，避免刷屏
            log(f"[块 {chunk_count}] (略)")
            continue

        log(f"\n[块 {chunk_count}]")
        log(f"  类型: {type(chunk)}")

        if hasattr(chunk, "msgs"):
            msgs = chunk.msgs
            log(f"  msgs 数量: {len(msgs)}")
            for i, msg in enumerate(msgs):
                content = msg.content or ""
                log(f"  msg[{i}] content (前100字符): {content[:100]}")
                # 重点检查 reasoning 相关属性
                for attr in dir(msg):
                    if "reasoning" in attr.lower():
                        try:
                            value = getattr(msg, attr)
                            log(f"  msg[{i}].{attr}: {str(value)[:200]}")
                        except Exception:
                            pass

    log(f"\n总计收到 {chunk_count} 个流式块")


def main():
    parser = argparse.ArgumentParser(description="诊断 ChatAgent 响应结构")
    parser.add_argument(
        "--query",
        default="请解释什么是量子纠缠，用简单的语言说明。",
        help="测试查询语句（默认: 量子纠缠解释）",
    )
    args = parser.parse_args()

    log_dir = PROJECT_ROOT / "logs"
    log_file = setup_log(log_dir)
    log, close_log = make_logger(log_file)

    try:
        log("=" * 80)
        log("  ChatAgent 响应结构诊断")
        log("=" * 80)
        log(f"\n创建 ChatAgent...")

        agent = chat_agent_factory()
        log("ChatAgent 创建成功")

        inspect_sync_response(agent, args.query, log)
        inspect_stream_response(agent, args.query, log)

        log("\n" + "=" * 80)
        log("诊断完成")
        log("=" * 80)
    finally:
        close_log()

    print(f"\n结果已保存到: {log_file}")


if __name__ == "__main__":
    main()
