# 智能设计助手 RAG

面向电力系统与国家电网业务场景的 RAG 项目。当前主线是前后端分离架构：

- `frontend/`：React + Vite 前端，负责聊天、文件管理、用户管理、消息渲染
- `backend/`：FastAPI 后端，负责鉴权、会话、流式回答、文件服务接口
- `tools/`、`agents/`、`config/`、`data/`、`models/`：前后端共享的知识库、解析、检索和模型资源

项目历史上保留过 `run/streamlit.py` 旧入口，但当前部署主线已经统一为前后端分离架构。

## 1. 项目概览

这个项目主要解决以下问题：

- 上传 PDF / 文档并完成知识库入库
- 使用 MinerU 提取正文、图片、表格
- 使用 Qdrant 做向量检索与混合检索
- 对复杂表格做独立切块、表格摘要、证据回溯
- 在前端以聊天形式展示答案、来源、表格和附件图片

核心特点：

- 面向中文、电力行业、国网业务资料
- 支持图片与表格证据回溯
- 支持流式回答
- 支持用户鉴权与管理员文件管理
- 当前部署统一走前后端分离入口

## 2. 当前架构

### 2.1 总体拓扑

当前主线由四类组件组成：

- `frontend`：React + Vite 前端，负责页面、登录态、聊天 UI、文件管理 UI
- `backend`：FastAPI 后端，负责鉴权、会话、SSE 流式问答、文件接口
- `qdrant`：向量库服务，负责持久化向量、payload 和相似度检索
- `redis`：会话索引与元数据服务，负责会话列表、标题、最近活跃时间、消息数

运行拓扑如下：

```text
浏览器
  |
  v
frontend
  |
  |  /api
  v
backend
  |
  +--> qdrant        向量库服务
  +--> redis         会话索引与元数据
  +--> models/       本地 embedding / reranker / summary 模型
  +--> .user/        用户与鉴权数据
  +--> SHARED_STORAGE_ROOT/
       ├── stored_files/
       │   └── mineru_output/
       ├── content_lists/
       ├── exported_chunks/
       ├── agent_memory/
       └── chat_sessions/
```

### 2.2 状态分层

当前项目的状态分成三层：

1. 持久化服务层
   - `qdrant`：知识库向量、payload、collection 数据
   - `redis`：会话索引、会话元信息

2. 文件持久化层
   - `SHARED_STORAGE_ROOT/stored_files`：上传原始文件
   - `SHARED_STORAGE_ROOT/stored_files/mineru_output`：图片、表格截图
   - `SHARED_STORAGE_ROOT/agent_memory`：memory 快照
   - `SHARED_STORAGE_ROOT/chat_sessions`：完整 transcript

3. 进程内运行态
   - backend 进程内 `ChatAgent`
   - backend 进程内热模型缓存
   - backend 进程内 session 执行态

这也是当前仍然保持 `BACKEND_WORKERS=1` 的原因：会话索引已经外置，但 `ChatAgent` 执行态还没有完全无状态化。

### 2.3 当前支持的运行模式

当前代码支持三种模式：

- 本地最小模式
  - `QDRANT_MODE=local`
  - `REDIS_URL=` 为空
  - 用于先验证前后端主流程

- 本地完整链路模式
  - backend / frontend 本地启动
  - `qdrant` 和 `redis` 作为独立服务运行
  - 用于验证完整服务链

- Docker 部署模式
  - `web + backend + qdrant + redis`
  - 用于标准化部署

### 2.4 历史旧入口

```text
streamlit run run/streamlit.py
```

该入口仅作为历史代码保留，不再作为主部署方案的一部分。

## 3. 目录结构

```text
rag/
├── frontend/                        # React + Vite 前端
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── stores/
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                         # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/                  # 路由层
│   │   ├── core/                    # 安全、中间件、Redis 客户端
│   │   ├── schemas/                 # Pydantic schema
│   │   ├── services/                # chat / file / user / auth
│   │   ├── config.py                # 后端配置入口
│   │   ├── dependencies.py          # 依赖注入与资源缓存
│   │   └── main.py                  # FastAPI 应用入口
│   ├── run.py
│   └── requirements.txt
│
├── agents/                          # LLM、embedding、reranker、Agent 组装
├── tools/                           # MinerU、入库、检索、Qdrant 工具链
├── config/                          # MinerU 等公共配置
├── deploy/nginx/                    # Docker Nginx 反向代理配置
├── scripts/                         # 迁移、批量导入等脚本
├── docs/                            # 设计与改动日志
├── run/                             # 历史 Streamlit 入口
├── tests/                           # 测试与 smoke 脚本
├── storage_paths.py                 # 共享存储路径统一入口
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── README.md
└── .gitignore
```

