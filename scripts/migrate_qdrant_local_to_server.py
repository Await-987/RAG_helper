#!/usr/bin/env python
"""
Migrate a local Qdrant collection into a running Qdrant server.

This copies point ids, payloads, and vectors directly, so it avoids
re-embedding or re-importing source PDFs.
"""
from __future__ import annotations

import argparse
from typing import Any, Iterable, List

from qdrant_client import QdrantClient
from qdrant_client.http import models


def _iter_batches(items: Iterable[models.PointStruct], batch_size: int) -> Iterable[List[models.PointStruct]]:
    batch: List[models.PointStruct] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _clone_collection(local_client: QdrantClient, server_client: QdrantClient, collection_name: str, recreate: bool) -> None:
    info = local_client.get_collection(collection_name)
    if recreate and server_client.collection_exists(collection_name):
        server_client.delete_collection(collection_name=collection_name)

    if not server_client.collection_exists(collection_name):
        # Only use fields that are accepted consistently by the remote API.
        server_client.create_collection(
            collection_name=collection_name,
            vectors_config=info.config.params.vectors,
            sparse_vectors_config=info.config.params.sparse_vectors,
            on_disk_payload=info.config.params.on_disk_payload,
        )


def migrate(local_path: str, server_url: str, collection_name: str, batch_size: int, recreate: bool) -> None:
    local_client = QdrantClient(path=local_path)
    server_client = QdrantClient(url=server_url, timeout=60, check_compatibility=False)

    info = local_client.get_collection(collection_name)
    total_points = int(info.points_count or 0)
    print(f"[INFO] local collection={collection_name} points={total_points}")

    _clone_collection(local_client, server_client, collection_name, recreate=recreate)

    offset: Any = None
    migrated = 0

    while True:
        records, offset = local_client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not records:
            break

        points = [
            models.PointStruct(
                id=record.id,
                vector=record.vector,
                payload=record.payload or {},
            )
            for record in records
        ]
        server_client.upsert(collection_name=collection_name, points=points, wait=True)
        migrated += len(points)
        print(f"[INFO] migrated {migrated}/{total_points}")

        if offset is None:
            break

    server_info = server_client.get_collection(collection_name)
    print(
        f"[DONE] server collection={collection_name} points={int(server_info.points_count or 0)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate local Qdrant data to a Qdrant server")
    parser.add_argument("--local-path", default="data/storages", help="Local Qdrant path")
    parser.add_argument("--server-url", default="http://127.0.0.1:6333", help="Target Qdrant server URL")
    parser.add_argument("--collection", default="database", help="Collection name")
    parser.add_argument("--batch-size", type=int, default=256, help="Scroll/upsert batch size")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the target collection before importing",
    )
    args = parser.parse_args()

    migrate(
        local_path=args.local_path,
        server_url=args.server_url,
        collection_name=args.collection,
        batch_size=args.batch_size,
        recreate=args.recreate,
    )


if __name__ == "__main__":
    main()
