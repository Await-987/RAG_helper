# RAG 项目前端重写方案（参考 LibreChat 设计）

> 目标：参考 LibreChat 的成熟 UI 设计，在现有 React 19 + Zustand + Tailwind 技术栈上重写前端，同时优化后端 SSE 格式。后端核心逻辑完全不动。

---

## 一、为什么要重写

当前前端功能可用但 UI 简陋，主要问题：
- 侧边栏只有简单的会话列表，无可折叠/搜索功能
- 消息渲染缺少代码高亮、来源引用等关键功能
- 无主题切换、无欢迎页、无消息操作按钮
- 输入框功能单一，无自动调整、无快捷键提示

LibreChat 的 UI 模式值得参考：
- 左侧可折叠侧边栏 + 右侧内容区的主布局
- 丰富的消息渲染（Markdown + LaTeX + 代码高亮 + 图片）
- 智能输入框（自动调整、快捷键、停止按钮）
- 暗色/亮色主题切换

---

## 二、技术栈（不变）

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19 | UI 框架 |
| TypeScript | 5.9 | 类型安全 |
| Vite | 7 | 构建工具 |
| Zustand | 5 | 状态管理 |
| Tailwind CSS | 4 | 样式 |
| react-markdown | 10 | Markdown 渲染 |
| KaTeX | 通过 rehype-katex | 数学公式 |
| Lucide React | 0.577 | 图标 |

**新增依赖：**

| 包名 | 用途 |
|------|------|
| `react-syntax-highlighter` | 代码块语法高亮 |
| `react-virtuoso` | 长消息列表虚拟滚动 |

---

## 三、后端 SSE 格式改造

### 3.1 旧格式 vs 新格式

**旧格式**（自定义事件类型）：
```
event: session
data: {"session_id": "xxx"}

event: reasoning
data: {"content": "思考片段..."}

event: content
data: {"content": "正文片段..."}

event: done
data: {"content": "...", "reasoning": "...", "blocks": [...], "session_id": "xxx"}

event: error
data: {"message": "错误信息"}
```

**新格式**（统一 `event: message`，用 `type` 字段区分）：
```
event: message
data: {"type": "session", "session_id": "abc-123"}

event: message
data: {"type": "reasoning", "content": "让我分析这个问题..."}

event: message
data: {"type": "content", "content": "根据《电力系统规范》"}

event: message
data: {"type": "done", "session_id": "abc-123", "content": "完整回复", "reasoning": "完整思考", "blocks": [{"type": "markdown", "content": "..."}, {"type": "table", "content": "..."}], "reasoning_blocks": [...], "sources": ["文件A.pdf", "文件B.pdf"]}

event: error
data: {"type": "error", "message": "错误信息"}
```

### 3.2 新格式优势

1. **前端解析更简单**：所有业务事件都走 `event: message`，只看 `type` 字段
2. **向后兼容**：`error` 事件保持独立
3. **新增 `sources` 字段**：`done` 事件中包含知识库来源文件列表，前端直接展示
4. **blocks 结构不变**：`markdown`、`table`、`math`、`code` 四种类型保持不变

### 3.3 完整请求/响应示例

**请求：**
```
POST /api/v1/chat/stream
Content-Type: application/json
Authorization: Bearer eyJ...

{
  "message": "电力变压器的短路阻抗是多少？",
  "session_id": null
}
```