### 3.1 运行数据目录

默认 `SHARED_STORAGE_ROOT=data`，因此当前运行数据目录如下：

```text
data/
├── qdrant/                          # Qdrant Server 数据目录
├── redis/                           # Redis AOF / RDB 数据目录
├── lex_index/                       # 后端词汇索引缓存
├── stored_files/                    # 上传的原始文件
│   └── mineru_output/               # 图片、表格截图、方程截图
├── content_lists/                   # 文档解析中间结果
├── exported_chunks/                 # 调试导出的 chunk
├── agent_memory/                    # memory 快照
├── chat_sessions/                   # transcript 文件
└── storages/                        # 历史 local Qdrant 数据目录（兼容旧库）
```

## 4. 模块职责

### 4.1 前端

前端负责：

- 登录与用户态维护
- 聊天页面与历史会话列表
- 文件管理、导入、删除
- SSE 流式渲染
- Markdown / 表格 / 数学公式 / 附件图片区渲染

关键模块：

- `frontend/src/pages/Chat.tsx`
- `frontend/src/components/Chat/`
- `frontend/src/stores/`
- `frontend/src/api/`

### 4.2 后端

后端负责：

- JWT 鉴权
- Chat SSE 流式响应
- ChatAgent 会话生命周期管理
- transcript / memory 持久化
- 文件上传、入库、删除、预览
- 调用 `agents/` 与 `tools/`

关键模块：

- `backend/app/services/chat_service.py`
- `backend/app/services/file_service.py`
- `backend/app/services/user_service.py`
- `backend/app/core/redis_client.py`
- `backend/app/dependencies.py`

### 4.3 检索与入库层

共享核心能力：

- `tools/mineru_toolkit.py`
  - PDF 解析
  - 图片、表格、方程输出

- `tools/load_files.py`
  - 内容预处理
  - chunk 切分
  - 表格摘要
  - Qdrant 写入

- `tools/qdrant.py`
  - 支持 `local` / `server` 双模式
  - 向量检索
  - 词汇索引缓存
  - hybrid 检索

- `tools/database_toolkit.py`
  - 对 Agent 暴露 `search_database`
  - rerank
  - 动态裁剪和去重

### 4.4 模型层

- `agents/backend_model.py`
  - LLM
  - embedding
  - reranker
  - table summary model

- `agents/chat_agent.py`
  - 问答 Agent 工厂
  - 系统提示词与行为约束

## 5. 依赖要求

- Python 3.10+
- Node.js 20.19+ 或 22.12+
- 推荐 Linux 环境
- 推荐使用虚拟环境

## 6. 安装与初始化

### 6.1 Python 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

说明：

- 根目录 [`requirements.txt`](/home/ubuntu/rag_project/rag/requirements.txt) 已包含主工程依赖和后端运行时依赖
- [`backend/requirements.txt`](/home/ubuntu/rag_project/rag/backend/requirements.txt) 用于和 Docker 镜像安装链路保持一致，建议继续安装

### 6.2 前端环境

```bash
cd frontend
npm install
cd ..
```

### 6.3 独立服务准备

如果要跑完整服务链，需要额外准备：

- `qdrant` 服务
- `redis` 服务

你可以：

- 用 Docker 起这两个服务
- 或者在系统里单独安装它们并本地启动

## 7. 环境变量与配置模式

在项目根目录创建 `.env`。

示例：

```env
# 主对话模型
OPENAI_API_KEY=your-api-key
url=https://your-api-endpoint/v1
MODEL_NAME=qwq32b

# 本地模型路径
conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct

# 可选
DEBUG=false
SECRET_KEY=change-me

# Qdrant
QDRANT_MODE=local
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_LOCAL_PATH=data/storages
QDRANT_LEXICAL_INDEX_DIR=data/lex_index

# Redis
REDIS_URL=
REDIS_PREFIX=rag

# 共享文件根目录
SHARED_STORAGE_ROOT=data
```

