"""
Local memory wrappers to keep provider-facing message order valid.
"""
from __future__ import annotations

from typing import List

from camel.memories import LongtermAgentMemory
from camel.memories.records import ContextRecord, MemoryRecord
from camel.types import OpenAIBackendRole


class SafeLongtermAgentMemory(LongtermAgentMemory):
    """Long-term memory that never re-injects extra system messages.

    CAMEL's default `LongtermAgentMemory` writes every record, including the
    initial system message, into the vector DB and later concatenates vector
    retrieval results back into the model context. For OpenAI-compatible
    providers that require the system message to appear strictly at the
    beginning, that can produce an invalid message order.

    This wrapper keeps the original chat history intact while:
    - skipping system messages when writing to the vector DB
    - filtering system messages from vector retrieval
    - deduplicating retrieved records already present in chat history
    """

    def retrieve(self) -> List[ContextRecord]:
        chat_history = self.chat_history_block.retrieve()
        seen_uuids = {
            str(record.memory_record.uuid)
            for record in chat_history
        }
        vector_db_retrieve = [
            record
            for record in self.vector_db_block.retrieve(
                self._current_topic,
                self.retrieve_limit,
            )
            if (
                record.memory_record.role_at_backend
                != OpenAIBackendRole.SYSTEM
                and str(record.memory_record.uuid) not in seen_uuids
            )
        ]
        return chat_history[:1] + vector_db_retrieve + chat_history[1:]

    def write_records(self, records: List[MemoryRecord]) -> None:
        vector_records = [
            record
            for record in records
            if record.role_at_backend != OpenAIBackendRole.SYSTEM
        ]
        if vector_records:
            self.vector_db_block.write_records(vector_records)

        self.chat_history_block.write_records(records)

        for record in records:
            if record.role_at_backend == OpenAIBackendRole.USER:
                self._current_topic = record.message.content
