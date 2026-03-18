"""
Backend runtime helpers for model factories and cached local models.
"""
import gc
from pathlib import Path

from dotenv import load_dotenv

from ..config import settings

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

    model_type = getattr(ModelType, settings.MEMORY_TOKEN_COUNTER_MODEL, ModelType.GPT_4O_MINI)

    try:
        counter = OpenAITokenCounter(model_type)
        counter.count_tokens_from_messages([])
        return counter
    except Exception as exc:
        print(f"[WARNING] OpenAITokenCounter unavailable, fallback to StubTokenCounter: {exc}")
        return StubTokenCounter()


def _build_model_config(
    *,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stream: bool = False,
) -> dict:
    config: dict = {}
    if temperature is not None:
        config["temperature"] = temperature
    if top_p is not None:
        config["top_p"] = top_p
    if max_tokens is not None:
        config["max_tokens"] = max_tokens
    if stream:
        config["stream"] = True
        config["stream_options"] = {"include_usage": True}
    return config


def backend_model(
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    url: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
):
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    model_config_dict = _build_model_config(
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model_name or settings.MODEL_NAME,
        api_key=api_key or settings.OPENAI_API_KEY,
        url=url or settings.OPENAI_API_URL,
        token_counter=build_token_counter(),
        model_config_dict=model_config_dict or None,
    )


def stream_model(
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    url: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
):
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model_name or settings.MODEL_NAME,
        api_key=api_key or settings.OPENAI_API_KEY,
        url=url or settings.OPENAI_API_URL,
        token_counter=build_token_counter(),
        model_config_dict=_build_model_config(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stream=True,
        ),
    )


def get_embedding_model():
    global _embedding_model_cache

    if _embedding_model_cache is not None:
        return _embedding_model_cache

    from camel.embeddings import SentenceTransformerEncoder

    full_path = _resolve_project_path(settings.EMBEDDING_MODEL_PATH)
    if full_path is None:
        raise ValueError("Missing env var `conan_path` for local embedding model path")

    device = _auto_detect_device(settings.EMBEDDING_DEVICE)
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

    reranker_path = _resolve_project_path(settings.RERANKER_PATH)
    if reranker_path is None:
        return None

    try:
        from sentence_transformers import CrossEncoder

        device = _auto_detect_device(settings.RERANKER_DEVICE)
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

        model_path = _resolve_project_path(settings.TABLE_SUMMARY_MODEL_PATH or "models/Qwen2.5-1.5B-Instruct")
        if model_path is None or not model_path.exists():
            print(f"[WARNING] Table summary model not found: {model_path}")
            return False

        device = _auto_detect_device(settings.TABLE_SUMMARY_DEVICE)
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