### 7.1 常用变量说明

| 变量 | 作用 |
|---|---|
| `OPENAI_API_KEY` | 主对话模型 API Key |
| `url` | OpenAI 兼容接口地址 |
| `MODEL_NAME` | 主对话模型名称 |
| `conan_path` | embedding 模型路径 |
| `reranker_path` | reranker 模型路径 |
| `TABLE_SUMMARY_MODEL_PATH` | 表格摘要模型路径 |
| `SECRET_KEY` | 后端 JWT 密钥 |
| `DEBUG` | 后端调试模式 |
| `QDRANT_MODE` | Qdrant 运行模式，`local` 或 `server` |
| `QDRANT_URL` | Qdrant 服务地址，服务模式必填 |
| `QDRANT_LEXICAL_INDEX_DIR` | BM25 词汇索引缓存目录 |
| `REDIS_URL` | Redis 地址，用于会话索引和元数据共享 |
| `REDIS_PREFIX` | Redis key 前缀 |
| `SHARED_STORAGE_ROOT` | 共享文件根目录，默认 `data` |

### 7.2 推荐配置模式

#### 本地最小模式

用于先跑通前后端主流程：

```env
QDRANT_MODE=local
QDRANT_URL=
REDIS_URL=
SHARED_STORAGE_ROOT=data
```

#### 本地完整链路模式

用于验证独立服务链：

```env
QDRANT_MODE=server
QDRANT_URL=http://127.0.0.1:6333
REDIS_URL=redis://127.0.0.1:6379/0
SHARED_STORAGE_ROOT=data
```

#### Docker 模式

Docker Compose 会覆盖为：

```env
QDRANT_MODE=server
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379/0
SHARED_STORAGE_ROOT=data
```

## 8. 模型与数据目录

以下目录默认不提交远程仓库：

- `models/`
- `data/qdrant/`
- `data/redis/`
- `data/lex_index/`
- `data/stored_files/`
- `data/content_lists/`
- `data/exported_chunks/`
- `data/agent_memory/`
- `data/chat_sessions/`
- `.user/`

这些目录分别存放：

- 本地模型
- Qdrant Server 持久化数据
- Redis 持久化数据
- 本地词汇索引缓存
- 上传原始文件
- MinerU 输出图片/表格截图
- 文档解析缓存
- 会话与 agent memory 持久化数据
- 用户数据

## 9. 运行方式

### 9.1 本地最小模式

适用于先验证：

- 后端可启动
- 前端可启动
- 本地 local Qdrant 可工作
- 上传、入库、问答链路可跑通

后端：

```bash
cd /home/ubuntu/rag_project/rag
source .venv/bin/activate
python backend/run.py --host 0.0.0.0 --port 8000
```

前端：

```bash
cd /home/ubuntu/rag_project/rag/frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

访问：

- 前端：`http://127.0.0.1:3000`
- 后端：`http://127.0.0.1:8000/docs`

### 9.2 本地完整链路模式

适用于验证：

- backend
- frontend
- qdrant server
- redis
- 完整服务链

典型启动顺序：

1. 启动 `redis`
2. 启动 `qdrant`
3. 启动 `backend`
4. 启动 `frontend`

推荐先把 `.env` 切到服务模式：

```env
QDRANT_MODE=server
QDRANT_URL=http://127.0.0.1:6333
REDIS_URL=redis://127.0.0.1:6379/0
SHARED_STORAGE_ROOT=data
```

四个终端分别执行：

终端 1，启动 `redis`：

```bash
mkdir -p /home/ubuntu/rag_project/rag/data/redis
redis-server --port 6379 --appendonly yes --dir /home/ubuntu/rag_project/rag/data/redis
```

