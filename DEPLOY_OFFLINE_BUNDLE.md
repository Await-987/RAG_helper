# 离线部署包导出与跨服务器迁移

适用场景：

- 当前服务器上的 4 个 Docker 容器已经正常运行
- 想把当前可运行状态迁移到另一台服务器
- 目标服务器可以直接 `docker load` + `docker compose up -d`
- 不希望在目标服务器重新构建镜像

本文档基于当前项目目录 `/home/ubuntu/rag_project/rag` 和现有 `docker-compose.yml`。

## 1. 迁移包里需要带什么

完整迁移当前可运行状态，建议带上：

- 4 个镜像 tar
- `docker-compose.yml`
- `docker-compose.deploy.yml`
- `.env`
- `data/`
- `models/`
- `.user/`

其中：

- `data/qdrant/`：向量库数据
- `data/redis/`：Redis 持久化数据
- `data/stored_files/`：上传的原始文件
- `data/lex_index/`：词汇索引缓存
- `data/agent_memory/`、`data/chat_sessions/`：会话和 memory 数据
- `models/`：本地模型目录
- `.user/users.json`：用户和密码数据

说明：

- `tools/`、`backend/`、`frontend/`、`config/`、`scripts/` 不需要单独带
- 这些代码已经在构建镜像时打进 `backend` / `web` 镜像中

## 2. 先在源服务器准备部署目录

```bash
cd /home/ubuntu/rag_project/rag
mkdir -p deploy_bundle/images
```

## 3. 给当前运行中的 4 个镜像打固定 tag

先查看当前 compose 使用的镜像：

```bash
docker compose images
```

给 4 个镜像打 tag：

```bash
docker tag $(docker compose images -q backend) rag-backend:v2
docker tag $(docker compose images -q web) rag-web:v2
docker tag redis:8-alpine redis:v2
docker tag qdrant/qdrant:latest qdrant:v2
```

说明：

- 这里统一使用 `v2` 作为本次离线包版本号

## 4. 导出 4 个镜像

```bash
docker save -o deploy_bundle/images/rag-backend-v2.tar rag-backend:v2
docker save -o deploy_bundle/images/rag-web-v2.tar rag-web:v2
docker save -o deploy_bundle/images/redis-v2.tar redis:v2
docker save -o deploy_bundle/images/qdrant-v2.tar qdrant:v2
```

## 5. 准备部署文件

复制 compose 和环境文件：

```bash
cp docker-compose.yml deploy_bundle/
cp .env deploy_bundle/.env
```

再创建一个专门给“导入镜像部署”用的 `docker-compose.deploy.yml`：

```bash
cat > deploy_bundle/docker-compose.deploy.yml <<'EOF'
services:
  redis:
    image: redis:v2

  qdrant:
    image: qdrant:v2

  backend:
    image: rag-backend:v2
    build: null

  web:
    image: rag-web:v2
    build: null
EOF
```

作用：

- 保留你原来的 `docker-compose.yml`
- 通过覆盖文件把 `backend` 和 `web` 从 `build:` 改成 `image:`
- 这样目标服务器不需要源码，也不需要重新 build

## 6. 复制必须带走的数据目录

完整迁移建议直接复制这 3 个目录：

```bash
rsync -a data deploy_bundle/
rsync -a models deploy_bundle/
rsync -a .user deploy_bundle/
```

## 7. 最终目录结构

```text
deploy_bundle/
├── .env
├── docker-compose.yml
├── docker-compose.deploy.yml
├── images/
│   ├── rag-backend-v2.tar
│   ├── rag-web-v2.tar
│   ├── redis-v2.tar
│   └── qdrant-v2.tar
├── data/
├── models/
└── .user/
```

## 8. 打成一个总包带走

```bash
tar -czf rag-deploy-bundle-v2.tar.gz deploy_bundle
```

## 9. 到目标服务器后怎么部署

### 9.1 解压

```bash
mkdir -p /home/ubuntu/rag_project
cd /home/ubuntu/rag_project
tar -xzf rag-deploy-bundle-v2.tar.gz
cd deploy_bundle
```

### 9.2 导入 4 个镜像

```bash
docker load -i images/rag-backend-v2.tar
docker load -i images/rag-web-v2.tar
docker load -i images/redis-v2.tar
docker load -i images/qdrant-v2.tar
```

### 9.3 如果目标服务器模型地址不同，先改 `.env`

常见需要修改的配置包括：

