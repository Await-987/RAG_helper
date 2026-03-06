# @ qiaoyu
import streamlit as st
import os
import sys
import re
from pathlib import Path
from config import layout
from loguru import logger
import markdown
import html as html_module

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
from tools import file_manager_ui
from tools import user_auth
from tools.user_auth import UserRole
from agents import chat_agent_factory

# ========== 辅助函数：处理 checkbox 状态变化 ==========
def handle_checkbox_change(file_idx: int):
    """处理复选框状态变化"""
    # checkbox 的状态存储在 st.session_state[key] 中，直接复制到 selected_{i}
    checkbox_key = f"checkbox_{file_idx}"
    if checkbox_key in st.session_state:
        st.session_state[f"selected_{file_idx}"] = st.session_state[checkbox_key]
    else:
        st.session_state[f"selected_{file_idx}"] = False


# ========== 登录状态初始化 ==========
def init_session_state():
    """初始化 session_state"""
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "user_role" not in st.session_state:
        st.session_state.user_role = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chat_agent" not in st.session_state:
        st.session_state.chat_agent = chat_agent_factory()
    if "uploaded_files_list" not in st.session_state:
        st.session_state.uploaded_files_list = []
    if "page" not in st.session_state:
        st.session_state.page = "login"  # login, chat, admin