终端 2，启动 `qdrant`：

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
mkdir -p /home/ubuntu/rag_project/rag/data/qdrant
QDRANT__STORAGE__STORAGE_PATH=/home/ubuntu/rag_project/rag/data/qdrant /home/ubuntu/qdrant-src/target/release/qdrant
```

终端 3，启动 `backend`：

```bash
cd /home/ubuntu/rag_project/rag
source .venv/bin/activate
python backend/run.py --host 0.0.0.0 --port 8000
```

终端 4，启动 `frontend`：

```bash
cd /home/ubuntu/rag_project/rag/frontend
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

验证命令：

```bash
curl http://127.0.0.1:6333/collections
redis-cli -p 6379 ping
curl http://127.0.0.1:8000/health
```

### 9.3 旧 local Qdrant 数据迁移到 server

如果你之前使用的是：

- `QDRANT_MODE=local`
- 旧库位于 `data/storages`

而现在切到：

- `QDRANT_MODE=server`

那么需要把旧数据迁移到 Qdrant Server。

项目已提供迁移脚本：

- [`scripts/migrate_qdrant_local_to_server.py`](/home/ubuntu/rag_project/rag/scripts/migrate_qdrant_local_to_server.py)

推荐命令：

```bash
cd /home/ubuntu/rag_project/rag
source .venv/bin/activate
python scripts/migrate_qdrant_local_to_server.py \
  --local-path data/storages \
  --server-url http://127.0.0.1:6333 \
  --collection database \
  --recreate
```

说明：

- 迁移直接复制 `id + vector + payload`
- 不需要重新 embedding
- 不需要重新导入 PDF

迁移后验证：

```bash
curl http://127.0.0.1:6333/collections/database
```

### 9.4 Docker 部署

当前只推荐一种启动方式：使用根目录 `docker-compose.yml` 统一启动 `web + backend + qdrant + redis`。

架构如下：

```text
浏览器
  |
  v
nginx + frontend 静态资源   (:APP_PORT，默认 8080)
  |
  v
backend (FastAPI, 容器内 :8000)
  |
  +--> qdrant (容器内 :6333)
  +--> redis  (容器内 :6379)
  |
  +--> data/     持久化文档、词汇索引、截图、transcript、memory
  +--> models/   本地模型目录
  +--> .user/    用户数据
```

### 9.4.1 部署文件结构

部署相关文件现在只保留这一组：

```text
rag/
├── docker-compose.yml              # 唯一启动入口
├── Dockerfile.backend              # 后端镜像
├── Dockerfile.frontend             # 前端静态构建 + Nginx 镜像
└── deploy/nginx/default.conf       # 统一反向代理配置
```

旧的 `Dockerfile`、`Dockerfile.cuda`、`docker-compose.gpu.yml` 不再保留，避免入口分叉。

### 9.4.2 启动前准备

确认以下目录和文件存在：

- 根目录 `.env`
- 根目录 `data/`
- 根目录 `models/`
- 根目录 `.user/`

最少需要在 `.env` 中提供：

```env
OPENAI_API_KEY=your-api-key
url=https://your-api-endpoint/v1
MODEL_NAME=qwq32b
SECRET_KEY=change-me

conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct
```

可选覆盖项：

```env
APP_PORT=8080
BACKEND_WORKERS=1
```

说明：

- `APP_PORT` 是宿主机对外端口，默认 `8080`
- `BACKEND_WORKERS` 默认固定为 `1`，这是为了避免本地会话状态和本地向量存储在多进程下产生不一致

建议在首次 Docker 部署前手动创建持久化目录：

```bash
mkdir -p \
  data/qdrant \
  data/redis \
  data/lex_index \
  data/stored_files \
  data/content_lists \
  data/exported_chunks \
  data/agent_memory \
  data/chat_sessions \
  models \
  .user
```

如果你此前在宿主机本地手动启动过：

- `redis-server`
- `qdrant`
- `python backend/run.py`
- `npm run dev`

建议先停掉这些本地进程，再启动 Docker。  
原因是 `data/` 会被容器直接挂载，本地进程和容器不要同时占用同一套数据目录。

### 9.4.3 外部挂载约定

当前只需要把下面 3 个顶层目录作为宿主机持久化挂载：

- `./data:/app/data`
- `./models:/app/models`
- `./.user:/app/.user`

说明：

