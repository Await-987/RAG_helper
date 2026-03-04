# MinerU 混合模式：Pipeline + VLM

## 背景

针对电网文档的特点：
- **表格数据密集**：需要 Pipeline 模式的 Table-OCR 能力
- **图表/公式复杂**：需要 VLM 模式的语义理解能力

单一模式无法同时满足这两种需求：
- Pipeline 模式：表格识别好，但图表/公式理解有限
- VLM 模式：图表/公式理解强，但表格识别不佳

## 变更内容

### tools/load_files.py

1. **新增 `backend` 参数**
   - 默认值：`"both"`（混合模式）
   - 可选值：`"pipeline"`、`"vlm-transformers"`、`"both"`

2. **混合模式实现**
   - 同时运行 Pipeline 和 VLM 两种模式
   - 合并结果时按类型选择最优来源：
     - `table` 类型：使用 Pipeline 的结果
     - 其他类型（text/equation/image）：使用 VLM 的结果

## 模式对比

| 数据类型 | Pipeline 模式 | VLM 模式 | 混合模式 |
|---------|--------------|-----------|----------|
| table | ✅ Table-OCR 准确 | ❌ 可能合并到 text | ✅ 取 Pipeline |
| text | ⚠️ 基础 OCR | ✅ 语义理解强 | ✅ 取 VLM |
| equation | ⚠️ 基础识别 | ✅ 公式理解强 | ✅ 取 VLM |
| image | ⚠️ 仅提取图片 | ✅ 图像理解强 | ✅ 取 VLM |
| list | ❌ 不支持 | ✅ 支持 | ✅ 取 VLM |

## 使用示例

```python
from tools.load_files import load_and_store_file

# 方式1：Pipeline 模式（表格多时推荐）
load_and_store_file(
    file_path="path/to/file.pdf",
    collection_name="my_collection",
    backend="pipeline"
)

# 方式2：VLM 模式（图表/公式多时推荐）
load_and_store_file(
    file_path="path/to/file.pdf",
    collection_name="my_collection",
    backend="vlm-transformers"
)

# 方式3：混合模式（默认，推荐）
load_and_store_file(
    file_path="path/to/file.pdf",
    collection_name="my_collection"
    # backend="both"  # 默认值
)
```

## 性能考虑

| 模式 | 处理速度 | 内存占用 | 适用场景 |
|------|----------|----------|----------|
| Pipeline | 快 | 中等 | 表格多、批量大 |
| VLM | 慢（2-3倍） | 高 | 图表/公式多 |
| Both | 最慢（两种模式总和） | 高 | 重要文档、需要最佳质量 |

## 相关文件

- `tools/load_files.py` - 核心修改文件
- `docs/changes/mineru_vlm_mode_and_dpi_boost.md` - VLM 模式文档

## 后续优化方向

1. 添加缓存机制：避免重复处理同一 PDF
2. 异步处理：Pipeline 和 VLM 并行运行
3. 自适应选择：根据文档特征自动选择最优模式
