# Local Qdrant -> Server Qdrant 迁移脚本日志

日期：2026-03-16

## 背景

项目从本地 embedded Qdrant 迁移到独立 Qdrant Server 后，旧数据仍然保存在：

- `data/storages`

而新服务模式默认读取：

- `http://127.0.0.1:6333`

这会导致：

- 本地 PDF 文件仍然存在；
- 但当前 server collection 为空；
- 文件管理页显示“未建库”。

## 本次新增

涉及文件：

- `scripts/migrate_qdrant_local_to_server.py`

新增能力：

- 从旧 local collection 读取点数据；
- 直接迁移 `id + vector + payload` 到目标 Qdrant Server；
- 支持保留原 collection 参数；
- 支持 `--recreate` 覆盖重建目标 collection。

## 推荐用途

当以下条件同时满足时使用：

1. `QDRANT_MODE=server`
2. 旧库仍在 `data/storages`
3. 新 server collection 为空或数据不完整

## 推荐命令

```bash
cd /home/ubuntu/rag_project/rag
source .venv/bin/activate
python scripts/migrate_qdrant_local_to_server.py \
  --local-path data/storages \
  --server-url http://127.0.0.1:6333 \
  --collection database \
  --recreate
```

## 验证方式

迁移后执行：

```bash
curl http://127.0.0.1:6333/collections/database
```

并重启后端，确认启动日志中的词汇索引预热不再显示 `docs=0`。