- `data/` 已经包含 `qdrant/`、`redis/`、`lex_index/`、`stored_files/`、`content_lists/`、`exported_chunks/`、`agent_memory/`、`chat_sessions/`
- `models/` 用于本地 embedding、reranker、表格模型以及其他下载模型
- `.user/` 用于用户数据和鉴权信息
- `.env` 只通过 `env_file` 注入，不需要作为 volume 挂载
- 当前 Compose 默认注入 `SHARED_STORAGE_ROOT=data`，所有上传文件、MinerU 输出、transcript、memory 都从这个根目录派生

### 9.4.4 启动命令

最简单的标准命令：

```bash
docker compose up -d --build
```

当你修改了 [`Dockerfile.backend`](/home/ubuntu/rag_project/rag/Dockerfile.backend)、[`Dockerfile.frontend`](/home/ubuntu/rag_project/rag/Dockerfile.frontend)、[`requirements.txt`](/home/ubuntu/rag_project/rag/requirements.txt)、[`backend/requirements.txt`](/home/ubuntu/rag_project/rag/backend/requirements.txt) 之后，都应继续使用 `--build` 触发镜像重建。

如果你的环境拉取基础镜像或执行 `pip install / npm ci / git clone` 时网络不稳定，推荐使用本项目当前验证过的回退方式：

```bash
DOCKER_BUILDKIT=0 docker compose up -d --build
```

如果你只想先构建镜像，再单独启动容器：

```bash
DOCKER_BUILDKIT=0 docker compose build --no-cache
docker compose up -d
```

#### 9.4.4.1 使用宿主机代理构建镜像

如果你宿主机上已经开了 HTTP 代理，例如：

```bash
export http_proxy=http://127.0.0.1:7897
export https_proxy=http://127.0.0.1:7897
```

那么构建 Docker 镜像前，建议同时导出大小写两套变量：

```bash
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
export NO_PROXY=localhost,127.0.0.1,qdrant,redis,backend,web

export http_proxy=http://127.0.0.1:7897
export https_proxy=http://127.0.0.1:7897
export no_proxy=localhost,127.0.0.1,qdrant,redis,backend,web
```

本项目当前 Compose 已经做了两件事：

- `build` 阶段会把这些代理变量透传给 `apt-get`、`pip install`、`npm ci`
- 运行阶段不会再把代理写进 `backend` 容器环境，避免模型请求被错误转发到 `127.0.0.1:7897`

如果你已经构建完成，且后续不再需要 Docker 构建联网，可以在宿主机清掉这些变量：

```bash
unset HTTP_PROXY HTTPS_PROXY NO_PROXY
unset http_proxy https_proxy no_proxy
```

#### 9.4.4.2 按服务重建

如果你只改了前端代码，不需要整套重建，只重建 `web` 即可：

```bash
DOCKER_BUILDKIT=0 docker compose build --no-cache web
docker compose up -d web
```

如果你只改了后端代码或后端依赖，只重建 `backend`：

```bash
DOCKER_BUILDKIT=0 docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

如果你同时改了前后端：

```bash
DOCKER_BUILDKIT=0 docker compose build --no-cache backend web
docker compose up -d --force-recreate backend web
```

查看状态：

```bash
docker compose ps
docker compose logs -f redis
docker compose logs -f qdrant
docker compose logs -f backend
docker compose logs -f web
```

停止服务：

```bash
docker compose down
```

如果只是想重启容器但保留数据目录：

```bash
docker compose restart
```

### 9.4.5 访问地址

- 主应用：`http://localhost:8080`
- 后端健康检查：`http://localhost:8080/health`
- Swagger：`http://localhost:8080/docs`
- ReDoc：`http://localhost:8080/redoc`

如果你设置了 `APP_PORT`，把上面的 `8080` 替换掉即可。

### 9.4.6 Windows 部署

Windows 可以部署这套多容器架构，但建议区分两种方式理解：

- 推荐方式：`Windows + Docker Desktop + WSL2`
- 可运行但不推荐：`Windows 原生目录 + Docker Desktop`

#### 9.4.6.1 推荐方式：Docker Desktop + WSL2

更稳的做法是：

1. 安装 Docker Desktop
2. 打开 WSL2 backend
3. 安装一个 Linux 发行版，例如 Ubuntu
4. 在 Docker Desktop 里开启该 WSL 发行版的集成
5. 把项目放在 WSL 的 Linux 文件系统中，例如：

