import asyncio
import os
import hashlib
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from app import db
from app.models.schemas import MergeExportRequest
from app.services.excel import (
    AUDIT_HEADERS,
    BASE_HEADERS,
    DERIVED_HEADERS,
    EXPORT_PROFILE_FULL,
    EXPORT_PROFILE_STANDARD,
    csv_line,
    audit_headers_for,
    derived_headers_for,
    export_columns_for,
    flatten_result_row,
    generate_csv_zip,
    generate_excel,
    normalize_fields_for_export,
)

router = APIRouter()
EXPORTABLE_STATUSES = {"completed", "partial_failed", "timeout_partial"}
IN_PROGRESS_STATUSES = {"queued", "processing", "uploaded", "pending"}


@router.get("/{job_id}")
async def download_excel(
    request: Request,
    job_id: str,
    columns: str = Query(default="", description="逗号分隔的自定义列名"),
    format: str = Query(default="xlsx", pattern="^(xlsx|csv)$"),
    include_partial: bool = Query(default=False, description="任务未结束时导出当前已产生的结果"),
    detail: str = Query(default=EXPORT_PROFILE_STANDARD, pattern="^(standard|full)$", description="导出明细级别: standard 财务简洁版, full 完整排查版"),
):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    effective_status = job["status"]
    if job.get("is_batch"):
        counts = await asyncio.to_thread(db.get_result_counts_recursive, job_id)
        child_jobs = await asyncio.to_thread(db.get_child_jobs, job_id)
        child_statuses = [child["status"] for child in child_jobs]
        if any(status in ("queued", "processing", "uploaded", "pending") for status in child_statuses):
            effective_status = "processing"
        elif counts["failed_files"] or counts["pending_files"]:
            effective_status = "partial_failed" if counts["completed_files"] else "failed"
        else:
            effective_status = "completed"
    total_results = await asyncio.to_thread(db.count_results_recursive, job_id)
    if total_results <= 0:
        raise HTTPException(status_code=404, detail="没有处理结果")
    if effective_status not in EXPORTABLE_STATUSES and not include_partial:
        raise HTTPException(
            status_code=400,
            detail=f"任务状态为 {effective_status}，请等待处理完成，或选择导出当前结果",
        )

    custom_columns = None
    if columns.strip():
        custom_columns = [c.strip() for c in columns.split(",") if c.strip()]

    if format == "csv":
        results = await asyncio.to_thread(db.get_results_recursive, job_id)
        doc_types = {
            result.get("document_type") or "unknown"
            for result in results
        }
        if len(doc_types) > 1:
            export_path = await asyncio.to_thread(generate_csv_zip, job_id, results, custom_columns, detail)
            return FileResponse(
                path=export_path,
                filename=f"识别结果_{job_id}.zip",
                media_type="application/zip",
                headers={"X-Export-File-Extension": "zip"},
            )

        csv_filename = quote(f"识别结果_{job_id}.csv")
        return StreamingResponse(
            _csv_stream(job_id, custom_columns, detail),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{csv_filename}",
                "X-Export-File-Extension": "csv",
            },
        )

    results = await asyncio.to_thread(db.get_results_recursive, job_id)
    if not results or not any(r["status"] == "completed" for r in results):
        raise HTTPException(status_code=404, detail="没有处理结果")
    updated_at = await asyncio.to_thread(db.get_recursive_updated_at, job_id)
    export_path = await asyncio.to_thread(generate_excel, job_id, results, custom_columns, updated_at, detail)

    filename = f"识别结果_{job_id}.xlsx"
    return FileResponse(
        path=export_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/merge")
async def download_merged_standard_export(
    request: Request,
    body: MergeExportRequest,
):
    api_token = getattr(request.state, "session_id", "")
    job_ids = _dedupe_job_ids(body.job_ids)
    if len(job_ids) < 2:
        raise HTTPException(status_code=400, detail="请选择至少 2 个任务进行合并导出")
    if len(job_ids) > 200:
        raise HTTPException(status_code=400, detail="一次最多合并导出 200 个任务")

    export_format = (body.format or "xlsx").lower()
    if export_format not in {"xlsx", "csv"}:
        raise HTTPException(status_code=400, detail="不支持的导出格式")

    all_results = []
    invalid_jobs = []
    empty_jobs = []
    for job_id in job_ids:
        job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
        if not job:
            invalid_jobs.append(job_id)
            continue
        effective_status = await _effective_job_status(job)
        if effective_status not in EXPORTABLE_STATUSES and not body.include_partial:
            invalid_jobs.append(f"{job_id}({effective_status})")
            continue
        results = await asyncio.to_thread(db.get_results_recursive, job_id)
        if not results:
            empty_jobs.append(job_id)
            continue
        for result in results:
            item = dict(result)
            item["filename"] = f"{job_id}/{item.get('filename', '')}"
            all_results.append(item)

    if invalid_jobs:
        raise HTTPException(status_code=400, detail=f"以下任务不可导出或无权限：{', '.join(invalid_jobs[:10])}")
    if not all_results:
        raise HTTPException(status_code=404, detail="所选任务没有可导出的结果")
    if not any(result.get("status") == "completed" for result in all_results):
        raise HTTPException(status_code=404, detail="所选任务没有成功识别结果")

    export_id = _merge_export_id(job_ids)
    export_profile = (body.detail or EXPORT_PROFILE_STANDARD).lower()
    if export_profile not in {EXPORT_PROFILE_STANDARD, EXPORT_PROFILE_FULL}:
        raise HTTPException(status_code=400, detail="不支持的导出明细级别")

    if export_format == "csv":
        export_path = await asyncio.to_thread(generate_csv_zip, export_id, all_results, None, export_profile)
        return FileResponse(
            path=export_path,
            filename=f"合并识别结果_{export_id}.zip",
            media_type="application/zip",
            headers={"X-Export-File-Extension": "zip"},
        )

    export_path = await asyncio.to_thread(generate_excel, export_id, all_results, None, None, export_profile)
    return FileResponse(
        path=export_path,
        filename=f"合并识别结果_{export_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"X-Export-File-Extension": "xlsx"},
    )


def _dedupe_job_ids(job_ids: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for job_id in job_ids or []:
        normalized = str(job_id or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _merge_export_id(job_ids: list[str]) -> str:
    digest = hashlib.sha1(",".join(job_ids).encode("utf-8")).hexdigest()[:10]
    return f"merge_{datetime_slug()}_{digest}"


def datetime_slug() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d%H%M%S")


async def _effective_job_status(job: dict) -> str:
    if not job.get("is_batch"):
        return job["status"]
    counts = await asyncio.to_thread(db.get_result_counts_recursive, job["id"])
    child_jobs = await asyncio.to_thread(db.get_child_jobs, job["id"])
    child_statuses = [child["status"] for child in child_jobs]
    if any(status in IN_PROGRESS_STATUSES for status in child_statuses):
        return "processing"
    if counts["failed_files"] or counts["pending_files"]:
        return "partial_failed" if counts["completed_files"] else "failed"
    return "completed"


async def _csv_stream(job_id: str, custom_columns: list[str] = None, detail: str = EXPORT_PROFILE_STANDARD):
    all_fields = set()
    doc_types = []
    for rows in db.iter_results_recursive(job_id, chunk_size=1000):
        for result in rows:
            doc_type = result.get("document_type") or "unknown"
            if doc_type not in doc_types:
                doc_types.append(doc_type)
            fields = normalize_fields_for_export(result.get("structured_data", {}), doc_type)
            if isinstance(fields, dict):
                all_fields.update(fields.keys())

    doc_type = doc_types[0] if len(doc_types) == 1 else "unknown"
    columns = export_columns_for(doc_type, all_fields, custom_columns, detail)
    headers = BASE_HEADERS + derived_headers_for(detail) + columns + audit_headers_for(detail)

    yield "\ufeff"
    yield csv_line(headers)
    for rows in db.iter_results_recursive(job_id, chunk_size=1000):
        for result in rows:
            row = flatten_result_row(result, columns)
            yield csv_line([row.get(header, "") for header in headers])
