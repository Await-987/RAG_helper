# 智能设计助手 - RAG系统

基于 CAMEL 框架的检索增强生成（RAG）系统，专为电力系统与国家电网业务场景设计的知识问答智能体。

## 项目结构

```
rag/
├── agents/                              # Agent 模块
│   ├── __init__.py
│   ├── backend_model.py                  # LLM/Embedding 模型配置 + 表格摘要模型
│   └── chat_agent.py                     # 对话 Agent 工厂函数（含系统提示词）
│
├── config/                              # 配置文件
│   └── mineru.json                       # MinerU 解析配置
│
├── data/                                # 数据目录（运行时生成）
│   ├── storages/                         # Qdrant 向量数据库存储
│   ├── stored_files/                     # 上传的 PDF 文件
│   │   └── mineru_output/                 # MinerU 输出（表格/图片）
│   └── content_lists/                    # 文档内容列表缓存（JSON）
│
├── docs/                                # 文档目录
│   ├── bugfix/                           # Bug 修复记录
│   │   └── 2026-01-mineru-discarded-preprocess.md
│   └── changes/                          # 变更日志
│       ├── keyword&vector_hybrid_dynamic_topk_rerank.md
│       ├── table_independent_storage_llm_summary.md
│       └── ...
│
├── models/                              # 本地模型目录（需下载）
│   ├── bge-base-zh-v1.5/                 # Embedding 模型（文本向量化）
│   ├── bge-reranker-base/                # 重排序模型（优化检索结果）
│   ├── mineru/                           # MinerU PDF 解析依赖模型
│   └── Qwen2.5-1.5B-Instruct/            # 表格摘要小模型（LLM 生成表格摘要）
│
├── run/                                 # Streamlit 运行模块
│   ├── .streamlit/
│   │   └── config.toml                   # Streamlit 主题配置
│   ├── config.py                         # UI 布局配置（含 MathJax 公式渲染）
│   └── streamlit.py                      # Streamlit Web 应用主入口
│
├── scripts/                             # 工具脚本
│   ├── batch_import.py                   # 批量导入 PDF 文件
│   └── download_table_summary_model.py   # 下载表格摘要模型
│
├── tests/                               # 测试文件
│   ├── agents/
│   │   ├── test_backend_model.py         # 后端模型测试
│   │   └── test_chat_agent.py            # Agent 测试
│   ├── tools/
│   │   ├── test_load_files.py            # 文件加载测试
│   │   └── test_qdrant.py                # 向量数据库测试
│   ├── smoke_*.py                        # 烟雾测试（端到端）
│   ├── eval_*.py                         # 评估测试
│   └── debug_*.py                        # 调试脚本
│
├── tools/                               # 核心工具模块
│   ├── __init__.py
│   ├── database_toolkit.py               # 数据库工具包（检索/重排序）
│   ├── load_files.py                     # PDF 文件加载、预处理、入库
│   ├── mineru_toolkit.py                 # MinerU PDF 解析封装
│   ├── qdrant.py                         # Qdrant 向量数据库接口（混合检索）
│   ├── file_manager_ui.py                # 文件管理 UI 辅助函数（含图片删除）
│   └── user_auth.py                      # 用户认证和权限管理
│
├── .user/                               # 用户数据目录（隐藏）
│   └── users.json                        # 用户认证数据
│
├── .env                                 # 环境变量配置（需自行创建）
├── .gitignore
├── Dockerfile                            # Docker 部署文件（CPU）
├── Dockerfile.cuda                       # Docker 部署文件（GPU）
├── docker-compose.yml                    # Docker Compose 配置（CPU）
├── docker-compose.gpu.yml                # Docker Compose 配置（GPU）
├── requirements.txt                      # Python 依赖
└── README.md                             # 项目说明文档
```

### 核心模块说明

