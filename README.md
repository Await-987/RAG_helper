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
│   └── storages/                         # Qdrant 向量数据库存储
├── .user/                               # 用户数据目录（隐藏）
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

本项目需要以下本地模型（总大小约 23GB）：

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

> **注意**：首次加载模型需要 10-60 秒，请耐心等待。

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

## 常用命令

```bash
# 清空数据库
python -c "from tools.qdrant import QdrantDB, QdrantDB_Init; db = QdrantDB(input=QdrantDB_Init(collection_name='database')); db.storage_instance._client.delete_collection(collection_name='database')"

# 测试模型响应结构
python test_qwq_response.py

# 测试 MinerU 解析
python tests/tools/test_load_files.py
```
