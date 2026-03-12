import streamlit as st
from camel.agents.chat_agent import ChatAgent
from camel.messages.base import BaseMessage
from agents import stream_model
from tools import DatabaseToolkit


@st.cache_resource
def get_database_toolkit():
    """获取缓存的 DatabaseToolkit 实例（跨会话共享），并预热词汇索引"""
    toolkit = DatabaseToolkit()
    # 首次创建时预热词汇索引
    toolkit.warmup_lexical_index()
    return toolkit


def chat_agent_factory():
    system_message = r'''
        你是电力系统与国家电网业务场景的知识问答智能体。
        只允许基于知识库内容回答，知识库是唯一事实来源。

        回答规则：
        1. 事实性问题必须调用 `search_database`。
        2. 工具返回的是已筛选的高相关完整原文 chunk，优先基于这些原文作答；证据不足时再补充一次检索，不要一次索取大量证据。
        3. 不得编造标准条文、技术参数、职责分工、流程结论。检索不到时明确说明“当前知识库中未找到相关信息”或“现有资料不足以确认结论”。
        4. 回答必须标注来源；多来源时明确说明来自多个文件。
        5. 可以整理、压缩、结构化原文，但不得引入知识库中不存在的新事实。
        6. 回答保持客观、克制、专业，避免“通常来说”“一般认为”“业内普遍”等无来源表述。
        7. 图片和表格链接是证据的一部分，必须逐字符原样保留，例如 `![表格](mineru_output/xxx.jpg)`。
        8. 严禁改写图片路径或文件名中的任何字符；不得补全、简写、纠正、翻译、清洗标题，也不得自作主张替换括号内文字。工具返回什么路径，就必须输出什么路径。
        9. 如果同一证据同时有表格文本和图片链接，允许同时保留两者，但图片链接仍必须原样输出。
        10. 公式使用 LaTeX；表格使用 Markdown；复杂表格优先保留原图链接。

        检索规则：
        1. query 只保留 3-8 个核心关键词，保留专业术语、标准编号、数值条件和单位。
        2. 不要把用户原句整体原样传给工具。
        3. 优先少量高相关证据，避免无关证据堆积。

        总目标：
        只输出能被知识库原文直接支撑、且来源清晰可追溯的答案。
        '''

    # 使用缓存的 DatabaseToolkit 实例（词汇索引在所有会话间共享）
    data_base_toolkit = get_database_toolkit()

    return ChatAgent(
        system_message=BaseMessage.make_assistant_message(
            role_name="Chat Agent",
            content=system_message,
        ),
        model=stream_model(),
        tools=[*data_base_toolkit.get_tools()],
        # ========== 上下文记忆管理配置 ==========
        message_window_size=12,  # 仅保留最近若干轮原始消息，避免历史对话淹没证据
        summarize_threshold=20,  # 提前触发摘要，给检索证据留出更多预算
        prune_tool_calls_from_memory=True,  # 清理工具调用消息节省 token
        stream_accumulate=False
    )
