# Reranker 导入修复和 StaticMethod 调用优化

## 问题描述

### 问题1：Reranker 导入失败
```
WARNING - Failed to init reranker: cannot import name 'backend_reranker_model' from 'agents.backend_model'
```

`database_toolkit.py` 尝试导入 `backend_reranker_model` 函数，但该函数在 `agents/backend_model.py` 中不存在。

### 问题2：`_apply_dynamic_cut` 参数冲突
```
Error: DatabaseToolkit._apply_dynamic_cut() got multiple values for argument 'hits'
```

在 `database_toolkit.py` 和 `qdrant.py` 中调用 `@staticmethod` 时使用 `self` 方式可能导致参数传递问题。

## 根本原因

1. `backend_reranker_model` 函数未在 `agents/backend_model.py` 中定义
2. 使用 `self._apply_dynamic_cut()` 调用静态方法时，在某些 Python 版本或特定环境下可能导致参数解析异常

## 变更内容

### agents/backend_model.py

**新增函数**：
```python
_reranker_model_cache = None


def backend_reranker_model():
    """
    Reranker (cross-encoder) for improving search relevance.
    Controlled by env var `reranker_path`.

    Returns:
        CrossEncoder instance if configured, None otherwise
    """
    global _reranker_model_cache
    if _reranker_model_cache is not None:
        return _reranker_model_cache

    try:
        from sentence_transformers import CrossEncoder
        reranker_path = os.getenv('reranker_path')
        if reranker_path:
            BASE_DIR = Path(__file__).resolve().parent.parent
            full_path = os.path.join(BASE_DIR, reranker_path)
            print(f"Loading reranker model from: {full_path}")
            _reranker_model_cache = CrossEncoder(full_path)
            return _reranker_model_cache
    except Exception as e:
        print(f"Failed to load reranker: {e}")

    return None
```

### agents/__init__.py

**更新导出列表**，添加 `backend_reranker_model`：
```python
from .backend_model import backend_model, stream_model, backend_embedding_model, backend_reranker_model

__all__ = [
    "backend_model",
    "stream_model",
    "backend_embedding_model",
    "backend_reranker_model",
    "chat_agent_factory"
]
```

### tools/qdrant.py

**修改第504行**，使用类名调用静态方法：
```python
# 修改前
return self._apply_dynamic_cut(...)

# 修改后
return QdrantDB._apply_dynamic_cut(...)
```

### tools/database_toolkit.py

**修改第104行**，使用类名调用静态方法：
```python
# 修改前
norm_scores = self._minmax_norm(scores)

# 修改后
norm_scores = DatabaseToolkit._minmax_norm(scores)
```

**修改第166行**，使用类名调用静态方法：
```python
# 修改前
hits = self._apply_dynamic_cut(...)

# 修改后
hits = DatabaseToolkit._apply_dynamic_cut(...)
```

## 变更后效果

1. Reranker 功能正常工作（如果配置了 `reranker_path` 环境变量）
2. `_apply_dynamic_cut` 调用不再报参数冲突错误
3. 混合检索 + 重排 + 动态 topk 流程正常运行

## 环境变量配置

可选：配置 reranker 模型路径以启用重排功能

```env
reranker_path=models/bge-reranker-base
```

或使用完整路径：
```env
reranker_path=/path/to/your/reranker/model
```

## 相关文件

- `agents/backend_model.py` - 新增 `backend_reranker_model` 函数
- `agents/__init__.py` - 导出新增函数
- `tools/qdrant.py` - 修改静态方法调用方式
- `tools/database_toolkit.py` - 修改静态方法调用方式
