# 可扩容 Docker 部署方案

本文档给出当前项目面向多人共享和后端横向扩容时的唯一推荐部署方案。

注意：这是一份目标架构设计，不是当前仓库已经完全实现的即插即用配置。当前代码仍存在本地会话和本地向量库存储依赖，必须先完成下面列出的改造点，才能安全启用多后端负载均衡。

## 1. 推荐架构

```text
browser
  |
  v
nginx
  |
  +--> backend-1
  +--> backend-2
  +--> backend-3
         |
         +--> redis
         +--> qdrant
         +--> shared-files
         +--> models
```

职责划分：

- `nginx`：托管前端静态资源，负责 `/api` 反向代理、SSE 转发、负载均衡
- `backend-*`：只负责 FastAPI 业务逻辑，设计目标是无状态
- `redis`：保存共享会话状态、session 元信息、短期缓存
- `qdrant`：独立向量库服务，替代本地 `data/storages`
- `shared-files`：上传文件、MinerU 输出、截图等共享文件根目录
- `models`：本地 embedding/reranker/summary 模型目录

## 2. 宿主机目录建议

推荐把当前零散目录收束为以下结构：

```text
deploy-data/
├── qdrant/              # Qdrant 持久化数据
├── redis/               # Redis 持久化数据
└── files/               # 共享文件根目录
    ├── stored_files/
    ├── mineru_output/
    ├── content_lists/
    ├── exported_chunks/
    ├── agent_memory/
    └── chat_sessions/

models/                  # 本地模型
.user/                   # 用户与鉴权数据
```

推荐挂载关系：

- `./deploy-data/qdrant:/qdrant/storage`
- `./deploy-data/redis:/data`
- `./deploy-data/files:/app/shared-files`
- `./models:/app/models`
- `./.user:/app/.user`

## 3. 服务关系

### 3.1 Nginx

- 对外只暴露一个端口
- 提供前端静态文件
- `/api` 转发到多个 backend
- 对 SSE 关闭代理缓冲
- 可按需使用 least_conn 或 ip_hash

### 3.2 Backend

目标是多副本、无状态：

- 不再把 session 只保存在进程内
- 不再把 agent memory 只保存在本地文件
- 不再直接依赖本地 `data/storages`
- 文件读写统一走共享文件根目录

### 3.3 Redis

建议承担：

- 会话索引
- session 元信息
- 聊天短期状态
- 可选：JWT 黑名单或刷新 token 相关状态

### 3.4 Qdrant

Qdrant 必须改成独立服务，原因如下：

- 当前代码虽然已支持 `local/server` 双模式，但生产部署默认已经切到独立 `qdrant` 服务
- 多 backend 同时访问本地目录型向量库不可靠
- 横向扩容需要所有 backend 指向同一个向量库服务

## 4. 当前代码中的主要阻塞点

### 4.1 Qdrant 服务模式

当前 [`tools/qdrant.py`](/home/ubuntu/rag_project/rag/tools/qdrant.py) 已支持：

- `QDRANT_MODE=local`
- `QDRANT_MODE=server`
- `QDRANT_URL`
- `QDRANT_API_KEY`（可选）
- `QDRANT_LEXICAL_INDEX_DIR`

当前根目录 Docker Compose 默认采用 `QDRANT_MODE=server`，并连接容器内的 `qdrant:6333`。

保留 `local` 模式只是为了兼容本地脚本或临时调试；生产部署应固定使用 `server` 模式。

### 4.2 会话状态在进程内 + 本地文件

当前 [`backend/app/services/chat_service.py`](/home/ubuntu/rag_project/rag/backend/app/services/chat_service.py) 中已经把会话索引和元数据接到了 Redis，但仍存在：

- `self._sessions`
- `data/agent_memory`
- `data/chat_sessions`

这意味着多 backend 下“会话列表和元信息”已经可以共享，但真正的 `ChatAgent` 执行态和 memory 快照恢复还没有完全无状态化。

目标改造方向：

- 保留 Redis 作为会话索引和 session 元信息的真相源
- 进程内 `_sessions` 只作为本地短缓存，不能作为唯一真相来源
- `agent_memory` 和 `chat_sessions` 迁移到共享文件路径，或进一步迁移到对象存储/数据库

### 4.3 共享文件根目录

当前代码已经新增统一环境变量：

- `SHARED_STORAGE_ROOT`

并将以下目录统一改为从该根目录派生：

- `stored_files`
- `stored_files/mineru_output`
- `content_lists`
- `exported_chunks`
- `agent_memory`
- `chat_sessions`

当前根目录 Docker Compose 默认使用：

```env
SHARED_STORAGE_ROOT=data
```

后续如果切到专门的共享挂载目录，只需要让 volume 和 `SHARED_STORAGE_ROOT` 保持一致。

## 5. 推荐环境变量

建议新增或统一以下变量：

```env
# 对话模型
OPENAI_API_KEY=...
url=...
MODEL_NAME=...

# 共享模型目录
conan_path=/app/models/bge-base-zh-v1.5
reranker_path=/app/models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=/app/models/Qwen2.5-1.5B-Instruct

# 共享文件目录
SHARED_STORAGE_ROOT=/app/shared-files

# Redis
REDIS_URL=redis://redis:6379/0

# Qdrant
QDRANT_MODE=server
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=database

# 鉴权
SECRET_KEY=change-me
```

## 6. 推荐 Compose 结构

这是目标结构示意，不应在当前代码未改完前直接上线：

```yaml
services:
  nginx:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    depends_on:
      - backend
    ports:
      - "8080:80"

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    deploy:
      replicas: 3
    env_file:
      - .env
    environment:
      SHARED_STORAGE_ROOT: /app/shared-files
      REDIS_URL: redis://redis:6379/0
      QDRANT_MODE: server
      QDRANT_URL: http://qdrant:6333
    volumes:
      - ./deploy-data/files:/app/shared-files
      - ./models:/app/models
      - ./.user:/app/.user

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - ./deploy-data/redis:/data

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - ./deploy-data/qdrant:/qdrant/storage
```

## 7. 唯一推荐的演进顺序

不要一次性把所有东西都改掉。建议严格按下面顺序推进：

1. 已完成：把 Qdrant 改成独立服务接入，并保留 local fallback
2. 已完成：把会话元数据和 session 索引迁到 Redis
3. 已完成：把文件、transcript、memory 路径统一改到 `SHARED_STORAGE_ROOT`
4. 把真正的会话执行态进一步去状态化
5. 最后再开启多个 backend 副本和 Nginx 负载均衡

## 8. 当前阶段的过渡建议

如果暂时不想做大改造，最稳妥的过渡方案是：

```text
nginx
  |
  +--> 单个 backend
  +--> redis
  +--> qdrant
```

也就是：

- 先不扩 backend 副本
- 已经把 `qdrant` 和 `redis` 服务化
- transcript 和 agent memory 仍保留文件持久化
- 等 backend 去状态化后，再扩容 backend

这也是当前仓库默认 Docker 部署已经采用的第一阶段形态。