| 模块 | 文件 | 主要功能 |
|-----|------|---------|
| **Agent** | `agents/chat_agent.py` | 对话智能体，含完整系统提示词 |
| **模型** | `agents/backend_model.py` | Embedding/Reranker/表格摘要模型加载 |
| **入库** | `tools/load_files.py` | PDF解析→图片重命名→预处理→向量存储 |
| **检索** | `tools/qdrant.py` | 混合检索（向量+关键词）+ 重排序 |
| **文件管理** | `tools/file_manager_ui.py` | 文件状态追踪 + 图片联动删除 |
| **前端** | `run/streamlit.py` | Streamlit Web 界面 |

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

创建 `.env` 文件并填写配置：

```env
# OpenAI 兼容 API 配置（用于主对话模型）
OPENAI_API_KEY=your-api-key-here
url=https://your-api-endpoint/v1

# 模型名称（可选，默认 qwq32b）
MODEL_NAME=qwq32b

# 本地模型路径（相对于项目根目录）
conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
```

### 4. 下载模型

本项目需要以下本地模型（总大小约 26GB）：

#### 方式一：从 NAS 下载（推荐）

| 项 | 内容 |
|---|---|
| 下载链接 | https://ug.link/nas-miaohan-sh1/filemgr/share-download/?id=780cb3acf9154a0c9ad7ec099dfd161d |
| 访问密码 | **pdXF** |

下载后解压，将 `models/` 文件夹放到项目根目录下。

#### 模型清单

| 模型目录 | 大小 | 用途 |
|---------|------|------|
| `bge-base-zh-v1.5/` | 391 MB | Embedding 模型（文本向量化） |
| `bge-reranker-base/` | 6.3 GB | 重排序模型（优化检索结果） |
| `mineru/` | 16 GB | MinerU PDF 解析依赖 |
| `Qwen2.5-1.5B-Instruct/` | 3 GB | 表格摘要小模型（LLM 生成表格摘要） |

> **注意**：首次加载模型需要 10-60 秒，请耐心等待。

#### 方式二：单独下载表格摘要模型

如果 NAS 下载的模型包中没有 `Qwen2.5-1.5B-Instruct`，可以单独下载：

**方法 1：使用自动下载脚本（推荐）**

```bash
# 激活虚拟环境
source .venv/bin/activate

# 自动选择最快镜像下载
python scripts/download_table_summary_model.py

# 或指定下载源
python scripts/download_table_summary_model.py --source modelscope   # ModelScope（国内推荐）
python scripts/download_table_summary_model.py --source hf-mirror     # HuggingFace 镜像
python scripts/download_table_summary_model.py --source hf            # HuggingFace 官方
```

**方法 2：手动下载**

| 下载源 | 链接 |
|-------|------|
| ModelScope（国内推荐） | https://modelscope.cn/models/Qwen/Qwen2.5-1.5B-Instruct |
| HuggingFace 镜像 | https://hf-mirror.com/Qwen/Qwen2.5-1.5B-Instruct |
| HuggingFace 官方 | https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct |

下载后，将所有文件放到 `models/Qwen2.5-1.5B-Instruct/` 目录下。

**目录结构示例：**
```
models/
└── Qwen2.5-1.5B-Instruct/
    ├── config.json
    ├── model.safetensors
    ├── tokenizer.json
    ├── tokenizer_config.json
    ├── vocab.json
    └── ... (其他模型文件)
```

**验证模型是否可用：**

```bash
python scripts/download_table_summary_model.py --test-only
```

#### 环境变量配置（可选）

如果模型放在非默认路径，可以在 `.env` 中配置：

```env
# 表格摘要模型路径（默认 models/Qwen2.5-1.5B-Instruct）
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct
```

### 5. 启动服务

```bash
streamlit run run/streamlit.py
```

服务将在浏览器中自动打开，默认地址：`http://localhost:8501`

### 6. Docker 部署

本项目提供完整的 Docker 部署方案，支持数据持久化和卷挂载。

#### 6.1 项目结构（Docker）