**响应（SSE 流）：**
```
event: message
data: {"type": "session", "session_id": "f47ac10b-58cc"}

event: message
data: {"type": "reasoning", "content": "用户询问变压器短路阻抗参数，这是事实性问题..."}

event: message
data: {"type": "reasoning", "content": "检索关键词：变压器 短路阻抗 标准值..."}

event: message
data: {"type": "content", "content": "根据《电力变压器 第1部分：总则》GB/T 1094.1，"}

event: message
data: {"type": "content", "content": "电力变压器的短路阻抗标准值如下：\n\n"}

event: message
data: {"type": "content", "content": "| 额定容量 (kVA) | 短路阻抗 (%) |\n|---|---|\n| ≤630 | 4.0 |\n| 631~1250 | 5.0 |\n\n"}

event: message
data: {"type": "content", "content": "短路阻抗计算公式：$$Z_k = \\frac{U_k}{U_N} \\times 100\\%$$\n\n"}

event: message
data: {"type": "content", "content": "![测试接线图](/api/v1/files/content/stored_files/mineru_output/circuit.png)\n\n"}

event: message
data: {"type": "content", "content": "**来源**：GB/T 1094.1-2013 电力变压器 第1部分：总则"}

event: message
data: {"type": "done", "session_id": "f47ac10b-58cc", "content": "根据《电力变压器...》...(完整内容)", "reasoning": "用户询问...(完整思考)", "blocks": [{"type": "markdown", "content": "根据..."}, {"type": "table", "content": "| 额定容量..."}, {"type": "math", "content": "Z_k = \\frac..."}, {"type": "markdown", "content": "![测试接线图]..."}], "reasoning_blocks": [{"type": "markdown", "content": "用户询问..."}], "sources": ["GB/T 1094.1-2013.pdf", "变压器技术手册.pdf"]}
```

### 3.4 后端改动点

**文件：`backend/app/services/chat_service.py`**

修改 `_format_sse` 方法：
```python
# 旧方法（保留为 legacy）
def _format_sse(self, event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

# 新方法
def _format_message_sse(self, msg_type: str, data: dict) -> str:
    payload = {"type": msg_type, **data}
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

def _format_error_sse(self, message: str) -> str:
    return f"event: error\ndata: {json.dumps({'type': 'error', 'message': message}, ensure_ascii=False)}\n\n"
```

修改 `stream_chat` 中的 yield 语句：
```python
# 旧：yield self._format_sse("session", {"session_id": session_id})
# 新：
yield self._format_message_sse("session", {"session_id": session_id})

# 旧：yield self._format_sse("reasoning", {"content": reasoning_text})
# 新：
yield self._format_message_sse("reasoning", {"content": reasoning_text})

# 旧：yield self._format_sse("content", {"content": content_text})
# 新：
yield self._format_message_sse("content", {"content": content_text})

# 旧：yield self._format_sse("done", {...})
# 新：增加 sources 字段
yield self._format_message_sse("done", {
    "session_id": session_id,
    "content": full_response,
    "reasoning": full_reasoning,
    "blocks": response_blocks,
    "reasoning_blocks": reasoning_blocks,
    "sources": self._extract_sources(full_response),  # 新增
})

# 旧：yield self._format_sse("error", {"message": str(e)})
# 新：
yield self._format_error_sse(str(e))
```

新增 `sources` 提取方法：
```python
def _extract_sources(self, content: str) -> List[str]:
    """从回复内容中提取来源文件名"""
    # 从 content 中匹配 Markdown 图片或文件引用
    sources = set()
    for match in re.finditer(r'来源[：:]\s*(.+?)(?:\n|$)', content):
        for src in match.group(1).split('、'):
            src = src.strip().strip('《》')
            if src:
                sources.add(src)
    return list(sources)
```

---

## 四、前端目录结构

