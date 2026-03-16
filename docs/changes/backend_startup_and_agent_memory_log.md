# 后端启动预热与 Agent Memory 改动日志

日期：2026-03-16

## 变更目标

本轮修改聚焦两件事：

1. 把文件管理和数据库词汇索引预热放到后端启动阶段执行，避免首次请求冷启动。
2. 给后端 `ChatAgent` 接入完整的 CAMEL memory 机制，并补齐会话持久化与按用户隔离。

## 已完成改动

### 0. 多轮对话工具复用问题修正

涉及文件：

- `backend/app/services/chat_service.py`
- `docs/changes/backend_startup_and_agent_memory_log.md`

问题现象：

- Agent 在第一轮调用 `search_database` 后，后续多轮追问容易直接依据上一次搜索到的内容回答，不再重新调用工具。

原因分析：

- 后端当前实际使用的 system prompt 约束不够强，只要求“事实性问题必须调用工具”，但没有把“每轮事实追问都必须重新检索”写成硬规则。
- 接入 memory 后，历史回答、历史检索结果和摘要会继续出现在上下文中，模型容易把这些旧证据误判为“本轮已足够回答”的依据。

修正内容：

- 强化后端实际使用的 system prompt。
- 明确规定：
  - 每一轮事实性问题都必须调用 `search_database`；
  - 历史对话只允许用于指代消解、补全主体、改写 `query` 和 `intent_description`；
  - 历史回答、历史检索结果、历史摘要都不能直接作为本轮证据；
  - 即使上一轮刚检索过，只要本轮继续追问事实、参数、条件、范围、差异、是否、多少等内容，也必须重新检索；
  - 只有在“本轮调用工具后仍无结果”时，才允许回答知识库中未找到相关信息。
  - 只有当链接对应表格证据时才允许输出图片链接，非表格图片链接默认不输出。

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

### 4. 历史对话功能

涉及文件：

- `backend/app/config.py`
- `backend/app/schemas/chat.py`
- `backend/app/services/chat_service.py`
- `backend/app/api/v1/chat.py`
- `frontend/src/types/chat.ts`
- `frontend/src/stores/chatStore.ts`
- `frontend/src/api/chat.ts`
- `frontend/src/pages/Chat.tsx`

具体改动：

- 新增后端会话转录持久化目录 `data/chat_sessions/<username>/`。
- 每轮聊天会把用户消息和助手消息写入 transcript 文件。
- 新增后端接口：
  - `GET /api/v1/chat/sessions`：获取当前用户的历史会话列表；
  - `GET /api/v1/chat/session/{session_id}`：获取单个历史会话详情；
  - 现有 `DELETE /api/v1/chat/session/{session_id}` 同时删除内存会话、memory 快照和 transcript。
- transcript 与 memory 一样按用户隔离，避免不同用户互相看到历史会话。
- 前端聊天页新增历史对话列表：
  - 左侧展示当前用户的历史会话；
  - 点击会话可恢复历史消息；
  - 支持新建对话；
  - 支持删除单个历史会话。
- 新对话不再自动清除旧会话，而是保留为历史记录，更接近 GPT 类产品的交互方式。
- 清理重复入口后，前端仅保留一个全局“新对话”按钮，避免聊天页出现多个相同操作入口。

### 5. 删除用户时统一清理本地对话与记忆

涉及文件：

- `backend/app/services/user_service.py`
- `docs/changes/backend_startup_and_agent_memory_log.md`

具体改动：

- 管理员删除用户成功后，会自动清理该用户的运行时数据：
  - `data/agent_memory/<username>/`
  - `data/chat_sessions/<username>/`
- 如果该用户当前还有活跃会话在后端内存中，也会同步清理对应 session。
- 这样用户被删除后，本地对话历史、memory 快照和活跃会话状态都会统一回收，避免残留孤儿数据。

### 6. 登录态改为更鲁棒的会话校验

涉及文件：

- `backend/app/config.py`
- `backend/app/core/security.py`
- `frontend/src/stores/authStore.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/chat.ts`
- `frontend/src/api/files.ts`
- `frontend/src/components/Chat/AuthenticatedImage.tsx`
- `frontend/src/pages/Chat.tsx`
- `frontend/src/utils/authToken.ts`

具体改动：

