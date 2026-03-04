# 表格标题 LaTeX 公式转普通文本

## 修改日期
2026-03-04

## 背景

表格搜索"表27"无法正确匹配，即使内容已正确存储到数据库。

## 问题分析

### 原因
表格标题中包含 LaTeX 公式，例如：
```
表27 $5 0 0 ~ \mathbf { k V }$ 油浸式单相三绕组无励磁调压自耦电力变压器能效等级(中压线端调压)
```

当进行向量嵌入时：
1. LaTeX 公式 `$5 0 0 ~ \mathbf { k V }$` 被 tokenizer 切割成大量无意义的 token
2. "表27" 和后续文本被 LaTeX 分隔，降低了向量相似度
3. 搜索 "表27" 时，向量匹配度不够高

### 验证
- Chunk 35 确实包含表27内容（4272字符）
- 但搜索 "表27" 返回的是其他表格（表5、表16、表23）

## 修改内容

### 新增 `latex_to_plain_text()` 函数

将 LaTeX 公式转换为普通文本，保留语义信息：

| LaTeX 原文 | 转换后 | 说明 |
|------------|--------|------|
| `$5 0 0 ~ \mathbf { k V }$` | `500kV` | 电压等级 |
| `$Q _ { \\\\% }$` | `Q%` | 公式符号 |
| `~` | (移除) | LaTeX 空格 |
| `\mathbf{xxx}` | `xxx` | 移除格式 |

### 转换规则

```python
def latex_to_plain_text(latex_str: str) -> str:
    # 1. 移除 $...$ 包裹
    # 2. 移除 \mathbf{}, \textit{}, \mathrm{} 等格式命令
    # 3. 处理 ~, \quad, \qquad 等空格
    # 4. 移除花括号和多余空格
    # 5. 完全移除空格（"5 0 0" → "500"）
```

### `extract_table_content` 函数增强

```python
# 将LaTeX公式转换为普通文本
converted_caption = caption_text
latex_pattern = r'\$([^$]*)\$'
latex_matches = re.findall(latex_pattern, caption_text)
if latex_matches:
    for latex_match in latex_matches:
        plain_text = latex_to_plain_text(latex_match)
        converted_caption = converted_caption.replace(f'${latex_match}$', plain_text, 1)

# 添加转换后的版本到开头
content_parts.append(f'表格标题: {converted_caption}')
# 原始标题（保留完整LaTeX）
content_parts.append(caption_text)
```

### 输出格式对比

#### 修改前
```
表27 $5 0 0 ~ \mathbf { k V }$ 油浸式单相三绕组无励磁调压自耦电力变压器能效等级(中压线端调压)
<table>...
```

#### 修改后
```
表格标题: 表27 500kV 油浸式单相三绕组无励磁调压自耦电力变压器能效等级(中压线端调压)
表27 $5 0 0 ~ \mathbf { k V }$ 油浸式单相三绕组无励磁调压自耦电力变压器能效等级(中压线端调压)
<table>...
```

## 效果

1. **向量匹配改善**：转换后的标题没有 LaTeX 噪声，"表27" 可以更好地匹配
2. **信息保留**：LaTeX 公式内容转换为可读文本（500kV），搜索 "500kV" 也能匹配
3. **内容完整性**：原始内容（包括 LaTeX 和 HTML）完全保留
4. **向后兼容**：不影响已有功能，只是额外添加转换版本

## 测试建议

1. 清空 Qdrant 数据库
2. 重新上传 GB20052-2020.pdf
3. 搜索验证：
   - "表27" → 应返回表27内容
   - "500kV" → 应返回表27（包含500kV变压器）
   - "油浸式单相三绕组" → 应返回表27

## 影响范围

- `tools/load_files.py` - `extract_table_content()` 函数
- `latex_to_plain_text()` 新增函数
- 所有使用 MinerU 解析的表格内容入库

## 注意事项

- 仅处理表格标题中的 LaTeX，不影响表格正文（HTML）和脚注
- 转换是简化版本，复杂公式可能需要手动调整
- 正则表达式匹配 `$...$`，不支持嵌套公式
