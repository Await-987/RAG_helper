"""
测试 ChatAgent 调用 QwQ-32B 时的响应结构
检查 reasoning_content 是否被 CAMEL 框架传递
"""
import sys
sys.path.append('.')

from backend.app.core.agent_factory import chat_agent_factory
from pathlib import Path
from datetime import datetime

# 设置输出文件
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"chat_agent_reasoning_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

with open(log_file, 'w', encoding='utf-8') as f:
    def log(msg):
        f.write(msg + '\n')
        print(msg)

    log("=" * 80)
    log("  ChatAgent + QwQ-32B 思考过程测试")
    log("=" * 80)

    # 创建 ChatAgent
    log("\n创建 ChatAgent...")
    agent = chat_agent_factory()

    # 测试问题
    test_query = "请解释什么是量子纠缠，用简单的语言说明。"
    log(f"\n测试问题: {test_query}")
    log("-" * 80)

    # 获取响应
    log("\n开始调用 ChatAgent.step()...")
    response = agent.step(test_query)

    log("\n【Response 对象结构】")
    log("-" * 40)
    log(f"Response 类型: {type(response)}")
    log(f"Response 属性: {dir(response)}")

    # 检查 response 是否有 msg 属性
    if hasattr(response, 'msg'):
        msg = response.msg
        log(f"\nresponse.msg 类型: {type(msg)}")
        log(f"response.msg 属性: {dir(msg)}")

        if hasattr(msg, 'content'):
            log(f"\nresponse.msg.content 类型: {type(msg.content)}")
            log(f"response.msg.content 长度: {len(str(msg.content))}")
            log(f"\nresponse.msg.content 内容:\n{msg.content}")

    # 检查 response 是否有 msgs 属性
    if hasattr(response, 'msgs'):
        msgs = response.msgs
        log(f"\nresponse.msgs 类型: {type(msgs)}")
        log(f"response.msgs 长度: {len(msgs)}")

        for i, msg in enumerate(msgs):
            log(f"\n[消息 {i}]")
            log(f"  类型: {type(msg)}")
            log(f"  属性: {dir(msg)}")

            if hasattr(msg, 'content'):
                content = msg.content
                log(f"  content 类型: {type(content)}")
                log(f"  content 长度: {len(str(content))}")
                log(f"  content 内容:\n{content}")

            # 检查是否有其他特殊属性
            for attr in dir(msg):
                if not attr.startswith('_') and attr not in ['content', 'role', 'role_name']:
                    try:
                        value = getattr(msg, attr)
                        if not callable(value):
                            log(f"  {attr}: {value}")
                    except:
                        pass

    # 流式响应测试
    log("\n\n" + "=" * 80)
    log("【流式响应测试】")
    log("=" * 80)

    response2 = agent.step(test_query)

    log("\n流式处理数据块:")
    chunk_count = 0
    reasoning_chunks = []
    content_chunks = []

    for chunk in response2:
        chunk_count += 1
        log(f"\n[块 {chunk_count}]")
        log(f"  类型: {type(chunk)}")
        log(f"  属性: {dir(chunk)}")

        if hasattr(chunk, 'msgs'):
            msgs = chunk.msgs
            log(f"  msgs 数量: {len(msgs)}")

            for i, msg in enumerate(msgs):
                log(f"  msg[{i}] content: {msg.content[:100] if msg.content else 'None'}...")

                # 检查是否有 reasoning_content
                for attr in dir(msg):
                    if 'reasoning' in attr.lower():
                        value = getattr(msg, attr)
                        log(f"  msg[{i}] {attr}: {str(value)[:200]}...")

    log(f"\n总计收到 {chunk_count} 个块")

print(f"\n✅ 测试完成！结果已保存到: {log_file}")
