"""
RAG API schemas for external service access.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class RagQueryRequest(BaseModel):
    """RAG query request schema for external API."""
    query: str = Field(..., min_length=1, max_length=5000, description="User question to query the knowledge base")


class RagSearchRequest(BaseModel):
    """RAG pure search request (retrieval only, no AI generation)."""
    query: str = Field(..., min_length=1, max_length=5000, description="Search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")


class SourceFile(BaseModel):
    """Source file information with absolute path."""
    file_name: str = Field(..., description="File name (e.g., 'GB50229-2019.pdf')")
    absolute_path: str = Field(..., description="Absolute file path on the server")


class ImageInfo(BaseModel):
    """Image file information."""
    file_name: str = Field(..., description="Image file name (e.g., '文档名_1.jpg')")
    absolute_path: str = Field(..., description="Absolute image path on the server")


class RagQueryResponse(BaseModel):
    """RAG query response schema (AI-generated answer)."""
    answer: str = Field(..., description="RAG-generated answer text")
    sources: List[SourceFile] = Field(default_factory=list, description="List of referenced source files")
    images: List[ImageInfo] = Field(default_factory=list, description="List of referenced images from sources")
    query: str = Field(..., description="Original query for logging/reference")


class SearchResult(BaseModel):
    """Single search result (original document chunk)."""
    file_name: str = Field(..., description="Source file name")
    absolute_path: str = Field(..., description="Absolute file path")
    content: str = Field(..., description="Original text content from the chunk")
    score: float = Field(..., description="Relevance score (higher = more relevant)")
    chunk_type: Optional[str] = Field(None, description="Chunk type: 'text' or 'table'")
    images: List[ImageInfo] = Field(default_factory=list, description="Images extracted from this source document")


class RagSearchResponse(BaseModel):
    """RAG pure search response (original chunks, no AI processing)."""
    query: str = Field(..., description="Original search query")
    results: List[SearchResult] = Field(default_factory=list, description="Search results with original content")
    total: int = Field(..., description="Total number of results returned")