st.set_page_config(
    page_title="智能设计助手",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(layout, unsafe_allow_html=True)

# 初始化 session state
init_session_state()

STORAGE_DIR = project_root / "data" / "stored_files"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# 图片存储目录（mineru 输出）
MINERU_OUTPUT_DIR = project_root / "data" / "mineru_output"


def safe_html(content: str) -> str:
    """
    安全地转义HTML，同时保留换行符
    """
    import html
    # 转义HTML特殊字符
    escaped = html.escape(content)
    # 将换行符转换为 <br>
    escaped = escaped.replace('\n', '<br>')
    return escaped


def render_streaming_content(content: str, container):
    """
    流式渲染内容（支持表格，但不处理图片）
    用于流式更新时的快速渲染
    """
    # 使用 markdown 库渲染（支持表格）
    md_html = markdown.markdown(content, extensions=['tables', 'fenced_code'])
    container.markdown(f"""
        <div class="assistant-message-container">
            <div class="avatar assistant-avatar">🤖</div>
            <div class="message-bubble assistant-bubble">
                <div class="markdown-content">
                    {md_html}
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)


def render_message(role: str, content: str):
    """
    渲染消息（支持图片）
    """
    if role == "user":
        safe_content = safe_html(content)
        st.markdown(f"""
            <div class="user-message-container">
                <div class="message-bubble user-bubble">
                    {safe_content}
                </div>
                <div class="avatar user-avatar">👤</div>
            </div>
        """, unsafe_allow_html=True)
    else:  # assistant
        # 使用 parse_and_render_content 渲染内容（支持图片）
        parse_and_render_content(content)


def parse_and_render_content(content: str):
    """
    解析内容中的图片链接并渲染
    支持 Markdown 图片格式: ![alt](path)
    使用 markdown 库渲染，支持表格
    """
    import re
    import base64

    # 提取所有图片链接
    # 匹配 ![alt](path) 格式
    img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    images = re.findall(img_pattern, content)

    if not images:
        # 没有图片，使用 markdown 库渲染（支持表格）
        # 使用 markdown 库把 markdown 转换成 HTML
        md_html = markdown.markdown(content, extensions=['tables', 'fenced_code'])
        st.markdown(f"""
            <div class="assistant-message-container">
                <div class="avatar assistant-avatar">🤖</div>
                <div class="message-bubble assistant-bubble">
                    <div class="markdown-content">
                        {md_html}
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        # 分离文本和图片，构建完整的 HTML
        parts = []
        last_end = 0

        for match in re.finditer(img_pattern, content):
            # 添加图片前的文本
            if match.start() > last_end:
                text_part = content[last_end:match.start()]
                if text_part.strip():
                    parts.append(("text", text_part))

            # 添加图片
            alt, img_path = match.groups()
            parts.append(("image", img_path))
            last_end = match.end()

        # 添加最后的文本
        if last_end < len(content):
            text_part = content[last_end:]
            if text_part.strip():
                parts.append(("text", text_part))

        # 构建 HTML 内容
        html_content = ""

        for part_type, part_content in parts:
            if part_type == "text":
                # 使用 markdown 库渲染文本（支持表格）
                md_html = markdown.markdown(part_content, extensions=['tables', 'fenced_code'])
                html_content += md_html
            elif part_type == "image":
                img_path = part_content
                full_path = Path(img_path)

                # 检查文件是否存在
                if full_path.exists():
                    try:
                        # 读取图片并转换为 base64
                        with open(full_path, "rb") as img_file:
                            img_base64 = base64.b64encode(img_file.read()).decode()
                        # 使用 data URI 嵌入图片
                        html_content += f'<img src="data:image/jpeg;base64,{img_base64}" style="max-width: 100%; height: auto; margin: 10px 0;">'
                    except Exception as e:
                        html_content += f'<p style="color: orange;">⚠️ 无法加载图片: {html_module.escape(img_path)}</p>'
                else:
                    html_content += f'<p style="color: orange;">⚠️ 图片文件不存在: {html_module.escape(img_path)}</p>'

        # 一次性渲染完整的 HTML
        st.markdown(f"""
            <div class="assistant-message-container">
                <div class="avatar assistant-avatar">🤖</div>
                <div class="message-bubble assistant-bubble">
                    <div class="markdown-content">
                        {html_content}
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)


# ========== 登录页面 ==========
def render_login_page():
    """渲染登录页面"""
    st.markdown("""
        <style>
        .login-container {
            max-width: 400px;
            margin: 100px auto;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
        }
        .login-title {
            font-size: 28px;
            margin-bottom: 30px;
            color: #1f77b4;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<h2 class="login-title">💬 智能设计助手</h2>', unsafe_allow_html=True)

    # 登录表单
    with st.form("login_form"):
        username = st.text_input("👤 用户名", placeholder="请输入用户名")
        password = st.text_input("🔒 密码", type="password", placeholder="请输入密码")
        submit = st.form_submit_button("🚀 登录", use_container_width=True, type="primary")

        if submit:
            if not username or not password:
                st.error("⚠️ 请输入用户名和密码")
            else:
                user = user_auth.auth.authenticate(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.username = user["username"]
                    st.session_state.user_role = user["role"]
                    st.success(f"✅ 登录成功！欢迎回来，{user['username']}")
                    st.rerun()
                else:
                    st.error("❌ 用户名或密码错误")

    st.markdown("""
        <div style="margin-top: 30px; padding: 15px; background: #f0f2f6; border-radius: 8px; font-size: 14px;">
        <strong>🔑 默认管理员账户：</strong><br>
        用户名: <code>admin</code><br>
        密码: <code>admin123</code>
        </div>
    """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ========== 用户管理页面（管理员专用） ==========
def render_user_management():
    """渲染用户管理页面"""
    st.markdown("---")
    st.markdown("## 👥 用户管理")

    # 获取所有用户
    users = user_auth.auth.get_all_users()

    # 统计信息
    col1, col2, col3 = st.columns(3)
    with col1:
        admin_count = sum(1 for u in users if u["role"] == UserRole.ADMIN)
        st.metric("👑 管理员", f"{admin_count} 个")
    with col2:
        user_count = sum(1 for u in users if u["role"] == UserRole.USER)
        st.metric("👤 普通用户", f"{user_count} 个")
    with col3:
        st.metric("📊 总用户", f"{len(users)} 个")

    st.markdown("---")

    # 添加新用户
    with st.expander("➕ 添加新用户", expanded=False):
        with st.form("add_user_form"):
            new_username = st.text_input("用户名")
            new_password = st.text_input("密码", type="password")
            new_role = st.selectbox("角色", [UserRole.USER, UserRole.ADMIN],
                                    format_func=lambda x: "管理员" if x == UserRole.ADMIN else "普通用户")
            submit_add = st.form_submit_button("➕ 添加用户", type="primary")

            if submit_add:
                if not new_username or not new_password:
                    st.error("⚠️ 请填写完整信息")
                else:
                    success, msg = user_auth.auth.add_user(
                        new_username, new_password, new_role, st.session_state.username
                    )
                    if success:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

    st.markdown("---")

    # 用户列表
    st.markdown("### 📋 用户列表")
    for user in users:
        with st.container():
            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 2, 3])

            with col1:
                st.markdown(f"**👤 {user['username']}**")

            with col2:
                if user["role"] == UserRole.ADMIN:
                    st.markdown('<span style="color:gold">👑 管理员</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="color:gray">👤 普通用户</span>', unsafe_allow_html=True)

            with col3:
                last_login = user.get("last_login")
                if last_login:
                    # 只显示日期部分
                    last_login = last_login.split("T")[0] if "T" in last_login else last_login
                else:
                    last_login = "从未登录"
                st.caption(f"最后登录: {last_login}")

            with col4:
                # 修改角色
                if user["username"] != st.session_state.username:  # 不能修改自己的角色
                    new_role = UserRole.USER if user["role"] == UserRole.ADMIN else UserRole.ADMIN
                    if st.button(f"🔄 改为{'管理员' if new_role == UserRole.ADMIN else '用户'}",
                               key=f"change_role_{user['username']}"):
                        success, msg = user_auth.auth.change_user_role(
                            user["username"], new_role, st.session_state.username
                        )
                        if success:
                            st.success(f"✅ {msg}")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")

            with col5:
                # 重置密码
                if st.button(f"🔑 重置密码", key=f"reset_pwd_{user['username']}"):
                    st.session_state[f"reset_pwd_{user['username']}"] = True
                    st.rerun()

                # 重置密码对话框
                if st.session_state.get(f"reset_pwd_{user['username']}", False):
                    new_pwd = st.text_input(f"新密码 ({user['username']})", type="password",
                                           key=f"new_pwd_{user['username']}")
                    if st.button("✅ 确认", key=f"confirm_reset_{user['username']}", type="primary"):
                        if new_pwd:
                            success, msg = user_auth.auth.reset_password(
                                user["username"], new_pwd, st.session_state.username
                            )
                            if success:
                                st.success(f"✅ {msg}")
                                del st.session_state[f"reset_pwd_{user['username']}"]
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
                        else:
                            st.warning("请输入新密码")
                    if st.button("❌ 取消", key=f"cancel_reset_{user['username']}"):
                        del st.session_state[f"reset_pwd_{user['username']}"]
                        st.rerun()

            with col6:
                # 删除用户
                if user["username"] != st.session_state.username:  # 不能删除自己
                    if st.button(f"🗑️ 删除", key=f"delete_user_{user['username']}"):
                        st.session_state[f"confirm_delete_user_{user['username']}"] = True
                        st.rerun()

                    # 删除确认对话框
                    if st.session_state.get(f"confirm_delete_user_{user['username']}", False):
                        st.warning(f"确认删除用户 **{user['username']}**？")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ 确认删除", key=f"yes_delete_{user['username']}", type="primary"):
                                success, msg = user_auth.auth.delete_user(
                                    user["username"], st.session_state.username
                                )
                                if success:
                                    st.success(f"✅ {msg}")
                                    del st.session_state[f"confirm_delete_user_{user['username']}"]
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg}")
                        with col_no:
                            if st.button("❌ 取消", key=f"no_delete_{user['username']}"):
                                del st.session_state[f"confirm_delete_user_{user['username']}"]
                                st.rerun()

            st.markdown("---")


# ========== 修改密码页面 ==========
def render_change_password():
    """渲染修改密码页面"""
    st.markdown("---")
    st.markdown("## 🔑 修改密码")

    with st.form("change_password_form"):
        old_pwd = st.text_input("原密码", type="password")
        new_pwd = st.text_input("新密码", type="password")
        confirm_pwd = st.text_input("确认新密码", type="password")
        submit = st.form_submit_button("✅ 修改密码", type="primary")

        if submit:
            if not old_pwd or not new_pwd:
                st.error("⚠️ 请填写完整信息")
            elif new_pwd != confirm_pwd:
                st.error("❌ 两次输入的密码不一致")
            elif len(new_pwd) < 6:
                st.error("❌ 新密码长度至少6位")
            else:
                success, msg = user_auth.auth.change_password(
                    st.session_state.username, old_pwd, new_pwd
                )
                if success:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")


# ========== 登录检查 ==========
if not st.session_state.logged_in:
    render_login_page()
    st.stop()  # 停止执行后续代码

# 已登录，显示主界面
st.markdown("---")


with st.sidebar:
    # ========== 用户信息栏 ==========
    st.markdown("---")
    user_col1, user_col2, user_col3 = st.columns([2, 2, 1])
    with user_col1:
        if st.session_state.user_role == UserRole.ADMIN:
            st.markdown("**👑 管理员**")
        else:
            st.markdown("**👤 普通用户**")
    with user_col2:
        st.caption(f"`{st.session_state.username}`")
    with user_col3:
        if st.button("🚪", key="logout_btn", help="退出登录"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            init_session_state()
            st.rerun()

    st.markdown("---")

    # ========== 导航菜单 ==========
    page = st.radio(
        "📍 导航",
        ["💬 聊天", "📊 文件管理"],
        label_visibility="collapsed"
    )

    # 管理员专用功能
    if st.session_state.user_role == UserRole.ADMIN:
        st.markdown("---")
        st.markdown("**🔧 管理员功能**")
        if st.button("👥 用户管理", use_container_width=True):
            st.session_state.page = "user_management"
            st.rerun()
        if st.button("🔑 修改密码", use_container_width=True):
            st.session_state.page = "change_password"
            st.rerun()
    else:
        st.markdown("---")
        if st.button("🔑 修改密码", use_container_width=True):
            st.session_state.page = "change_password"
            st.rerun()

    st.markdown("---")

    # ========== 根据页面显示不同内容 ==========
    if page == "📊 文件管理" or st.session_state.page == "user_management" or st.session_state.page == "change_password":
        # 显示文件管理或用户管理界面
        if st.session_state.page == "user_management" and st.session_state.user_role == UserRole.ADMIN:
            # 用户管理页面（管理员专用）
            st.header("📁 文档管理")
            st.markdown("---")
        elif st.session_state.page == "change_password":
            # 修改密码页面
            st.header("📁 文档管理")
            st.markdown("---")
        else:
            # 文件管理页面
            st.header("📁 文档管理")
            st.markdown("---")

            # 上传功能（仅管理员可见）
            if st.session_state.user_role == UserRole.ADMIN:
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
            else:
                st.info("📁 仅管理员可以上传文件")

            # ========== 文件管理功能 ==========
            st.markdown("---")
            st.markdown("### 📊 文件管理")

    # 刷新和批量操作按钮
    col_refresh, col_batch = st.columns(2)
    with col_refresh:
        if st.button("🔄 刷新", key="refresh_files", use_container_width=True):
            # 清除选择状态
            for key in list(st.session_state.keys()):
                if key.startswith("selected_"):
                    del st.session_state[key]
            st.rerun()

    # 获取文件信息（显示所有本地文件及其数据库状态）
    file_info_list, total_chunks = file_manager_ui.get_local_files_with_db_status(STORAGE_DIR)

    # 统计信息
    imported_files = [f for f in file_info_list if f["type"] == "imported"]
    not_imported_files = [f for f in file_info_list if f["type"] == "not_imported"]
    ghost_files = [f for f in file_info_list if f["type"] == "ghost"]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("本地文件", f"{len(imported_files) + len(not_imported_files)} 个")
    with col2:
        st.metric("已建库", f"{len(imported_files)} 个")
    with col3:
        st.metric("未建库", f"{len(not_imported_files)} 个")
    with col4:
        st.metric("残留数据", f"{len(ghost_files)} 个")

    # 未建库文件提示（仅管理员可见）
    is_admin = st.session_state.user_role == UserRole.ADMIN
    if is_admin and not_imported_files:
        st.warning(f"📦 检测到 {len(not_imported_files)} 个文件尚未建库")

    # 残留数据提示（仅管理员可见）
    if is_admin and ghost_files:
        st.warning(f"👻 检测到 {len(ghost_files)} 个残留数据（本地文件已删除，仅数据库有记录）")

        # 展开/收起未建库文件列表
        with st.expander("📋 查看未建库文件", expanded=False):
            for file_info in not_imported_files:
                size_mb = file_info["path"].stat().st_size / (1024 * 1024)
                st.markdown(f"- 📄 `{file_info['name']}` ({size_mb:.2f} MB)")

        # 一键建库按钮
        if st.button(f"🚀 一键建库 ({len(not_imported_files)} 个文件)", type="primary", key="batch_import_btn"):
            st.session_state["batch_import_confirm"] = True
            st.rerun()

        # 建库确认对话框
        if st.session_state.get("batch_import_confirm", False):
            st.info(f"### 📦 即将导入 {len(not_imported_files)} 个文件到数据库")
            st.write("**注意：此过程可能需要较长时间，请耐心等待。**")

            file_list = "\n".join([f"- `{f['name']}`" for f in not_imported_files])
            st.write(file_list)

            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("✅ 开始导入", key="batch_import_yes", type="primary"):
                    # 清除确认状态
                    del st.session_state["batch_import_confirm"]

                    # 显示进度
                    progress_container = st.empty()
                    with progress_container:
                        with st.spinner(f"⏳ 正在处理 {len(not_imported_files)} 个文件，请稍候..."):
                            file_paths = [str(f["path"]) for f in not_imported_files]
                            results = file_manager_ui.batch_import_files(
                                file_paths=file_paths,
                                collection_name="database",
                                dpi=200,
                                debug=True
                            )

                    # 显示结果
                    if results["success_count"] > 0:
                        st.success(f"✅ 成功导入 {results['success_count']} 个文件")
                    if results["failed_count"] > 0:
                        st.error(f"❌ 导入失败 {results['failed_count']} 个文件")
                        with st.expander("查看失败详情"):
                            for file_path, error_msg in results["failed"]:
                                st.write(f"- `{os.path.basename(file_path)}`: {error_msg}")

                    st.rerun()

            with col_no:
                if st.button("❌ 取消", key="batch_import_no"):
                    del st.session_state["batch_import_confirm"]
                    st.rerun()

    # ========== 搜索和筛选 ==========
    st.markdown("**🔍 搜索与筛选：**")

    # 搜索框
    search_query = st.text_input(
        "🔎 搜索文件名",
        placeholder="输入文件名关键词...",
        key="file_search_input"
    ).strip().lower()

    # 类型筛选
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        filter_type = st.selectbox(
            "文件类型",
            ["全部", "已建库", "未建库", "残留数据"],
            key="filter_type_select"
        )
    with filter_col2:
        sort_by = st.selectbox(
            "排序方式",
            ["文件名", "切片数"],
            key="sort_by_select"
        )
    with filter_col3:
        sort_order = st.selectbox(
            "排序顺序",
            ["升序", "降序"],
            key="sort_order_select"
        )

    # 应用筛选和排序
    filtered_list = file_info_list.copy()

    # 类型筛选
    if filter_type == "已建库":
        filtered_list = [f for f in filtered_list if f["type"] == "imported"]
    elif filter_type == "未建库":
        filtered_list = [f for f in filtered_list if f["type"] == "not_imported"]
    elif filter_type == "残留数据":
        filtered_list = [f for f in filtered_list if f["type"] == "ghost"]

    # 搜索过滤
    if search_query:
        filtered_list = [f for f in filtered_list if search_query in f["name"].lower()]

    # 排序
    if sort_by == "文件名":
        filtered_list.sort(key=lambda x: x["name"], reverse=(sort_order == "降序"))
    else:  # 切片数
        filtered_list.sort(key=lambda x: x["chunk_count"], reverse=(sort_order == "降序"))

    # 显示筛选结果
    if filter_type != "全部" or search_query:
        st.caption(f"📋 筛选结果: {len(filtered_list)} 个文件")

    # ========== 批量操作（仅管理员可见） ==========
    is_admin = st.session_state.user_role == UserRole.ADMIN

    if filtered_list and is_admin:
        # 全选按钮
        batch_col1, batch_col2, batch_col3 = st.columns(3)
        with batch_col1:
            select_all = st.checkbox("📌 全选当前列表", key="select_all_checkbox")

        with batch_col2:
            if st.button("🗑️ 批量删除选中", key="batch_delete_btn", type="primary"):
                selected_count = sum(1 for i in range(len(filtered_list)) if st.session_state.get(f"selected_{i}", False))
                if selected_count > 0:
                    st.session_state["batch_delete_confirm"] = True
                    st.rerun()
                else:
                    st.warning("⚠️ 请先选择要删除的文件")

        with batch_col3:
            # 显示选中数量
            selected_count = sum(1 for i in range(len(filtered_list)) if st.session_state.get(f"selected_{i}", False))
            st.caption(f"已选: {selected_count} 个")

        # 处理全选/取消全选
        # 使用一个标志来避免重复设置
        select_all_key = "select_all_last_state"
        current_select_all = st.session_state.get("select_all_checkbox", False)
        last_select_all = st.session_state.get(select_all_key, None)

        # 只有当全选状态发生变化时才更新
        if last_select_all is not None and current_select_all != last_select_all:
            if current_select_all:
                for i in range(len(filtered_list)):
                    st.session_state[f"selected_{i}"] = True
            else:
                for i in range(len(filtered_list)):
                    st.session_state.pop(f"selected_{i}", None)

        # 保存当前状态
        st.session_state[select_all_key] = current_select_all

    # ========== 批量删除确认对话框（仅管理员可见） ==========
    if is_admin and st.session_state.get("batch_delete_confirm", False):
        st.markdown("---")
        st.error(f"### ⚠️ 确认批量删除")

        selected_files = []
        imported_count = 0
        ghost_count = 0
        for i, info in enumerate(filtered_list):
            if st.session_state.get(f"selected_{i}", False):
                selected_files.append(info["name"])
                if info["type"] == "imported":
                    imported_count += 1
                elif info["type"] == "ghost":
                    ghost_count += 1

        st.write(f"将删除以下 **{len(selected_files)}** 个文件：")
        if imported_count > 0 or ghost_count > 0:
            desc = []
            if imported_count > 0:
                desc.append(f"{imported_count} 个已建库文件（同时删除本地+数据库）")
            if ghost_count > 0:
                desc.append(f"{ghost_count} 个残留数据（仅删除数据库记录）")
            st.caption(f"说明：{', '.join(desc)}")
        for name in selected_files:
            st.write(f" - `{name}`")

        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("✅ 确认批量删除", key="batch_delete_yes", type="primary"):
                try:
                    imported_count = 0
                    not_imported_count = 0
                    ghost_count = 0
                    db_success = 0
                    db_fail = 0
                    local_success = 0
                    local_fail = 0

                    # 先收集所有要删除的文件信息
                    to_delete = []
                    for i, info in enumerate(filtered_list):
                        if st.session_state.get(f"selected_{i}", False):
                            to_delete.append(info)
                            if info["type"] == "imported":
                                imported_count += 1
                            elif info["type"] == "ghost":
                                ghost_count += 1
                            else:  # not_imported
                                not_imported_count += 1

                    # 第一步：删除数据库切片（已建库 + 残留数据）
                    for info in to_delete:
                        if info["type"] in ["imported", "ghost"]:
                            if file_manager_ui.delete_file_by_tag(info["tag"]):
                                db_success += 1
                            else:
                                db_fail += 1
                                logger.error(f"删除数据库切片失败: {info['tag']}")

                    # 第二步：删除本地文件（已建库 + 未建库）
                    for info in to_delete:
                        if info["path"]:  # imported 和 not_imported 有本地文件
                            if file_manager_ui.delete_local_file(info["path"]):
                                local_success += 1
                            else:
                                local_fail += 1
                                logger.error(f"删除本地文件失败: {info['path']}")

                    # 清除选择状态
                    st.session_state.pop("batch_delete_confirm", None)
                    for key in list(st.session_state.keys()):
                        if key.startswith("selected_"):
                            del st.session_state[key]

                    # 显示结果
                    if db_fail == 0 and local_fail == 0:
                        parts = []
                        if local_success > 0:
                            parts.append(f"本地文件 {local_success} 个")
                        if db_success > 0:
                            parts.append(f"数据库记录 {db_success} 个")
                        msg = "✅ 成功删除：" + "、".join(parts)
                        st.success(msg)
                    else:
                        msg = f"⚠️ 删除完成：本地文件成功 {local_success} 个，失败 {local_fail} 个"
                        if db_fail > 0:
                            msg += f"；数据库记录成功 {db_success} 个，失败 {db_fail} 个"
                        st.warning(msg)

                    st.rerun()
                except Exception as e:
                    logger.error(f"批量删除异常: {e}")
                    st.error(f"❌ 批量删除失败: {str(e)}")

        with col_cancel:
            if st.button("❌ 取消", key="batch_delete_no"):
                st.session_state.pop("batch_delete_confirm", None)
                st.rerun()

    # ========== 文件列表 ==========
    st.markdown("**📁 文件列表：**")

    if filtered_list:
        # 表头（根据角色显示不同列）
        is_admin = st.session_state.user_role == UserRole.ADMIN

        if is_admin:
            header_col1, header_col2, header_col3, header_col4, header_col5 = st.columns([0.5, 3, 2, 2, 1])
            with header_col1:
                st.markdown("**选择**")
            with header_col2:
                st.markdown("**文件名**")
            with header_col3:
                st.markdown("**切片数**")
            with header_col4:
                st.markdown("**类型**")
            with header_col5:
                st.markdown("**操作**")
        else:
            header_col1, header_col2, header_col3, header_col4 = st.columns([3, 2, 2, 2])
            with header_col1:
                st.markdown("**文件名**")
            with header_col2:
                st.markdown("**切片数**")
            with header_col3:
                st.markdown("**类型**")
            with header_col4:
                st.markdown("**状态**")

        st.markdown("---")

        # 文件列表
        for i, info in enumerate(filtered_list):
            with st.container():
                if is_admin:
                    col_select, col_name, col_chunks, col_type, col_action = st.columns([0.5, 3, 2, 2, 1])
                else:
                    col_name, col_chunks, col_type, col_status = st.columns([3, 2, 2, 2])

                # 复选框（仅管理员可见）
                if is_admin:
                    with col_select:
                        # 复选框 - key 必须与后续检查代码一致（selected_{i}）
                        st.checkbox(
                            "select",
                            key=f"selected_{i}",
                            label_visibility="collapsed"
                        )

                # 文件名
                with col_name:
                    # 文件名
                    if info["type"] == "ghost":
                        st.markdown(f"👻 `{info['name']}`")
                    else:
                        st.markdown(f"📄 `{info['name']}`")

                with col_chunks:
                    # 切片数
                    if info["chunk_count"] > 0:
                        st.caption(f"📊 {info['chunk_count']} 个")
                    else:
                        st.caption("📊 0 个")

                with col_type:
                    # 类型标记
                    if info["type"] == "imported":
                        st.markdown('<span style="color:green">已建库</span>', unsafe_allow_html=True)
                    elif info["type"] == "ghost":
                        st.markdown('<span style="color:red">残留数据</span>', unsafe_allow_html=True)
                    else:
                        st.markdown('<span style="color:orange">未建库</span>', unsafe_allow_html=True)

                # 操作列（仅管理员可见）
                if is_admin:
                    with col_action:
                        # 单个删除按钮
                        button_key = f"single_delete_{i}"
                        help_text = "删除此文件（本地+数据库）" if info["type"] != "ghost" else "删除此文件（仅数据库记录）"
                        if st.button("🗑️", key=button_key, help=help_text):
                            st.session_state[f"single_delete_confirm_{i}"] = True
                            st.rerun()
                else:
                    # 普通用户看到的状态信息
                    with col_status:
                        if info["type"] == "imported":
                            st.caption("✅ 可用")
                        elif info["type"] == "ghost":
                            st.caption("⚠️ 仅数据库")
                        else:
                            st.caption("⚠️ 未建库")

                # 单个删除确认对话框（仅管理员可见）
                if is_admin and st.session_state.get(f"single_delete_confirm_{i}", False):
                    with st.container():
                        # 根据文件类型显示不同的确认信息
                        if info["type"] == "imported":
                            confirm_msg = f"⚠️ 确认删除 **{info['name']}**？（将同时删除本地文件和数据库记录）"
                        elif info["type"] == "ghost":
                            confirm_msg = f"⚠️ 确认删除 **{info['name']}**？（仅删除数据库记录，本地文件不存在）"
                        else:  # not_imported
                            confirm_msg = f"⚠️ 确认删除 **{info['name']}**？（仅删除本地文件，数据库无记录）"

                        st.info(confirm_msg)
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ 确认", key=f"single_yes_{i}", type="primary"):
                                try:
                                    # 根据类型执行不同的删除操作
                                    db_deleted = True
                                    local_deleted = True

                                    if info["type"] == "imported":
                                        # 已建库：删除本地文件 + 数据库记录
                                        db_deleted = file_manager_ui.delete_file_by_tag(info["tag"])
                                        local_deleted = file_manager_ui.delete_local_file(info["path"])
                                    elif info["type"] == "ghost":
                                        # 残留数据：只删除数据库记录
                                        db_deleted = file_manager_ui.delete_file_by_tag(info["tag"])
                                        local_deleted = True  # 本地没有文件，跳过
                                    else:  # not_imported
                                        # 未建库：只删除本地文件
                                        local_deleted = file_manager_ui.delete_local_file(info["path"])
                                        db_deleted = True  # 数据库没有记录，跳过

                                    if db_deleted and local_deleted:
                                        st.success(f"✅ 已删除 {info['name']}")
                                    elif db_deleted and not local_deleted:
                                        st.warning(f"⚠️ 数据库记录已删除，但本地文件删除失败")
                                    elif not db_deleted and local_deleted:
                                        st.warning(f"⚠️ 本地文件已删除，但数据库记录删除失败")
                                    else:
                                        st.error(f"❌ 删除失败")

                                    del st.session_state[f"single_delete_confirm_{i}"]
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ 删除失败: {str(e)}")
                        with col_no:
                            if st.button("❌ 取消", key=f"single_no_{i}"):
                                del st.session_state[f"single_delete_confirm_{i}"]
                                st.rerun()
    else:
        st.info("📭 没有找到匹配的文件")

    st.markdown("---")

    # ========== 原有的已导入文件列表（移除，不再需要） ==========

# ========== 主页面内容 ==========
# 根据页面状态显示不同内容
if st.session_state.page == "user_management" and st.session_state.user_role == UserRole.ADMIN:
    # 用户管理页面
    render_user_management()
elif st.session_state.page == "change_password":
    # 修改密码页面
    render_change_password()

# 聊天功能（所有页面都显示）
st.title("💬 智能设计助手")

chat_container = st.container()

with chat_container:
    for message in st.session_state.messages:
        render_message(message["role"], message["content"])

if prompt := st.chat_input("💭 请输入您的问题..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 渲染用户消息（使用气泡样式）
    st.markdown(f"""
        <div class="user-message-container">
            <div class="message-bubble user-bubble">
                {safe_html(prompt)}
            </div>
            <div class="avatar user-avatar">👤</div>
        </div>
    """, unsafe_allow_html=True)

    # 创建助手消息容器
    assistant_container = st.empty()

    # 显示加载状态
    assistant_container.markdown(f"""
        <div class="assistant-message-container">
            <div class="avatar assistant-avatar">🤖</div>
            <div class="message-bubble assistant-bubble">
                <div class="loading-dots">正在思考<span>.</span><span>.</span><span>.</span></div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    try:
        response = st.session_state.chat_agent.step(prompt)
        print(f"Response from chat_agent: {response}")

        full_response = ""
        has_shown_content = False  # 标记是否已显示内容

        # 流式处理响应
        for chunk_response in response:
            if hasattr(chunk_response, 'msgs') and len(chunk_response.msgs) > 0:
                message = chunk_response.msgs[0]
                content_text = message.content
                if content_text:
                    if content_text.startswith(full_response):
                        full_response = content_text
                    else:
                        full_response += content_text

                    # 只有当有实际内容（不只是符号）时才更新UI
                    # 在工具调用期间，content可能为空或只有符号，保持"正在思考"
                    if full_response and len(full_response.strip()) > 0 and not has_shown_content:
                        has_shown_content = True
                        # 第一次有内容时，更新UI - 使用带气泡的渲染
                        render_streaming_content(full_response, assistant_container)
                    elif has_shown_content and full_response:
                        # 已经显示过内容，继续更新
                        render_streaming_content(full_response, assistant_container)

        # 如果没有流式内容，尝试获取完整响应
        if not full_response:
            if hasattr(response, 'msg') and hasattr(response.msg, 'content'):
                full_response = response.msg.content
            elif hasattr(response, 'msgs') and len(response.msgs) > 0:
                full_response = response.msgs[-1].content
            else:
                full_response = "抱歉，我无法生成回复。"

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response
        })

        st.rerun()

    except Exception as e:
        error_message = f"❌ 处理消息时出错：{str(e)}"

        # 渲染错误消息
        safe_error = safe_html(error_message)
        assistant_container.markdown(f"""
            <div class="assistant-message-container">
                <div class="avatar assistant-avatar">🤖</div>
                <div class="message-bubble assistant-bubble">
                    {safe_error}
                </div>
            </div>
        """, unsafe_allow_html=True)

        st.session_state.messages.append({
            "role": "assistant",
            "content": error_message
        })
