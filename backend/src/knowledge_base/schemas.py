"""知识库 Pydantic Schema"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


class DocumentRead(CustomBaseModel):
    """文档详情响应"""

    id: int
    workspace_id: int | None
    title: str
    source_type: str
    source_url: str | None
    file_name: str | None
    industry_tags: list[str]
    chunk_count: int
    processing_status: str  # pending / processing / ready / failed
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(CustomBaseModel):
    """文档上传响应"""

    id: int
    title: str
    processing_status: str
    message: str = "文档上传成功，正在后台处理"


class SearchRequest(CustomBaseModel):
    """RAG 检索请求"""

    query: str = Field(..., min_length=1, description="检索查询文本")
    top_k: int = Field(6, ge=1, le=20, description="返回结果数量")


class ChunkResult(CustomBaseModel):
    """检索结果分块"""

    document_id: int
    document_title: str
    content: str
    score: float
    chunk_index: int


class SearchResponse(CustomBaseModel):
    """RAG 检索响应"""

    query: str
    results: list[ChunkResult]
    total: int
