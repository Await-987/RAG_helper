# 大模型二期应用部署说明

## 安全提示

> ⚠️ **安全建议**：本文档包含敏感信息（密码、IP 地址），请妥善保管，不要提交到公开代码仓库。

## 服务器概览

紫竹目前有三台服务器，分别是 4090 24G、4090 48G、5090 32G×4。三台服务器均可通过 SSH 登录使用。

| 服务器型号 | GPU 配置 | 操作系统 | SSH 端口 | IP 地址 | 备注 |
|-----------|---------|---------|---------|---------|------|
| 4090 24G | 单卡 4090 24G | Ubuntu 22.04 | 9922 | 117.186.43.62 | - |
| 4090 48G | 单卡 4090 48G | Ubuntu 22.04 | 9934 | 117.186.43.62 | - |
| 5090 32G×4 | 四卡 5090 32G | Ubuntu 22.04 | 5090 | 117.168.43.62 | 环境配置与经研院内网服务器相同 |

> **注意**：5090 32G×4 服务器环境配置及 IP 完全与经研院内网服务器相同，使用过程中注意保持环境纯粹，非经研院项目请不要在这台服务器上配置运行，经研院项目请按相同环境版本部署。

---

### 4090 24G 服务器

**配置信息**：
- GPU：单卡 4090 24G
- 操作系统：Ubuntu 22.04

**登录信息**：

登录命令：
```bash
ssh -p 9922 ubuntu@117.186.43.62
```

登录密码：`ineedhelp`

---

### 4090 48G 服务器

**配置信息**：
- GPU：单卡 4090 48G
- 操作系统：Ubuntu 22.04

**登录信息**：

登录命令：
```bash
ssh -p 9934 ubuntu@117.186.43.62
```

登录密码：`ineedheelp`


### 5090 32G×4 服务器

**配置信息**：
- GPU：四卡 5090 32G × 4
- 操作系统：Ubuntu 22.04

**登录信息**：

登录命令：
```bash
ssh -p 5090 ubuntu@117.186.43.62
```

登录密码：`kk12345678`

**重要提示**：
> ⚠️ 本服务器环境配置及 IP 完全与经研院内网服务器相同，使用过程中注意保持环境纯粹，非经研院项目请不要在这台服务器上配置运行。

**已部署项目**：

在这个服务器中已部署 RAG 智能设计助手。

当前部署主线为 Docker Compose 四服务架构：`web + backend + qdrant + redis`

## 应用部署说明

为方便大模型二期的平台配合，所有项目应统一使用 Docker Compose 部署。当前 RAG 项目的标准部署命令如下：

```bash
docker compose up -d
```

如需停止服务：

```bash
docker compose down
```

### 部署前准备

启动前请确认项目根目录下已准备以下内容：

- `.env`
- `data/`
- `models/`
- `.user/`
- `docker-compose.yml`

最少需要在 `.env` 中提供：

```env
OPENAI_API_KEY=your-api-key
url=https://your-openai-compatible-endpoint/v1
MODEL_NAME=qwq32b
SECRET_KEY=change-me

MAIN_AGENT_MODEL_NAME=qwq32b
MAIN_AGENT_TEMPERATURE=0.2
MAIN_AGENT_TOP_P=0.9
MAIN_AGENT_MAX_TOKENS=4000
MAIN_AGENT_SYSTEM_PROMPT_PATH=config/prompts/main_agent_system.txt

conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct
MINERU_MODELS_DIR_PIPELINE=models/mineru/OpenDataLab/PDF-Extract-Kit-1___0
MINERU_MODELS_DIR_VLM=models/mineru/OpenDataLab/mineru2.5/OpenDataLab/MinerU2___5-2509-1___2B
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=change-this-admin-password
APP_PORT=8080
BACKEND_WORKERS=1
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

### 主要参数说明

- `docker compose up -d`：后台启动所有服务
- `docker compose down`：停止并移除当前 Compose 创建的容器网络
- `docker-compose.yml`：主部署文件，定义 `web`、`backend`、`qdrant`、`redis` 四个服务
- `APP_PORT`：宿主机对外访问端口，默认 `8080`
- `BACKEND_WORKERS=1`：当前建议保持单 worker，避免会话执行态不一致
- `NVIDIA_VISIBLE_DEVICES=all`：把宿主机 GPU 暴露给后端容器
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`：保证容器内可执行推理与 `nvidia-smi`
- `./data:/app/data`：持久化知识库、会话、上传文件等运行数据
- `./models:/app/models`：挂载 embedding、reranker、MinerU、本地摘要模型
- `./.user:/app/.user`：持久化用户、密码和鉴权信息

对应的运行时配置文件为项目根目录下的 `.env`。当前仓库启动 `docker compose up -d` 时，会由 `docker-compose.yml` 和后端配置入口自动读取 `.env`，不需要额外准备 `project_config.json`。

建议直接在项目根目录维护 `.env`，示例如下：

```env
OPENAI_API_KEY=your-api-key
url=https://your-openai-compatible-endpoint/v1
MODEL_NAME=qwq32b
SECRET_KEY=change-me

MAIN_AGENT_MODEL_NAME=qwq32b
MAIN_AGENT_TEMPERATURE=0.2
MAIN_AGENT_TOP_P=0.9
MAIN_AGENT_MAX_TOKENS=4000
MAIN_AGENT_SYSTEM_PROMPT_PATH=config/prompts/main_agent_system.txt

conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct
MINERU_MODELS_DIR_PIPELINE=models/mineru/OpenDataLab/PDF-Extract-Kit-1___0
MINERU_MODELS_DIR_VLM=models/mineru/OpenDataLab/mineru2.5/OpenDataLab/MinerU2___5-2509-1___2B

INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=change-this-admin-password

APP_PORT=8080
BACKEND_WORKERS=1
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility

SHARED_STORAGE_ROOT=data
QDRANT_MODE=server
QDRANT_URL=http://qdrant:6333
QDRANT_LEXICAL_INDEX_DIR=data/lex_index
QDRANT_TIMEOUT_SEC=30
QDRANT_INIT_RETRIES=20
QDRANT_INIT_DELAY_SEC=3

REDIS_URL=redis://redis:6379/0
REDIS_PREFIX=rag
REDIS_SOCKET_TIMEOUT_SEC=5
REDIS_SOCKET_CONNECT_TIMEOUT_SEC=5
```