```
frontend/src/
├── main.tsx                      # 入口
├── App.tsx                       # 路由配置
├── index.css                     # 全局样式 + 主题变量
│
├── api/
│   ├── client.ts                 # axios 实例（保留）
│   ├── auth.ts                   # 认证 API（保留）
│   ├── chat.ts                   # 聊天 API（重写 SSE 解析）
│   ├── files.ts                  # 文件 API（保留）
│   └── users.ts                  # 用户 API（保留）
│
├── stores/
│   ├── authStore.ts              # 认证状态（保留）
│   ├── chatStore.ts              # 聊天状态（重写）
│   └── uiStore.ts                # UI 状态（新增）
│
├── types/
│   ├── chat.ts                   # 聊天类型（重写）
│   └── ...                       # 其他类型保留
│
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx         # 主布局：可折叠侧边栏 + 内容区
│   │   ├── Sidebar.tsx           # 侧边栏（新建对话 + 搜索 + 会话列表）
│   │   └── Header.tsx            # 顶部栏（当前页面标题 + 操作）
│   │
│   ├── chat/
│   │   ├── ChatView.tsx          # 聊天主容器（消息列表 + 输入框）
│   │   ├── MessageList.tsx       # 消息列表（自动滚动到底部）
│   │   ├── MessageItem.tsx       # 单条消息（头像 + 内容 + hover 操作）
│   │   ├── MessageContent.tsx    # 消息内容（markdown/表格/公式/图片/代码）
│   │   ├── ReasoningBlock.tsx    # 思考过程（折叠/展开）
│   │   ├── SourceCitation.tsx    # 来源引用标签
│   │   ├── CodeBlock.tsx         # 代码块（语法高亮 + 复制按钮）
│   │   ├── ChatInput.tsx         # 输入框（自动调整 + Enter 发送 + 停止按钮）
│   │   └── WelcomeScreen.tsx     # 空对话欢迎页
│   │
│   ├── files/
│   │   ├── FileManager.tsx       # 文件管理主组件
│   │   ├── FileList.tsx          # 文件表格
│   │   ├── FileUploader.tsx      # 拖拽上传区域
│   │   ├── ImportProgress.tsx    # 导入进度浮层
│   │   ├── FileStatusBadge.tsx   # 文件状态标签
│   │   └── StatsCards.tsx        # 统计卡片
│   │
│   └── ui/
│       ├── Button.tsx            # 按钮组件
│       ├── Modal.tsx             # 弹窗组件
│       ├── Toast.tsx             # 通知提示
│       └── ThemeToggle.tsx       # 主题切换
│
└── pages/
    ├── ChatPage.tsx              # 聊天页
    ├── LoginPage.tsx             # 登录页
    ├── FileManagerPage.tsx       # 文件管理页
    ├── UserManagementPage.tsx    # 用户管理页
    └── ChangePasswordPage.tsx    # 修改密码页
```

---

## 五、每个组件的设计（参考 LibreChat 模式）

### 5.1 AppLayout — 主布局

参考 LibreChat 的 Root.tsx 布局模式：
```
┌──────────────────────────────────────────────────┐
│ ┌──────────┐ ┌────────────────────────────────┐  │
│ │          │ │          Header                 │  │
│ │          │ ├────────────────────────────────┤  │
│ │ Sidebar  │ │                                │  │
│ │ (260px)  │ │        Content Area            │  │
│ │          │ │                                │  │
│ │          │ │                                │  │
│ │          │ ├────────────────────────────────┤  │
│ │          │ │       ChatInput (固定底部)      │  │
│ └──────────┘ └────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

- 侧边栏可折叠（移动端覆盖式，桌面端推拉式）
- 内容区占满剩余空间
- 移动端通过汉堡菜单切换侧边栏

### 5.2 Sidebar — 侧边栏

参考 LibreChat 的 UnifiedSidebar 模式：
```
┌──────────────────┐
│  [+ 新建对话]     │ ← 按钮
│──────────────────│
│  🔍 搜索对话...   │ ← 搜索框
│──────────────────│
│  今天的对话        │ ← 时间分组
│   ├ 对话标题1      │
│   └ 对话标题2      │
│  昨天的对话        │
│   ├ 对话标题3      │
│   └ 对话标题4      │
│──────────────────│
│  📁 文件管理       │ ← 导航链接
│  👥 用户管理       │ ← 仅管理员可见
│──────────────────│
│  👤 用户名 ▾       │ ← 底部用户信息
│     修改密码        │
│     退出登录        │
└──────────────────┘
```

- 会话项 hover 显示删除按钮
- 当前会话高亮
- 搜索实时过滤
- 移动端点击会话后自动关闭侧边栏

### 5.3 ChatView — 聊天主视图

参考 LibreChat 的 ChatView.tsx：
- 无会话时显示 WelcomeScreen
- 有会话时显示 MessageList + ChatInput
- 消息列表自动滚动到底部（流式输出时）
- 顶部显示会话标题

### 5.4 MessageItem — 单条消息

参考 LibreChat 的 Message.tsx：
```
┌─────────────────────────────────────────┐
│  🤖  AI                                 │
│  ─────────────────────────────────────  │
│  💭 思考过程 (点击展开)                  │ ← 折叠
│  ─────────────────────────────────────  │
│  根据《电力系统规范》，该参数...          │ ← 正文
│                                          │
│  | 参数 | 值 |                           │ ← 表格
│  |---|---|                              │
│  | A   | 1  |                           │
│                                          │
│  $$Z = \frac{U}{I}$$                    │ ← 公式
│                                          │
│  📎 来源: 文件A.pdf  文件B.pdf           │ ← 来源标签
│  ─────────────────────────────────────  │
│  [复制] [重新生成]              hover 显示 │ ← 操作按钮
└─────────────────────────────────────────┘

