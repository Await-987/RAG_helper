# RAG Backend API

FastAPI 后端服务，实现前后端分离架构。

## 快速开始

```bash
# 进入后端目录
cd backend

# 启动服务（默认端口 8000）
python run.py

# 指定端口和主机
python run.py --host 0.0.0.0 --port 8080

# 开发模式（自动重载）
python run.py --reload
```

启动后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/health

## 项目结构

```
backend/
├── run.py                    # 服务启动脚本
├── requirements.txt          # 后端依赖
├── app/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理
│   ├── dependencies.py      # 依赖注入（模型缓存、服务）
│   ├── api/v1/
│   │   ├── router.py        # 路由聚合
│   │   ├── auth.py          # 认证接口
│   │   ├── chat.py          # 聊天接口（SSE）
│   │   ├── files.py         # 文件管理接口
│   │   └── users.py         # 用户管理接口
│   ├── schemas/
│   │   ├── auth.py          # 认证相关 Pydantic 模型
│   │   ├── chat.py          # 聊天相关 Pydantic 模型
│   │   ├── file.py          # 文件相关 Pydantic 模型
│   │   └── user.py          # 用户相关 Pydantic 模型
│   ├── services/
│   │   ├── auth_service.py  # 认证业务逻辑
│   │   ├── chat_service.py  # 聊天业务逻辑 + SessionManager
│   │   ├── file_service.py  # 文件管理业务逻辑
│   │   └── user_service.py  # 用户管理业务逻辑
│   └── core/
│       ├── security.py      # JWT 认证
│       └── middleware.py    # CORS、日志、错误处理
└── tests/
    └── test_auth.py         # 认证测试
```

## API 接口

### 认证模块 `/api/v1/auth`

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/login` | 登录获取 JWT Token | 公开 |
| GET | `/me` | 获取当前用户信息 | 需登录 |
| POST | `/logout` | 登出（客户端丢弃 Token） | 需登录 |

### 聊天模块 `/api/v1/chat`

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/stream` | SSE 流式聊天 | 需登录 |
| DELETE | `/session/{session_id}` | 清空对话历史 | 需登录 |

**SSE 事件类型**：
- `session`: 返回 session_id
- `reasoning`: 思考过程内容
- `content`: 回答内容
- `done`: 完成，包含完整响应
- `error`: 错误信息

### 文件模块 `/api/v1/files`

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/` | 文件列表（分页） | 需登录 |
| POST | `/upload` | 上传文件 | 管理员 |
| POST | `/import` | 导入文件到向量库 | 管理员 |
| DELETE | `/` | 批量删除文件 | 管理员 |
| DELETE | `/{file_tag}` | 删除单个文件 | 管理员 |

### 用户模块 `/api/v1/users`

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/` | 用户列表 | 管理员 |
| POST | `/` | 创建用户 | 管理员 |
| GET | `/{username}` | 获取用户信息 | 管理员 |
| DELETE | `/{username}` | 删除用户 | 管理员 |
| POST | `/change-password` | 修改自己的密码 | 需登录 |
| POST | `/reset-password` | 重置用户密码 | 管理员 |
| POST | `/change-role` | 修改用户角色 | 管理员 |

## 认证方式

使用 JWT Bearer Token 认证：

```bash
# 1. 登录获取 Token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<your_admin_username>","password":"<your_admin_password>"}'

# 2. 使用 Token 访问受保护接口
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <your_token>"
```

## 配置说明

配置通过环境变量管理，支持 `.env` 文件。推荐以根目录 `.env.example` 为模板。