- 后端 JWT 新增 `auth_instance_id` 绑定当前后端实例。
- 后端重启后会生成新的 `AUTH_INSTANCE_ID`，旧 token 将自动失效。
- 前端 token 存储从 `localStorage` 改为 `sessionStorage`，降低长期残留登录态的风险。
- 前端不再持久化 `user`、`isAuthenticated` 这类派生状态，而是在启动时用当前 token 实时校验 `/auth/me`。
- 统一抽出了 `authToken` 工具，避免不同模块混用不同存储逻辑。

结果：

- 后端重启后，旧登录态不会再继续“无感复活”。
- 前端刷新时会以当前 token 的实时校验结果为准，而不是直接相信上一次保存在本地的已登录状态。

### 7. 长 PDF 检索增强：父块去重、邻接补全、问题类型路由

涉及文件：

- `tools/load_files.py`
- `tools/qdrant.py`
- `tools/database_toolkit.py`

具体改动：

- 入库时为每个 chunk 新增 metadata：
  - `chunk_index`
  - `chunk_count`
  - `chunk_type`
- 检索阶段新增 `max_per_parent=1` 约束：
  - 当多个子索引命中同一个父块时，最终只保留一个父块结果。
- 新增邻接补全能力：
  - `QdrantDB.get_file_chunks()`
  - `QdrantDB.get_adjacent_chunks()`
  - 对普通文本命中结果，会按同文件的 `chunk_index` 自动补充相邻 chunk 内容。
- 新增问题类型路由增强：
  - 数值问题优先提升含数字/单位的 chunk；
  - 表格问题优先提升表格块；
  - 普通问答继续走现有 hybrid 检索主链路。
- 同时修正了表格 metadata 的读取方式：
  - 检索层现在会同时兼容 payload 顶层和 `payload.metadata` 中的 `is_table/context_before/context_after`。

效果：

- 大 PDF 中多个子 chunk 指向同一父块时，不会再重复占满返回结果。
- 对长文档的正文问答，命中后能补齐前后相邻上下文，减少“只命中局部碎片导致答偏”的情况。
- 对参数类问题和表格类问题，召回结果会更偏向真正含数值或表格结构的证据块。

注意：

- 邻接补全依赖 `chunk_index` metadata。
- 只有在本次改动之后重新入库的文档，才能完整启用邻接补全。
- 旧库中的历史数据如果没有 `chunk_index`，仍然可以使用：
  - 父块去重
  - 数值问题优先
  - 表格问题优先
  但邻接补全效果会受限。

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

## 多轮对话流式输出卡顿排查与修复

### 现象

- 在同一个会话持续进行 5 到 6 轮后，前端流式输出明显变卡；
- 体感上像是“模型输出慢了”，但实际问题主要集中在流式传输和前端渲染链路。

### 排查结论

本次确认了三个主要瓶颈：

1. 后端 SSE 事件在每个 `content` / `reasoning` 分片里都重复携带整段 `full_response` / `full_reasoning`。
   - 这会导致响应越长，单个事件体越大；
   - 累积下来形成明显的 O(n²) 级别网络传输和 JSON 解析开销。

2. 前端在流式阶段每收到一个事件就立刻写入 Zustand 状态。
   - `Chat.tsx` 整页会随之重新渲染；
   - 历史消息列表也会被连带走一遍渲染流程。

3. `StreamingMessage` 在 `isLoading` 期间其实只显示纯文本预览，但每次渲染仍会先执行 `normalizeChatMarkdown(content)`。
   - 当回答正文越来越长时，这个 Markdown 归一化会反复扫描整段文本；
   - 会进一步放大流式阶段的卡顿。

另外，后端每轮默认执行 `_log_context_budget()` 时会调用 `memory.get_context()`，会额外扫描当前 memory；这不是主因，但在多轮长会话下会增加不必要开销。

### 已做修改

#### 1. 后端流式事件改为只发送增量

文件：

- `backend/app/services/chat_service.py`

修改内容：

- `reasoning` 和 `content` 类型的 SSE 事件不再携带 `full` 字段；
- 流式阶段只发送当前增量片段；
- 最终完整结果仍然通过 `done` 事件返回。

效果：

- 避免把越来越长的完整答案在每个分片里重复传输；
- 显著降低多轮会话下的 SSE 体积和前端 JSON 处理压力。

#### 2. 上下文预算扫描默认关闭

文件：

- `backend/app/config.py`
- `backend/app/services/chat_service.py`

修改内容：