用户消息：
┌─────────────────────────────────────────┐
│                              👤 用户名   │
│  ─────────────────────────────────────  │
│  短路阻抗是多少？                        │
│  ─────────────────────────────────────  │
│                              [复制]      │
└─────────────────────────────────────────┘
```

### 5.5 MessageContent — 消息内容渲染

基于现有 ChatContent.tsx 增强：
- Markdown 文本：react-markdown + remark-gfm
- 数学公式：remark-math + rehype-katex
- 代码块：react-syntax-highlighter（新增语法高亮 + 复制按钮）
- 表格：Tailwind 排版样式
- 图片：带鉴权的图片加载（保留 AuthenticatedImage 逻辑）
- 来源引用：从 `sources` 字段渲染标签

### 5.6 ReasoningBlock — 思考过程

参考 LibreChat 的 reasoning 展示：
- 默认折叠，点击 `<details>` 展开
- 显示思考图标 💭
- 思考内容支持 Markdown 渲染
- 流式输出时自动展开

### 5.7 ChatInput — 输入框

参考 LibreChat 的 ChatForm.tsx：
```
┌─────────────────────────────────────────┐
│  输入消息... (Shift+Enter 换行)          │
│                                          │
│                           [停止] / [发送] │
└─────────────────────────────────────────┘
```

- 自动调整高度（最小 1 行，最大 6 行）
- Enter 发送，Shift+Enter 换行
- 流式输出时显示"停止生成"按钮
- 空消息禁用发送
- 加载状态时禁用输入

### 5.8 WelcomeScreen — 欢迎页

参考 LibreChat 的 Landing.tsx：
```
┌─────────────────────────────────────────┐
│                                          │
│             ⚡ 智能知识库助手              │
│                                          │
│      基于文档的专业问答系统               │
│      支持 PDF 解析、表格提取、公式识别     │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  输入您的问题...                   │   │
│  │                          [发送] → │   │
│  └──────────────────────────────────┘   │
│                                          │
│  💡 试试问:                              │
│  "变压器短路阻抗标准值是多少？"          │
│  "电力线路保护配置有哪些要求？"          │
│                                          │
└─────────────────────────────────────────┘
```

### 5.9 FileManager — 文件管理

参考当前 FileManagerPage 功能 + LibreChat 文件 UI 模式：
```
┌─────────────────────────────────────────┐
│  📊 本地文件: 12  已建库: 8  未建库: 3  残留: 1 │ ← 统计卡片
│──────────────────────────────────────────│
│  [上传文件] [批量导入]  🔍 搜索  筛选▾    │ ← 操作栏
│──────────────────────────────────────────│
│  ☐ 文件名          状态     chunk数  操作 │
│  ☐ 变压器规范.pdf  🟢已建库   45    [预览][删除] │
│  ☐ 线路保护.pdf    🟡未建库   -     [导入][删除] │
│  ☐ 旧报告.pdf      🔴残留     3     [清理]       │
│──────────────────────────────────────────│
│  导入中: 变压器规范.pdf ██████░░ 75%     │ ← 进度浮层
└─────────────────────────────────────────┘
```

### 5.10 主题系统

参考 LibreChat 的暗色/亮色主题：

**暗色主题（默认）：**
- 背景：#0d0d0d（深黑）
- 侧边栏：#171717
- 消息气泡：#2f2f2f
- 输入框：#212121
- 文字：#ececec

**亮色主题：**
- 背景：#ffffff
- 侧边栏：#f9f9f9
- 消息气泡：#f7f7f8
- 输入框：#ffffff
- 文字：#212121

通过 CSS 变量 + Tailwind `dark:` 类实现切换。

---

## 六、必须保留的自定义功能

| 功能 | 说明 | 涉及组件 |
|------|------|---------|
| SSE 流式输出 | reasoning + content 增量推送 | ChatView, chatStore |
| 思考过程展示 | 折叠展示 AI 推理过程 | ReasoningBlock |
| 内容分块渲染 | markdown/table/math/code 四种 block | MessageContent |
| 来源引用 | 回答底部展示知识库来源文件 | SourceCitation |
| 会话持久化 | 列表/切换/删除/重命名 | Sidebar, chatStore |
| MinerU 文件导入 | 三模式选择 + 进度跟踪 | FileManager, ImportProgress |
| 文件状态跟踪 | imported/not_imported/ghost | FileStatusBadge |
| 管理员文件操作 | 上传/导入/删除（仅管理员） | FileManager |
| 用户管理 CRUD | 创建/删除/角色/密码重置 | UserManagementPage |
| 密码管理 | 修改密码/重置密码 | ChangePasswordPage |

---

## 七、chatStore 状态设计（重写）

```typescript
interface ChatState {
  // 当前会话
  sessionId: string | null;
  messages: ChatMessage[];