| 环境变量 | 描述 | 默认值 |
|----------|------|--------|
| `SECRET_KEY` | JWT 密钥 | 需要设置 |
| `DEBUG` | 调试模式 | false |
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `url` | API URL | - |
| `MODEL_NAME` | 默认模型名称 | qwq32b |
| `MAIN_AGENT_MODEL_NAME` | 主回答 agent 模型名称 | `MODEL_NAME` |
| `MAIN_AGENT_TEMPERATURE` | 主回答 agent 温度 | 0.2 |
| `MAIN_AGENT_TOP_P` | 主回答 agent top_p | 0.9 |
| `MAIN_AGENT_MAX_TOKENS` | 主回答 agent 最大生成 token 数 | 4000 |
| `MAIN_AGENT_MESSAGE_WINDOW_SIZE` | 主回答 agent 短窗口消息数 | 12 |
| `MAIN_AGENT_SUMMARIZE_THRESHOLD` | 主回答 agent 摘要阈值 | 20 |
| `MAIN_AGENT_PRUNE_TOOL_CALLS` | 是否裁掉工具调用痕迹 | true |
| `MAIN_AGENT_STREAM_ACCUMULATE` | 流式输出时是否内部累积 | false |
| `MAIN_AGENT_SYSTEM_PROMPT_PATH` | 主回答 agent 系统提示词文件路径 | `config/prompts/main_agent_system.txt` |
| `INTENT_ROUTER_MODEL_NAME` | 意图路由器模型名 | `MODEL_NAME` |
| `INTENT_ROUTER_TEMPERATURE` | 意图路由器温度 | 0.0 |
| `INTENT_ROUTER_TOP_P` | 意图路由器 top_p | 1.0 |
| `INTENT_ROUTER_MAX_TOKENS` | 意图路由器最大生成 token 数 | 800 |
| `SEARCH_REWRITER_MODEL_NAME` | 检索改写器模型名 | `MODEL_NAME` |
| `SEARCH_REWRITER_TEMPERATURE` | 检索改写器温度 | 0.1 |
| `SEARCH_REWRITER_TOP_P` | 检索改写器 top_p | 1.0 |
| `SEARCH_REWRITER_MAX_TOKENS` | 检索改写器最大生成 token 数 | 1200 |
| `conan_path` | Embedding 模型路径 | - |
| `reranker_path` | Reranker 模型路径 | - |
| `TABLE_SUMMARY_MODEL_PATH` | 表格摘要模型路径 | - |
| `EMBEDDING_DEVICE` | Embedding 模型设备 | 自动检测 |
| `RERANKER_DEVICE` | Reranker 模型设备 | 自动检测 |
| `TABLE_SUMMARY_DEVICE` | 表格摘要模型设备 | 自动检测 |
| `AGENT_MEMORY_ENABLED` | 是否启用 CAMEL 长期记忆 | true |
| `AGENT_MEMORY_TOKEN_LIMIT` | Agent memory 上下文 token 上限 | 12000 |
| `AGENT_MEMORY_RETRIEVE_LIMIT` | 语义记忆召回条数 | 6 |
| `AGENT_MEMORY_KEEP_RATE` | 历史消息衰减系数 | 0.9 |
| `MEMORY_TOKEN_COUNTER_MODEL` | CAMEL token counter 使用的模型枚举 | GPT_4O_MINI |
| `QDRANT_MODE` | Qdrant 运行模式，`local` 或 `server` | local |
| `QDRANT_URL` | Qdrant 服务地址 | - |
| `QDRANT_LOCAL_PATH` | Qdrant 本地存储目录 | `data/storages` |
| `QDRANT_LEXICAL_INDEX_DIR` | BM25 词汇索引目录 | `data/lex_index` |
| `REDIS_URL` | Redis 地址 | - |
| `REDIS_PREFIX` | Redis key 前缀 | rag |
| `SHARED_STORAGE_ROOT` | 共享数据根目录 | data |

## 核心改造点

### 1. 模型缓存

运行时模型统一收敛到 `backend/app/core/model_runtime.py`，使用模块级缓存：

```python
# backend/app/core/model_runtime.py

_embedding_model_cache = None

def get_embedding_model():
    global _embedding_model_cache
    if _embedding_model_cache is not None:
        return _embedding_model_cache
    # ... 初始化模型
    _embedding_model_cache = model
    return _embedding_model_cache
```

### 2. 会话管理

新增 `SessionManager` 类管理 ChatAgent 实例，并为每个会话挂载 CAMEL `LongtermAgentMemory`（若当前运行环境支持）。每轮对话结束后会把 memory 快照保存到 `data/agent_memory/`，同一个 `session_id` 重建时自动恢复：

```python
class SessionManager:
    def get_or_create(self, session_id: Optional[str] = None) -> Tuple[str, ChatAgent]:
        if session_id not in self._sessions:
            self._sessions[session_id] = self._create_chat_agent()
        return session_id, self._sessions[session_id]
```

### 3. SSE 流式响应

使用 `sse-starlette` 实现 SSE：

```python
@router.post("/stream")
async def stream_chat(request: ChatRequest, ...):
    return EventSourceResponse(
        chat_service.stream_chat(request.message, request.session_id),
        media_type="text/event-stream"
    )
```

### 4. 复用现有代码

- **用户认证**: 复用 `tools/user_auth.py` 中的 `UserAuth` 类
- **数据库工具**: 复用 `tools/database_toolkit.py` 中的 `DatabaseToolkit`
- **文件管理**: 复用 `backend/app/core/file_catalog.py` 中的后端目录/入库辅助函数
- **模型初始化**: 统一使用 `backend/app/core/model_runtime.py`

## 测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio httpx

# 运行测试
python -m pytest backend/tests -v
```

## 注意事项

1. **Qdrant 并发限制**: 本地 Qdrant 存储不支持高并发访问。生产建议使用 Qdrant Server。

2. **Token 过期**: JWT Token 默认 24 小时过期，可在 `config.py` 中修改 `ACCESS_TOKEN_EXPIRE_MINUTES`

3. **CORS 配置**: 默认允许所有来源，生产环境应修改 `CORS_ORIGINS`

## 后续优化建议

1. **数据库连接池**: 对于高并发场景，考虑使用 Qdrant Server
2. **Redis 缓存**: 用于分布式部署时的会话共享
3. **API 限流**: 添加 rate limiting 中间件
4. **WebSocket**: 考虑用 WebSocket 替代 SSE 实现双向通信
5. **单元测试覆盖**: 增加更多测试用例
