import os
import sys
from pathlib import Path
from camel.storages import QdrantStorage
from camel.storages import VectorRecord
from camel.storages.vectordb_storages import VectorDBQuery, VectorDBQueryResult
from dataclasses import dataclass
from loguru import logger
from typing import List, Dict
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv()


@dataclass
class QdrantDB_Init:
    collection_name: str = None


@dataclass
class save2Qdrant_Input:
    text: List[str] | str
    origin_file: str = None
    meta_data: dict = None


class QdrantDB:
    def __init__(self, input: QdrantDB_Init):
        storages_dir = os.path.join(BASE_DIR, "data", "storages")
        os.makedirs(storages_dir, exist_ok=True)
        self.storage_path = storages_dir

        try:
            from agents.backend_model import backend_embedding_model
            self.embedding_instance = backend_embedding_model()
        except Exception as e:
            raise Exception(f"Failed to initialize embedding model via API: {e}")

        self.collection_name = input.collection_name

        try:
            vector_dim = self.embedding_instance.get_output_dim()
            self.storage_instance = QdrantStorage(
                vector_dim=vector_dim,
                path=self.storage_path,
                collection_name=self.collection_name
            )
        except Exception as e:
            raise Exception(f"QdrantStorage initialization failed: {e}")

    def close(self):
        """close qdrant client"""
        try:
            if hasattr(self, 'storage_instance') and hasattr(self.storage_instance, '_client'):
                self.storage_instance._client.close()
        except Exception as e:
            logger.warning(f"Error closing Qdrant client: {e}")

    def __enter__(self):
        """support context manager"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """close qdrant client when exit"""
        self.close()
        return False

    def save2Qdrant(self, input: save2Qdrant_Input):
        """
        Input text and store the text data along with its source information into the Qdrant database.
        """
        base_payload = {'Original_file': '', 'metadata': {}, 'Content:': ''}
        if input.origin_file:
            base_payload["Original_file"] = input.origin_file

        if input.meta_data:
            base_payload["metadata"] = input.meta_data

        records = []
        texts_to_embed = [input.text] if isinstance(input.text, str) else input.text

        # calculate for all vectors
        vectors = self.embedding_instance.embed_list(list(texts_to_embed))

        # Create a separate payload for each text segment
        for vector, text_chunk in zip(vectors, texts_to_embed):
            payload = base_payload.copy()
            payload["Content"] = text_chunk
            record = VectorRecord(vector=vector, payload=payload)
            records.append(record)

        if records:
            self.storage_instance.add(records)

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Performs semantic search in the database based on a text query."""
        query_vector = self.embedding_instance.embed(query)
        query_object = VectorDBQuery(query_vector=query_vector, top_k=top_k)

        try:
            search_results: List[VectorDBQueryResult] = self.storage_instance.query(query_object)
        except Exception as e:
            logger.error(f"Error occurred while calling storage_instance.query: {e}")
            return []

        formatted_hits = []
        try:
            for hit in search_results:
                payload_data = {}
                score_data = 0.0

                # Safely access the nested attribute hit.record.payload
                if hasattr(hit, 'record') and hit.record is not None and hasattr(hit.record, 'payload'):
                    payload_data = hit.record.payload
                else:
                    logger.warning(f"Search result missing 'record' or 'record.payload' attribute: {hit}")

                # Safely access the similarity attribute
                if hasattr(hit, 'similarity'):
                    score_data = hit.similarity
                else:
                    logger.warning(f"Search result missing 'similarity' attribute: {hit}")

                # Store the extracted data in a dictionary,
                # keeping the keys 'payload' and 'score' unchanged for easy processing by the toolkit
                formatted_hits.append({
                    "payload": payload_data,
                    "score": score_data,
                })
        except Exception as e:
            logger.error(f"Error occurred while formatting search results: {e}")
            return [{"raw_result": str(r)} for r in search_results]
        return formatted_hits

    def check_storage(self, limit: int = None) -> List[Dict]:
        """
        Extracts all text fields from data stored in the Qdrant vector database.
        """
        client = self.storage_instance._client
        all_contents = []
        offset_val = None

        while True:
            points, next_page_offset = client.scroll(
                collection_name=self.collection_name,
                with_payload=True,
                with_vectors=False,
                limit=100,
                offset=offset_val
            )

            if points:
                contents = [p.payload for p in points]
                all_contents.extend(contents)

            if not next_page_offset or (limit and len(all_contents) >= limit):
                break

            offset_val = next_page_offset

        return all_contents[:limit] if limit else all_contents

    def delete_or_reset_collection(self, collectionname: str = None, reset: bool = False):
        """
        Deletes or clears a collection in the Qdrant database.
        """
        name = collectionname if collectionname else self.collection_name
        if reset:
            self.storage_instance.clear()
            logger.info(f"Collection '{name}' has been cleared.")
        else:
            # Note: _delete_collection is an internal method and may change in the future
            self.storage_instance._client.delete_collection(collection_name=name)
            logger.info(f"Collection '{name}' has been deleted.")
