# Linux 服务器从 0 部署教程

本文面向一台全新的 Linux 服务器，目标是把当前项目以 Docker Compose 方式部署起来，并支持：

- `web` 前端入口
- `backend` 后端服务
- `qdrant` 向量库
- `redis` 会话索引
- NVIDIA GPU 容器透传
- 容器内执行 `nvidia-smi`

本文默认假设：

- 系统为 Ubuntu 22.04 或 24.04
- 服务器有 NVIDIA GPU
- 你希望按当前仓库的标准方式部署
- 项目部署目录为 `/opt/rag`

如果你的服务器没有 GPU，需要先把 [`docker-compose.yml`](/home/ubuntu/rag_project/rag/docker-compose.yml) 里的 `backend.gpus: all` 和 NVIDIA 相关环境变量去掉，再按 CPU-only 方式部署。当前仓库默认是 GPU 部署方案。

## 1. 你需要准备的文件

最少需要准备以下内容：

### 1.1 项目代码

把整个仓库放到服务器，例如：

- `docker-compose.yml`
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `deploy/nginx/default.conf`
- `backend/`
- `frontend/`
- `tools/`
- `scripts/`
- `config/`
- `requirements.txt`
- `backend/requirements.txt`

最简单的方式是直接把整个仓库 clone 或上传到服务器。

### 1.2 必须准备的本地模型目录

当前项目依赖本地模型目录，至少包括：

- `models/bge-base-zh-v1.5`
- `models/bge-reranker-base`
- `models/Qwen2.5-1.5B-Instruct`
- `models/mineru/OpenDataLab/PDF-Extract-Kit-1___0`
- `models/mineru/OpenDataLab/mineru2.5/OpenDataLab/MinerU2___5-2509-1___2B`

说明：

- `bge-base-zh-v1.5`：embedding 模型
- `bge-reranker-base`：reranker 模型
- `Qwen2.5-1.5B-Instruct`：表格摘要模型
- `PDF-Extract-Kit-1___0`：MinerU pipeline 模型目录
- `MinerU2___5-2509-1___2B`：MinerU VLM 模型目录

如果你是新机器、但已有旧服务器在运行，最稳妥的方式是直接把旧服务器上的整个 `models/` 目录复制过来。

### 1.3 必须创建的环境变量文件

项目根目录需要一个 `.env` 文件。

最少建议包含：

