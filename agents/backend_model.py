import os
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType, ModelType
from camel.embeddings import SentenceTransformerEncoder
from pathlib import Path
# from camel.models.stub_model import StubTokenCounter

load_dotenv()

# ==================== 表格摘要小模型 ====================
_table_summary_model_cache = None
_table_summary_tokenizer_cache = None


def init_table_summary_model():
    """
    初始化表格摘要小模型（本地部署）

    使用 transformers 直接加载，按需初始化
    模型路径通过环境变量 TABLE_SUMMARY_MODEL_PATH 配置
    """
    global _table_summary_model_cache, _table_summary_tokenizer_cache

    if _table_summary_model_cache is not None:
        return True

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_path = os.getenv('TABLE_SUMMARY_MODEL_PATH', 'models/Qwen2.5-1.5B-Instruct')
        BASE_DIR = Path(__file__).resolve().parent.parent
        full_path = os.path.join(BASE_DIR, model_path)

        # 检查模型是否存在
        if not os.path.exists(full_path):
            print(f"[WARNING] 表格摘要模型不存在: {full_path}")
            print(f"[INFO] 请下载模型到该目录，或设置环境变量 TABLE_SUMMARY_MODEL_PATH")
            return False

        print(f"[INFO] 加载表格摘要模型: {full_path}")

        # 自动检测设备
        device = os.getenv('TABLE_SUMMARY_DEVICE', None)
        if device is None:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"  使用设备: {device}")

        # 加载 tokenizer
        _table_summary_tokenizer_cache = AutoTokenizer.from_pretrained(
            full_path,
            trust_remote_code=True
        )

        # 加载模型
        _table_summary_model_cache = AutoModelForCausalLM.from_pretrained(
            full_path,
            torch_dtype=torch.float16 if device == 'cuda' else torch.float32,
            device_map=device,
            trust_remote_code=True
        )
        _table_summary_model_cache.eval()

        print(f"  表格摘要模型加载成功!")
        return True

    except Exception as e:
        print(f"[ERROR] 加载表格摘要模型失败: {e}")
        _table_summary_model_cache = None
        _table_summary_tokenizer_cache = None
        return False


def cleanup_table_summary_model():
    """清理表格摘要模型，释放显存"""
    global _table_summary_model_cache, _table_summary_tokenizer_cache

    # 如果模型已经被清理，直接返回
    if _table_summary_model_cache is None:
        return

    import torch
    import gc

    try:
        # 移动到 CPU 再删除（避免显存残留）
        _table_summary_model_cache = _table_summary_model_cache.to('cpu')
        del _table_summary_model_cache
    except Exception:
        pass

    _table_summary_model_cache = None
    _table_summary_tokenizer_cache = None

    # 清理 CUDA 缓存
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

    print("[INFO] 表格摘要模型已释放")


def get_table_summary_model():
    """
    获取表格摘要模型和 tokenizer

    Returns:
        tuple: (model, tokenizer) 或 (None, None)
    """
    if _table_summary_model_cache is None:
        init_table_summary_model()
    return _table_summary_model_cache, _table_summary_tokenizer_cache


def generate_table_summary_local(prompt: str, max_new_tokens: int = 300) -> str:
    """
    使用本地小模型生成表格摘要

    Args:
        prompt: 输入 prompt
        max_new_tokens: 最大生成 token 数

    Returns:
        生成的摘要文本
    """
    model, tokenizer = get_table_summary_model()

    if model is None or tokenizer is None:
        return None

    try:
        import torch

        # 构建消息格式
        messages = [
            {"role": "system", "content": "你是一个专业的表格摘要助手。请简洁准确地总结表格内容，突出关键信息。"},
            {"role": "user", "content": prompt}
        ]

        # 应用 chat template
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        # Tokenize
        inputs = tokenizer([text], return_tensors="pt")
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        # 生成
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,  # 确定性输出
                temperature=1.0,
                top_p=1.0,
                pad_token_id=tokenizer.eos_token_id
            )

        # 解码
        generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
        response = tokenizer.decode(generated_ids, skip_special_tokens=True)

        return response.strip()

    except Exception as e:
        print(f"[ERROR] 表格摘要生成失败: {e}")
        return None


def backend_model():
    api_key = os.getenv('OPENAI_API_KEY')
    url = os.getenv('url')
    model_name = os.getenv('MODEL_NAME', 'qwq32b')

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        # model_type=ModelType.GPT_5_NANO,
        model_type=model_name,
        api_key=api_key,
        url=url,
        # token_counter=StubTokenCounter()
    )


def stream_model():
    api_key = os.getenv('OPENAI_API_KEY')
    url = os.getenv('url')
    model_name = os.getenv('MODEL_NAME', 'qwq32b')
    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model_name,
        api_key=api_key,
        url=url,
        # token_counter=StubTokenCounter(),
        model_config_dict={
                "stream": True,
                "stream_options": {"include_usage": True},
                "max_tokens": 4000,
            },
    )

_embedding_model_cache = None

"""
@qiaoyu 2026-01-26 注释掉改为在线 embedding 版本：
def backend_embedding_model():
    global _embedding_model_cache
    if _embedding_model_cache is None:
        api_key = os.getenv('OPENAI_API_KEY')
        base_url = os.getenv('url') or os.getenv('OPENAI_API_BASE_URL')
        # 改为在线 embedding，默认 text-embedding-3-small
        _embedding_model_cache = OpenAIEmbedding(
            model_type=EmbeddingModelType.TEXT_EMBEDDING_3_SMALL,
            api_key=api_key,
            url=base_url,
        )

    return _embedding_model_cache
"""

def backend_embedding_model():
    global _embedding_model_cache
    if _embedding_model_cache is None:
        path = os.getenv('conan_path')  # models/bge-base-zh-v1.5
        if not path:
            raise ValueError("Missing env var `conan_path` for local embedding model path")

        BASE_DIR = Path(__file__).resolve().parent.parent
        path = os.path.join(BASE_DIR, path)
        print(f"Loading embedding model from: {path}")

        # 自动检测并使用 CUDA（如果可用）
        device = os.getenv('EMBEDDING_DEVICE', None)  # 允许通过环境变量指定
        if device is None:
            # 自动检测：优先使用 CUDA
            import torch
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

        print(f"  使用设备: {device}")
        if device == 'cpu':
            print("  (首次加载需要 10-60 秒，请耐心等待...)")
        else:
            print("  (GPU 加速模式)")

        _embedding_model_cache = SentenceTransformerEncoder(
            model_name=str(path),
            device=device,
            trust_remote_code=True,
        )

        print("  Embedding model loaded successfully!")

    return _embedding_model_cache


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

            # 自动检测并使用 CUDA（如果可用）
            device = os.getenv('RERANKER_DEVICE', None)
            if device is None:
                import torch
                device = 'cuda' if torch.cuda.is_available() else 'cpu'

            print(f"  使用设备: {device}")
            _reranker_model_cache = CrossEncoder(full_path, device=device)
            return _reranker_model_cache
    except Exception as e:
        print(f"Failed to load reranker: {e}")

    return None