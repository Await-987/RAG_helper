# 后端启动预热与 Agent Memory 改动日志

日期：2026-03-16

## 变更目标

本轮修改聚焦两件事：

1. 把文件管理和数据库词汇索引预热放到后端启动阶段执行，避免首次请求冷启动。
2. 给后端 `ChatAgent` 接入完整的 CAMEL memory 机制，并补齐会话持久化与按用户隔离。

## 已完成改动

### 1. 后端启动阶段预热

涉及文件：

- `backend/app/main.py`
- `backend/app/dependencies.py`
- `backend/app/services/file_service.py`
- `docs/前后端分离项目架构详解.md`

具体改动：

- 在 `FastAPI lifespan` 启动阶段调用统一初始化入口 `init_backend_startup()`。
- 启动时主动初始化共享 `DatabaseToolkit`。
- 启动时预热数据库词汇索引与 reranker，避免首次检索长时间等待。
- 启动时调用 `FileService.warmup()`，提前完成文件管理依赖准备。
- `FileService.warmup()` 会：
  - 确保存储目录存在；
  - 确保 `mineru_output` 目录存在；
  - 提前执行一次文件列表与数据库切片统计，建立文件管理所需缓存。
- 服务关闭时增加 `cleanup_database_toolkit()`，释放共享数据库工具。

### 2. Agent 接入 CAMEL Long-Term Memory

涉及文件：

- `agents/backend_model.py`
- `backend/app/services/chat_service.py`
- `backend/app/config.py`
- `backend/README.md`

具体改动：

- 在 `SessionManager` 中新增 `_build_agent_memory()`。
- 每个新的聊天会话创建 `ChatAgent` 时，优先挂载：
  - `ScoreBasedContextCreator`
  - `ChatHistoryBlock`
  - `VectorDBBlock`
  - `LongtermAgentMemory`
- `ScoreBasedContextCreator` 负责按 token 上限裁剪上下文。
- `ChatHistoryBlock` 负责保留近期会话历史。
- `VectorDBBlock` 负责做语义记忆检索。
- `VectorDBBlock` 复用了当前项目已有的 embedding 模型，而不是额外引入另一套向量模型。
- 为模型后端和 memory context creator 增加了 token counter 回退逻辑：
  - 优先使用 `OpenAITokenCounter`
  - 当前环境若无法完成 `tiktoken` 编码初始化，则回退到 `StubTokenCounter`
- 如果当前运行环境的 CAMEL 版本不支持这些 memory API，会自动降级回默认 memory，不阻塞服务启动。

### 3. Agent Memory 持久化

涉及文件：

- `backend/app/services/chat_service.py`
- `backend/app/config.py`

具体改动：

- 新增 `AGENT_MEMORY_DIR` 配置，默认目录为 `data/agent_memory`。
- 每轮聊天结束后，调用 `save_session_memory()` 将当前 memory 快照保存到磁盘。
- 当已有 `session_id` 再次进入时，调用 `_restore_session_memory()` 从磁盘恢复 memory。
- 清理会话时，同时删除内存中的会话对象和磁盘上的 memory 快照文件。

## 当前用户隔离策略

当前实现已经支持按用户隔离，不再只是按 `session_id` 隔离。

具体策略：

- `Chat API` 在调用 `ChatService.stream_chat()` 时会传入当前登录用户的 `username`。
- `SessionManager.get_or_create()` 会校验会话归属：
  - 新建会话时记录所属用户；
  - 已存在的会话如果不属于当前用户，则拒绝复用。
- `clear_session()` 也会校验用户归属，防止用户删除别人的会话。
- memory 持久化文件按用户分目录存储：
  - `data/agent_memory/<username>/<session_id>.json`

这意味着：

- 不同用户之间的 memory 不共享。
- 即便两个用户拿到了相同的 `session_id` 字符串，也不能互相复用会话 memory。
- 同一个用户可以通过自己的 `session_id` 恢复自己的历史 memory。

## 新增配置项

位于 `backend/app/config.py`：

- `AGENT_MEMORY_ENABLED`
- `AGENT_MEMORY_DIR`
- `AGENT_MEMORY_TOKEN_LIMIT`
- `AGENT_MEMORY_RETRIEVE_LIMIT`
- `AGENT_MEMORY_KEEP_RATE`
- `MEMORY_TOKEN_COUNTER_MODEL`

说明：

- `AGENT_MEMORY_ENABLED`：是否启用 CAMEL memory。
- `AGENT_MEMORY_DIR`：memory 快照存储目录。
- `AGENT_MEMORY_TOKEN_LIMIT`：上下文 token 限制。
- `AGENT_MEMORY_RETRIEVE_LIMIT`：语义记忆召回数量。
- `AGENT_MEMORY_KEEP_RATE`：历史消息保留权重。
- `MEMORY_TOKEN_COUNTER_MODEL`：CAMEL token counter 使用的模型枚举名称。

## 已完成验证

- 已执行：

```bash
python3 -m py_compile backend/app/main.py backend/app/dependencies.py backend/app/services/file_service.py
python3 -m py_compile backend/app/config.py backend/app/services/chat_service.py
```

- 结果：
  - 语法校验通过。

补充运行时验证（虚拟环境中）：

- 已确认当前运行环境可正常导入：
  - `camel==0.2.81a0`
  - `ChatAgent(memory=...)`
  - `LongtermAgentMemory`
  - `ScoreBasedContextCreator`
  - `VectorDBBlock`
  - `ChatAgent.save_memory(...)`
  - `ChatAgent.load_memory_from_path(...)`
- 已成功完成最小化实例化验证：
  - 本地 embedding 模型可正常加载；
  - `LongtermAgentMemory` 可正常构建；
  - `ChatAgent` 可在挂载该 memory 的情况下成功初始化。
- 验证中发现两个环境相关问题：
  - 当本地 `Qdrant` 存储目录已被另一实例占用时，`SessionManager.get_or_create()` 的完整链路会因知识库 `DatabaseToolkit` 初始化失败而中断；
  - 当前环境第一次触发 `tiktoken` 编码加载时可能尝试联网，因此已补充 token counter 回退逻辑以降低初始化失败概率。

## 当前限制

- 本地 Qdrant 仍然不支持并发访问；如果另一个进程已占用 `data/storages`，完整的知识库 Agent 装配依旧会被阻塞。
- 当前已验证 memory 本身和最小化 Agent 初始化可用；若要做完整的知识库对话链路验证，需要保证 Qdrant 存储未被其他进程占用，或改用 Qdrant Server。

## 后续建议

建议下一步补两项：

1. 在实际后端运行环境中确认 CAMEL 版本是否支持：
   - `LongtermAgentMemory`
   - `ScoreBasedContextCreator`
   - `VectorDBBlock(embedding=...)`
   - `ChatAgent.save_memory(...)`
   - `ChatAgent.load_memory_from_path(...)`
2. 增加一个仅管理员可见的调试接口，用于查看某个 session 当前 memory 是否已恢复、当前上下文 token 估算和 memory 文件路径。
