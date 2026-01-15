import os
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType, ModelType
from camel.embeddings import SentenceTransformerEncoder
# from camel.models.stub_model import StubTokenCounter
from pathlib import Path

load_dotenv()


def backend_model():
    api_key = os.getenv('OPENAI_API_KEY')
    url = os.getenv('url')

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=ModelType.GPT_5_NANO,
        api_key=api_key,
        url=url,
        # token_counter=StubTokenCounter()
    )


def stream_model():
    api_key = os.getenv('OPENAI_API_KEY')
    url = os.getenv('url')

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=ModelType.GPT_5_NANO,
        api_key=api_key,
        url=url,
        # token_counter=StubTokenCounter(),
        model_config_dict={
                "stream": True,
                "stream_options": {"include_usage": True},
            },
    )

_embedding_model_cache = None

def backend_embedding_model():
    global _embedding_model_cache
    if _embedding_model_cache is None:
        path = os.getenv('conan_path')
        BASE_DIR = Path(__file__).resolve().parent.parent
        path = os.path.join(BASE_DIR, path)
        print(f"Loading embedding model from: {path}")
        _embedding_model_cache = SentenceTransformerEncoder(model_name=path)

    return _embedding_model_cache
