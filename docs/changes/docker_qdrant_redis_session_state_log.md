# Docker Qdrant / Redis 会话状态改动日志

日期：2026-03-16

## 变更目标

本轮修改继续推进 Docker 可扩容方案，完成两项基础设施改造：

1. 把向量库接入从本地 embedded Qdrant 切到独立 `qdrant` 服务。
2. 把聊天会话的索引与元数据迁到 `redis`，为后续多 backend 做准备。

## 已完成改动

### 1. Qdrant 支持 local / server 双模式

涉及文件：

- `tools/qdrant.py`
- `backend/app/config.py`
- `docker-compose.yml`

具体改动：

- 新增 `QDRANT_MODE` 配置，支持：
  - `local`
  - `server`
- 新增配置项：
  - `QDRANT_URL`
  - `QDRANT_API_KEY`
  - `QDRANT_LEXICAL_INDEX_DIR`
  - `QDRANT_INIT_RETRIES`
  - `QDRANT_INIT_DELAY_SEC`
- `tools/qdrant.py` 在 `server` 模式下通过 `QdrantStorage(url_and_api_key=...)` 连接独立 Qdrant 服务。
- 词汇索引缓存目录从原本依附本地向量库存储目录的方式中拆出，独立到 `data/lex_index/`。
- 后端在 Docker Compose 中默认使用：
  - `QDRANT_MODE=server`
  - `QDRANT_URL=http://qdrant:6333`

结果：

- 当前 Docker 部署默认不再依赖 backend 容器内部的本地 embedded Qdrant。
- 本地 `local` 模式仍然保留，用于单机调试或历史脚本兼容。

### 2. Docker Compose 新增 Qdrant 服务

涉及文件：

- `docker-compose.yml`
- `README.md`

具体改动：

- 新增 `qdrant` 服务。
- Qdrant 持久化目录挂载到：
  - `data/qdrant/`
- backend 显式依赖 `qdrant`。
- README 中的默认部署结构、数据目录、日志查看命令已同步更新。

### 3. Redis 会话存储接入

涉及文件：

- `backend/app/core/redis_client.py`
- `backend/app/config.py`
- `backend/app/services/chat_service.py`
- `backend/requirements.txt`
- `docker-compose.yml`

具体改动：

- 新增共享 Redis 客户端模块 `backend/app/core/redis_client.py`。
- 新增配置项：
  - `REDIS_URL`
  - `REDIS_PREFIX`
  - `REDIS_SOCKET_TIMEOUT_SEC`
  - `REDIS_SOCKET_CONNECT_TIMEOUT_SEC`
- `docker-compose.yml` 新增 `redis` 服务，并默认向 backend 注入：
  - `REDIS_URL=redis://redis:6379/0`
- `backend/requirements.txt` 新增 `redis` Python 依赖。

### 4. SessionManager 会话元数据迁移到 Redis

涉及文件：

- `backend/app/services/chat_service.py`
- `backend/app/services/user_service.py`
- `backend/app/main.py`

具体改动：

- 在 `chat_service.py` 中新增 `RedisSessionStore`：
  - 使用 Redis 存储单个会话元数据；
  - 使用 Redis Sorted Set 存储每个用户的会话索引。
- Redis 中共享的元数据包含：
  - `session_id`
  - `username`
  - `title`
  - `created_at`
  - `updated_at`
  - `last_activity`
  - `message_count`
  - `memory_enabled`
- `SessionManager` 现在采用三层状态来源：
  - 进程内 `_session_metadata` 缓存
  - Redis 真相源
  - transcript 文件回填
- 会话列表 `list_sessions()` 现在会：
  - 优先读取 Redis 中的用户会话索引；
  - 再扫描本地 transcript 文件补齐；
  - 自动把文件中缺失的元数据回写到 Redis。
- `clear_session()` 现在会同步清理：
  - 进程内 active session
  - Redis 元数据
  - Redis 用户会话索引
  - 本地 memory 文件
  - 本地 transcript 文件
- `UserService` 删除用户时不再直接读取 `_session_metadata` 内部字典，而是通过 `list_session_ids_for_user()` 做统一清理。
- FastAPI 关闭时会显式关闭 Redis 客户端。

结果：

- 当前会话列表、标题、消息数、最近活跃时间、归属用户已经支持跨 backend 共享。
- 旧的 transcript 文件在首次访问时会自动回填进 Redis，不需要手工迁移。

### 5. 当前仍未完成的部分

虽然 Redis 已经接入，但当前还没有做到完整无状态：

- `ChatAgent` 实例本身仍在进程内；
- `agent_memory` 仍落盘到 `data/agent_memory/`；
- transcript 正文仍落盘到 `data/chat_sessions/`；
- 一个会话如果真正切到另一个 backend 副本，仍需要进一步处理执行态恢复。

因此当前部署仍然保持：

- 单个 backend
- `BACKEND_WORKERS=1`

这仍然是现阶段最稳妥的运行方式。

## 已完成验证

已执行：

```bash
python -m py_compile backend/app/core/redis_client.py
python -m py_compile backend/app/config.py
python -m py_compile backend/app/main.py
python -m py_compile backend/app/services/chat_service.py
python -m py_compile backend/app/services/user_service.py
docker compose config
```

补充验证：

- 已确认 `QDRANT_MODE=server` 配置可被运行时正确解析。
- 已确认 Compose 中包含：
  - `redis`
  - `qdrant`
  - `backend`
  - `web`

## 当前默认部署形态

```text
browser
  |
  v
nginx
  |
  +--> backend
         |
         +--> redis
         +--> qdrant
         +--> data/   (transcript / memory / files / lex_index)
         +--> models/
         +--> .user/
```

## 下一步建议

下一步应该做的是：

1. 把文件路径统一抽象为 `SHARED_STORAGE_ROOT`
2. 再评估 transcript / agent memory 是否迁移到共享存储或对象存储
3. 最后再考虑多 backend 副本和 Nginx 负载均衡