- 新增 `CHAT_CONTEXT_BUDGET_LOG_ENABLED` 配置项，默认 `false`；
- `_log_context_budget()` 只有在显式开启时才会执行。

效果：

- 避免每轮都主动调用 `memory.get_context()` 做预算估算；
- 降低长会话下的额外同步开销。

#### 3. 前端流式状态改为节流刷新

文件：

- `frontend/src/pages/Chat.tsx`

修改内容：

- 对流式 `content` / `reasoning` 使用本地 `ref` 累积；
- 通过约 `33ms` 的定时节流批量刷新到 Zustand；
- 使用 `startTransition(...)` 降低流式更新对主交互线程的抢占。

效果：

- 不再每个 token / 每个 SSE 片段都触发一次页面状态更新；
- 多轮会话下滚动和输入响应更稳定。

#### 4. 历史消息组件避免跟随流式重复渲染

文件：

- `frontend/src/components/Chat/MessageItem.tsx`

修改内容：

- `MessageItem` 改为 `memo(...)` 包装。

效果：

- 流式过程中旧消息不会因为外层页面状态变化而重复渲染；
- 降低消息列表长度增长后的渲染成本。

#### 5. 流式组件在加载阶段不再做完整 Markdown 归一化

文件：

- `frontend/src/components/Chat/StreamingMessage.tsx`

修改内容：

- 仅在流式结束、需要正式渲染 Markdown 时才执行 `normalizeChatMarkdown(content)`；
- 流式中只显示纯文本预览。

效果：

- 避免对增长中的回答正文做高频全量 Markdown 归一化；
- 明显降低流式阶段 CPU 消耗。

### 验证

已执行：

```bash
python -m py_compile backend/app/config.py backend/app/services/chat_service.py
npm run build
```

结果：

- 后端语法校验通过；
- 前端生产构建通过。

### 说明

- 这次修复主要解决的是“会话轮次增加后，流式链路自身越来越重”的问题；
- 如果后续仍然在某些问题上感觉首 token 很慢，那更可能是检索、重排、memory 恢复或模型推理本身的耗时，需要单独做后端耗时埋点继续拆分。

### 后续补丁：历史会话发送后误显示“未收到完整响应，请重试”

排查结果：

- 这不是单纯的前后端重启问题，而是前端流式状态机里的一个逻辑错误；
- `done` 事件到达后，页面先把 `streamingDoneRef.current = true`，但随后又调用了 `resetStreamingBuffers()`；
- 而 `resetStreamingBuffers()` 内部把 `streamingDoneRef.current` 重置成了 `false`；
- 导致流循环结束后仍然会误走兜底分支，追加“未收到完整响应，请重试。”。

已修复：

- `frontend/src/pages/Chat.tsx`

修改内容：

- `resetStreamingBuffers()` 不再重置 `streamingDoneRef.current`；
- 每次真正发起新请求前，再显式将 `streamingDoneRef.current = false`。

效果：

- 正常收到 `done` 事件后，不会再误追加兜底失败消息；
- 历史会话里继续追问时，流式结束逻辑恢复正常。

验证：

```bash
npm run build
```

结果：

- 前端构建通过。

## 多轮会话上下文爆长后的 compact 机制

### 问题现象

- 某些会话在约 16 条消息后触发上游模型 400 错误：

```text
This model's maximum context length is 40960 tokens.
However, your request has 82595 input tokens.
```

- 这说明实际发给模型的上下文已经远超上限，现有的自动摘要没有稳定兜住长会话场景。

### 排查结论

当前实现里会叠加几类上下文：

- system prompt；
- CAMEL memory 的历史上下文；
- 多轮检索返回的大段原文 chunk；
- 工具调用后写回 memory 的历史结果。

虽然 `ChatAgent` 自带 `summarize_threshold`，但在你的实际链路里仍然可能出现：

- 长工具结果累计过多；
- memory 中历史证据过长；
- 自动摘要触发不够稳定，最终仍把超大上下文直接送进模型。

### 已做修改

文件：

- `backend/app/config.py`
- `backend/app/services/chat_service.py`

#### 1. 新增可配置 compact 开关与阈值

新增配置项：

- `AGENT_COMPACT_ENABLED`
- `AGENT_COMPACT_TRIGGER_MESSAGES`
- `AGENT_COMPACT_TRIGGER_CHARS`
- `AGENT_COMPACT_KEEP_RECENT_MESSAGES`

默认值：