```env
OPENAI_API_KEY=your-api-key
url=https://your-openai-compatible-endpoint/v1
MODEL_NAME=qwq32b
SECRET_KEY=change-this-secret-key

conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct
MINERU_MODELS_DIR_PIPELINE=models/mineru/OpenDataLab/PDF-Extract-Kit-1___0
MINERU_MODELS_DIR_VLM=models/mineru/OpenDataLab/mineru2.5/OpenDataLab/MinerU2___5-2509-1___2B

INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=change-this-admin-password

APP_PORT=8080
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

说明：

- `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` 只会在 `.user/users.json` 不存在时初始化首个管理员
- 当前仓库已经不再内置固定默认管理员口令
- MinerU 模型路径也建议通过 `.env` 统一管理，不再依赖手改 `config/mineru.json`
- `NVIDIA_DRIVER_CAPABILITIES` 需要包含 `utility`，否则容器里通常不能执行 `nvidia-smi`

### 1.4 可选迁移数据

如果你要从旧环境迁移现有业务数据，额外复制：

- `data/`
- `.user/`

其中：

- `data/` 包含上传文件、MinerU 输出、Qdrant 数据、Redis 数据、聊天 transcript、memory
- `.user/` 包含用户账户数据

如果是纯新部署，不迁移旧数据，这两个目录可以先创建空目录。

## 2. 服务器初始化

先登录服务器并安装基础工具：

```bash
sudo apt update
sudo apt install -y git curl ca-certificates gnupg lsb-release
```

如果你准备把项目放到 `/opt/rag`：

```bash
sudo mkdir -p /opt
sudo chown -R "$USER":"$USER" /opt
cd /opt
```

## 3. 安装 Docker Engine

以下步骤参考 Docker 官方 Ubuntu 安装文档。

先移除可能冲突的旧包：

```bash
sudo apt remove -y docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc || true
```

安装 Docker 官方 apt 源并安装 Docker Engine：

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

验证 Docker：

```bash
sudo systemctl enable docker
sudo systemctl start docker
sudo docker run hello-world
docker compose version
```

可选：如果你不想每次都写 `sudo`，可以把当前用户加入 `docker` 组：

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

## 4. 安装 NVIDIA 驱动与 NVIDIA Container Toolkit

这一步只在 GPU 服务器上需要。

### 4.1 先确认宿主机能看到 GPU

如果宿主机还没装好 NVIDIA 驱动，请先把驱动装好，再继续下面步骤。

先确认宿主机直接执行 `nvidia-smi` 没问题：

```bash
nvidia-smi
```

只有宿主机 `nvidia-smi` 正常，容器 GPU 透传才有意义。

### 4.2 安装 NVIDIA Container Toolkit

以下步骤参考 NVIDIA 官方安装文档。官方文档当前展示的是版本固定安装；为了降低文档过期成本，这里直接安装仓库中的当前稳定版本。

```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  gnupg2

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
```

把 NVIDIA runtime 接到 Docker：

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

验证容器 GPU 透传：

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

如果这一步能看到 GPU 信息，说明 Docker GPU 透传已经可用。

## 5. 上传或拉取项目代码

### 5.1 方式 A：直接 clone 仓库

```bash
cd /opt
git clone <your_repo_url> rag
cd /opt/rag
```

### 5.2 方式 B：从本地机器复制整个项目目录

在本地机器执行：

```bash
scp -r /your/local/rag user@your-server:/opt/
```

复制后在服务器确认目录：

```bash
cd /opt/rag
ls
```

## 6. 准备目录结构

在项目根目录创建运行目录：

```bash
cd /opt/rag
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

## 7. 准备模型文件

### 7.1 推荐方案：从旧服务器复制整个 `models/`

在旧服务器上确认：

```bash
ls /path/to/old/rag/models
```

在新服务器上接收：

```bash
scp -r user@old-server:/path/to/old/rag/models /opt/rag/
```

### 7.2 新环境手动准备模型

至少保证以下目录存在：

```text
/opt/rag/models/bge-base-zh-v1.5
/opt/rag/models/bge-reranker-base
/opt/rag/models/Qwen2.5-1.5B-Instruct
/opt/rag/models/mineru/OpenDataLab/PDF-Extract-Kit-1___0
/opt/rag/models/mineru/OpenDataLab/mineru2.5/OpenDataLab/MinerU2___5-2509-1___2B
```

当前仓库只提供了表格摘要模型的下载脚本：

```bash
cd /opt/rag
python3 scripts/download_table_summary_model.py --source modelscope
```

`bge-base-zh-v1.5` 和 `bge-reranker-base` 当前没有统一下载脚本，建议直接从已有环境复制，或者手动下载后放到 `models/` 下对应目录。

MinerU 这两条模型路径建议通过 `.env` 统一配置：

- `MINERU_MODELS_DIR_PIPELINE`
- `MINERU_MODELS_DIR_VLM`

## 8. 创建 `.env`

在项目根目录创建 `.env`：

```bash
cd /opt/rag
cat > .env <<'EOF'
OPENAI_API_KEY=your-api-key
url=https://your-openai-compatible-endpoint/v1
MODEL_NAME=qwq32b
SECRET_KEY=change-this-secret-key

conan_path=models/bge-base-zh-v1.5
reranker_path=models/bge-reranker-base
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct
MINERU_MODELS_DIR_PIPELINE=models/mineru/OpenDataLab/PDF-Extract-Kit-1___0
MINERU_MODELS_DIR_VLM=models/mineru/OpenDataLab/mineru2.5/OpenDataLab/MinerU2___5-2509-1___2B

INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=change-this-admin-password

APP_PORT=8080
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
EOF
```