```env
OPENAI_API_URL=...
MAIN_AGENT_API_URL=...
MODEL_NAME=...
MAIN_AGENT_MODEL_NAME=...
OPENAI_API_KEY=...
MAIN_AGENT_API_KEY=...
APP_PORT=8080
```

说明：

- 模型 URL 和 API key 是运行时配置，不需要重新 build 镜像
- 改 `.env` 后直接重新创建容器即可

### 9.4 启动

```bash
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d
```

### 9.5 检查

```bash
docker compose ps
docker logs rag-backend --tail 100
docker logs rag-web --tail 50
```

## 10. 如果想瘦身，可以不带哪些内容

可以不带下面这些，但会丢失对应状态：

- 可不带 `data/redis/`
  - 影响：会话索引会重建或丢失
- 可不带 `data/agent_memory/`、`data/chat_sessions/`
  - 影响：历史会话和 memory 丢失
- 如果不带 `data/qdrant/`
  - 影响：知识库丢失
- 如果不带 `models/`
  - 影响：本地模型无法运行
- 如果不带 `.user/`
  - 影响：用户数据丢失，需要重新初始化管理员

如果你要迁移的是“当前完整可运行状态”，不建议瘦身。

## 11. 最推荐的一套命令

### 11.1 源服务器

```bash
cd /home/ubuntu/rag_project/rag
mkdir -p deploy_bundle/images

docker tag $(docker compose images -q backend) rag-backend:v2
docker tag $(docker compose images -q web) rag-web:v2
docker tag redis:8-alpine redis:v2
docker tag qdrant/qdrant:latest qdrant:v2

docker save -o deploy_bundle/images/rag-backend-v2.tar rag-backend:v2
docker save -o deploy_bundle/images/rag-web-v2.tar rag-web:v2
docker save -o deploy_bundle/images/redis-v2.tar redis:v2
docker save -o deploy_bundle/images/qdrant-v2.tar qdrant:v2

cp docker-compose.yml deploy_bundle/
cp .env deploy_bundle/.env

cat > deploy_bundle/docker-compose.deploy.yml <<'EOF'
services:
  redis:
    image: redis:v2

  qdrant:
    image: qdrant:v2

  backend:
    image: rag-backend:v2
    build: null

  web:
    image: rag-web:v2
    build: null
EOF

rsync -a data deploy_bundle/
rsync -a models deploy_bundle/
rsync -a .user deploy_bundle/

tar -czf rag-deploy-bundle-v2.tar.gz deploy_bundle
```

### 11.2 目标服务器

```bash
mkdir -p /home/ubuntu/rag_project
cd /home/ubuntu/rag_project
tar -xzf rag-deploy-bundle-v2.tar.gz
cd deploy_bundle

docker load -i images/rag-backend-v2.tar
docker load -i images/rag-web-v2.tar
docker load -i images/redis-v2.tar
docker load -i images/qdrant-v2.tar

docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d
```

## 12. 常见问题

### 12.1 目标服务器模型链接不同怎么办

直接修改 `deploy_bundle/.env`，然后执行：

```bash
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d --force-recreate backend
```

不需要重新 build 镜像。

### 12.2 `tools/` 这些代码要不要单独带

不用。

原因是：

- `backend` 镜像构建时已经 `COPY tools ./tools`
- `backend/`、`config/`、`scripts/` 也都已经打包进镜像
- 目标服务器只要导入镜像即可运行

### 12.3 什么时候才需要带源码目录

只有这两种情况需要：

- 想在目标服务器重新 `docker compose build`
- 想在目标服务器继续开发或直接改代码

如果只是部署运行，不需要额外带源码目录。

## 13. Linux 部署流程

适用场景：

- 目标机器是 Linux 服务器
- 已安装 Docker 和 Docker Compose plugin
- 如需本地模型/GPU，已安装 NVIDIA 驱动和 `nvidia-container-toolkit`

### 13.1 准备目录

```bash
mkdir -p /home/ubuntu/rag_project
cd /home/ubuntu/rag_project
```

把你的离线包上传到这个目录，例如：

```text
/home/ubuntu/rag_project/rag-deploy-bundle-v2.tar.gz
```

### 13.2 解压

```bash
tar -xzf rag-deploy-bundle-v2.tar.gz
cd deploy_bundle
```

如果你传的是目录而不是压缩包，直接进入：

```bash
cd /home/ubuntu/rag_project/deploy_bundle
```

### 13.3 导入 4 个镜像

