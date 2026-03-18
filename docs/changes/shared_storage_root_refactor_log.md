# Shared Storage Root 路径收敛改动日志

日期：2026-03-16

## 变更目标

本轮修改继续推进可扩容部署，目标是把原先散落在多个模块中的 `data/...` 路径硬编码统一收口为一个共享根目录配置：

- `SHARED_STORAGE_ROOT`

这样后续无论是继续使用当前 `./data:/app/data` 挂载，还是迁移到专门的共享目录，都只需要改一个入口。

## 已完成改动

### 1. 新增统一路径模块

涉及文件：

- `storage_paths.py`

具体改动：

- 新增共享路径模块，统一定义：
  - `PROJECT_ROOT`
  - `SHARED_STORAGE_ROOT`
  - `SHARED_STORAGE_ROOT_REL`
  - `STORED_FILES_DIR`
  - `MINERU_OUTPUT_DIR`
  - `CONTENT_LISTS_DIR`
  - `EXPORTED_CHUNKS_DIR`
  - `AGENT_MEMORY_DIR`
  - `CHAT_SESSION_DIR`
- 新增辅助函数：
  - `project_relative_path(...)`
  - `tag_to_project_path(...)`

结果：

- 所有关键运行时路径现在可以从一个统一入口派生。
- 同时保留了对旧 `data/...` 标签的兼容解析能力。

### 2. 后端配置切到共享路径入口

涉及文件：

- `backend/app/config.py`

具体改动：

- 新增配置项：
  - `SHARED_STORAGE_ROOT`
- 后端以下路径不再手写 `data/...`，而是从共享路径模块读取：
  - `STORAGE_DIR`
  - `MINERU_OUTPUT_DIR`
  - `AGENT_MEMORY_DIR`
  - `CHAT_SESSION_DIR`

### 3. 工具链与脚本统一使用共享路径

涉及文件：

- `tools/mineru_toolkit.py`
- `tools/load_files.py`
- `backend/app/core/file_catalog.py`
- `tools/file_manager.py`
- `scripts/batch_import.py`
- `run/streamlit.py`

具体改动：

- MinerU 默认输出基础目录改为共享 `stored_files/`
- 文件导入脚本、文件管理辅助函数、旧版 Streamlit 入口统一改为使用共享路径模块
- `load_files.py` 中新生成的 `file_tag` 统一通过 `project_relative_path(...)` 生成

结果：

- 上传文件、MinerU 截图、导入脚本、旧入口路径行为保持一致，但不再依赖写死的 `data/stored_files`

### 4. 文件服务增加新旧路径兼容

涉及文件：

- `backend/app/services/file_service.py`
- `backend/app/api/v1/files.py`

具体改动：

- 文件服务的 `_path_to_tag()` 统一改为走共享路径相对化逻辑
- `_tag_to_path()` 现在支持：
  - 当前 `SHARED_STORAGE_ROOT/...`
  - 旧 `data/...`
  - `mineru_output/...`
- 文件导入接口在解析 `file_tag` 时，不再假设只会出现 `data/...`
- API 文档补充了共享根目录变化后的 `file_tag` 形式

结果：

- 历史入库数据中的旧 `data/stored_files/...` 标签仍可继续工作
- 后续如果切换 `SHARED_STORAGE_ROOT`，文件服务不需要再做第二轮大改

### 5. Docker 与文档同步

涉及文件：

- `docker-compose.yml`
- `README.md`
- `docs/scalable_docker_architecture.md`

具体改动：

- 当前 Compose 默认向 backend 注入：
  - `SHARED_STORAGE_ROOT=data`
- README 补充：
  - `SHARED_STORAGE_ROOT` 环境变量说明
  - 当前 `data/` 下派生目录说明
- 可扩容文档中把“文件路径统一到 `SHARED_STORAGE_ROOT`”标记为已完成

## 已完成验证

已执行：

```bash
python -m py_compile storage_paths.py
python -m py_compile backend/app/config.py
python -m py_compile backend/app/services/file_service.py
python -m py_compile tools/mineru_toolkit.py
python -m py_compile tools/load_files.py
python -m py_compile backend/app/core/file_catalog.py
python -m py_compile tools/file_manager.py
python -m py_compile scripts/batch_import.py
docker compose config
```

## 当前默认形态

当前默认部署仍然是：

```text
./data   -> /app/data
./models -> /app/models
./.user  -> /app/.user
```

并且 backend 默认使用：

```env
SHARED_STORAGE_ROOT=data
```

所以这次改动不会改变现有挂载结构，只是把路径入口统一收束，为后续共享存储迁移做准备。
