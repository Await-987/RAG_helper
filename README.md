# 智能设计助手 - RAG系统

基于 CAMEL 框架的检索增强生成（RAG）系统，专为电力系统与国家电网业务场景设计的知识问答智能体。

## 项目结构

```
run/
├── agents/                              # Agent 模块
│   ├── __init__.py
│   ├── backend_model.py                  # LLM/Embedding 模型配置
│   └── chat_agent.py                     # 对话 Agent 工厂函数
│
├── config/                              # 配置文件
│   └── mineru.json                       # MinerU 解析配置
│
├── data/                                # 数据目录
│   ├── stored_files/                     # 本地 PDF 文件存储
│   │   └── mineru_output/                # MinerU 输出（表格/图片）
│   ├── content_lists/                    # 文档内容列表缓存
│   ├── exported_chunks/                  # 导出的切片数据
│   ├── storages/                         # 旧版存储目录
│   └── users.json                        # 用户认证数据
│
├── docs/                                # 文档目录
│   ├── bugfix/                           # Bug 修复记录
│   └── changes/                          # 变更日志
│
├── logs/                                # 日志目录
│   └── qwq_response_test_*.log           # 模型测试日志
│
├── models/                              # 模型文件
│   ├── bge-base-zh-v1.5/                 # Embedding 模型
│   ├── bge-reranker-base/                # 重排序模型
│   └── mineru/                           # MinerU 依赖模型
│
├── new_tools/                           # 旧版工具目录（待清理）
│
├── run/                                 # Streamlit 运行模块
│   ├── .streamlit/
│   │   └── config.toml                   # Streamlit 主题配置
│   ├── config.py                         # UI 布局配置
│   └── streamlit.py                      # Streamlit Web 应用
│
├── tests/                               # 测试文件
│   ├── agents/
│   │   ├── test_backend_model.py         # 后端模型测试
│   │   └── test_chat_agent.py            # Agent 测试
│   ├── tools/
│   │   ├── test_load_files.py            # 文件加载测试
│   │   └── test_qdrant.py                # 向量数据库测试
│   └── test_model_think.py               # QwQ 模型思考测试
│
├── tools/                               # 工具模块
│   ├── __init__.py
│   ├── database_toolkit.py               # 数据库工具包（检索/重排序）
│   ├── load_files.py                     # PDF 文件加载和处理
│   ├── mineru_toolkit.py                 # MinerU PDF 解析工具
│   ├── qdrant.py                         # Qdrant 向量数据库接口
│   ├── file_manager_ui.py                # 文件管理 UI 辅助函数
│   └── user_auth.py                      # 用户认证和权限管理
│
├── .env                                 # 环境变量配置（需自行创建）
├── .gitignore
├── Dockerfile                            # Docker 部署文件
├── requirements.txt                      # Python 依赖
├── test_qwq_response.py                  # QwQ-32B 响应结构测试
└── README.md                             # 项目说明文档
```

## Quick Start

### 1. 环境准备

**系统要求：**
- Python 3.10+
- 建议使用虚拟环境

**创建虚拟环境：**

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括：
- `camel-ai` - CAMEL AI 框架
- `mineru` - PDF 文档解析工具（v2.7.1）
- `streamlit` - Web 界面
- `qdrant-client` - 向量数据库客户端
- `python-dotenv` - 环境变量管理
- `openai` - OpenAI 兼容 API 接口

### 3. 配置环境变量

创建 `.env` 文件并填写 API 配置：

```env
# OpenAI 兼容 API 配置（用于主对话模型）
OPENAI_API_KEY=your-api-key-here
url=https://your-api-endpoint/v1

# Qwen API 配置（用于 Embedding 和 OCR）
QWEN_API_KEY=your-qwen-api-key-here
url_qwen=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 4. 启动服务

```bash
streamlit run run/streamlit.py
```

服务将在浏览器中自动打开，默认地址：`http://localhost:8501`

### 5. Docker 部署

本项目提供 Dockerfile 支持离线部署：

```bash
docker build -t rag-assistant .
docker run -p 8501:8501 rag-assistant
```

## 功能特色

### 1. 文档管理
- **拖拽上传**：支持批量上传 PDF 文件
- **自动解析**：使用 MinerU 提取文本、表格、公式、图片
- **增量建库**：自动向量化存储到 Qdrant 数据库
- **文件状态**：
  - ✅ 已建库（本地有文件 + 数据库有记录）
  - ⚠️ 未建库（本地有文件 + 数据库无记录）
  - 👻 残留数据（本地无文件 + 数据库有记录）

### 2. 智能检索
- **混合检索**：关键词 + 向量混合搜索
- **动态 Top-K**：根据查询复杂度调整返回数量
- **重排序**：使用 BGE-Reranker 优化结果
- **表格支持**：智能处理多标题表格和 LaTeX 公式

### 3. 用户权限
- **角色管理**：管理员 / 普通用户
- **权限控制**：
  - 管理员：上传、删除、用户管理
  - 普通用户：聊天和查看文件
- **默认账户**：admin / admin123

### 4. 对话功能
- **思考过程显示**：支持 QwQ-32B 等推理模型
- **表格渲染**：正确显示 Markdown 表格
- **图片展示**：支持文档中提取的图片显示

## 常用命令

```bash
# 清空数据库
python -c "from tools.qdrant import QdrantDB, QdrantDB_Init; db = QdrantDB(input=QdrantDB_Init(collection_name='database')); db.storage_instance._client.delete_collection(collection_name='database')"

# 测试模型响应结构
python test_qwq_response.py

# 测试 MinerU 解析
python tests/tools/test_load_files.py
```
