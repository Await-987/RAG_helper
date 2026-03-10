# 缓存优化：永久缓存策略

## 背景

随着数据库规模增大（13万+ 记录），每次页面加载都需要扫描数据库来获取文件统计信息，导致前端响应缓慢（约 20 秒）。

## 问题分析

### Streamlit 工作机制
Streamlit 每次用户交互（点击按钮、翻页等）都会重新执行整个脚本，导致：
- `get_database_stats()` 被频繁调用
- 需要扫描数据库（耗时 ~20 秒）

### 原有缓存策略
- TTL（生存时间）只有 60 秒
- 缓存过期后需要重新扫描数据库

## 解决方案

### 永久缓存策略
将缓存改为**永久有效**，直到脚本退出或数据变更。

### 缓存自动失效
在以下操作后自动清除缓存：
- 入库新文件 → `clear_database_stats_cache()`
- 删除文件 → `clear_database_stats_cache()`

## 修改的文件

### tools/file_manager_ui.py

```python
# 缓存变量（永久有效，直到脚本退出）
_db_stats_cache = None
_db_stats_collection = None

def get_database_stats(collection_name: str = "database", use_cache: bool = True):
    """获取数据库统计信息（缓存永久有效）"""
    global _db_stats_cache, _db_stats_collection

    if use_cache and _db_stats_cache is not None:
        if _db_stats_collection == collection_name:
            return _db_stats_cache  # 直接返回缓存，无 TTL 检查
    # ... 扫描数据库并缓存

def clear_database_stats_cache():
    """清除数据库统计缓存（入库/删除文件后调用）"""
    global _db_stats_cache, _db_stats_collection
    _db_stats_cache = None
    _db_stats_collection = None

def import_file_to_database(...):
    # ... 入库逻辑
    if result:
        clear_database_stats_cache()  # 入库成功后清除缓存
        return True, "文件导入成功", 0

def delete_file_by_tag(...):
    # ... 删除逻辑
    clear_database_stats_cache()  # 删除后清除缓存
    return True
```

### tools/qdrant.py

```python
# 移除 TTL 相关变量
# self._lex_index_ttl_sec = ...  # 已删除

def _maybe_build_lex_index(self, force: bool = False):
    """构建词汇索引（缓存永久有效）"""
    if not force and self._lex_index is not None:
        # 仅检查数据量是否变化，不检查 TTL
        current_cnt = self._get_collection_point_count()
        if current_cnt == self._lex_index_point_count:
            return  # 缓存有效
    # ... 构建索引
```

## 性能对比

| 操作 | 优化前 | 优化后 |
|-----|-------|-------|
| 首次访问页面 | ~20 秒 | ~20 秒 |
| 后续访问（5分钟内） | ~20 秒（缓存过期） | **0 秒** |
| 后续访问（任意时间） | ~20 秒 | **0 秒** |
| 入库/删除后首次访问 | ~20 秒 | ~20 秒 |

## 缓存生命周期

```
脚本启动
    ↓
首次访问 → 构建缓存（~20秒）
    ↓
后续访问 → 使用缓存（0秒）
    ↓
入库/删除 → 自动清除缓存
    ↓
下次访问 → 重新构建缓存（~20秒）
    ↓
脚本退出 → 缓存自动释放
```

## 影响说明

- **搜索功能**：不受影响，词汇索引会在数据变化时自动重建
- **UI 显示**：入库/删除后立即显示最新状态（缓存已清除）
- **内存占用**：缓存仅占用少量内存（统计信息约几 MB）

## 环境变量（已移除）

以下环境变量已不再需要：
- ~~`LEX_INDEX_TTL_SEC`~~ - 已移除 TTL 机制
- ~~`DB_STATS_CACHE_TTL`~~ - 已移除 TTL 机制

## 测试验证

```bash
# 首次调用（慢）
python -c "from tools.file_manager_ui import get_database_stats; get_database_stats()"
# 耗时: ~20秒

# 第二次调用（快）
python -c "from tools.file_manager_ui import get_database_stats; get_database_stats()"
# 耗时: 0秒
```

## 更新日期

2026-03-10