```bash
/home/<your-user>/rag
```

为什么推荐 WSL2：

- 当前项目依赖 Linux 风格路径和工具链
- `data/`、`models/`、`.user/` 这些目录在 Linux 文件系统下读写更稳
- Qdrant、Redis、OCR、PDF 解析、模型文件加载都更适合 Linux 文件系统
- 如果项目直接放在 `C:\Users\...` 这类 Windows 路径下，挂载性能和兼容性通常更差

WSL2 下的推荐命令流程：

进入 WSL 终端后执行：

```bash
cd /home/<your-user>/rag
mkdir -p \
  data/qdrant \
  data/redis \
  data/lex_index \
  data/stored_files \
  data/content_lists \
  data/exported_chunks \
  data/agent_memory \
  data/chat_sessions \
  models \
  .user
```

确认根目录 `.env` 已配置好模型地址、密钥和模型路径后，执行：

```bash
DOCKER_BUILDKIT=0 docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f web
```

访问地址仍然是：

- `http://localhost:8080`

这里的 `localhost` 指 Windows 宿主机浏览器访问 Docker Desktop 暴露出来的端口。

WSL2 下的目录建议：

建议把以下目录长期保存在 WSL Linux 文件系统里：

- `data/`
- `models/`
- `.user/`

尤其是 `models/` 和 `data/qdrant/`，文件多且体积大，放在 WSL 内部磁盘通常更稳。

WSL2 下的注意事项：

- 不建议一边在 Windows 原生 Python 环境里手动跑后端，一边再用 Docker Desktop 跑同一套 `data/`
- 如果宿主机需要代理，优先先确认 Docker Desktop 本身能正常拉镜像
- 如果你已经在 WSL 中验证过 `DOCKER_BUILDKIT=0 docker compose up -d --build` 能成功，就继续沿用这一条
- 如果修改了前端代码，只重建 `web`
- 如果修改了后端代码或依赖，只重建 `backend`

#### 9.4.6.2 可运行但不推荐：Windows 原生目录部署

如果你不想用 WSL2，也可以直接在 Windows 上这样做：

1. 安装 Docker Desktop
2. 把项目放在 Windows 路径，例如：

```text
D:\rag
```

3. 用 PowerShell 进入项目目录
4. 准备 `data/`、`models/`、`.user/`
5. 执行：

```powershell
docker compose up -d --build
```

这种方式可以跑，但要明确它的局限：

- `data/qdrant/`、`data/redis/`、`models/` 在 Windows 文件系统上的 IO 性能通常更差
- 大量小文件、模型目录和向量库目录更容易拖慢容器
- Windows 路径、权限和换行细节更容易引入兼容性问题
- 如果后续涉及代理、镜像构建、OCR 或模型依赖排查，Windows 原生路径通常更难处理

因此：

- 临时验证功能，可以这样跑
- 长期使用、多人共用、模型较大或数据量较大时，不建议这样部署

### 9.4.7 方案特性

- 前端静态资源由 Nginx 托管，启动更稳定，资源占用低
- 外部只暴露一个端口，后端不直接对公网开放
- `/api` 反向代理已关闭缓冲，兼容 SSE 流式输出
- 向量库已切换为独立 `qdrant` 服务，不再依赖 backend 容器内的本地 embedded storage
- 会话索引、标题、消息数和最近活跃时间已切到独立 `redis` 服务
- Redis 容器当前默认使用 `redis:8-alpine`，与现有 `data/redis/` 持久化数据格式兼容性更稳
- `data/`、`models/`、`.user/` 全部通过 bind mount 持久化
- redis、backend 和 web 都带健康检查；backend 会在启动时自动等待 redis 并重试连接 qdrant
- `init: true` 和 `restart: unless-stopped` 已开启，降低僵尸进程和意外退出影响

### 9.4.8 为什么不推荐多进程后端

当前后端包含：

- 进程内会话缓存
- 本地 agent memory 持久化恢复
- 本地 chat transcript 持久化文件

虽然向量库和会话索引已经切到独立服务，但 `ChatAgent` 实例本身、memory 快照恢复和 transcript 文件仍然是单实例语义，所以 Docker 部署默认采用单 worker。如果后续把会话执行态也进一步外置，再考虑多 backend 横向扩展。