```bash
docker load -i images/rag-backend-v2.tar
docker load -i images/rag-web-v2.tar
docker load -i images/redis-v2.tar
docker load -i images/qdrant-v2.tar
```

### 13.4 修改 `.env`

如果目标服务器的模型地址、API key、端口和源服务器不同，先改：

```env
OPENAI_API_URL=...
MAIN_AGENT_API_URL=...
MODEL_NAME=...
MAIN_AGENT_MODEL_NAME=...
OPENAI_API_KEY=...
MAIN_AGENT_API_KEY=...
APP_PORT=8080
```

### 13.5 启动

```bash
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d
```

### 13.6 检查

```bash
docker compose ps
docker logs rag-backend --tail 100
docker logs rag-web --tail 50
```

如果后端模型地址改过，后续只需要重建后端容器：

```bash
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d --force-recreate backend
```

### 13.7 可选：开放防火墙端口

如果 Linux 服务器启用了防火墙，需要放行 `.env` 里的 `APP_PORT`，例如 `8080`：

Ubuntu `ufw`：

```bash
sudo ufw allow 8080/tcp
```

CentOS / Rocky `firewalld`：

```bash
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

## 14. Windows 部署流程

适用场景：

- 目标机器是 Windows
- 使用 Docker Desktop
- 推荐使用 WSL2 backend

建议：

- 尽量把部署目录放在 WSL Linux 文件系统里，而不是 `C:\` 盘
- 大目录如 `data/`、`models/`、`.user/` 放在 WSL 内部磁盘，IO 会更稳

### 14.1 推荐部署位置

推荐放在 WSL 内，例如 Ubuntu 发行版里：

```text
/home/ubuntu/rag_project
```

不推荐直接放在：

```text
C:\Users\<用户名>\Desktop\...
```

### 14.2 把离线包复制到 Windows

你可以先把压缩包拷到 Windows，再放进 WSL。

例如在 PowerShell 中：

```powershell
mkdir C:\rag_deploy
```

然后把 `rag-deploy-bundle-v2.tar.gz` 放到：

```text
C:\rag_deploy\
```

### 14.3 进入 WSL 并准备目录

在 PowerShell 中进入 Ubuntu：

```powershell
wsl
```

在 WSL 里执行：

```bash
mkdir -p /home/ubuntu/rag_project
cp /mnt/c/rag_deploy/rag-deploy-bundle-v2.tar.gz /home/ubuntu/rag_project/
cd /home/ubuntu/rag_project
```

### 14.4 解压

```bash
tar -xzf rag-deploy-bundle-v2.tar.gz
cd deploy_bundle
```

如果你不用 WSL，也可以在 Windows 上用 7-Zip 解压，但后续仍建议在 WSL 里运行 Docker Compose。

### 14.5 导入 4 个镜像

在 WSL 或 PowerShell 中均可执行：

```bash
docker load -i images/rag-backend-v2.tar
docker load -i images/rag-web-v2.tar
docker load -i images/redis-v2.tar
docker load -i images/qdrant-v2.tar
```

### 14.6 修改 `.env`

目标机器如果模型地址、key、端口不同，先改：

```env
OPENAI_API_URL=...
MAIN_AGENT_API_URL=...
MODEL_NAME=...
MAIN_AGENT_MODEL_NAME=...
OPENAI_API_KEY=...
MAIN_AGENT_API_KEY=...
APP_PORT=8080
```

说明：

- 如果模型服务仍在另一台 Linux 机器上，Windows 这里填可访问的 HTTP 地址即可
- 如果是局域网模型服务，先确认 Windows/WSL 能访问该地址

### 14.7 启动

```bash
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d
```

### 14.8 检查

```bash
docker compose ps
docker logs rag-backend --tail 100
docker logs rag-web --tail 50
```

浏览器访问：

```text
http://localhost:8080
```

如果 `.env` 中 `APP_PORT` 不是 `8080`，按实际端口访问。

### 14.9 Windows 部署注意事项

- 确保 Docker Desktop 已启动
- 确保 Docker Desktop 使用 WSL2
- 如果用本地 GPU 模型，Windows 侧还需要满足 Docker Desktop + WSL GPU 支持条件
- `models/`、`data/qdrant/`、`data/redis/` 在 Windows 文件系统上的 IO 一般更慢，建议放在 WSL 内部磁盘

### 14.10 后续只改模型地址怎么办

只需要修改 `.env`，然后重建后端容器：

```bash
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d --force-recreate backend
```
