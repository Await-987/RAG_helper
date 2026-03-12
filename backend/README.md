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
  -d '{"username":"admin","password":"admin123"}'

# 2. 使用 Token 访问受保护接口
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <your_token>"
```

## 配置说明

配置通过环境变量管理，支持 `.env` 文件：

| 环境变量 | 描述 | 默认值 |
|----------|------|--------|
| `SECRET_KEY` | JWT 密钥 | 需要设置 |
| `DEBUG` | 调试模式 | false |
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `url` | API URL | - |
| `MODEL_NAME` | 模型名称 | qwq32b |
| `conan_path` | Embedding 模型路径 | - |
| `reranker_path` | Reranker 模型路径 | - |

## 核心改造点

### 1. 模型缓存（移除 Streamlit 依赖）

原代码使用 `@st.cache_resource`，改为模块级缓存：

```python
# backend/app/dependencies.py

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

新增 `SessionManager` 类管理 ChatAgent 实例：

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
- **文件管理**: 复用 `tools/file_manager_ui.py` 中的函数
- **模型初始化**: 复用 `agents/backend_model.py` 中的模型工厂函数

## 测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio httpx

# 运行测试
cd backend
pytest tests/ -v
```

## 注意事项

1. **Qdrant 并发限制**: 本地 Qdrant 存储不支持并发访问。如果 Streamlit 正在运行，后端首次访问数据库时会报错。解决方案：
   - 使用 Qdrant Server 替代本地存储
   - 或者停止 Streamlit 后再启动后端

2. **Token 过期**: JWT Token 默认 24 小时过期，可在 `config.py` 中修改 `ACCESS_TOKEN_EXPIRE_MINUTES`

3. **CORS 配置**: 默认允许所有来源，生产环境应修改 `CORS_ORIGINS`

## 后续优化建议

1. **数据库连接池**: 对于高并发场景，考虑使用 Qdrant Server
2. **Redis 缓存**: 用于分布式部署时的会话共享
3. **API 限流**: 添加 rate limiting 中间件
4. **WebSocket**: 考虑用 WebSocket 替代 SSE 实现双向通信
5. **单元测试覆盖**: 增加更多测试用例
