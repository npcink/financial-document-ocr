"""Pydantic 请求/响应模型"""

from typing import Optional
from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    job_id: str
    total_files: int
    filenames: list
    upload_id: Optional[str] = None


class UploadSessionCreateRequest(BaseModel):
    total_files: int = 0
    total_size: int = 0
    total_chunks: int = 0
    chunk_size: int = 300


class UploadSessionResponse(BaseModel):
    upload_id: str
    total_files: int = 0
    total_size: int = 0
    total_chunks: int = 0
    chunk_size: int = 300
    completed_chunks: list[int] = []
    failed_chunks: list[int] = []
    uploaded_files: int = 0
    status: str = "created"


class UploadChunkResponse(BaseModel):
    upload_id: str
    chunk_index: int
    file_count: int
    uploaded_files: int
    completed_chunks: list[int]
    status: str = "uploaded"


class ProcessRequest(BaseModel):
    requirement: str = Field(
        default="",
        description="用户自定义提取需求，如 '提取发票号码、日期、金额、销售方名称'",
    )
    template_type: str = Field(
        default="general",
        description="模板类型: invoice, receipt, bank_receipt, transaction_list, subscription_record, general",
    )


class MergeExportRequest(BaseModel):
    job_ids: list[str] = Field(default_factory=list, description="需要合并导出的任务 ID")
    format: str = Field(default="xlsx", description="导出格式: xlsx 或 csv")
    include_partial: bool = Field(default=False, description="是否允许导出未结束任务的当前结果")
    detail: str = Field(default="standard", description="导出明细级别: standard 或 full")


class JobStatus(BaseModel):
    id: str
    status: str
    requirement: str
    template_type: str
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    total_files: int
    processed_files: int
    error_message: Optional[str] = None
    eta_seconds: Optional[float] = None
    avg_time_per_file_ms: Optional[float] = None
    queue_eta_seconds: Optional[float] = None
    queue_ahead_count: int = 0
    completed_files: int = 0
    failed_files: int = 0
    pending_files: int = 0
    queue_position: Optional[int] = None


class BatchChildStatus(BaseModel):
    id: str
    parent_job_id: Optional[str] = None
    batch_index: int = 0
    status: str
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    total_files: int
    processed_files: int
    completed_files: int = 0
    failed_files: int = 0
    pending_files: int = 0
    queue_position: Optional[int] = None
    error_message: Optional[str] = None


class BatchSummary(BaseModel):
    job: JobStatus
    children: list[BatchChildStatus]
    total_batches: int = 0
    active_batches: int = 0
    queued_batches: int = 0
    completed_batches: int = 0
    failed_batches: int = 0


class ResultItem(BaseModel):
    id: int
    filename: str
    document_type: str
    raw_ocr_text: str
    structured_data: dict
    confidence: float
    low_confidence_fields: list
    status: str
    error_message: str = ""
    source_document_index: int = 1
    source_document_count: int = 1


class ResultSummaryItem(BaseModel):
    id: int
    filename: str
    document_type: str
    structured_data: dict
    confidence: float
    low_confidence_fields: list
    status: str
    created_at: str
    error_message: str = ""
    source_document_index: int = 1
    source_document_count: int = 1


class JobDetail(BaseModel):
    job: JobStatus
    results: list[ResultItem]


class JobSummary(BaseModel):
    job: JobStatus
    results: list[ResultSummaryItem]
    total_results: int = 0
    limit: int = 500
    offset: int = 0
    has_more: bool = False


class TemplateInfo(BaseModel):
    key: str
    name: str
    description: str
    default_fields: list


class HealthResponse(BaseModel):
    status: str
    ocr_available: bool
    llm_available: Optional[bool] = None
    llm_model: str = ""