```
├── Dockerfile              # 镜像构建文件
├── docker-compose.yml      # Docker Compose 编排配置
├── .dockerignore          # 构建忽略文件
│
├── data/                  # 业务数据（挂载到容器外）
│   ├── storages/          # Qdrant 向量数据库
│   ├── stored_files/      # 上传的文件
│   ├── content_lists/     # 文件列表缓存
│   └── exported_chunks/   # 导出的切块
├── .user/                 # 用户数据（挂载到容器外，隐藏目录）
├── models/                # 本地模型（挂载到容器外）
│   ├── bge-base-zh-v1.5/  # Embedding 模型
│   └── bge-reranker-base/ # Reranker 模型
└── .env                   # 环境配置（挂载到容器外）
```

#### 6.2 使用 Docker Compose（推荐）

**CPU 版本：**

```bash
# 构建镜像
docker-compose build

# 启动服务（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

**GPU 版本（需要 NVIDIA GPU + nvidia-docker）：**

```bash
# 构建镜像
docker-compose -f docker-compose.gpu.yml build

# 启动服务
docker-compose -f docker-compose.gpu.yml up -d

# 查看日志
docker-compose -f docker-compose.gpu.yml logs -f

# 停止服务
docker-compose -f docker-compose.gpu.yml down
```

> **GPU 加速说明**：GPU 版本可将 embedding 和 reranker 速度提升 **10-20 倍**，适合大规模建库场景。

#### 6.3 GPU 支持配置

本项目支持 CUDA 加速，可用于 embedding 和 reranker 模型：

**环境变量配置（.env）：**

```env
# 设备配置（可选，默认自动检测）
EMBEDDING_DEVICE=cuda   # embedding 模型: cuda/cpu/auto
RERANKER_DEVICE=cuda     # reranker 模型: cuda/cpu/auto
```

**性能对比：**

| 操作 | CPU | GPU (CUDA) | 加速比 |
|------|-----|------------|--------|
| 单文本 embedding | 500ms | 50ms | 10x |
| 1000 条文本 | ~8 分钟 | ~50 秒 | 10x |
| 1375 个 PDF 建库 | ~2-3 小时 | ~10-20 分钟 | 10x+ |

**前提条件：**

- NVIDIA GPU（支持 CUDA 11.8+）
- 安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- 验证：`docker run --rm --gpus all nvidia/cuda:12.3.1-base-ubuntu22.04 nvidia-smi`

#### 6.4 Volume 挂载说明

| 宿主机路径 | 容器内路径 | 说明 |
|-----------|-----------|------|
| `./data` | `/app/data` | 业务数据目录 |
| `./.user` | `/app/.user` | 用户认证数据 |
| `./models` | `/app/models` | 本地 ML 模型 |
| `./.env` | `/app/.env` | 环境变量配置 |

> **注意**：数据和模型存储在容器外部，容器删除后数据不会丢失。

#### 6.5 访问应用

启动后浏览器访问：`http://localhost:8501`

#### 6.6 使用 Docker 直接构建

```bash
# 构建镜像
docker build -t rag-chatbot .

# 运行容器
docker run -d \
  -p 8501:8501 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/.user:/app/.user \
  -v $(pwd)/models:/app/models \
  --env-file .env \
  --name rag-chatbot \
  rag-chatbot
```

#### 6.7 数据迁移（如果有旧数据）

如果你有旧版本的 `data/users.json`，需要迁移到新位置：