- `AGENT_COMPACT_ENABLED=true`
- `AGENT_COMPACT_TRIGGER_MESSAGES=12`
- `AGENT_COMPACT_TRIGGER_CHARS=24000`
- `AGENT_COMPACT_KEEP_RECENT_MESSAGES=4`

含义：

- 当会话消息条数或 transcript 内容长度超过阈值时，主动执行 compact；
- compact 后保留最近若干条消息，其余内容压成摘要。

#### 2. 增加主动 compact

在 `stream_chat()` 里，在真正调用 `chat_agent.step(...)` 之前：

- 读取当前用户该 session 的 transcript；
- 如果消息数或累计字符数超过阈值，则先执行一次 compact。

compact 行为：

- 调用 `chat_agent.summarize(include_summaries=True)` 生成全量摘要；
- `clear_memory()` 清空当前 memory；
- 写回一条 `[CONTEXT_SUMMARY]` 摘要消息；
- 再把最近若干条真实消息回放进 memory；
- 摘要中显式注明“事实性结论仍需在本轮重新调用 search_database 验证”，避免压缩后的摘要被当成直接证据。

#### 3. 增加 token limit 后的自动 compact 重试

如果本轮 `chat_agent.step(...)` 或流式迭代过程中直接抛出 token limit 异常：

- 后端会先自动执行一次 compact；
- 然后对同一条用户消息自动重试一次。

这样即使会话在主动阈值前漏过了，也不会第一时间把 400 直接抛给前端。

### 效果

- 长会话不再只能依赖 CAMEL 的默认自动摘要；
- 会话在进入危险区前就会主动压缩；
- 即使仍然撞上 token limit，也会先 compact 再自动 retry 一次；
- 保留最近几轮上下文，同时把更早历史压成摘要，整体更接近你说的 `compact` 行为。

### 已完成验证

```bash
python -m py_compile backend/app/config.py backend/app/services/chat_service.py
```

结果：

- 后端语法校验通过。

### 后续修复：多轮追问的指代消解与扩展检索

问题现象：

- 第一轮已经围绕某个具体规范、标准或文件完成回答；
- 第二轮继续追问“涉及的表都给我看看”“它具体有哪些附件”“这个规范里怎么规定”等问题时；
- Agent 虽然判断出了“需要强制检索”，但前置检索仍然只拿当前这句短追问本身去搜；
- 结果 query 缺少上一轮主体，容易漂移到别的 PDF 或别的标准。

根因：

- 旧实现里的前置强制检索只做了 `message -> keywordize_query`；
- 没有在强制检索阶段真正做指代消解、主体补全、追问改写；
- 因此“你能把涉及的表都给我看看吗”这类多轮追问，实际检索 query 过于短而且失去上下文主体。

已做修改：

- `backend/app/services/chat_service.py`

新增能力：

- 增加 `SearchRewritePlan` 结构化输出；
- 增加前置 `Search Rewriter` Agent；
- 该 Agent 会读取最近几轮 transcript，上下文改写本轮检索计划；
- 输出：
  - `query`
  - `intent_description`
  - `expanded_queries`
  - `referent`
  - `reason`

新的强制检索流程：

- 先由意图路由 Agent 判断这轮是否必须强制检索；
- 如果需要，再由 `Search Rewriter` Agent 做上下文感知的检索改写；
- 主检索 query 必须补全被省略的主体；
- 允许再追加最多 2 条扩展检索 query，用于：
  - 别名
  - 简称
  - 表号
  - 同义表达
  - 缺失维度补检
- 同一轮多次检索仍复用已有的 turn-scope 证据去重机制，避免重复返回同一批父块。

约束：

- 扩展检索不允许无关泛化到别的文档；
- 如果用户是在问“涉及的表/附表/表格/图片/图表/明细表”，改写阶段会优先补充：
  - 表号
  - 清单表
  - 投标报价表
  - 附表

回退策略：

- 如果 `Search Rewriter` Agent 失败，不会直接退回到原始短 query；
- 会启发式读取最近一条相关用户消息，把上一轮主体和本轮追问拼接后再做 query 提炼；
- 至少保证比“只搜当前短句”更稳。

预期效果：

- 多轮追问时，检索 query 不再丢失上一轮主体；
- “你能把涉及的表都给我看看吗”这类指代型问题，更容易继续落在同一规范/同一文件上；
- 表格类追问也能结合扩展 query 更稳地召回清单表、附表、投标报价表等结果。

