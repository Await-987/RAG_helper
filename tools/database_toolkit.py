# @ qiaoyu
from loguru import logger
from typing import List
from camel.toolkits.base import BaseToolkit, FunctionTool
from tools import QdrantDB, QdrantDB_Init


class DatabaseToolkit(BaseToolkit):
    """A toolkit for retrieving information from your local Qdrant knowledge base."""
    def __init__(self):
        super().__init__()
        # Initialize the vector database
        qdrant_init = QdrantDB_Init(collection_name="database")
        self.db = QdrantDB(input=qdrant_init)

    def close(self):
        """Close the database connection"""
        if hasattr(self, 'db'):
            self.db.close()

    def __enter__(self):
        """Support context manager"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close database connection when exit"""
        self.close()
        return False

    def search_database(self, query: str, top_k: int = 5) -> str:
        """
        Performs semantic search within the local database.
        This tool searches using natural language queries and returns the most relevant matches with confidence scores.
        Use this tool whenever you need to recall, locate, or reference previously stored knowledge or written information.

        Args:
            query (str): Natural language search query describing the information to find in notes
                        (e.g., "电网有哪些设计指标", "什么是国网经济技术研究院")
            top_k (int): Number of most relevant note results to return. Defaults to 5.
                        Increase this value if you need more comprehensive results from the notes database.

        Returns:
            str: Formatted string containing search results with the following information for each match:
                - File: Title of the note
                - Content: The matched note text content
                - Confidence: Similarity score (0.0 to 1.0) indicating relevance to the query
                Returns "No results from the vector database." if no matches are found.

        Note:
            - The search is semantic, understanding query meaning rather than exact keyword matching.
            - Higher top_k values provide more results but may include less relevant matches.
        """

        search_results = self.db.search(query=query, top_k=top_k)

        if not search_results:
            return "No results from the vector database."

        # format the output
        formatted_results = []
        for hit in search_results:
            payload = hit.get("payload", {})
            source = payload.get("Original_file", "Unknown Source")
            content = payload.get("Content", "")
            score = hit.get("score", 0.0)

            result_str = (
                f"File: {source}\n"
                f"Content: \n---\n{content}\n---\n"
                f"Confidence: {score:.4f}"
            )
            formatted_results.append(result_str)
        logger.info(f"Database Search Results:{formatted_results}")
        return "\n\n".join(formatted_results)

    def get_tools(self) -> List[FunctionTool]:
        return [
            FunctionTool(self.search_database),
            # FunctionTool(self.close)
        ]