  // 流式状态
  isStreaming: boolean;
  streamingContent: string;
  streamingReasoning: string;
  abortController: AbortController | null;

  // 会话列表
  sessions: SessionInfo[];

  // 操作
  sendMessage: (message: string) => Promise<void>;
  stopStreaming: () => void;
  loadSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  createNewChat: () => void;
  loadSessions: () => Promise<void>;
}
```

---

## 八、实施步骤

### 步骤 1：后端 SSE 格式改造
- 修改 `chat_service.py` 的 SSE 格式方法
- 新增 `_extract_sources` 方法
- 测试新格式输出

### 步骤 2：前端基础框架
- 安装新依赖（react-syntax-highlighter, react-virtuoso）
- 创建 uiStore（主题/侧边栏状态）
- 创建 AppLayout + Sidebar + Header
- 更新路由配置
- 实现暗色/亮色主题 CSS 变量

### 步骤 3：聊天页面重写
- 重写 chatStore（新 SSE 格式解析 + 会话管理）
- 创建 WelcomeScreen
- 创建 ChatView + MessageList + MessageItem
- 创建 MessageContent（markdown/table/math/code 渲染）
- 创建 ReasoningBlock（折叠展示）
- 创建 SourceCitation（来源标签）
- 创建 ChatInput（自动调整 + 快捷键 + 停止按钮）
- 创建 CodeBlock（语法高亮）

### 步骤 4：文件管理重写
- 创建 StatsCards
- 创建 FileStatusBadge
- 创建 FileUploader（拖拽上传）
- 创建 ImportProgress
- 重写 FileManagerPage

### 步骤 5：其他页面
- 重写 LoginPage（参考 LibreChat 登录页设计）
- 重写 UserManagementPage
- 重写 ChangePasswordPage

### 步骤 6：测试与部署
- 全功能测试
- 移动端适配测试
- 更新 Docker 配置

---

## 九、验证清单

- [ ] 登录/登出
- [ ] 新建对话
- [ ] 发送消息 + SSE 流式回复
- [ ] 思考过程折叠/展开
- [ ] Markdown 渲染（标题、列表、链接）
- [ ] 表格渲染
- [ ] 数学公式渲染（LaTeX）
- [ ] 代码块渲染（语法高亮 + 复制）
- [ ] 图片渲染（带鉴权）
- [ ] 来源引用标签
- [ ] 会话列表/切换/删除
- [ ] 文件上传（拖拽）
- [ ] 文件导入 + 进度
- [ ] 文件状态标签
- [ ] 用户管理（管理员）
- [ ] 主题切换（暗色/亮色）
- [ ] 移动端响应式
