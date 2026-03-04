# @ qiaoyu
import streamlit as st
import os
import sys
from pathlib import Path
from config import layout
from loguru import logger

# 配置日志输出到终端
logger.remove()  # 移除默认handler
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools import load_multiple_files
from agents import chat_agent_factory

st.set_page_config(
    page_title="智能设计助手",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(layout, unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "chat_agent" not in st.session_state:
    st.session_state.chat_agent = chat_agent_factory()

if "uploaded_files_list" not in st.session_state:
    st.session_state.uploaded_files_list = []

STORAGE_DIR = project_root / "data" / "stored_files"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

with st.sidebar:
    st.header("📁 文档管理")
    st.markdown("---")

    uploaded_files = st.file_uploader(
        "批量上传PDF文件",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
        help="支持同时上传多个PDF文件"
    )

    if uploaded_files:
        st.info(f"📄 已选择 {len(uploaded_files)} 个文件")
        with st.expander("查看文件列表", expanded=True):
            for i, file in enumerate(uploaded_files, 1):
                st.markdown(f"`{i}. {file.name}`")

    if st.button("🚀 导入到数据库", type="primary", disabled=not uploaded_files):
        if uploaded_files:
            with st.spinner("⏳ 正在处理文件，请稍候..."):
                saved_file_paths = []

                progress_bar = st.progress(0)
                for idx, uploaded_file in enumerate(uploaded_files):
                    file_path = STORAGE_DIR / uploaded_file.name
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    saved_file_paths.append(str(file_path.absolute()))
                    progress_bar.progress((idx + 1) / len(uploaded_files))

                try:
                    results = load_multiple_files(
                        file_paths=saved_file_paths,
                        collection_name="database",
                        dpi=200,
                        debug=True,  # 启用调试模式
                        search_keyword="表27"  # 搜索"表27"相关内容
                    )

                    if results["success"]:
                        st.success(f"✅ 成功导入 {len(results['success'])} 个文件！")
                        for file_path in results["success"]:
                            file_name = os.path.basename(file_path)
                            if file_name not in st.session_state.uploaded_files_list:
                                st.session_state.uploaded_files_list.append(file_name)

                    if results["failed"]:
                        st.error(f"❌ 导入失败 {len(results['failed'])} 个文件")
                        with st.expander("查看失败文件"):
                            for file_path in results["failed"]:
                                file_name = os.path.basename(file_path)
                                st.write(f"- {file_name}")

                except Exception as e:
                    st.error(f"❌ 处理文件时出错：{str(e)}")

    if st.session_state.uploaded_files_list:
        st.markdown("---")
        st.subheader("📚 已导入的文件")
        st.caption(f"共 {len(st.session_state.uploaded_files_list)} 个文件")

        with st.expander("查看全部", expanded=False):
            for i, file_name in enumerate(st.session_state.uploaded_files_list, 1):
                st.markdown(f'<div class="file-item">{i}. {file_name}</div>', unsafe_allow_html=True)

st.title("💬 智能设计助手")

chat_container = st.container()

with chat_container:
    for message in st.session_state.messages:
        if message["role"] == "user":
            st.markdown(f"""
                <div class="user-message-container">
                    <div class="message-bubble user-bubble">
                        {message["content"]}
                    </div>
                    <div class="avatar user-avatar">👤</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div class="assistant-message-container">
                    <div class="avatar assistant-avatar">🤖</div>
                    <div class="message-bubble assistant-bubble">
                        {message["content"]}
                    </div>
                </div>
            """, unsafe_allow_html=True)

if prompt := st.chat_input("💭 请输入您的问题..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    st.markdown(f"""
        <div class="user-message-container">
            <div class="message-bubble user-bubble">
                {prompt}
            </div>
            <div class="avatar user-avatar">👤</div>
        </div>
    """, unsafe_allow_html=True)

    assistant_container = st.empty()
    
    try:
        response = st.session_state.chat_agent.step(prompt)
        print(f"Response from chat_agent: {response}")

        full_response = ""

        assistant_container.markdown(f"""
            <div class="assistant-message-container">
                <div class="avatar assistant-avatar">🤖</div>
                <div class="message-bubble assistant-bubble">
                    <div class="loading-dots">正在思考<span>.</span><span>.</span><span>.</span></div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        for chunk_response in response:
            if hasattr(chunk_response, 'msgs') and len(chunk_response.msgs) > 0:
                message = chunk_response.msgs[0]
                content_text = message.content
                if content_text:
                    # full_response += content_text
                    if content_text.startswith(full_response):
                        full_response = content_text
                    else:
                        full_response += content_text

                    assistant_container.markdown(f"""
                        <div class="assistant-message-container">
                            <div class="avatar assistant-avatar">🤖</div>
                            <div class="message-bubble assistant-bubble">
                                {full_response}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

        if full_response:
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response
            })
        else:
            if hasattr(response, 'msg') and hasattr(response.msg, 'content'):
                full_response = response.msg.content
            elif hasattr(response, 'msgs') and len(response.msgs) > 0:
                full_response = response.msgs[-1].content
            else:
                full_response = "抱歉，我无法生成回复。"
            
            assistant_container.markdown(f"""
                <div class="assistant-message-container">
                    <div class="avatar assistant-avatar">🤖</div>
                    <div class="message-bubble assistant-bubble">
                        {full_response}
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response
            })

        st.rerun()
        
    except Exception as e:
        error_message = f"❌ 处理消息时出错：{str(e)}"
        assistant_container.markdown(f"""
            <div class="assistant-message-container">
                <div class="avatar assistant-avatar">🤖</div>
                <div class="message-bubble assistant-bubble">
                    {error_message}
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        st.session_state.messages.append({
            "role": "assistant",
            "content": error_message
        })
