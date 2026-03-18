"""
Backend runtime helpers for model factories and cached local models.
"""
import gc
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_embedding_model_cache = None
_reranker_model_cache = None
_table_summary_model_cache = None
_table_summary_tokenizer_cache = None


def _resolve_project_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _auto_detect_device(explicit_device: str | None) -> str:
    if explicit_device:
        return explicit_device

    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def build_token_counter():
    """
    Build a token counter that still works when tiktoken downloads fail.
    """
    from camel.models.stub_model import StubTokenCounter
    from camel.types import ModelType
    from camel.utils import OpenAITokenCounter

    counter_model_name = os.getenv("MEMORY_TOKEN_COUNTER_MODEL", "GPT_4O_MINI")
    model_type = getattr(ModelType, counter_model_name, ModelType.GPT_4O_MINI)

    try:
        counter = OpenAITokenCounter(model_type)
        counter.count_tokens_from_messages([])
        return counter
    except Exception as exc:
        print(f"[WARNING] OpenAITokenCounter unavailable, fallback to StubTokenCounter: {exc}")
        return StubTokenCounter()


def backend_model():
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=os.getenv("MODEL_NAME", "qwq32b"),
        api_key=os.getenv("OPENAI_API_KEY"),
        url=os.getenv("url"),
        token_counter=build_token_counter(),
    )


def stream_model():
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=os.getenv("MODEL_NAME", "qwq32b"),
        api_key=os.getenv("OPENAI_API_KEY"),
        url=os.getenv("url"),
        token_counter=build_token_counter(),
        model_config_dict={
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": 4000,
        },
    )


def get_embedding_model():
    global _embedding_model_cache

    if _embedding_model_cache is not None:
        return _embedding_model_cache

    from camel.embeddings import SentenceTransformerEncoder

    full_path = _resolve_project_path(os.getenv("conan_path"))
    if full_path is None:
        raise ValueError("Missing env var `conan_path` for local embedding model path")

    device = _auto_detect_device(os.getenv("EMBEDDING_DEVICE"))
    print(f"Loading embedding model from: {full_path}")
    print(f"  Using device: {device}")

    _embedding_model_cache = SentenceTransformerEncoder(
        model_name=str(full_path),
        device=device,
        trust_remote_code=True,
    )
    print("  Embedding model loaded successfully!")
    return _embedding_model_cache


def get_reranker_model():
    global _reranker_model_cache

    if _reranker_model_cache is not None:
        return _reranker_model_cache

    reranker_path = _resolve_project_path(os.getenv("reranker_path"))
    if reranker_path is None:
        return None

    try:
        from sentence_transformers import CrossEncoder

        device = _auto_detect_device(os.getenv("RERANKER_DEVICE"))
        print(f"Loading reranker model from: {reranker_path}")
        print(f"  Using device: {device}")
        _reranker_model_cache = CrossEncoder(str(reranker_path), device=device)
        print("  Reranker model loaded successfully!")
    except Exception as exc:
        print(f"Failed to load reranker: {exc}")
        _reranker_model_cache = None

    return _reranker_model_cache


def init_table_summary_model():
    global _table_summary_model_cache, _table_summary_tokenizer_cache

    if _table_summary_model_cache is not None:
        return True

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model_path = _resolve_project_path(
            os.getenv("TABLE_SUMMARY_MODEL_PATH", "models/Qwen2.5-1.5B-Instruct")
        )
        if model_path is None or not model_path.exists():
            print(f"[WARNING] Table summary model not found: {model_path}")
            return False

        device = _auto_detect_device(os.getenv("TABLE_SUMMARY_DEVICE"))
        print(f"Loading table summary model: {model_path}")
        print(f"  Using device: {device}")

        _table_summary_tokenizer_cache = AutoTokenizer.from_pretrained(
            str(model_path),
            trust_remote_code=True,
        )
        _table_summary_model_cache = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map=device,
            trust_remote_code=True,
        )
        _table_summary_model_cache.eval()
        print("  Table summary model loaded successfully!")
        return True
    except Exception as exc:
        print(f"[ERROR] Failed to load table summary model: {exc}")
        _table_summary_model_cache = None
        _table_summary_tokenizer_cache = None
        return False


def get_table_summary_model():
    if _table_summary_model_cache is None:
        init_table_summary_model()
    return _table_summary_model_cache, _table_summary_tokenizer_cache


def is_table_summary_model_loaded() -> bool:
    return _table_summary_model_cache is not None


def generate_table_summary_local(prompt: str, max_new_tokens: int = 300) -> str | None:
    model, tokenizer = get_table_summary_model()
    if model is None or tokenizer is None:
        return None

    try:
        import torch

        messages = [
            {"role": "system", "content": "你是一个专业的表格摘要助手。请简洁准确地总结表格内容，突出关键信息。"},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer([text], return_tensors="pt")
        inputs = {key: value.to(model.device) for key, value in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                temperature=1.0,
                top_p=1.0,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
        response = tokenizer.decode(generated_ids, skip_special_tokens=True)
        return response.strip()
    except Exception as exc:
        print(f"[ERROR] Table summary generation failed: {exc}")
        return None


def cleanup_table_summary_model():
    global _table_summary_model_cache, _table_summary_tokenizer_cache

    if _table_summary_model_cache is None:
        return

    import torch

    try:
        _table_summary_model_cache = _table_summary_model_cache.to("cpu")
        del _table_summary_model_cache
    except Exception:
        pass

    _table_summary_model_cache = None
    _table_summary_tokenizer_cache = None

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

    print("[INFO] Table summary model released")


backend_embedding_model = get_embedding_model
backend_reranker_model = get_reranker_model
_build_token_counter = build_token_counter
