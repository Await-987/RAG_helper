# MinerU 类型信息丢失修复

## 问题描述

MinerU 确实提取了公式和表格数据，但用户询问 Agent 列出指定文档里的公式时，Agent 回复说没有公式。

## 根本原因

在 `tools/load_files.py` 的 `load_and_store_file` 函数中：

1. `preprocess` 函数只返回 `List[str]`（纯文本字符串列表），丢失了类型信息
2. `save2Qdrant_Input` 的 `meta_data` 参数为 `None`，没有保存类型标记
3. 存储的 payload 中 `metadata` 字段为空，无法区分 chunk 是否包含公式/表格

## 变更内容

### tools/load_files.py

1. **`preprocess` 函数签名变更**
   - 原返回值：`List[str]`
   - 新返回值：`Tuple[List[str], List[List[str]]]` - (文本列表, 每个chunk对应的类型列表)

2. **`preprocess` 函数内部变更**
   - 新增 `chunk_types` 列表，记录每个 chunk 包含的类型
   - 遇到 `equation` 或 `table` 类型时，记录到 `types_in_chunk`
   - 返回时同时返回文本和类型信息

3. **`load_and_store_file` 函数变更**
   - 接收 `preprocess` 返回的类型列表
   - 构建包含 `content_types` 的 `meta_data`
   - 将类型信息传递给 `save2Qdrant_Input`

## 变更后效果

存储的 payload 结构示例：
```json
{
  "Original_file": "...",
  "Content": "...",
  "metadata": {
    "content_types": ["equation", "table"]
  }
}
```

## 已知限制

由于 `qdrant.py` 的 `save2Qdrant` 方法目前不支持为每个 chunk 设置独立的 `meta_data`，当前实现中：

- 所有 chunk 共享相同的 `content_types` 列表（文档级别的类型集合）
- 无法精确区分某个 chunk 是否包含公式或表格

**如需 chunk 级别的精确类型过滤，需进一步修改 `qdrant.py` 的 `save2Qdrant` 方法。**

## 测试建议

1. 重新入库包含公式/表格的 PDF 文档
2. 查询向量库，确认 payload 中 `metadata.content_types` 字段正确
3. 测试 Agent 是否能正确识别文档中的公式和表格

## 相关文件

- `tools/load_files.py` - 核心修改文件
- `tools/qdrant.py` - 可选：如需 chunk 级别类型支持，需修改此文件
