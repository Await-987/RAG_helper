# 表格独立存储 + LLM 摘要生成

## 修改日期
2026-03-09

## 背景

当前 RAG 系统将表格与其他文本混合存储在同一个 chunk 中，导致：
1. 大表格可能被截断
2. 表格检索精度受周围文本干扰
3. 无法针对表格内容做精准的语义匹配

## 修改目标

1. 将每个表格作为独立的 chunk 存储
2. 使用 LLM 为表格生成摘要，用于向量检索
3. 保留表格与原上下文的关联，检索时可返回完整上下文

## 修改内容

### 1. 新增表格摘要生成函数

**文件**: `tools/load_files.py`

```python
def generate_table_summary(table_content: str, table_caption: str = "", use_llm_summary: bool = True) -> str:
    """
    使用 LLM 为表格生成摘要，用于向量检索

    Args:
        table_content: 表格内容（包含标题、body、脚注）
        table_caption: 表格标题（用于优先处理）
        use_llm_summary: 是否使用 LLM 生成摘要，默认开启

    Returns:
        表格摘要（200字以内）
    """
```

**特性**:
- 使用本地小模型 **Qwen2.5-1.5B-Instruct** 生成摘要
- 基于 MD5 哈希的缓存机制，避免重复生成相同表格的摘要
- 默认开启，可通过 `use_llm_summary=False` 关闭
- 模型不可用或生成失败时，自动降级为原始内容截断

### 2. 本地小模型部署

**文件**: `agents/backend_model.py`

新增以下函数用于管理本地小模型：

```python
def init_table_summary_model():
    """初始化表格摘要小模型（本地部署）"""

def cleanup_table_summary_model():
    """清理表格摘要模型，释放显存"""

def get_table_summary_model():
    """获取表格摘要模型和 tokenizer"""

def generate_table_summary_local(prompt: str, max_new_tokens: int = 300) -> str:
    """使用本地小模型生成表格摘要"""
```

**模型信息**:
- 模型: Qwen2.5-1.5B-Instruct
- 大小: ~3GB
- 显存: ~3GB (FP16) 或 ~1.5GB (INT4)
- 支持纯 CPU 运行

### 3. Streamlit 生命周期管理

**文件**: `run/streamlit.py`

- 启动时自动加载模型
- 退出时自动释放显存
- 使用 `atexit` 注册清理函数

```python
# 注册退出时的清理函数
atexit.register(cleanup_table_summary_model)

def init_session_state():
    ...
    # 初始化表格摘要模型（只执行一次）
    if "table_summary_model_initialized" not in st.session_state:
        st.session_state.table_summary_model_initialized = True
        init_table_summary_model()
```

### 4. 环境变量配置

**文件**: `.env`

```bash
# 表格摘要小模型（本地部署）
TABLE_SUMMARY_MODEL_PATH=models/Qwen2.5-1.5B-Instruct
# TABLE_SUMMARY_DEVICE=cuda  # 可选: cuda/cpu，默认自动检测
```

### 5. 修改 preprocess 函数

**新增参数**:
- `use_llm_summary: bool = True` - 是否使用 LLM 生成表格摘要
- `context_size: int = 500` - 表格上下文大小（字符数）

**新增辅助函数**:
- `extract_context()` - 提取表格前后的上下文文本
- `create_text_chunks()` - 为普通文本创建子 chunks
- `create_table_chunk()` - 创建独立的表格 chunk

### 6. 数据结构设计

**表格 chunk 结构**:
```python
{
    'child': "该表格展示了500kV变电站的主要设备参数，包括变压器容量、电压等级等...",  # LLM 摘要
    'parent': "![表格](...)\n表格标题: ...\n<table>...</table>",  # 完整表格
    'types': ['table'],
    'is_table': True,
    'context': {
        'before': "上文内容（前500字）...",   # 表格前的上下文
        'after': "下文内容（后500字）...",    # 表格后的上下文
    }
}
```

### 7. 检索时上下文恢复（可选增强）

**文件**: `tools/database_toolkit.py`

新增参数 `restore_table_context: bool = False`

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `agents/backend_model.py` | 新增本地小模型加载和管理函数 |
| `tools/load_files.py` | 1. 新增 `generate_table_summary` 函数<br>2. 新增 `extract_context` 函数<br>3. 修改 `preprocess` 函数，表格独立处理<br>4. 修改存储逻辑 |
| `tools/database_toolkit.py` | 可选：新增 `restore_table_context` 参数 |
| `run/streamlit.py` | 新增模型生命周期管理 |
| `.env` | 新增 `TABLE_SUMMARY_MODEL_PATH` 配置 |
| `scripts/download_table_summary_model.py` | 新增模型下载脚本 |

## 使用方法

### 1. 下载模型

```bash
# 方式1: 使用下载脚本
python scripts/download_table_summary_model.py

# 方式2: 手动下载
# 从 https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct 下载到 models/Qwen2.5-1.5B-Instruct/
```

### 2. 启动服务

```bash
streamlit run run/streamlit.py
```

启动时会自动加载模型：
```
[INFO] 加载表格摘要模型: /path/to/models/Qwen2.5-1.5B-Instruct
  使用设备: cuda
  表格摘要模型加载成功!
✅ 表格摘要模型初始化成功
```

### 3. 处理文件

```python
from tools.load_files import load_and_store_file

# 默认：LLM 摘要开启
load_and_store_file("document.pdf", "my_collection")

# 关闭 LLM 摘要
load_and_store_file("document.pdf", "my_collection", use_llm_summary=False)
```

## 资源占用

| 配置 | 磁盘 | 显存 | 内存 |
|------|------|------|------|
| GPU FP16 | ~3GB | ~3GB | ~1GB |
| CPU 模式 | ~3GB | 0 | ~4GB |

## 注意事项

1. **首次启动**: 模型加载需要 5-10 秒
2. **显存管理**: 退出 Streamlit 时自动释放显存
3. **降级处理**: 模型加载失败时，自动使用原始表格内容
4. **向后兼容**: 设置 `use_llm_summary=False` 可禁用摘要功能