验证：

```bash
python -m py_compile backend/app/services/chat_service.py
```

结果：

- 后端语法校验通过。

## 事实性问题强制调用 `search_database`

### 问题背景

- 仅靠 system prompt 约束时，Agent 仍然可能在“是什么 / 定义 / 作用 / 参数 / 是否 / 多少”这类事实性问题上跳过工具调用；
- 原因是工具调用仍由模型自行决定，prompt 只能降低概率，不能强制执行。

### 已做修改

文件：

- `backend/app/services/chat_service.py`

#### 1. 增加事实性问题判定

在后端增加了启发式识别：

- `是什么`
- `什么是`
- `谁是`
- `定义`
- `含义`
- `作用`
- `用途`
- `区别`
- `参数`
- `是否`
- `多少`
- `哪一条 / 哪一项 / 哪一个`

以及部分通用问句模式。

#### 2. 改为前置强制检索

为避免“先判断后放行”破坏流式体验，执行策略进一步调整为：

- 如果判定为事实性问题；
- 后端先直接调用一次 `DatabaseToolkit.search_database(...)`；
- 使用启发式关键词抽取生成 `query`；
- 使用用户原问题作为 `intent_description`；
- 将检索到的证据以强约束提示注入给 Agent。

#### 3. Agent 仍然正常流式输出

新的执行方式下：

- 后端不再先缓冲整轮响应再做放行判断；
- 而是把“强制检索”的动作前移到 `chat_agent.step(...)` 之前；
- Agent 在回答阶段仍然保持正常的 `reasoning/content` 流式输出。

#### 4. 检索失败或无结果时的约束

如果前置检索失败，或知识库未返回有效结果：

- 后端会把“检索失败 / 未找到有效结果”的约束说明注入给 Agent；
- Agent 只能明确说明证据不足或未找到相关信息；
- 禁止基于常识或历史记忆补充事实性答案。

### 行为变化

- 事实性问题现在不再只是“提示词建议调用工具”；
- 而是后端会在回答前直接完成一次强制知识库检索；
- 检索结果会作为本轮回答的唯一证据来源注入给 Agent。

### 额外说明

- 这次调整是为了解决“上一版虽然更稳，但把流式体验打坏了”的问题；
- 现在事实性问题重新恢复正常流式输出和思考过程流式输出；
- 代价是这类问题会在真正开始生成前，多一个后端前置检索步骤。

### 验证

```bash
python -m py_compile backend/app/services/chat_service.py
```

结果：

- 后端语法校验通过。

## 前端图片渲染修复：支持裸 `mineru_output/...jpg` 路径

### 问题现象

- 某些回答里虽然已经输出了图片路径，例如：

```text
mineru_output/1.《20kV及以下配电网工程工程量清单计价规范》_2.jpg
```

- 但前端没有把它渲染成图片，只是当普通文本显示。

### 根因

前端原有图片提取逻辑只识别两类：

- Markdown 图片：`![alt](path)`
- HTML 图片：`<img src="...">`

如果回答里只是“裸路径”：

- `mineru_output/...jpg`
- 或 `data/stored_files/...png`

则不会进入图片附件解析逻辑，因此不会渲染。

### 已做修改

文件：

- `frontend/src/components/Chat/markdown.ts`

新增能力：

- 识别裸的知识库图片路径：
  - `mineru_output/...jpg|png|webp|gif`
  - `data/stored_files/...jpg|png|webp|gif`
- 将这类路径也提取为图片附件；
- 同时从正文里剔除，避免“正文重复显示路径 + 附件区再显示图片”。

### 效果

- 即使 Agent 没有输出标准 Markdown 图片语法，只输出了裸路径；
- 前端也会自动把它识别成附件图片并尝试加载渲染。

### 验证

```bash
npm run build
```

结果：

- 前端生产构建通过。

### 后续补丁：修复 `\[...\]` 公式显示与中文标点中的裸图片路径识别

进一步处理了两个前端渲染问题：

1. 公式定界符问题

- 一些回答会输出 LaTeX 显示公式：

```text
\[
\text{材机费} = \text{消耗性材机费} + \text{机械费}
\]
```

- 前端原先没有把 `\[...\]` / `\(...\)` 统一转换成 `remark-math` 更稳定识别的定界格式；
- 现在在 `frontend/src/components/Chat/markdown.ts` 增加了 `normalizeLatexDelimiters(...)`；
- 会把：
  - `\[...\]` 转成 `$$...$$`
  - `\(...\)` 转成 `$...$`

