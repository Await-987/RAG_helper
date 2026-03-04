# MinerU 切换 VLM 模式并提高 DPI

## 背景

针对电网相关文档的特点：
- 复杂的电气原理图/接线图
- 密集的数据表格（参数表、实验数据）
- 大量数学公式（电路计算、电磁场公式）
- 专业术语和符号

原有的 pipeline 模式（OCR + 规则组合）在处理这些复杂场景时效果有限。

## 变更内容

### tools/mineru_toolkit.py

1. **启用 ModelScope 自动下载**
   - 原设置：`os.environ['MINERU_MODEL_SOURCE'] = "local"`
   - 新设置：`os.environ['MINERU_MODEL_SOURCE'] = "modelscope"`
   - 作用：VLM 模型首次使用时自动从 ModelScope 下载

### tools/load_files.py

1. **启用 VLM 模式**
   - 原调用：`mineru_tool.run(pdf_file_path=file_name)` - 使用默认 pipeline 模式
   - 新调用：
     ```python
     recognized_text = mineru_tool.run(
         pdf_file_path=file_name,
         parse_method="auto",
         backend="vlm-transformers"
     )
     ```

2. **提高 DPI**
   - 原默认值：`dpi: int = 150`
   - 新默认值：`dpi: int = 200`

## 预期效果

| 场景 | Pipeline 模式 | VLM 模式预期改进 |
|------|---------------|------------------|
| 复杂电气图纸 | 布局分析可能不准确，容易混淆图例和文字 | 视觉语言模型能更好理解图片语义 |
| 复杂表格 | 某些嵌套或多栏表格解析不完整 | 更准确的表格结构识别 |
| 公式识别 | 虽支持 LaTeX，但复杂公式可能错误 | 更好的公式语义理解 |
| 图表理解 | 仅提取图片，缺乏语义理解 | 可提取图表内容描述 |

## 前置条件

VLM 模式依赖以下配置（已在 `config/mineru.json` 中设置）：

```json
{
    "models-dir": {
        "pipeline": "models/mineru/OpenDataLab/PDF-Extract-Kit-1___0",
        "vlm": "/root/.cache/modelscope/hub/models/OpenDataLab/MinerU2___0-2505-0___9B"
    }
}
```

## 测试计划

1. 重新入库电网相关的 PDF 文档
2. 对比 pipeline 模式和 VLM 模式的解析结果：
   - 检查表格内容的完整性
   - 验证公式 LaTeX 输出的准确性
   - 查看图片/图表是否被正确识别
3. 观察 Agent 问答质量的提升

## 可能遇到的问题

1. **VLM 模型路径问题**：如果本地未下载 VLM 模型，首次运行会尝试下载
2. **处理速度变慢**：VLM 模式相比 pipeline 模式速度会慢一些
3. **内存占用增加**：VLM 模型需要更多 GPU/CPU 内存

## 后续优化方向

1. 如果 VLM 模式仍不够理想，可考虑：
   - 集成 Chart-LLM、UniChart 等专门图表理解模型
   - 结合 tabula-py 对复杂表格进行二次解析
   - 尝试 Table-Transformer 等专用表格识别模型

2. 性能优化：
   - 部署 SGLang 服务端，使用 `vlm-sglang-client` 模式
   - 根据实际效果调整 DPI 平衡速度和精度

## 相关文件

- `tools/load_files.py` - 核心修改文件
- `config/mineru.json` - VLM 模型配置
- `tools/mineru_toolkit.py` - MinerU 组件封装

## 参考资源

- [MinerU 官网](https://mineru.net/)
- [MinerU GitHub](https://github.com/opendatalab/MinerU)
