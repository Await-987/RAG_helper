# 缓存优化：永久缓存策略

## 背景

随着数据库规模增大（13万+ 记录），每次页面加载都需要扫描数据库来获取文件统计信息，导致前端响应缓慢（约 20 秒）。

## 问题分析

### Streamlit 工作机制
Streamlit 每次用户交互（点击按钮、翻页等）都会重新执行整个脚本，导致：
- `get_database_stats()` 被频繁调用
- 需要扫描数据库（耗时 ~20 秒）

### 原有缓存策略
- 最初使用 TTL（生存时间）60 秒
- 后改为模块级变量永久缓存，但刷新页面后失效

### 问题：模块级缓存在刷新后失效
- Python 模块级变量在 Streamlit 热重载时会重置
- 浏览器刷新可能触发 Streamlit 重新加载模块
- 导致每次刷新后都要重新扫描数据库

## 解决方案

### 使用 Streamlit 原生缓存 `@st.cache_data`
将缓存改为使用 Streamlit 的 `@st.cache_data(ttl=None)` 装饰器：
- **跨会话持久化**：刷新页面后缓存仍然有效
- **支持磁盘缓存**：即使服务器重启也能恢复
- **自动管理**：Streamlit 自动处理缓存失效

### 缓存自动失效
在以下操作后自动清除缓存：
- 入库新文件 → `clear_database_stats_cache()`
- 删除文件 → `clear_database_stats_cache()`

## 修改的文件

### backend/app/core/file_catalog.py

```python
import streamlit as st

@st.cache_data(ttl=None, show_spinner=False)
def _get_database_stats_impl(collection_name: str) -> Tuple[Dict[str, int], int]:
    """
    内部实现：获取数据库统计信息（使用 Streamlit 缓存）
    ttl=None 表示永久缓存，直到手动清除
    """
    # ... 扫描数据库

def get_database_stats(collection_name: str = "database", use_cache: bool = True):
    """获取数据库统计信息"""
    if use_cache:
        return _get_database_stats_impl(collection_name)
    else:
        clear_database_stats_cache()
        return _get_database_stats_impl(collection_name)

def clear_database_stats_cache():
    """清除数据库统计缓存（入库/删除文件后调用）"""
    _get_database_stats_impl.clear()
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
| 点击按钮（同一会话） | ~20 秒（缓存过期） | **0 秒** |
| 刷新页面后访问 | ~20 秒（模块变量重置） | **0 秒** |
| 新标签页访问 | ~20 秒 | **0 秒** |
| 入库/删除后首次访问 | ~20 秒 | ~20 秒 |

## 缓存生命周期

```
首次访问 → 构建缓存（~20秒）
    ↓
后续访问 → 使用缓存（0秒）
    ↓
刷新页面 → 使用缓存（0秒）✅ 新增
    ↓
入库/删除 → 自动清除缓存
    ↓
下次访问 → 重新构建缓存（~20秒）
```

## 影响说明

- **搜索功能**：不受影响，词汇索引会在数据变化时自动重建
- **UI 显示**：入库/删除后立即显示最新状态（缓存已清除）
- **内存占用**：缓存仅占用少量内存（统计信息约几 MB）
- **跨会话持久**：刷新页面、新标签页都使用同一缓存

## 环境变量（已移除）

以下环境变量已不再需要：
- ~~`LEX_INDEX_TTL_SEC`~~ - 已移除 TTL 机制
- ~~`DB_STATS_CACHE_TTL`~~ - 已移除 TTL 机制

## 更新日期

2026-03-10（更新：使用 Streamlit 原生缓存）