效果：

- 公式会更稳定地按 KaTeX 方式渲染，而不是原样显示方括号转义文本。

2. 中文标点环境中的裸图片路径

- 之前虽然已经支持裸 `mineru_output/...jpg`，但像下面这种写法仍可能漏掉：

```text
（表格格式及示例见图片链接：mineru_output/xxx.jpg）
```

- 原因是前面的中文冒号 `：`、后面的全角括号 `）` 不在原先正则边界里；
- 现在已扩展裸图片路径识别边界，支持：
  - 前导 `：`、`，`、`（`
  - 结尾 `）`、`。`、`；` 等中文标点

效果：

- 这类嵌在说明文字里的裸图片路径也会被提取到“附件图片”区域并渲染。

验证：

```bash
npm run build
```

结果：

- 前端生产构建通过。

### 后续补丁：支持裸公式行与反引号包裹的图片路径

根据实际返回样例，进一步发现两个边界情况：

1. 裸公式行

示例：

```text
\text{材机费} = \text{消耗性材机费} + \text{机械费}
```

这类内容：

- 本身是 LaTeX 片段；
- 但没有被 `$...$` 或 `$$...$$` 包起来；
- 因此前端不会自动按公式渲染。

已修复：

- 在 `frontend/src/components/Chat/markdown.ts` 增加 `normalizeBareLatexBlocks(...)`；
- 对明显形如 LaTeX 公式的裸行，自动包成显示公式 `$$...$$`。

效果：

- 这类裸公式行会按 KaTeX 正常渲染，而不是以普通文本显示。

2. 反引号包裹的图片路径

示例：

```text
`mineru_output/1.xxx_2.jpg`
```

这类路径：

- 之前只支持裸路径、Markdown 图片、HTML 图片；
- 如果被包在反引号里，会被当成 inline code，导致图片提取再次漏掉。

已修复：

- 新增对反引号包裹的知识库图片路径识别；
- 同时在正文清洗时移除该 inline code 路径，避免正文重复展示。

效果：

- 像你贴出的这类 `` `mineru_output/...jpg` `` 会进入“附件图片”区域渲染。

验证：

```bash
npm run build
```

结果：

- 前端生产构建通过。

### 后续补丁：修复公式后续 Markdown 结构粘连

根据进一步测试，发现另一类渲染问题：

- 公式本身已经正确渲染；
- 但公式后面紧跟的 `---`、`###`、编号列表、项目符号如果被模型输出在同一行，会导致后续整段 Markdown 结构失效；
- 表现为后面的标题、列表、分隔线糊在一起，样式也会串掉。

已修复：

- 在 `frontend/src/components/Chat/markdown.ts` 增加 `normalizeInlineBlockMarkers(...)`；
- 自动把这类 inline 结构拆成真正的块级 Markdown：
  - `---`
  - `###`
  - `1. ...`
  - `- ...`

同时补充了 `cleanupEmptyImageLeadIns(...)`：

- 清理图片路径被提取走之后留下的空壳文字，例如：
  - `（表格格式及示例见图片链接：）`

效果：

- 公式后的标题、分隔线、列表会恢复正常块级排版；
- 不会再和公式样式黏在一起；
- 图片路径被提取后，正文里的残留空壳也会更干净。

验证：

```bash
npm run build
```

结果：

- 前端生产构建通过。

## 将正则判定替换为前置意图理解 Agent

### 背景

- 仅靠关键词/正则判断“这轮是否必须强制检索”仍然不够稳；
- 容易在边界问法、代词追问、主观/事实混合表达里误判；
- 因此改为由一个前置意图理解 Agent 来做检索路由判断。

### 已做修改

文件：

- `backend/app/services/chat_service.py`

#### 1. 新增意图路由结构化输出

新增 `IntentRoutingDecision`：

- `needs_search`
- `confidence`
- `reason`

用于让前置路由 Agent 以结构化结果输出判定，而不是依赖自由文本解析。

#### 2. 新增前置意图理解 Agent

在 `ChatService` 内新增了一个懒加载的 `Intent Router` Agent：

- 使用 `backend_model()`；
- 不挂工具；
- 不做摘要；
- 只负责判断当前轮是否必须强制检索知识库。

它会结合：

