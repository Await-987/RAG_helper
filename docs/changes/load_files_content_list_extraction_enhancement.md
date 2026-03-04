# MinerU content_list.json 内容提取增强

## 修改日期
2026-03-04

## 背景

参考 [MinerU 官方文档 - 输出文件格式](https://opendatalab.github.io/MinerU/zh/reference/output_files/)，基于 `content_list.json` 的结构增强预处理函数，完整提取公式、表格、图片的内容组合。

## 修改内容

### 1. 公式提取增强 (`extract_equation_content`)

#### 修改前
- 仅提取 `text` 字段（LaTeX 公式）
- 缺少公式标号和解释

#### 修改后
- 新增 `extract_equation_content()` 函数
- 完整提取公式的三个组成部分：
  - **公式正文**：LaTeX 公式（`text` 字段）
  - **公式标号/下标**：向后查找最多3个元素，识别包含 "Eq", "式", "(", "[", "Equation" 等特征的短文本
  - **公式解释**：查找 10-200 字符的说明性文本

#### 输出格式
```
公式: $$Q_{\%} = f(P) + g(T)$$
公式标号: (1)
公式解释: 该公式表示百分比流量与降雨量和温度的关系
```

### 2. 图片提取增强 (`extract_image_content`)

#### 修改前
- 仅提取 `image_caption`（图片描述）

#### 修改后
- 新增 `extract_image_content()` 函数
- 完整提取图片的两个组成部分：
  - **图片描述**（`image_caption`）
  - **图片脚注**（`image_footnote`）

#### 输出格式
```
图片: Fig. 1. Annual flow duration curves...
图片脚注: Data source: Pine Creek, Australia, 1989-2000
```

### 3. 表格解析重构（矩阵化）

#### 修改前
- `parse_html_table()` 直接返回格式化的文本
- 解析和格式化耦合在一起

#### 修改后
- 拆分为两个函数：
  1. **`parse_html_table_to_matrix()`**：解析 HTML 为结构化矩阵
     - 返回 `{'matrix': [[...], [...]], 'header_row': N}`
     - 处理 `colspan`（重复内容）
     - 识别表头行（`<th>`）

  2. **`format_table_matrix()`**：格式化矩阵为易读表格
     - 自动计算列宽
     - 限制单元格最大宽度（`max_width // 3`）
     - 生成标准边框格式（`+---+`）

#### 输出格式
```
表格: Table 2 Significance of rainfall terms
表格内容:
+------+-----+-----+
| Site | 10  | 20  |
+------+-----+-----+
| A    | P   | P,* |
| B    | P,T | **  |
+------+-----+-----+
表格脚注: * indicates 5% significance level
```

### 4. 类型支持扩展

#### 新增支持的类型
| 类型 | 说明 | 提取字段 |
|------|------|----------|
| `code` | 代码块/算法 | `code_body`, `code_caption` |
| `image` | 图片 | `image_caption`, `image_footnote` |

#### 更新 `type2key` 映射
```python
type2key = {
    'text': 'text',
    'equation': 'text',
    'image': 'image_caption',
    'table': 'table_caption',
    'list': 'text',
    'footer': 'text',
    'page_number': 'text',
    'code': 'code_body',  # 新增
}
```

### 5. 类型追踪增强

#### 修改前
- 仅追踪 `equation` 和 `table` 类型

#### 修改后
- 追踪 `equation`、`table`、`image` 三种特殊处理类型

## 代码结构

### 新增函数
```python
# 公式提取（带前瞻查找）
extract_equation_content(equation_item, data_list, current_idx)

# 图片提取（描述+脚注）
extract_image_content(image_item)

# 表格解析（HTML -> 矩阵）
parse_html_table_to_matrix(html_content)

# 表格格式化（矩阵 -> 文本）
format_table_matrix(matrix_data, max_width=120)
```

### 主提取逻辑
```python
if chunk_type == 'table':
    content = extract_table_content(data[idx])
elif chunk_type == 'equation':
    content = extract_equation_content(data[idx], data, idx)
elif chunk_type == 'image':
    content = extract_image_content(data[idx])
else:
    # 其他类型按原逻辑处理
```

## MinerU content_list.json 结构参考

### equation 类型
```json
{
  "type": "equation",
  "img_path": "images/xxx.jpg",
  "text": "$$\\nQ _ { \\% } = f ( P )\\n$$",
  "text_format": "latex",
  "bbox": [62, 480, 946, 904],
  "page_idx": 2
}
```

### table 类型
```json
{
  "type": "table",
  "img_path": "images/xxx.jpg",
  "table_caption": ["Table 2 ..."],
  "table_footnote": ["..."],
  "table_body": "<table>...</table>",
  "bbox": [62, 480, 946, 904],
  "page_idx": 5
}
```

### image 类型
```json
{
  "type": "image",
  "img_path": "images/xxx.jpg",
  "image_caption": ["Fig. 1. ..."],
  "image_footnote": [],
  "bbox": [62, 480, 946, 904],
  "page_idx": 1
}
```

## 影响范围

### 修改的文件
- `tools/load_files.py`

### 影响的功能
- `preprocess()` 函数：内容提取逻辑
- `load_and_store_file()` 函数：调用预处理
- 所有使用 MinerU 解析的 PDF 入库流程

## 测试建议

### 1. 公式提取测试
- 验证 LaTeX 公式完整提取
- 验证公式标号正确识别
- 验证公式解释正确关联

### 2. 图片提取测试
- 验证图片描述和脚注都包含
- 测试无脚注的图片

### 3. 表格解析测试
- 验证 HTML 表格正确转换为矩阵
- 验证复杂表格（跨列）的处理
- 验证输出格式对齐正确

### 4. 混合内容测试
- 测试包含公式、表格、图片的复杂文档
- 验证 chunk 大小和重叠正确

## 注意事项

1. **公式前瞻查找**：最多向后查找 3 个元素，可能无法关联距离较远的解释
2. **BeautifulSoup 依赖**：表格解析需要 `bs4`，无时会降级为正则解析
3. **单元格截断**：超长单元格会截断为 `max_width // 3` 字符并添加 `...`

## 相关文档

- [MinerU 官方文档 - 输出文件格式](https://opendatalab.github.io/MinerU/zh/reference/output_files/)
- `docs/changes/load_files_enhancement_table_formula_extraction.md` - 之前的表格提取增强
- `docs/changes/mineru_type_info_fix.md` - 类型信息修复