如果你是从旧环境迁移 `.user/users.json`，那么 `INITIAL_ADMIN_*` 不会生效；因为已有用户文件时，系统不会再初始化首个管理员。

## 9. 启动项目

进入项目目录：

```bash
cd /opt/rag
```

构建并启动：

```bash
docker compose up -d --build
```

如果你的网络环境对 BuildKit 不稳定，也可以用：

```bash
DOCKER_BUILDKIT=0 docker compose up -d --build
```

## 10. 启动后验证

### 10.1 看容器状态

```bash
docker compose ps
```

正常情况下应看到：

- `rag-redis`
- `rag-qdrant`
- `rag-backend`
- `rag-web`

### 10.2 看后端健康状态

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/api/v1/auth/me -I
```

如果你修改了 `.env` 中的 `APP_PORT`，把 `8080` 替换成对应端口。

### 10.3 验证 GPU 是否进容器

```bash
docker compose exec backend nvidia-smi
```

如果能看到 GPU 列表，说明当前项目的 `backend` 容器已经拿到 GPU。

### 10.4 查看日志

```bash
docker compose logs -f backend
docker compose logs -f web
```

## 11. 首次登录

浏览器打开：

```text
http://<server-ip>:8080
```

首次登录说明：

- 如果 `.user/users.json` 原本不存在，系统会用 `.env` 中的 `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` 初始化首个管理员
- 如果 `.user/users.json` 已存在，则继续使用那个文件里的已有用户
- 登录页不再展示固定默认管理员账号密码

## 12. 后续常用命令

重建前后端：

```bash
docker compose up -d --build backend web
```

只重启后端：

```bash
docker compose restart backend
```

只看后端日志：

```bash
docker compose logs -f --tail=200 backend
```

验证 Compose 配置：

```bash
docker compose config
```

## 13. 故障排查

### 13.1 `docker compose up` 报 GPU 相关错误

先检查宿主机：

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

如果这两步失败，先修宿主机驱动和 NVIDIA Container Toolkit，不要先怀疑项目代码。

### 13.2 `backend` 起不来

重点检查：

- `.env` 是否存在
- `OPENAI_API_KEY` / `url` / `MODEL_NAME` 是否正确
- `models/` 下三个模型目录是否齐全
- `docker compose logs backend` 是否报模型路径不存在

### 13.3 前端能打开但登录失败

重点检查：

- `.user/users.json` 是否存在且格式正常
- 初始管理员是否真的被创建
- 如果你迁移了旧 `.user/`，请使用旧用户口令，不要再使用新的 `INITIAL_ADMIN_*`

### 13.4 页面能打开，但问答没有结果

重点检查：

- 是否已经导入知识库文件
- `data/qdrant` 是否为空
- `docker compose logs backend` 里是否有 Qdrant 或 Redis 连接报错

## 14. 推荐的交付清单

如果你要把这个项目交给另一台新服务器，建议至少准备以下内容：

- 完整项目代码目录
- `.env`
- `models/`
- `data/`
- `.user/`

其中：

- 纯新部署最少需要：代码 + `.env` + `models/`
- 如需保留历史数据和用户：再加 `data/` + `.user/`

## 15. 参考来源

以下安装步骤参考了官方文档：

- Docker Engine Ubuntu 安装文档：https://docs.docker.com/engine/install/ubuntu/
- NVIDIA Container Toolkit 安装文档：https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

其中第 4 节里使用 `apt install nvidia-container-toolkit` 安装当前稳定版本，是基于 NVIDIA 官方仓库配置步骤做的实际部署化简写；如果你需要严格锁版本，请以 NVIDIA 官方页面当时的版本号为准。