- 当前用户问题；
- 最近若干条对话上下文；
- 代词/追问关系；

来决定本轮是否需要前置强制检索。

#### 3. 正则保留为失败兜底

如果意图路由 Agent 发生以下情况：

- 调用失败；
- 未返回结构化结果；

则才会退回原来的关键词/正则判断。

也就是说：

- 现在是“意图理解 Agent 为主”；
- “正则规则为辅”。

### 效果

- 对“这是什么 / 这个流程 / 那它的要求呢 / 这种情况是否适用”这类依赖上下文理解的问法，路由更稳；
- 比单纯正则匹配更适合多轮对话场景；
- 同时保留兜底，不会因为前置分类器偶发失败就完全失去强制检索能力。

### 验证

```bash
python -m py_compile backend/app/services/chat_service.py
```

结果：

- 后端语法校验通过。

### 后续补丁：扩充事实性问题识别范围，减少漏判

进一步补充了事实性问题识别词和模式，新增覆盖：

- `概念 / 解释 / 介绍`
- `联系 / 分类 / 类型`
- `要求 / 依据 / 标准 / 规范`
- `流程 / 步骤 / 条件 / 范围`
- `适用 / 适用于`
- `包括 / 包含`
- `注意事项 / 职责 / 负责`
- `阈值 / 上限 / 下限 / 比例 / 计算 / 公式`
- `怎么规定 / 如何规定 / 怎么要求 / 如何要求`

并补充了多组正则问句模式，用于识别：

- `什么 / 谁 / 哪些 / 哪几 / 多少 / 几...`
- `是否 / 能否 / 可否 / 有没有...`
- `指什么 / 属于什么...`
- `怎么规定 / 如何计算...`

效果：

- 对知识问答页里常见的“是什么、要求、依据、流程、范围、原因、参数、计算方式”等提问，前置强制检索的命中率更高；
- 减少事实问题漏判成普通对话的概率。

验证：

```bash
python -m py_compile backend/app/services/chat_service.py
```

结果：

- 后端语法校验通过。

## 允许证据不足时二次检索 + 当前轮已见证据过滤

### 1. Prompt 增强：证据不足时允许再次检索

文件：

- `backend/app/services/chat_service.py`

更新内容：

- 在 Agent system prompt 中明确增加规则：
  - 如果本轮证据不足以支持完整回答，允许再次调用 `search_database`；
  - 二次检索必须针对缺失信息补检，例如补参数、补范围、补条件、补反例、补表格；
  - 不能机械重复同一 query，也不能重复消费同一批证据。

效果：

- Agent 在“首次检索不够完整”的情况下，不必硬答或直接结束；
- 可以更自然地进行补充检索。

### 2. 当前轮已见证据过滤

文件：

- `tools/database_toolkit.py`
- `backend/app/services/chat_service.py`

实现方式：

- 在 `DatabaseToolkit` 内增加了基于 `ContextVar` 的 turn-scope 去重状态；
- `ChatService.stream_chat()` 在每轮开始时调用 `begin_turn()`，结束时调用 `end_turn()`；
- 同一轮里每次 `search_database` 返回的证据，都会记录一个 evidence key；
- 后续同轮再检索时，优先过滤已经返回过的证据。

evidence key 优先使用：

- `Original_file + page + chunk_index`

若缺少 chunk metadata，则回退到：

- `Original_file + Content`

### 3. 无新增证据时的返回行为

如果本轮后续检索命中的结果全部都已经在本轮返回过：

- 不再把重复结果再返回一遍；
- 直接返回：

```text
No new results from the vector database in this turn.
```

并在日志中记录“本轮后续检索未发现新增证据，已过滤重复结果”。

### 效果

- 同一轮允许补充搜索；
- 但补充搜索会优先返回新增证据，而不是重复父块/重复 chunk；
- 比较适合“第一次搜到定义，第二次补参数/范围/条件”的场景。

### 验证

```bash
python -m py_compile backend/app/services/chat_service.py tools/database_toolkit.py
```

结果：

- 后端语法校验通过。

## token-limit 进一步兜底：检索证据截断 + compact 降级摘要 + 最外层拦截

### 问题背景

在已有 compact 和“开启新对话”兜底后，仍可能遇到 token 400，原因主要有两类：

1. `compact` 本身在超长上下文上调用 `chat_agent.summarize(...)` 时，也可能因为上下文过大而失败；
2. 事实性问题的前置强制检索，如果直接把过长证据注入给 Agent，也会进一步推高输入 token。

