# 智能设计助手 RAG

面向电力系统与国家电网业务场景的 RAG 项目。当前主线是前后端分离架构：

- `frontend/`：React + Vite 前端，负责聊天、文件管理、用户管理、消息渲染
- `backend/`：FastAPI 后端，负责鉴权、会话、流式回答、文件服务接口
- `tools/`、`agents/`、`config/`、`data/`、`models/`：前后端共享的知识库、解析、检索和模型资源

项目内仍保留 `run/streamlit.py` 作为旧入口，但不再是推荐主路径。后续如果继续演进，建议以前后端分离版本为准。

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
- 兼容旧版 Streamlit 入口

## 2. 当前架构

### 2.1 主线架构

```text
用户浏览器
   |
   v
frontend (React/Vite, :3000)
   |
   |  /api 代理
   v
backend (FastAPI, :8000)
   |
   +--> agents/   对话与模型装配
   +--> tools/    入库、解析、检索、Qdrant
   +--> data/     上传文件、图片、向量库
   +--> models/   本地模型
```

### 2.2 旧入口

```text
streamlit run run/streamlit.py
```

旧入口仍可运行，但其 UI、鉴权和前后端逻辑与当前主线已经分离，后续维护建议优先以 `frontend/ + backend/` 为主。

## 3. 目录结构

```text
rag/
├── frontend/                        # React/Vite 前端
│   ├── src/
│   │   ├── api/                     # 前端 API 调用
│   │   ├── components/              # 消息、布局等组件
│   │   ├── pages/                   # 页面
│   │   ├── stores/                  # Zustand 状态管理
│   │   └── types/                   # TS 类型定义
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                         # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/                  # 路由
│   │   ├── services/                # 业务服务
│   │   ├── schemas/                 # Pydantic 模型
│   │   ├── core/                    # 安全、日志、中间件
│   │   ├── dependencies.py          # 依赖注入
│   │   └── main.py                  # FastAPI 应用入口
│   ├── run.py                       # 启动脚本
│   └── requirements.txt
│
├── agents/                          # Agent 与模型装配
│   ├── backend_model.py             # LLM / embedding / reranker / 表格摘要模型
│   └── chat_agent.py                # 系统提示词与 Agent 工厂
│
├── tools/                           # 核心能力
│   ├── database_toolkit.py          # 检索工具入口
│   ├── load_files.py                # 文档解析、切块、入库
│   ├── mineru_toolkit.py            # MinerU 封装
│   ├── qdrant.py                    # Qdrant 检索与混合检索
│   ├── file_manager_ui.py           # 文件管理与入库辅助
│   └── user_auth.py                 # 用户鉴权底层能力
│
├── config/                          # 公共配置
│   └── mineru.json
│
├── data/                            # 运行数据
│   ├── storages/                    # Qdrant 本地存储
│   ├── stored_files/                # 上传文档
│   │   └── mineru_output/           # 图片/表格截图输出
│   ├── content_lists/               # 文档解析结果缓存
│   └── exported_chunks/             # 调试导出的切块
│
├── models/                          # 本地模型目录
├── docs/                            # 设计与变更文档
├── scripts/                         # 下载模型、批量导入等脚本
├── run/                             # 旧版 Streamlit
├── tests/                           # 公共测试
├── README.md
└── .gitignore
```

## 4. 功能模块说明

### 4.1 前端

前端主要负责：

- 登录与用户态维护
- 会话聊天页面
- 文件管理页面
- 用户管理页面
- 消息内 markdown / 表格 / 附件图片渲染

关键目录：

- `frontend/src/components/Chat/`
  消息渲染、流式渲染、表格渲染、附件图片区
- `frontend/src/api/`
  对后端的 API 封装
- `frontend/src/stores/`
  聊天状态、鉴权状态

### 4.2 后端

后端主要负责：

- JWT 鉴权
- 会话管理
- 聊天 SSE 流式响应
- 文件上传、导入、删除、内容预览
- 调用共享 `tools/` 和 `agents/`

关键目录：

- `backend/app/api/v1/`
  路由层
- `backend/app/services/`
  聊天、文件、用户、鉴权服务
