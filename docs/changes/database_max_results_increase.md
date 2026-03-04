# 数据库检索默认值增大（top_k 和 max_results）

## 修改日期
2026-03-04

## 背景

用户询问"有哪些表"时，agent 只能看到部分表格，无法获取所有表格。

## 问题分析

### 原因
`database_toolkit.py` 中的 `search_database` 函数默认参数过小：
- `top_k: int = 5` - 初始检索只返回 5 个结果
- `max_results: int = 20` - 最大返回 20 个结果

文档中约有 27 个表格，但检索最多返回 20 个结果，导致部分表格无法被 agent 看到。

## 修改内容

### 默认参数调整

| 参数 | 修改前 | 修改后 | 说明 |
|------|--------|--------|------|
| `top_k` | 5 | 15 | 初始检索数量 |
| `max_results` | 20 | 50 | 最大返回结果数 |
| dynamic_topk 最小保证 | 20 | 50 | 动态扩展下限 |

### 代码修改

```python
def search_database(
    self,
    query: str,
    top_k: int = 15,  # 5 → 15
    *,
    use_hybrid: bool = True,
    use_rerank: bool = True,
    dynamic_topk: bool = True,
    score_threshold: Optional[float] = None,
    max_results: int = 50,  # 20 → 50
    alpha: float = 0.75,
) -> str:
    ...
    if dynamic_topk:
        max_results = max(int(max_results), 50)  # 20 → 50
```

## 效果

- 初始检索 **15 个结果**（更多候选进入 rerank）
- Rerank + 动态阈值后最多返回 **50 个结果**
- 询问"有哪些表"时，agent 可以看到更多表格
- 适用于表格较多的文档（如 GB20052-2020 有 27 个表格）

## 影响范围

- `tools/database_toolkit.py` - `search_database()` 函数
- 所有使用数据库检索的查询

## 注意事项

- `top_k` 和 `max_results` 增大会增加检索时间
- 更多结果会占用更多 LLM 上下文
- 可通过调用时传入参数覆盖默认值
