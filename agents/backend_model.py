import os
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType, ModelType
from camel.embeddings import SentenceTransformerEncoder
from pathlib import Path
# from camel.models.stub_model import StubTokenCounter

load_dotenv()


def backend_model():
    api_key = os.getenv('OPENAI_API_KEY')
    url = os.getenv('url')
    model_name = "qwq32b"

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
    model_name = "qwq32b"
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
        print("  (首次加载需要 10-60 秒，请耐心等待...)")

        _embedding_model_cache = SentenceTransformerEncoder(
            model_name=str(path),
            device='cpu',
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
            _reranker_model_cache = CrossEncoder(full_path)
            return _reranker_model_cache
    except Exception as e:
        print(f"Failed to load reranker: {e}")

    return None