- `backend/app/core/`
  JWT、安全、中间件、请求日志

### 4.3 共享核心能力

- `tools/load_files.py`
  PDF 解析、MinerU 输出接入、图片重命名、切块、入库
- `tools/database_toolkit.py`
  对外暴露给 Agent 的检索工具
- `tools/qdrant.py`
  Qdrant 本地存储、检索、混合检索、动态阈值、重排序
- `agents/backend_model.py`
  模型初始化与缓存
- `agents/chat_agent.py`
  问答 Agent 的提示词约束

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
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 6.2 前端环境

```bash
cd frontend
npm install
cd ..
```

## 7. 环境变量

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

## 8. 模型与数据目录

以下目录默认不提交远程仓库：

- `models/`
- `data/storages/`
- `data/stored_files/`
- `data/content_lists/`
- `data/exported_chunks/`
- `.user/`

这些目录分别存放：

- 本地模型
- Qdrant 向量库
- 上传原始文件
- MinerU 输出图片/表格截图
- 文档解析缓存
- 用户数据

## 9. 启动方式

### 9.1 推荐：前后端分离

启动后端：

```bash
source .venv/bin/activate
cd backend
python3 run.py
```

默认地址：

- `http://localhost:8000`
- Swagger：`http://localhost:8000/docs`

启动前端：

```bash
cd frontend
npm run dev
```

默认地址：

- `http://localhost:3000`

前端会把 `/api` 自动代理到 `http://localhost:8000`。

### 9.2 旧版 Streamlit

```bash
source .venv/bin/activate
streamlit run run/streamlit.py
```

默认地址：

- `http://localhost:8501`

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

## 12. API 简述

### 12.1 鉴权

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

### 12.2 聊天

- `POST /api/v1/chat/stream`
- `DELETE /api/v1/chat/session/{session_id}`

### 12.3 文件

- `GET /api/v1/files`
- `POST /api/v1/files/upload`
- `POST /api/v1/files/import`
- `GET /api/v1/files/content/{file_tag}`
- `DELETE /api/v1/files`

### 12.4 用户

- `GET /api/v1/users`
- `POST /api/v1/users`
- `POST /api/v1/users/change-password`
- `POST /api/v1/users/reset-password`

更多细节见：

- `backend/README.md`
- `http://localhost:8000/docs`

## 13. 测试与检查

### 13.1 Python 测试

```bash
source .venv/bin/activate
python3 -m pytest
```

### 13.2 前端构建检查

```bash
cd frontend
npm run build
```

### 13.3 后端启动检查

```bash
cd backend
python3 run.py
```

## 14. 常见问题

### 14.1 前端页面一直 loading

优先检查：

- 前端是否跑在 `3000`
- 后端是否跑在 `8000`
- 浏览器是否拿到旧 bundle
- `/api/v1/auth/me` 是否异常

### 14.2 图片或表格不显示

优先检查：

- `data/stored_files/mineru_output/` 中是否存在对应图片
- 文件服务接口 `/api/v1/files/content/...` 是否可访问
- 回答中的图片路径是否被模型改写
- 浏览器是否仍在使用旧前端代码

### 14.3 表格检索内容被截断

当前项目已对表格/议程/清单类 query 自动放宽检索预算。如果仍然截断，优先检查：

- `tools/database_toolkit.py` 中预算参数
- 表格切块是否正常
- 原始文档在 MinerU 输出中是否已被截断

### 14.4 Streamlit 和 FastAPI 是否能同时跑

可以，但不建议长期作为主运行方式。因为两套入口已经分化，后续维护更推荐以前后端分离架构为主。

## 15. 仓库提交建议

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
- `data/storages/`
- `frontend/node_modules/`
- `frontend/dist/`
- 大日志与压缩包

推送前建议执行：

```bash
git status
git diff --cached --stat
git check-ignore -v .env models data/stored_files frontend/node_modules frontend/dist
```

## 16. 当前仓库状态说明

- 主线：前后端分离
- Streamlit：保留但视为旧入口
- 数据与模型目录按本地运行资源管理，不建议入库
- 仓库适合提交为代码仓，不适合直接提交运行数据仓
