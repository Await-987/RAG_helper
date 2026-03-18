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
docker tag $(docker compose images -q backend) rag-backend:20260318
docker tag $(docker compose images -q web) rag-web:20260318
docker tag redis:8-alpine rag-redis:8-alpine
docker tag qdrant/qdrant:latest rag-qdrant:latest
```

说明：

- `20260318` 只是示例版本号
- 你可以替换成自己的日期或版本，例如 `2026-03-18`、`v1`

## 4. 导出 4 个镜像

```bash
docker save -o deploy_bundle/images/rag-backend-20260318.tar rag-backend:20260318
docker save -o deploy_bundle/images/rag-web-20260318.tar rag-web:20260318
docker save -o deploy_bundle/images/rag-redis-8-alpine.tar rag-redis:8-alpine
docker save -o deploy_bundle/images/rag-qdrant-latest.tar rag-qdrant:latest
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
    image: rag-redis:8-alpine

  qdrant:
    image: rag-qdrant:latest

  backend:
    image: rag-backend:20260318
    build: null

  web:
    image: rag-web:20260318
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
│   ├── rag-backend-20260318.tar
│   ├── rag-web-20260318.tar
│   ├── rag-redis-8-alpine.tar
│   └── rag-qdrant-latest.tar
├── data/
├── models/
└── .user/
```

## 8. 打成一个总包带走

```bash
tar -czf rag-deploy-bundle-20260318.tar.gz deploy_bundle
```

## 9. 到目标服务器后怎么部署

### 9.1 解压

```bash
mkdir -p /home/ubuntu/rag_project
cd /home/ubuntu/rag_project
tar -xzf rag-deploy-bundle-20260318.tar.gz
cd deploy_bundle
```

### 9.2 导入 4 个镜像

```bash
docker load -i images/rag-backend-20260318.tar
docker load -i images/rag-web-20260318.tar
docker load -i images/rag-redis-8-alpine.tar
docker load -i images/rag-qdrant-latest.tar
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

docker tag $(docker compose images -q backend) rag-backend:20260318
docker tag $(docker compose images -q web) rag-web:20260318
docker tag redis:8-alpine rag-redis:8-alpine
docker tag qdrant/qdrant:latest rag-qdrant:latest

docker save -o deploy_bundle/images/rag-backend-20260318.tar rag-backend:20260318
docker save -o deploy_bundle/images/rag-web-20260318.tar rag-web:20260318
docker save -o deploy_bundle/images/rag-redis-8-alpine.tar rag-redis:8-alpine
docker save -o deploy_bundle/images/rag-qdrant-latest.tar rag-qdrant:latest

cp docker-compose.yml deploy_bundle/
cp .env deploy_bundle/.env

cat > deploy_bundle/docker-compose.deploy.yml <<'EOF'
services:
  redis:
    image: rag-redis:8-alpine

  qdrant:
    image: rag-qdrant:latest

  backend:
    image: rag-backend:20260318
    build: null

  web:
    image: rag-web:20260318
    build: null
EOF

rsync -a data deploy_bundle/
rsync -a models deploy_bundle/
rsync -a .user deploy_bundle/

tar -czf rag-deploy-bundle-20260318.tar.gz deploy_bundle
```

### 11.2 目标服务器

```bash
mkdir -p /home/ubuntu/rag_project
cd /home/ubuntu/rag_project
tar -xzf rag-deploy-bundle-20260318.tar.gz
cd deploy_bundle

docker load -i images/rag-backend-20260318.tar
docker load -i images/rag-web-20260318.tar
docker load -i images/rag-redis-8-alpine.tar
docker load -i images/rag-qdrant-latest.tar

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
