import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class DocumentRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    title: str
    filename: str
    source_name: str
    source_type: str
    status: DocumentStatus
    error: str | None
    size_bytes: int
    page_count: int | None
    chunk_count: int
    flagged_chunks: int
    embedding_backend: str | None
    uploaded_by_username: str | None
    created_at: datetime


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page: int | None
    text: str
    flagged: bool


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=5, ge=1, le=10)


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    source_name: str
    source_type: str
    page: int | None
    text: str
    score: float
    preferred: bool


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID | None
    step_index: int
    title: str
    publisher: str
    source_type: str | None
    origin: str
    status: str
    rejected_by: str | None
    score: float | None
    created_at: datetime