如果后续要走多人共享和后端多副本部署，参考 [`docs/scalable_docker_architecture.md`](/home/ubuntu/rag_project/rag/docs/scalable_docker_architecture.md)。

## 10. 文档入库流程

文档入库大致流程如下：

```text
上传 PDF
  -> MinerU 解析
  -> 图片重命名
  -> 提取文本 / 表格 / 图片内容
  -> 表格独立切块
  -> 可选表格摘要
  -> embedding
  -> 写入 Qdrant
```

关键实现：

- `tools/load_files.py`
- `tools/mineru_toolkit.py`
- `tools/qdrant.py`

## 11. 检索与回答流程

回答链路大致如下：

```text
用户提问
  -> Chat Agent 调用 search_database
  -> Qdrant 混合检索
  -> rerank
  -> 动态阈值筛选
  -> 返回完整原文 chunk
  -> 生成最终回答
  -> 前端渲染正文 / 表格 / 附件图片
```

当前项目对表格类问题做了额外保护：

- 表格类 query 会自动放宽证据预算
- 表格和图片证据路径要求尽量原样保留
- 前端将图片与正文分离，放到附件图片区

## 12. 会话与状态架构

### 12.1 会话索引

会话索引和元数据目前保存在 Redis 中，包括：

- `session_id`
- `username`
- `title`
- `created_at`
- `updated_at`
- `last_activity`
- `message_count`
- `memory_enabled`

### 12.2 transcript 与 memory

会话全文和 memory 快照目前仍然通过文件持久化：

- `data/chat_sessions/<username>/`
- `data/agent_memory/<username>/`

这意味着：

- 会话列表可以跨 backend 共享
- 但具体 `ChatAgent` 执行态仍然不是完全无状态

### 12.3 文件路径统一入口

当前所有文件类路径统一收口在：

- [`storage_paths.py`](/home/ubuntu/rag_project/rag/storage_paths.py)

后端、工具链、脚本都会从 `SHARED_STORAGE_ROOT` 派生：

- `stored_files`
- `mineru_output`
- `content_lists`
- `exported_chunks`
- `agent_memory`
- `chat_sessions`

## 13. API 简述

### 13.1 鉴权

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

### 13.2 聊天

- `POST /api/v1/chat/stream`
- `DELETE /api/v1/chat/session/{session_id}`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/session/{session_id}`

### 13.3 文件

- `GET /api/v1/files`
- `POST /api/v1/files/upload`
- `POST /api/v1/files/import`
- `GET /api/v1/files/content/{file_tag}`
- `DELETE /api/v1/files`

### 13.4 用户

- `GET /api/v1/users`
- `POST /api/v1/users`
- `POST /api/v1/users/change-password`
- `POST /api/v1/users/reset-password`

更多细节见：

- `backend/README.md`
- `http://localhost:8000/docs`

## 14. 测试、检查与联调

### 14.1 Python 语法检查

```bash
source .venv/bin/activate
python -m py_compile backend/app/config.py
python -m py_compile backend/app/services/chat_service.py
python -m py_compile tools/qdrant.py
```

### 14.2 Python 测试

```bash
source .venv/bin/activate
python3 -m pytest
```

### 14.3 前端构建检查

```bash
cd frontend
npm run build
```

### 14.4 后端启动检查

```bash
cd backend
python3 run.py
```

### 14.5 完整链路自检顺序

推荐按这个顺序检查：

1. `qdrant` 是否可访问
2. `redis` 是否可访问
3. 后端 `/health` 是否正常
4. 前端能否登录
5. 文件列表是否正常显示
6. 文件入库后 `database` collection 点数是否增加
7. 聊天是否返回检索结果

## 15. 常见问题

### 15.1 前端页面一直 loading

优先检查：

- 前端是否跑在 `3000`
- 后端是否跑在 `8000`
- 浏览器是否拿到旧 bundle
- `/api/v1/auth/me` 是否异常

### 15.2 Docker 构建时基础镜像或依赖拉取失败

优先检查：

