# 智能设计助手 RAG 项目

面向电网工程设计、建设管理、规范检索和技术资料问答的本地化 RAG 系统。项目采用前后端分离架构，使用 FastAPI 提供鉴权、文件入库、RAG 检索、流式问答和知识图谱接口，使用 React + Vite 提供聊天、文件管理、用户管理和知识图谱可视化页面，使用 Qdrant 持久化向量库，使用 Redis 管理会话索引。

本 README 是项目唯一维护入口，覆盖开发、部署、目录结构、环境变量、数据管理、API、常用脚本和排障。项目内旧的分散 README 已合并到本文档。

## 目录

- [项目能力](#项目能力)
- [整体架构](#整体架构)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [运行数据和 Git 管理](#运行数据和-git-管理)
- [环境要求](#环境要求)
- [环境变量](#环境变量)
- [Docker 部署](#docker-部署)
- [本地开发启动](#本地开发启动)
- [首次使用流程](#首次使用流程)
- [前端功能](#前端功能)
- [后端 API](#后端-api)
- [知识库入库与检索流程](#知识库入库与检索流程)
- [知识图谱](#知识图谱)
- [常用脚本](#常用脚本)
- [测试和验证](#测试和验证)
- [运维和排障](#运维和排障)
- [安全注意事项](#安全注意事项)

## 项目能力

### 已实现能力

- 用户登录、JWT 鉴权、管理员和普通用户角色控制。
- 多轮聊天，支持 SSE 流式输出。
- 模型 reasoning 内容透传和前端折叠展示。
- 上传 PDF、DOC、DOCX、TXT、MD 文件。
- 管理员触发文件入库，后台任务跟踪导入状态。
- 使用 MinerU 解析 PDF，提取正文、图片、表格、公式等内容。
- 文档切块后写入 Qdrant collection。
- 支持向量检索、词汇索引和混合检索。
- 支持 reranker 对召回片段重排。
- 支持表格独立切块和本地表格摘要模型。
- 文件管理页展示 imported、not_imported、ghost 三类状态。
- 聊天会话列表、会话详情和删除会话。
- 会话索引写入 Redis，完整 transcript 落盘。
- Agent memory 和长对话 compact。
- 外部 RAG API，可用 API Key 直接查询或纯检索。
- 知识图谱 JSON 接口、统计接口、预览图接口和子图接口。
- 前端知识图谱页面，使用 G6 可视化。
- Docker Compose 一键启动 web、backend、qdrant、redis。

### 适用场景

- 电网设计规范问答。
- 国网基建、技经、环保、施工、验收、安全等资料检索。
- 大批量规范 PDF 的解析和结构化入库。
- 将 RAG 能力作为外部系统的检索/问答服务。
- 从 Qdrant 片段抽取实体关系并展示知识图谱。

## 整体架构

当前主线是四服务架构：

```text
Browser
  |
  | http://127.0.0.1:8080
  v
web: Nginx + React 静态资源
  |
  | /api/*
  v
backend: FastAPI
  |
  +-- qdrant:6333
  |     向量、payload、collection 持久化
  |
  +-- redis:6379
  |     会话列表、标题、消息数、更新时间
  |
  +-- models/
  |     embedding、reranker、table summary 模型
  |
  +-- data/
  |     上传文件、MinerU 输出、内容列表、索引缓存、会话文件、知识图谱
  |
  +-- .user/
        用户账号文件
```

### 状态分层

项目状态分为三层：

1. 服务持久化层
   - `data/qdrant/`：Qdrant Server 存储。
   - `data/redis/`：Redis AOF/RDB 数据。

2. 文件持久化层
   - `data/stored_files/`：上传原始文件。
   - `data/stored_files/mineru_output/`：MinerU 生成图片、表格截图、公式截图等。
   - `data/content_lists/`：MinerU 内容列表。
   - `data/lex_index/`：词汇索引和文件级统计缓存。
   - `data/agent_memory/`：Agent memory 快照。
   - `data/chat_sessions/`：完整聊天 transcript。
   - `data/knowledge_graph/`：知识图谱 JSON 和预览图。

3. 进程运行态
   - backend 内存中的 ChatAgent。
   - backend 模型缓存。
   - 后台文件导入任务状态。

因此生产部署仍建议 `BACKEND_WORKERS=1`。虽然 Redis 已经保存会话索引，但 ChatAgent 执行态和模型缓存还不是完全无状态。

## 技术栈

### 前端

- React 19
- TypeScript
- Vite 7
- React Router 7
- Zustand
- Axios
- Tailwind CSS 4
- Radix UI
- lucide-react
- react-markdown、remark-gfm、remark-math、rehype-katex、rehype-raw
- react-virtuoso
- AntV G6
- sonner

### 后端

- Python 3.10
- FastAPI
- Uvicorn
- Pydantic settings
- CAMEL AI
- OpenAI-compatible LLM API
- SentenceTransformer embedding
- CrossEncoder reranker
- Transformers 表格摘要模型
- MinerU 文档解析
- Qdrant Client
- Redis

### 部署

- Docker Compose
- Nginx
- Qdrant
- Redis
- NVIDIA Container Runtime，按需使用 GPU

## 目录结构

```text
rag/
├── backend/                         # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/                  # auth、chat、files、users、rag、knowledge_graph 路由
│   │   ├── core/                    # 安全、Redis、Agent、模型运行时、文件目录
│   │   ├── schemas/                 # Pydantic schema
│   │   ├── services/                # auth/chat/file/user 服务
│   │   ├── config.py                # 环境变量和设置
│   │   ├── dependencies.py          # 依赖注入、启动预热、资源清理
│   │   └── main.py                  # FastAPI 应用入口
│   ├── tests/
│   ├── requirements.txt
│   └── run.py
│
├── frontend/                        # React + Vite 前端
│   ├── src/
│   │   ├── api/                     # API client
│   │   ├── components/              # 布局、聊天、UI、命令面板
│   │   ├── pages/                   # Chat、Files、Users、KnowledgeGraph 等页面
│   │   ├── stores/                  # auth/chat/ui 状态
│   │   ├── types/                   # TS 类型
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
│
├── tools/                           # RAG 核心工具链
│   ├── load_files.py                # 文件解析、切块、入库
│   ├── mineru_toolkit.py            # MinerU 封装
│   ├── qdrant.py                    # Qdrant 读写、检索、混合检索
│   ├── database_toolkit.py          # Agent 检索工具
│   ├── file_stats.py                # 文件级 chunk 统计
│   ├── kg_extractor.py              # 知识图谱抽取
│   ├── kg_layout.py                 # 知识图谱布局预计算
│   └── user_auth.py                 # 用户文件和权限管理
│
├── scripts/                         # 运维、导入、测试、审计脚本
├── config/                          # MinerU 和系统提示词配置
│   ├── mineru.json
│   ├── mineru.resolved.json
│   └── prompts/main_agent_system.txt
│
├── deploy/nginx/default.conf        # 前端 Nginx 和 API 反向代理配置
├── docs/                            # 设计说明、变更记录和规划文档
├── data/                            # 运行数据，默认不提交
├── models/                          # 本地模型，默认不提交
├── .user/                           # 用户账号文件，默认不提交
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── storage_paths.py                 # 共享存储路径统一入口
├── requirements.txt
└── README.md
```

## 运行数据和 Git 管理

项目源码、配置模板、脚本、Dockerfile、Compose 文件应提交到 GitHub。运行时数据、模型、上传文件、向量库、缓存和本地报告不应提交。

### 默认忽略的关键目录

```text
.env
.user/
.venv/
frontend/node_modules/
frontend/dist/
models/
data/stored_files/*.pdf
data/stored_files_classified/
data/content_lists/
data/knowledge_graph/
data/lex_index/
data/qdrant/
data/redis/
data/agent_memory/
data/chat_sessions/
data/scripts/
reports/
technical_report_latex/
word_output/
```

### 需要提交的关键文件

```text
README.md
docker-compose.yml
Dockerfile.backend
Dockerfile.frontend
deploy/nginx/default.conf
requirements.txt
backend/requirements.txt
backend/app/**
frontend/src/**
frontend/package.json
frontend/package-lock.json
tools/**
scripts/**
config/**
storage_paths.py
docs/**
```

`data/storages/.gitkeep` 是为了保留历史 local Qdrant 目录占位，可以提交。

## 环境要求

### Docker 部署

- Linux
- Docker Engine
- Docker Compose v2
- 可选：NVIDIA Driver + NVIDIA Container Toolkit
- 建议磁盘空间：
  - 代码和镜像：10GB+
  - 模型：20GB+
  - 知识库 PDF 和 Qdrant：按资料规模预留，当前项目数据可能达到几十 GB

### 本地开发

- Python 3.10
- Node.js 22，或满足 Vite 要求的 Node.js 20.19+
- npm
- Redis，可选
- Qdrant，可选
- 推荐 Linux 或 WSL2

## 环境变量

项目从根目录 `.env` 读取配置。`.env` 不提交 Git。

### 最小 `.env` 示例

```bash
# 安全配置
SECRET_KEY=请替换为足够长的随机字符串
AUTH_INSTANCE_ID=local-dev

# 首次启动时创建管理员。只在 .user/users.json 不存在时生效。
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=请替换为至少6位的密码

# OpenAI-compatible LLM
OPENAI_API_KEY=你的模型服务key
url=https://你的模型服务地址/v1
MODEL_NAME=你的模型名称

# 主回答 Agent，可不填，默认继承 OPENAI_API_KEY / url / MODEL_NAME
MAIN_AGENT_API_KEY=
MAIN_AGENT_API_URL=
MAIN_AGENT_MODEL_NAME=
MAIN_AGENT_TEMPERATURE=0.2
MAIN_AGENT_TOP_P=0.9
MAIN_AGENT_MAX_TOKENS=4000

# 外部 RAG API Key，调用 /api/v1/rag/* 时使用
RAG_API_KEY=请替换为外部服务调用密钥

# 本地模型路径
conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct

# 设备。留空时自动 cuda/cpu
EMBEDDING_DEVICE=
RERANKER_DEVICE=
TABLE_SUMMARY_DEVICE=

# Compose 对外端口
APP_PORT=8080

# Backend worker，当前建议保持 1
BACKEND_WORKERS=1

# Redis / Qdrant 在 Docker Compose 中会由 compose 覆盖
REDIS_PREFIX=rag
QDRANT_TIMEOUT_SEC=30
QDRANT_INIT_RETRIES=20
QDRANT_INIT_DELAY_SEC=3
```

### 关键变量说明

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `SECRET_KEY` | JWT 签名密钥，生产必须替换 | `your-secret-key-change-in-production` |
| `AUTH_INSTANCE_ID` | 鉴权实例 ID，可用于 token 失效隔离 | 随机 |
| `INITIAL_ADMIN_USERNAME` | 首次创建管理员用户名 | 空 |
| `INITIAL_ADMIN_PASSWORD` | 首次创建管理员密码 | 空 |
| `OPENAI_API_KEY` | OpenAI-compatible 模型服务 key | 空 |
| `url` | OpenAI-compatible base URL，代码中用于 `OPENAI_API_URL` | 空 |
| `MODEL_NAME` | 默认模型名称 | `qwq32b` |
| `MAIN_AGENT_*` | 主回答 Agent 模型、采样和上下文配置 | 见 `.env` 示例 |
| `RAG_API_KEY` | 外部 RAG API 鉴权密钥 | 空 |
| `conan_path` | embedding 模型路径 | 空，必填 |
| `reranker_path` | reranker 模型路径 | 空，可选 |
| `TABLE_SUMMARY_MODEL_PATH` | 表格摘要模型路径 | `models/Qwen2.5-1.5B-Instruct` |
| `SHARED_STORAGE_ROOT` | 共享运行数据根目录 | `data` |
| `QDRANT_MODE` | `local` 或 `server` | `local` |
| `QDRANT_URL` | Qdrant Server 地址 | 空 |
| `QDRANT_LOCAL_PATH` | local Qdrant 路径 | `data/storages` |
| `QDRANT_LEXICAL_INDEX_DIR` | 词汇索引缓存目录 | `data/lex_index` |
| `REDIS_URL` | Redis 连接地址 | 空 |
| `BACKEND_WORKERS` | Uvicorn worker 数 | `1` |

### 首次管理员创建规则

用户数据保存在 `.user/users.json`。首次启动时：

- 如果 `.user/users.json` 不存在，并且同时设置了 `INITIAL_ADMIN_USERNAME`、`INITIAL_ADMIN_PASSWORD`，系统会创建首个管理员。
- 如果 `.user/users.json` 已存在，环境变量不会覆盖已有用户。
- 如果首次启动没有设置初始管理员，系统会创建空用户文件，需要删除 `.user/users.json` 后重启，或手动写入用户。

## Docker 部署

### 1. 准备目录

```bash
mkdir -p data/redis data/qdrant data/stored_files data/lex_index data/content_lists data/agent_memory data/chat_sessions models .user
```

### 2. 准备 `.env`

按 [环境变量](#环境变量) 写入根目录 `.env`。至少需要：

- `SECRET_KEY`
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`
- `OPENAI_API_KEY`
- `url`
- `MODEL_NAME`
- `conan_path`

如果使用 reranker 或表格摘要，也要准备：

- `reranker_path`
- `TABLE_SUMMARY_MODEL_PATH`

### 3. 准备本地模型

至少需要 embedding 模型：

```text
models/bge-base-zh-v1.5/
```

推荐准备 reranker：

```text
models/bge-reranker-base/
```

表格摘要模型默认路径：

```text
models/Qwen2.5-1.5B-Instruct/
```

可用脚本下载表格摘要模型：

```bash
python scripts/download_table_summary_model.py --source modelscope
```

MinerU 相关模型应按 `config/mineru.json` 和 `config/mineru.resolved.json` 指向的路径准备。

### 4. 构建并启动

```bash
docker compose up -d --build
```

如镜像已构建，只启动：

```bash
docker compose up -d
```

### 5. 查看状态

```bash
docker compose ps
docker logs -f rag-backend
docker logs -f rag-web
docker logs -f rag-qdrant
docker logs -f rag-redis
```

### 6. 访问服务

默认地址：

```text
前端：http://127.0.0.1:8080
API 文档：http://127.0.0.1:8080/docs
后端健康检查：http://127.0.0.1:8080/health
Qdrant：http://127.0.0.1:6333
```

如果宿主机设置了代理，检查本机服务时建议绕过代理：

```bash
curl --noproxy '*' -sSI http://127.0.0.1:8080
curl --noproxy '*' -sS http://127.0.0.1:6333
```

### 7. 停止服务

```bash
docker compose down
```

停止并删除容器不会删除挂载在宿主机的 `data/`、`models/`、`.user/`。

## 本地开发启动

本地开发可以分开启动后端、前端、Qdrant 和 Redis。

### Python 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 前端依赖

```bash
cd frontend
npm ci
cd ..
```

### 启动 Qdrant 和 Redis

使用 Compose 只启动基础服务：

```bash
docker compose up -d qdrant redis
```

本地后端 `.env` 中可设置：

```bash
QDRANT_MODE=server
QDRANT_URL=http://127.0.0.1:6333
REDIS_URL=redis://127.0.0.1:6379/0
```

如果不使用 Redis，可留空 `REDIS_URL`，系统会退化到文件会话能力；完整功能推荐 Redis。

### 启动后端

```bash
source .venv/bin/activate
python backend/run.py --host 0.0.0.0 --port 8000 --reload
```

后端地址：

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/docs
```

### 启动前端

```bash
cd frontend
npm run dev
```

前端开发地址通常是：

```text
http://127.0.0.1:5173
```

前端通过 Vite 配置或 API client 访问后端 `/api`。

## 首次使用流程

1. 准备 `.env` 和模型目录。
2. 启动 Docker 服务。
3. 打开 `http://127.0.0.1:8080`。
4. 使用 `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` 登录。
5. 进入文件管理页上传文档。
6. 勾选文件并触发导入。
7. 等待导入任务完成。
8. 回到聊天页提问。
9. 在回答中查看来源、图片、表格和引用信息。
10. 需要时进入知识图谱页查看已抽取的图谱。

## 前端功能

### 页面

| 路径 | 页面 | 说明 |
| --- | --- | --- |
| `/login` | 登录页 | 用户登录 |
| `/` | 聊天页 | RAG 问答、多轮会话、SSE 流式渲染 |
| `/files` | 文件管理 | 上传、导入、删除、搜索、状态筛选 |
| `/users` | 用户管理 | 管理员创建/删除用户、改角色、重置密码 |
| `/change-password` | 修改密码 | 当前用户修改密码 |
| `/knowledge-graph` | 知识图谱 | G6 图谱展示、统计和子图浏览 |

### 聊天渲染

前端支持：

- Markdown
- GFM 表格
- 代码块高亮
- 数学公式
- 图片附件
- 来源引用
- reasoning 折叠块
- 长会话虚拟列表

### 文件管理状态

文件列表中有三类状态：

- `imported`：本地文件存在，且 Qdrant 中有对应 chunk。
- `not_imported`：本地文件存在，但尚未入库。
- `ghost`：Qdrant 中有数据，但本地原始文件不存在。

## 后端 API

后端根地址：

```text
http://127.0.0.1:8080/api/v1
```

Docker 里由 Nginx 转发 `/api/*` 到 backend。

### 鉴权

除登录和健康检查外，多数接口需要：

```http
Authorization: Bearer <JWT>
```

登录：

```http
POST /api/v1/auth/login
```

请求体：

```json
{
  "username": "admin",
  "password": "password"
}
```

返回：

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### API 清单

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/health` | 无 | 后端健康检查 |
| `POST` | `/api/v1/auth/login` | 无 | 登录获取 JWT |
| `GET` | `/api/v1/auth/me` | 登录 | 当前用户信息 |
| `POST` | `/api/v1/auth/logout` | 登录 | 客户端丢弃 token |
| `POST` | `/api/v1/chat/stream` | 登录 | SSE 流式聊天 |
| `GET` | `/api/v1/chat/sessions` | 登录 | 会话列表 |
| `GET` | `/api/v1/chat/session/{session_id}` | 登录 | 会话详情 |
| `DELETE` | `/api/v1/chat/session/{session_id}` | 登录 | 删除会话 |
| `GET` | `/api/v1/files` | 登录 | 文件列表 |
| `POST` | `/api/v1/files/upload` | 管理员 | 上传文件 |
| `GET` | `/api/v1/files/content` | 登录或 query token | 文件/图片预览 |
| `POST` | `/api/v1/files/import` | 管理员 | 创建导入任务 |
| `GET` | `/api/v1/files/import-jobs/active` | 管理员 | 当前导入任务 |
| `GET` | `/api/v1/files/import-jobs/{job_id}` | 管理员 | 导入任务详情 |
| `DELETE` | `/api/v1/files` | 管理员 | 批量删除文件 |
| `DELETE` | `/api/v1/files/{file_tag}` | 管理员 | 删除单个文件 |
| `GET` | `/api/v1/users` | 管理员 | 用户列表 |
| `POST` | `/api/v1/users` | 管理员 | 创建用户 |
| `GET` | `/api/v1/users/{username}` | 管理员 | 用户详情 |
| `DELETE` | `/api/v1/users/{username}` | 管理员 | 删除用户 |
| `POST` | `/api/v1/users/change-password` | 登录 | 修改自己的密码 |
| `POST` | `/api/v1/users/reset-password` | 管理员 | 重置用户密码 |
| `POST` | `/api/v1/users/change-role` | 管理员 | 修改用户角色 |
| `POST` | `/api/v1/rag/query` | `RAG_API_KEY` | 外部 RAG 问答 |
| `POST` | `/api/v1/rag/search` | `RAG_API_KEY` | 外部纯检索 |
| `GET` | `/api/v1/knowledge-graph` | 登录 | 完整图谱 JSON |
| `GET` | `/api/v1/knowledge-graph/stats` | 登录 | 图谱统计 |
| `GET` | `/api/v1/knowledge-graph/preview` | 登录 | 图谱预览图 |
| `GET` | `/api/v1/knowledge-graph/subgraph` | 登录 | 节点子图 |

### SSE 事件

`POST /api/v1/chat/stream` 返回 `text/event-stream`。前端消费的事件包括：

- `session`：返回或创建 `session_id`。
- `reasoning`：模型 reasoning 内容。
- `content`：回答正文增量。
- `done`：完整回答结束。
- `error`：异常。

### 外部 RAG API

外部系统调用 `/api/v1/rag/query` 和 `/api/v1/rag/search` 时使用 `RAG_API_KEY`。代码中的 `verify_rag_api_key` 支持两种鉴权头：

- `X-API-Key: <key>`
- `Authorization: ApiKey <key>`

纯检索示例：

```bash
curl --noproxy '*' -X POST http://127.0.0.1:8080/api/v1/rag/search \
  -H "X-API-Key: $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"变电站防雷接地要求", "top_k":5}'
```

问答示例：

```bash
curl --noproxy '*' -X POST http://127.0.0.1:8080/api/v1/rag/query \
  -H "X-API-Key: $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"110kV变电站接地设计需要关注哪些规范要求？"}'
```

## 知识库入库与检索流程

### 入库流程

```text
上传文件
  -> data/stored_files/
  -> MinerU 解析
  -> data/content_lists/
  -> data/stored_files/mineru_output/
  -> chunk 切分
  -> 表格独立处理和摘要
  -> embedding
  -> Qdrant 写入
  -> data/lex_index/database_file_stats.json 更新
```

### 检索流程

```text
用户问题
  -> 可选 query rewrite / intent router
  -> Qdrant 向量召回
  -> 词汇索引召回
  -> hybrid 融合
  -> reranker 重排
  -> 动态裁剪
  -> Agent 生成答案
  -> SSE 返回正文、reasoning、来源和附件信息
```

### Qdrant payload

写入 Qdrant 的 payload 主要包含：

- `Original_file`：源文件 tag。
- `Content`：chunk 正文，可能包含 Markdown 图片引用。
- `metadata`：chunk 类型、页码、表格信息等扩展数据。

## 知识图谱

知识图谱相关数据位于：

```text
data/knowledge_graph/
```

主要文件：

```text
database_kg.json
database_kg_main.json
kg_preview.png
```

### 抽取图谱

需要 Qdrant 正常运行，并且 collection 中已有知识库数据。

```bash
python tools/kg_extractor.py \
  --collection database \
  --qdrant-url http://127.0.0.1:6333 \
  --batch-size 5 \
  --max-chunks 500 \
  --output data/knowledge_graph/
```

该脚本会调用 OpenAI-compatible LLM 抽取实体关系三元组。

### 预计算布局

```bash
python tools/kg_layout.py --input data/knowledge_graph/database_kg.json --iterations 100 --scale 2000
```

### 前端查看

启动服务后访问：

```text
http://127.0.0.1:8080/knowledge-graph
```

如果接口返回 `Knowledge graph data not found`，说明还没有生成 `data/knowledge_graph/database_kg.json` 或 `database_kg_main.json`。

## 常用脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/import_file.py` | 命令行导入单个文件到 Qdrant |
| `scripts/search_qdrant.py` | 命令行检索 Qdrant |
| `scripts/migrate_qdrant_local_to_server.py` | local Qdrant 到 server Qdrant 迁移 |
| `scripts/smoke_mineru_embedding_qdrant.py` | MinerU、embedding、Qdrant 三合一 smoke |
| `scripts/smoke_hybrid_retrieval.py` | 混合检索 smoke |
| `scripts/smoke_e2e_pdf_hybrid_rerank.py` | PDF 入库、混合检索、rerank 端到端 smoke |
| `scripts/example_rag_api_client.py` | 外部 RAG API 调用示例 |
| `scripts/download_table_summary_model.py` | 下载/测试表格摘要模型 |
| `scripts/audit_public_search.py` | 根据 content list 文件名审计公开可检索性 |
| `scripts/classify_knowledge_domains.py` | 按文件名做知识领域分类 |
| `tools/kg_extractor.py` | 从 Qdrant chunk 抽取知识图谱 |
| `tools/kg_layout.py` | 给知识图谱预计算布局坐标 |

### 搜索 Qdrant

```bash
python scripts/search_qdrant.py "供电营业规则" --collection database --top-k 5
```

### 导入文件

```bash
python scripts/import_file.py data/stored_files/example.pdf --collection database --dpi 200
```

### 公开可检索性审计

```bash
python scripts/audit_public_search.py --delay 0.2 --timeout 25 --max-queries 3 --prefix public_search_audit
```

输出在：

```text
reports/
```

`reports/` 是本地生成物，默认不提交。

## 测试和验证

### Python 编译检查

```bash
python -m py_compile \
  backend/app/main.py \
  backend/app/config.py \
  tools/qdrant.py \
  tools/load_files.py
```

### 后端测试

```bash
pytest backend/tests
```

### 前端检查

```bash
cd frontend
npm run lint
npm run build
```

### Docker 健康检查

```bash
docker compose ps
curl --noproxy '*' -sSI http://127.0.0.1:8080
curl --noproxy '*' -sS http://127.0.0.1:6333
```

期望：

- 前端返回 `200 OK`。
- Qdrant 返回 JSON，包含 `qdrant - vector search engine`。
- `rag-backend` health 为 healthy。
- `rag-redis` health 为 healthy。

## 运维和排障

### 端口

| 服务 | 容器端口 | 宿主机端口 |
| --- | --- | --- |
| web | 80 | `${APP_PORT:-8080}` |
| backend | 8000 | 不直接暴露，由 web 代理 |
| qdrant | 6333 | 6333 |
| redis | 6379 | 不直接暴露 |

### 常用日志

```bash
docker logs -f rag-web
docker logs -f rag-backend
docker logs -f rag-qdrant
docker logs -f rag-redis
```

### 重启单个服务

```bash
docker compose restart backend
docker compose restart web
docker compose restart qdrant
docker compose restart redis
```

### 重新构建镜像

```bash
docker compose build backend
docker compose build web
docker compose up -d
```

### 前端 502

排查顺序：

1. `docker compose ps` 看 `rag-backend` 是否 healthy。
2. `docker logs -f rag-backend` 看是否模型加载失败、环境变量缺失、Qdrant 连接失败。
3. `curl --noproxy '*' http://127.0.0.1:8080/health` 看 Nginx 到 backend 转发是否正常。
4. 检查 `.env` 中 `conan_path`、`OPENAI_API_KEY`、`url`、`MODEL_NAME`。

### 登录失败

检查：

1. `.user/users.json` 是否存在。
2. 首次启动时是否设置了 `INITIAL_ADMIN_USERNAME` 和 `INITIAL_ADMIN_PASSWORD`。
3. 如果 `.user/users.json` 是空用户文件，可停止服务后备份/删除该文件，再设置初始管理员重启。

```bash
docker compose down
mv .user/users.json .user/users.json.bak
docker compose up -d
```

### Qdrant 无数据

检查：

```bash
curl --noproxy '*' http://127.0.0.1:6333/collections
curl --noproxy '*' http://127.0.0.1:6333/collections/database
```

如果 collection 不存在，需要先导入文件。

### 文件显示 ghost

`ghost` 表示 Qdrant 中有对应文件的 chunk，但本地 `data/stored_files/` 中找不到原始文件。处理方式：

- 如果仍需要该资料，重新上传同名文件。
- 如果不需要，在文件管理页删除该 ghost 数据。
- 或使用删除接口删除对应 `Original_file`。

### 模型加载失败

常见原因：

- `conan_path` 未设置。
- 模型目录不存在或不完整。
- GPU 不可用但设备强制设为 `cuda`。
- Docker 未安装 NVIDIA runtime。
- `models/` 未挂载到容器。

检查容器内模型目录：

```bash
docker exec -it rag-backend ls -lh /app/models
```

### 代理导致本地 curl 返回 502

如果宿主机设置了 `HTTP_PROXY` / `HTTPS_PROXY`，访问本机服务时要绕过代理：

```bash
curl --noproxy '*' http://127.0.0.1:8080
curl --noproxy '*' http://127.0.0.1:6333
```

也可以设置：

```bash
export NO_PROXY=localhost,127.0.0.1,qdrant,redis,backend,web
export no_proxy=localhost,127.0.0.1,qdrant,redis,backend,web
```

### 不要提交运行数据

提交前检查：

```bash
git status --short
git status --short --ignored
```

正常情况下，以下目录应处于 ignored：

```text
data/qdrant/
data/redis/
data/stored_files/
data/content_lists/
data/lex_index/
models/
reports/
.user/
frontend/node_modules/
frontend/dist/
```

## 安全注意事项

- 生产环境必须替换 `SECRET_KEY`。
- 生产环境必须设置强密码的初始管理员。
- `.env`、`.user/`、`models/`、`data/` 不应提交到 GitHub。
- `RAG_API_KEY` 应使用高强度随机值。
- Nginx 当前 `client_max_body_size` 为 `200m`，如允许更大文件，需要同步评估磁盘、解析耗时和超时。
- 后端 CORS 当前允许 `*`，对公网部署时应收紧。
- Redis 当前只在 Compose 内部网络暴露，不建议直接映射公网。
- Qdrant 当前映射到宿主机 `6333`，公网部署时应放在内网或加访问控制。
- 用户密码当前使用 SHA256 文件哈希保存，适合内部系统快速部署；如果面向公网，应升级为带盐 KDF，如 bcrypt/argon2。

## 推荐提交前检查清单

```bash
python -m py_compile backend/app/main.py tools/qdrant.py tools/load_files.py
cd frontend && npm run build
cd ..
git status --short
```

确认只提交：

- 源码
- 配置模板或非敏感配置
- Docker 和部署脚本
- 文档
- 必要的测试脚本

不要提交：

- `.env`
- `.user/`
- `data/`
- `models/`
- `reports/`
- `frontend/node_modules/`
- `frontend/dist/`
