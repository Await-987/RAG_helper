# 智能设计助手 RAG

面向电力系统与国家电网业务场景的 RAG 项目。当前主线是前后端分离架构：

- `frontend/`：React + Vite 聊天与文件管理前端
- `backend/`：FastAPI 接口服务
- `tools/`、`agents/`、`config/`、`data/`、`models/`：前后端共享的知识库、检索、解析和模型资源

原 `run/streamlit.py` 仍保留，作为旧入口，不再是推荐主路径。

## 项目结构

```text
rag/
├── frontend/                 # React/Vite 前端
├── backend/                  # FastAPI 后端
├── agents/                   # 问答 Agent 与模型装配
├── tools/                    # MinerU / Qdrant / 入库 / 检索核心能力
├── config/                   # 公共配置
├── data/                     # 运行数据（上传文件、图片、向量库等）
├── models/                   # 本地模型目录
├── docs/                     # 变更记录与设计文档
├── scripts/                  # 下载模型、批量导入等脚本
├── run/                      # 旧版 Streamlit 入口
├── tests/                    # 公共测试
└── README.md
```

## 功能概览

- PDF 上传、解析、入库
- MinerU 提取文本、图片、表格
- Qdrant 混合检索：向量 + 关键词 + rerank
- 表格独立切块与图片证据回溯
- 鉴权、会话管理、流式回答
- 前端消息内 markdown、表格、附件图片渲染

## 运行要求

- Python 3.10+
- Node.js 20.19+ 或 22.12+
- 建议使用虚拟环境

## 快速开始

### 1. 安装 Python 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 2. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 3. 配置环境变量

在项目根目录创建 `.env`：

```env
OPENAI_API_KEY=your-api-key
url=https://your-api-endpoint/v1
MODEL_NAME=qwq32b

conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct
```

## 模型与数据

以下目录默认不提交远程仓库：

- `models/`
- `data/storages/`
- `data/stored_files/`
- `data/content_lists/`
- `.user/`

这些目录包含本地模型、向量库、上传文件、解析图片和用户数据。

## 启动方式

### 推荐：前后端分离

启动后端：

```bash
source .venv/bin/activate
cd backend
python3 run.py
```

默认地址：

- `http://localhost:8000`

启动前端：

```bash
cd frontend
npm run dev
```

默认地址：

- `http://localhost:3000`

前端会将 `/api` 代理到后端 `8000` 端口。

### 旧入口：Streamlit

如需继续使用旧版界面：

```bash
source .venv/bin/activate
streamlit run run/streamlit.py
```

## 常用目录说明

### 前端

- `frontend/src/components/Chat/`
  消息渲染、表格渲染、附件图片渲染
- `frontend/src/api/`
  前端 API 调用
- `frontend/src/stores/`
  鉴权与聊天状态

### 后端

- `backend/app/api/v1/`
  路由层
- `backend/app/services/`
  聊天、文件、鉴权服务
- `backend/app/config.py`
  后端配置

### 共享核心能力

- `tools/load_files.py`
  PDF 解析、图片重命名、切块入库
- `tools/database_toolkit.py`
  检索工具入口
- `tools/qdrant.py`
  Qdrant 检索与混合排序
- `agents/chat_agent.py`
  对话系统提示词
- `agents/backend_model.py`
  模型加载

## 测试

后端/公共测试：

```bash
source .venv/bin/activate
python3 -m pytest
```

前端构建检查：

```bash
cd frontend
npm run build
```

## 推送前建议检查

- `.env` 未提交
- `.user/` 未提交
- `models/` 未提交
- `data/stored_files/` 与 `data/storages/` 未提交
- `frontend/node_modules/` 与 `frontend/dist/` 未提交
- 大体积日志、压缩包、导入产物未提交

可用以下命令确认：

```bash
git status
git check-ignore -v .env models data/stored_files frontend/node_modules frontend/dist
```

## 当前状态说明

- 主线架构：前后端分离
- Streamlit：保留但视为旧入口
- 仓库建议只提交代码、配置模板、必要文档与轻量测试