- 是否直接使用了 `DOCKER_BUILDKIT=0 docker compose up -d --build`
- 宿主机是否已经配置代理
- `HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy` 是否已导出
- Docker 构建日志里失败的是哪一层：
  - `FROM python/node/nginx`：通常是镜像源或 Docker daemon 网络问题
  - `apt-get / pip install / npm ci / git clone`：通常是构建阶段代理问题

推荐命令：

```bash
DOCKER_BUILDKIT=0 docker compose build --no-cache
```

### 15.3 Docker 运行中模型请求报 `Connection error`

如果后端日志里出现：

- `httpx.ConnectError`
- `openai.APIConnectionError`
- 或者显式显示正在连接 `127.0.0.1:7897`

优先检查：

- `docker compose exec backend env | grep -i proxy`
- `backend` 运行时是否还带着宿主机代理变量
- `.env` 中的 `url=` 是否是可从容器访问的模型地址

当前项目的正确行为是：

- 代理只用于 Docker `build`
- `backend` 运行时不再注入 `HTTP_PROXY/http_proxy`

如果你刚改过 Dockerfile 或 Compose，记得重建 `backend`：

```bash
DOCKER_BUILDKIT=0 docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

### 15.4 文件存在但显示“未建库”

优先检查：

- 当前后端使用的是 `QDRANT_MODE=local` 还是 `server`
- `QDRANT_MODE=server` 时，`http://127.0.0.1:6333/collections/database` 的 `points_count` 是否大于 0
- 旧库是否还停留在 `data/storages`
- 是否已经执行迁移脚本 `scripts/migrate_qdrant_local_to_server.py`

### 15.5 Redis 容器启动失败，提示 `Can't handle RDB format version`

这通常不是 Compose 配置错误，而是：

- 你挂载的 `data/redis/` 里已有旧持久化数据
- 当前 Redis 镜像版本太低，读不了已有数据格式

当前仓库已经默认使用：

- `redis:8-alpine`

如果你本地仍然遇到这个问题，优先检查：

- 是否已经重新 `docker compose up -d`
- `docker compose logs --tail=100 redis`

如果 Redis 中只是会话索引缓存，并且你接受重建，也可以清空 `data/redis/` 后再启动。

### 15.6 图片或表格不显示

优先检查：

- `data/stored_files/mineru_output/` 中是否存在对应图片
- 文件服务接口 `/api/v1/files/content/...` 是否可访问
- 回答中的图片路径是否被模型改写
- 浏览器是否仍在使用旧前端代码

### 15.7 聊天页底部出现大块黑色空白

这通常是前端旧 bundle 仍在运行，或者 `web` 容器还没重建。

优先处理：

```bash
DOCKER_BUILDKIT=0 docker compose build --no-cache web
docker compose up -d web
```

然后浏览器强刷页面。

### 15.8 表格检索内容被截断

当前项目已对表格/议程/清单类 query 自动放宽检索预算。如果仍然截断，优先检查：

- `tools/database_toolkit.py` 中预算参数
- 表格切块是否正常
- 原始文档在 MinerU 输出中是否已被截断

### 15.9 Streamlit 和 FastAPI 是否能同时跑

可以，但不建议长期作为主运行方式。因为两套入口已经分化，后续维护更推荐以前后端分离架构为主。

## 16. 仓库提交建议

建议提交：

- 代码
- 配置模板
- 文档
- 轻量测试

不要提交：

- `.env`
- `.user/`
- `models/`
- `data/stored_files/`
- `data/qdrant/`
- `data/redis/`
- `data/lex_index/`
- `frontend/node_modules/`
- `frontend/dist/`
- 大日志与压缩包

推送前建议执行：

```bash
git status
git diff --cached --stat
git check-ignore -v .env models data/stored_files data/qdrant data/redis data/lex_index frontend/node_modules frontend/dist
```

## 17. 当前仓库状态说明

- 主线：前后端分离
- Runtime 依赖：`backend + frontend + qdrant + redis`
- Streamlit：保留但视为旧入口
- 当前状态：Qdrant 服务化、Redis 会话索引化、共享存储根目录统一化均已完成
- 仍未完成：`ChatAgent` 执行态彻底无状态化
- 仓库适合提交为代码仓，不适合直接提交运行数据仓