```bash
# 创建 .user 目录
mkdir -p .user

# 迁移用户数据
mv data/users.json .user/users.json
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
- **公式渲染**：支持 LaTeX 公式（行内 `$...$`，块级 `$$...$$`）

### 5. 图片管理
- **图片绑定文档**：MinerU 提取的图片自动重命名为 `文档名_数字.jpg` 格式
- **联动删除**：删除文档时自动删除关联的所有图片文件
- **避免垃圾累积**：图片与文档一一对应，不会产生孤立图片

### 6. 表格智能处理
- **LLM 表格摘要**：使用本地小模型（Qwen2.5-1.5B-Instruct）为表格生成语义摘要
- **摘要向量化**：表格摘要用于向量检索，- **完整内容返回**：检索到表格时返回完整的表格内容（含图片）给用户
- **上下文关联**：表格 chunk 包含前后 500 字符的上下文信息

## 技术架构

### 图片管理流程

```
┌─────────────────────────────────────────────────────────────┐
│                        入库流程                              │
├─────────────────────────────────────────────────────────────┤
│  PDF文件                                                    │
│     ↓                                                       │
│  MinerU处理 → 生成哈希命名图片 (abc123.jpg)                 │
│     ↓                                                       │
│  rename_images_for_document() → 重命名为 (文档名_1.jpg)     │
│     ↓                                                       │
│  preprocess() → 生成chunks（包含新图片路径）                │
│     ↓                                                       │
│  存入Qdrant（图片路径：mineru_output/文档名_1.jpg）         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                        删除流程                              │
├─────────────────────────────────────────────────────────────┤
│  用户点击删除                                                │
│     ↓                                                       │
│  delete_file_by_tag(file_tag, delete_images=True)          │
│     ├── 删除Qdrant数据库记录                                │
│     └── delete_images_by_document_prefix(文档名)            │
│              ↓                                              │
│         删除所有 "文档名_*.jpg" 图片                         │
└─────────────────────────────────────────────────────────────┘
```

**图片命名规则：**

| 原名称 (哈希) | 新名称 (文档绑定) |
|--------------|-----------------|
| `abc123...jpg` | `文档名_1.jpg` |
| `def456...jpg` | `文档名_2.jpg` |

**相关文件：**
- `tools/load_files.py` - `rename_images_for_document()` 图片重命名
- `tools/file_manager_ui.py` - `delete_images_by_document_prefix()` 图片删除

### 表格处理流程

```
┌─────────────────────────────────────────────────────────────┐
│                      表格入库流程                          │
├─────────────────────────────────────────────────────────────┤
│  MinerU提取表格                                              │
│     ↓                                                       │
│  extract_table_content() → 提取表格内容（标题+正文+脚注）    │
│     ↓                                                       │
│  generate_table_summary() → LLM生成200字语义摘要            │
│     ↓                                                       │
│  创建表格chunk:                                              │
│    ├── child: LLM摘要（用于向量化检索）                      │
│    ├── parent: 完整表格内容（返回给用户）                    │
│    └── context: 前后500字符上下文                          │
│     ↓                                                       │
│  存入Qdrant（is_table=True 标记）                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      表格检索流程                          │
├─────────────────────────────────────────────────────────────┤
│  用户查询                                                    │
│     ↓                                                       │
│  向量检索（使用 LLM 摘要匹配）                              │
│     ↓                                                       │
│  返回完整表格内容（parent）给 LLM                           │
│     ↓                                                       │
│  LLM 基于完整表格内容回答用户问题                          │
└─────────────────────────────────────────────────────────────┘
```

**表格处理优势：**
- **语义检索**：LLM 摘要捕捉表格语义，提高检索准确率
- **完整返回**：用户看到完整表格（含图片），信息不丢失
- **上下文关联**：表格前后文帮助理解表格用途

**相关配置：**
- `use_llm_summary=True` - 启用 LLM 表格摘要（默认开启）
- `context_size=500` - 上下文窗口大小（字符数）

## 常用命令

```bash
# 清空数据库
python -c "from tools.qdrant import QdrantDB, QdrantDB_Init; db = QdrantDB(input=QdrantDB_Init(collection_name='database')); db.storage_instance._client.delete_collection(collection_name='database')"

# 测试模型响应结构
python test_qwq_response.py

# 测试 MinerU 解析
python tests/tools/test_load_files.py
```