### 已做修改

文件：

- `backend/app/config.py`
- `backend/app/services/chat_service.py`

#### 1. 限制前置检索证据注入长度

新增配置项：

- `FACTUAL_EVIDENCE_MAX_CHARS`

默认值：

- `6000`

行为：

- 对事实性问题前置检索得到的 evidence，在注入给 Agent 前先按字符数截断；
- 避免把过长检索结果直接塞进 prompt。

#### 2. compact 失败时改走降级摘要

如果 `chat_agent.summarize(include_summaries=True)` 失败：

- 不再直接放弃 compact；
- 改为基于 transcript 构建一个轻量级降级摘要；
- 仅保留最近若干条用户/助手消息的截断文本，用于继续会话。

效果：

- 即使 LLM 摘要本身在超长上下文上失败，compact 仍然能继续完成；
- 不会因为“compact 也失败”而把原始 token 错误继续放大。

#### 3. 最外层 token-limit 漏网拦截

在 `stream_chat()` 的最外层异常处理中新增了 token-limit 拦截：

- 如果还有漏网的 token limit 异常冒泡到最外层；
- 后端直接返回一条正常的 `done` 事件；
- 内容为“当前对话过长，请开启新对话继续”；
- 不再把底层 400 直接暴露给前端。

### 效果

- 极端长会话下，compact 不再因为自身摘要失败而完全失效；
- 事实性问题的前置证据注入更克制，不容易把 prompt 自己撑爆；
- 即使仍有漏网 token-limit，也会优先转换成用户可执行的提示，而不是原始 400 报错。

### 验证

```bash
python -m py_compile backend/app/config.py backend/app/services/chat_service.py
```

结果：

- 后端语法校验通过。

## 进一步修复：长会话恢复后先按 transcript 重建精简 memory

### 新定位到的根因

从实际日志看，问题并不只是“前置强制搜索太长”，而是：

- session 在进入本轮前已经执行了 `Restored agent memory from ...`；
- 恢复出来的旧 memory 本身已经膨胀；
- 当前轮再叠加前置检索证据后，最终把输入直接推到二十多万 token。

也就是说：

- 前置强制搜索是触发点；
- 但真正的底层根因是“恢复后的历史 memory 已经过大，继续沿用它进入新一轮生成”。

### 已做修改

文件：

- `backend/app/services/chat_service.py`

新增逻辑：

- 在每轮真正 `step(...)` 之前，如果 transcript 已达到 compact 阈值；
- 优先不再继续沿用已恢复的膨胀 memory；
- 而是直接基于 transcript 重新构造一份精简 memory。

重建方式：

- 保留一条轻量级 `[CONTEXT_SUMMARY]`；
- 只回放最近若干条消息；
- 用户消息、助手消息、reasoning 都做了字符截断；
- 重建后立即覆盖并保存当前 session memory。

效果：

- 长会话不会继续背着历史膨胀的 memory 前进；
- 每轮开始前都会先把真正送给模型的 memory 控制在更小范围；
- 比“恢复旧 memory 然后指望后面再 compact”更稳。

### 验证

```bash
python -m py_compile backend/app/services/chat_service.py
```

结果：

- 后端语法校验通过。

### 说明

- 这次 compact 只影响后端 Agent memory，不会删除前端历史会话列表，也不会丢 transcript；
- 前端仍然能看到完整历史消息，compact 只是减少后续继续问答时真正送给模型的上下文体积；
- 这次修改需要重启后端后才会生效。

### 后续补丁：compact 后仍超限时提示开启新对话

进一步处理：

- 即使已经执行 proactive compact 或 token-limit retry compact，极端情况下仍可能继续超过模型上限；
- 例如：压缩摘要本身仍然较长、最近保留消息较长、且本轮又触发了大段检索证据。

已补充兜底逻辑：

- `backend/app/services/chat_service.py`

行为：

- 如果 compact 之后再次命中 token limit；
- 后端不再把底层 400 直接透传给前端；
- 而是返回一条正常的 assistant 消息，明确提示用户“当前对话过长，请开启新对话继续”。

效果：

- 前端不会再直接看到底层模型的超长上下文报错；
- 用户会收到可执行的下一步指引。

验证：

```bash
python -m py_compile backend/app/services/chat_service.py
```

结果：

- 后端语法校验通过。
