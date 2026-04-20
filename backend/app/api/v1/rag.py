"""
RAG API routes for external service access.
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.rag_api import (
    RagQueryRequest, RagQueryResponse, SourceFile, ImageInfo,
    RagSearchRequest, RagSearchResponse, SearchResult,
)
from app.dependencies import verify_rag_api_key
from app.services.chat_service import ChatService
from app.config import settings, PROJECT_ROOT
from tools.qdrant import QdrantDB, QdrantDB_Init

router = APIRouter(prefix="/rag", tags=["RAG API"])


@router.post("/query", response_model=RagQueryResponse)
async def query_rag(
    request: RagQueryRequest,
    auth: dict = Depends(verify_rag_api_key),
):
    """
    Query the RAG knowledge base and return AI-generated answer with sources.

    This endpoint performs full RAG pipeline:
    1. Retrieve relevant documents from vector database
    2. Let LLM generate answer based on retrieved content
    3. Return answer + source file references + associated images

    Returns:
    - answer: AI-generated response text
    - sources: List of referenced source files with absolute paths
    - images: List of images extracted from referenced documents
    - query: Original query for reference
    """
    try:
        chat_service = ChatService()
        result = chat_service.query_rag_sync(request.query)

        # Convert source paths to absolute paths and collect images
        sources = []
        all_images = []
        seen_files = set()

        for src in result.get("sources", []):
            file_tag, file_name = _normalize_source_ref(src)
            if not file_tag:
                continue
            abs_path = _resolve_source_path(file_tag)

            sources.append(SourceFile(
                file_name=file_name,
                absolute_path=abs_path,
            ))

            # Get images for this document (avoid duplicates)
            if file_name not in seen_files:
                seen_files.add(file_name)
                images = _get_document_images(file_name)
                all_images.extend(images)

        return RagQueryResponse(
            answer=result.get("answer", ""),
            sources=sources,
            images=all_images,
            query=request.query,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG query failed: {str(e)}"
        )


@router.post("/search", response_model=RagSearchResponse)
async def search_rag(
    request: RagSearchRequest,
    auth: dict = Depends(verify_rag_api_key),
):
    """
    Pure retrieval: search the knowledge base and return original document chunks.

    This endpoint performs ONLY retrieval, without AI generation:
    1. Vector search to find similar document chunks
    2. Return original text content directly (no reranking)
    3. Extract image paths from content (Markdown format)

    Use this when you need raw document content, not AI summaries.

    Returns:
    - query: Original search query
    - results: List of matching chunks with original content and images
    - total: Number of results returned
    """
    try:
        # Direct vector search using QdrantDB
        db = QdrantDB(input=QdrantDB_Init(collection_name=settings.COLLECTION_NAME))
        hits = db.search(query=request.query, top_k=request.top_k)

        results = []
        for hit in hits:
            payload = hit.get("payload", {})
            original_file = payload.get("Original_file", "")
            content = payload.get("Content", "")
            metadata = payload.get("metadata", {})
            score = hit.get("score", 0.0)

            if not original_file or not content:
                continue

            file_name = _extract_filename(original_file)
            abs_path = _resolve_source_path(original_file)

            # Extract images from content (Markdown format)
            images = _extract_images_from_content(content)

            results.append(SearchResult(
                file_name=file_name,
                absolute_path=abs_path,
                content=content,
                score=score,
                chunk_type=metadata.get("chunk_type"),
                images=images,
            ))

        return RagSearchResponse(
            query=request.query,
            results=results,
            total=len(results),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG search failed: {str(e)}"
        )


def _extract_images_from_content(content: str) -> list:
    """
    Extract image paths from Markdown content.

    Markdown image format: ![alt](path)
    Example: ![表格](data/stored_files/mineru_output/电力变压器试验导则_4.jpg)

    Returns:
        List of ImageInfo objects with absolute paths
    """
    # Match Markdown image syntax: ![...](...)
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    matches = re.findall(pattern, content)

    images = []
    for alt_text, img_path in matches:
        # Convert relative path to absolute
        abs_path = _resolve_image_path(img_path)
        if abs_path:
            images.append(ImageInfo(
                file_name=_extract_filename(img_path),
                absolute_path=abs_path,
            ))

    return images


def _resolve_image_path(img_path: str) -> str:
    """
    Convert image relative path to absolute path.

    Input examples:
    - data/stored_files/mineru_output/doc_1.jpg
    - mineru_output/doc_1.jpg
    """
    img_path = img_path.strip()

    # If starts with data/stored_files, relative to project root
    if img_path.startswith("data/stored_files/"):
        return str(PROJECT_ROOT / img_path)

    # If starts with mineru_output, relative to stored_files
    if img_path.startswith("mineru_output/"):
        return str(PROJECT_ROOT / "data" / "stored_files" / img_path)

    # Otherwise, assume in mineru_output
    return str(PROJECT_ROOT / "data" / "stored_files" / "mineru_output" / img_path)


def _get_document_images(file_name: str) -> list:
    """
    Find all images associated with a document by filename pattern.

    Images are stored in mineru_output/ directory with naming pattern:
    {document_name_without_extension}_{number}.jpg

    Args:
        file_name: Document filename (e.g., "GB50229-2019.pdf")

    Returns:
        List of ImageInfo objects with absolute paths
    """
    # Remove extension
    doc_basename = Path(file_name).stem

    mineru_dir = PROJECT_ROOT / "data" / "stored_files" / "mineru_output"

    if not mineru_dir.exists():
        return []

    # Find images matching pattern: {doc_basename}_*.jpg
    pattern = re.compile(rf"^{re.escape(doc_basename)}_\d+\.(jpg|jpeg|png)$", re.IGNORECASE)

    images = []
    for img_file in mineru_dir.iterdir():
        if img_file.is_file() and pattern.match(img_file.name):
            images.append(ImageInfo(
                file_name=img_file.name,
                absolute_path=str(img_file.resolve()),
            ))

    # Sort by number suffix
    def extract_number(img: ImageInfo) -> int:
        match = re.search(r"_(\d+)\.", img.file_name)
        return int(match.group(1)) if match else 0

    images.sort(key=extract_number)
    return images


def _resolve_source_path(source: str) -> str:
    """
    Convert source reference to absolute path.

    Input could be:
    - Filename: "GB50229-2019.pdf"
    - Relative path: "data/stored_files/GB50229-2019.pdf"
    """
    source = source.strip()

    # If already starts with data/stored_files, treat as relative to project root
    if source.startswith("data/stored_files/"):
        return str(PROJECT_ROOT / source)

    # If starts with /data/, treat as relative to project root
    if source.startswith("/data/"):
        return str(PROJECT_ROOT / "data" / source[6:])

    # Otherwise, assume it's a filename in stored_files directory
    return str(settings.STORAGE_DIR / source)


def _extract_filename(source: str) -> str:
    """Extract filename from a path."""
    return Path(source).name


def _normalize_source_ref(source: object) -> tuple[str, str]:
    """Normalize a source ref that may be a plain string or a structured dict."""
    if isinstance(source, dict):
        file_tag = str(source.get("file_tag") or "").strip()
        label = str(source.get("label") or "").strip()
        if file_tag:
            return file_tag, label or _extract_filename(file_tag)
        if label:
            return label, label
        return "", ""

    source_text = str(source or "").strip()
    if not source_text:
        return "", ""
    return source_text, _extract_filename(source_text)
