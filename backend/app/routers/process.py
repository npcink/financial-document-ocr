import asyncio
import os
import json
import shutil
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.models.schemas import (
    BatchChildStatus,
    BatchSummary,
    JobStatus,
    JobDetail,
    JobSummary,
    ResultItem,
    ResultSummaryItem,
    ProcessRequest,
)
from app import db
from app.core import config
from app.services.job_queue import PRIORITY_RETRY, job_queue
from app.services.pipeline import process_single_file
from app.utils.field_normalizer import normalize_result_for_table
from app.utils.safe_paths import resource_path, sanitize_filename, validate_resource_id

router = APIRouter()

TERMINAL_STATUSES = {"completed", "partial_failed", "timeout_partial", "failed"}
RETRYABLE_JOB_STATUSES = {"failed", "partial_failed", "timeout_partial"}
RECENT_RESULT_STATUSES = {"completed", "failed", "pending"}


def _stored_file_path(job_id: object, filename: object) -> str:
    return resource_path(db.UPLOAD_DIR, job_id, sanitize_filename(filename))


def _calc_eta(job: dict) -> tuple:
    if job.get("status") != "processing":
        return None, None
    started_at = job.get("started_at")
    if not started_at:
        return None, None
    started = datetime.fromisoformat(started_at)
    elapsed = (datetime.now() - started).total_seconds()
    processed = job["processed_files"]
    total = job["total_files"]
    if processed == 0:
        return None, None
    avg_time = elapsed / processed
    remaining = total - processed
    eta_seconds = round(avg_time * remaining, 2)
    avg_time_per_file_ms = round(avg_time * 1000, 2)
    return eta_seconds, avg_time_per_file_ms


def _remaining_files(job: dict) -> int:
    return max(0, int(job.get("total_files") or 0) - int(job.get("processed_files") or 0))


def _file_worker_count_for_estimate(job: dict) -> int:
    total = int(job.get("total_files") or 0)
    if total <= 0:
        return 1
    if total <= 10:
        return max(1, total)
    error_message = job.get("error_message") or ""
    if "重新排队" in error_message or "重试" in error_message:
        return 2
    return 4


def _seconds_per_file_from_jobs(jobs: list[dict]) -> float:
    samples = []
    now = datetime.now()
    for job in jobs:
        processed = int(job.get("processed_files") or 0)
        started_at = job.get("started_at")
        if processed <= 0 or not started_at:
            continue
        try:
            started = datetime.fromisoformat(started_at)
        except ValueError:
            continue
        elapsed = max(1.0, (now - started).total_seconds())
        samples.append(elapsed / processed)
    if not samples:
        return 45.0
    samples.sort()
    mid = len(samples) // 2
    median = samples[mid] if len(samples) % 2 else (samples[mid - 1] + samples[mid]) / 2
    return max(10.0, min(180.0, median))


def _estimate_job_seconds(job: dict, seconds_per_file: float) -> float:
    remaining = _remaining_files(job)
    if remaining <= 0:
        return 0.0
    return (remaining * seconds_per_file) / _file_worker_count_for_estimate(job)


def _source_progress_from_results(results: list[dict], retry_filenames: set[str] = None) -> int:
    retry_filenames = retry_filenames or set()
    by_filename: dict[str, list[dict]] = {}
    for result in results:
        by_filename.setdefault(result["filename"], []).append(result)

    completed = 0
    for filename, items in by_filename.items():
        if filename in retry_filenames:
            continue
        if items and all(item.get("status") == "completed" for item in items):
            completed += 1
    return completed


async def _estimate_queue_wait(job: dict) -> tuple[float | None, int]:
    if job.get("status") != "queued":
        return None, 0

    snapshot = await job_queue.snapshot()
    queued_ids = snapshot["queued"]
    active_ids = snapshot["active"]
    if job["id"] not in queued_ids:
        return None, 0

    active_jobs = [j for j in await asyncio.gather(
        *[asyncio.to_thread(db.get_job, active_id) for active_id in active_ids]
    ) if j]
    seconds_per_file = _seconds_per_file_from_jobs(active_jobs)
    worker_slots = [
        _calc_eta(active_job)[0] or _estimate_job_seconds(active_job, seconds_per_file)
        for active_job in active_jobs
    ]
    while len(worker_slots) < max(1, config.JOB_QUEUE_WORKERS):
        worker_slots.append(0.0)

    queued_before = queued_ids[:queued_ids.index(job["id"])]
    queue_ahead_count = len(queued_before)
    for queued_id in queued_before:
        next_available = min(worker_slots)
        slot_index = worker_slots.index(next_available)
        queued_job = await asyncio.to_thread(db.get_job, queued_id)
        worker_slots[slot_index] = next_available + (
            _estimate_job_seconds(queued_job, seconds_per_file) if queued_job else 0.0
        )

    return round(min(worker_slots), 2), queue_ahead_count


async def _job_status(job: dict) -> JobStatus:
    if job.get("is_batch"):
        job = await asyncio.to_thread(_aggregate_batch_job, job)
    eta_seconds, avg_time_per_file_ms = _calc_eta(job)
    counts = await asyncio.to_thread(db.get_result_counts_recursive, job["id"])
    queue_position = await job_queue.position(job["id"])
    queue_eta_seconds, queue_ahead_count = await _estimate_queue_wait(job)
    return JobStatus(
        **job,
        eta_seconds=eta_seconds,
        avg_time_per_file_ms=avg_time_per_file_ms,
        queue_eta_seconds=queue_eta_seconds,
        queue_ahead_count=queue_ahead_count,
        **counts,
        queue_position=queue_position,
    )


async def _batch_child_status(child: dict) -> BatchChildStatus:
    return BatchChildStatus(
        id=child["id"],
        parent_job_id=child.get("parent_job_id"),
        batch_index=child.get("batch_index") or 0,
        status=child["status"],
        created_at=child["created_at"],
        updated_at=child["updated_at"],
        started_at=child.get("started_at"),
        total_files=child.get("total_files") or 0,
        processed_files=child.get("processed_files") or 0,
        completed_files=child.get("completed_files") or 0,
        failed_files=child.get("failed_files") or 0,
        pending_files=child.get("pending_files") or 0,
        queue_position=await job_queue.position(child["id"]),
        error_message=child.get("error_message"),
    )


def _aggregate_batch_job(parent: dict) -> dict:
    children = db.get_child_jobs(parent["id"])
    if not children:
        return parent

    counts = db.get_result_counts_recursive(parent["id"])
    processed_files = sum(int(child.get("processed_files") or 0) for child in children)
    statuses = [child.get("status") for child in children]

    if any(status == "processing" for status in statuses):
        status = "processing"
    elif any(status == "queued" for status in statuses):
        status = "queued"
    elif any(status in ("uploaded", "pending") for status in statuses):
        status = "uploaded"
    elif counts["failed_files"] or counts["pending_files"]:
        status = "partial_failed" if counts["completed_files"] else "failed"
    else:
        status = "completed"

    updated_at = max([child.get("updated_at") or parent.get("updated_at") for child in children] + [parent.get("updated_at")])
    started_values = [child.get("started_at") for child in children if child.get("started_at")]
    aggregated = dict(parent)
    aggregated.update({
        "status": status,
        "processed_files": processed_files,
        "updated_at": updated_at,
        "started_at": min(started_values) if started_values else parent.get("started_at"),
        "error_message": parent.get("error_message"),
    })
    return aggregated


async def _queue_child_unfinished(child: dict) -> int:
    results = await asyncio.to_thread(db.get_results, child["id"])
    unfinished = [r for r in results if r["status"] in ("failed", "pending")]
    if not unfinished and child["status"] == "uploaded":
        unfinished = results
    if not unfinished:
        return 0

    retry_filenames = {r["filename"] for r in unfinished}
    retry_count = 0
    for r in results:
        if r["filename"] not in retry_filenames:
            continue
        try:
            filepath = _stored_file_path(child["id"], r["filename"])
        except ValueError:
            continue
        if not os.path.exists(filepath):
            continue
        await asyncio.to_thread(db.update_result, r["id"], status="pending", error_message="等待处理")
        retry_count += 1

    if retry_count:
        completed_source_count = _source_progress_from_results(results, retry_filenames)
        await asyncio.to_thread(db.set_processed_files, child["id"], completed_source_count)
        await asyncio.to_thread(db.save_checkpoint, child["id"], [])
        await asyncio.to_thread(db.update_job_status, child["id"], "queued", f"批次任务排队处理 {retry_count} 个文件")
        await job_queue.enqueue(child["id"], priority=PRIORITY_RETRY)
    return retry_count


async def _queue_unfinished_job(job: dict) -> dict:
    job_id = job["id"]
    if job.get("is_batch"):
        children = await asyncio.to_thread(db.get_child_jobs, job_id)
        retry_count = 0
        for child in children:
            retry_count += await _queue_child_unfinished(child)
        if retry_count == 0:
            raise HTTPException(status_code=400, detail="没有未完成的文件需要重试")
        await asyncio.to_thread(db.update_job_status, job_id, "queued", f"已重新排队处理 {retry_count} 个未完成文件")
        return {"status": "queued", "count": retry_count}

    if job["status"] not in RETRYABLE_JOB_STATUSES:
        raise HTTPException(status_code=400, detail=f"任务状态为 {job['status']}，无法重试未完成文件")

    results = await asyncio.to_thread(db.get_results, job_id)
    unfinished = [r for r in results if r["status"] in ("failed", "pending")]
    if not unfinished:
        raise HTTPException(status_code=400, detail="没有未完成的文件需要重试")

    retry_filenames = {r["filename"] for r in unfinished}
    retry_count = 0
    marked_filenames = set()
    for r in results:
        if r["filename"] not in retry_filenames:
            continue
        try:
            filepath = _stored_file_path(job_id, r["filename"])
        except ValueError:
            continue
        if not os.path.exists(filepath):
            continue
        await asyncio.to_thread(
            db.update_result,
            r["id"],
            status="pending",
            error_message="等待重试",
        )
        if r["filename"] not in marked_filenames:
            marked_filenames.add(r["filename"])
            retry_count += 1

    if retry_count == 0:
        raise HTTPException(status_code=400, detail="所有未完成文件已被清理，无法重试，请重新上传")

    completed_source_count = _source_progress_from_results(results, retry_filenames)
    await asyncio.to_thread(db.set_processed_files, job_id, completed_source_count)
    await asyncio.to_thread(db.save_checkpoint, job_id, [])
    await asyncio.to_thread(db.update_job_status, job_id, "queued", f"已重新排队处理 {retry_count} 个未完成文件")
    await job_queue.enqueue(job_id, priority=PRIORITY_RETRY)
    return {"status": "queued", "count": retry_count}


@router.get("/", response_model=list[JobStatus])
async def list_jobs(request: Request, limit: int = 20, offset: int = 0):
    api_token = getattr(request.state, "session_id", "")
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    jobs = await asyncio.to_thread(db.list_jobs, limit, api_token, offset)
    return [await _job_status(job) for job in jobs]


@router.post("/{job_id}", response_model=JobStatus)
async def start_process(
    request: Request,
    job_id: str,
    body: ProcessRequest = None,
):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job["status"] not in ("uploaded", "failed", "partial_failed", "timeout_partial"):
        raise HTTPException(status_code=400, detail=f"任务状态为 {job['status']}，无法处理")

    template_type = body.template_type if body and body.template_type else "general"
    requirement = body.requirement if body and body.requirement else ""
    if template_type != job.get("template_type", "general") or requirement != job.get("requirement", ""):
        await asyncio.to_thread(db.update_job_template, job_id, template_type, requirement)

    if job.get("is_batch"):
        children = await asyncio.to_thread(db.get_child_jobs, job_id)
        if not children:
            raise HTTPException(status_code=400, detail="批次任务没有可处理的子任务")
        queued_count = 0
        for child in children:
            await asyncio.to_thread(db.update_job_template, child["id"], template_type, requirement)
            if child["status"] in ("completed", "processing", "queued"):
                continue
            await asyncio.to_thread(db.update_job_status, child["id"], "queued", "批次子任务已进入队列")
            if await job_queue.enqueue(child["id"]):
                queued_count += 1
        await asyncio.to_thread(db.update_job_status, job_id, "queued", f"批次任务已拆分为 {len(children)} 个子任务，已入队 {queued_count} 个")
        job = await asyncio.to_thread(db.get_job, job_id)
        return await _job_status(job)

    await asyncio.to_thread(db.update_job_status, job_id, "queued", "任务已进入队列，等待处理")
    await job_queue.enqueue(job_id)

    job = await asyncio.to_thread(db.get_job, job_id)
    return await _job_status(job)


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(request: Request, job_id: str):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return await _job_status(job)


@router.get("/{job_id}/batches", response_model=BatchSummary)
async def get_job_batches(request: Request, job_id: str):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    if not job.get("is_batch"):
        return BatchSummary(
            job=await _job_status(job),
            children=[],
            total_batches=0,
        )

    children = await asyncio.to_thread(db.get_child_job_summaries, job_id)
    child_statuses = [await _batch_child_status(child) for child in children]
    return BatchSummary(
        job=await _job_status(job),
        children=child_statuses,
        total_batches=len(children),
        active_batches=sum(1 for child in children if child.get("status") == "processing"),
        queued_batches=sum(1 for child in children if child.get("status") == "queued"),
        completed_batches=sum(1 for child in children if child.get("status") == "completed"),
        failed_batches=sum(1 for child in children if child.get("status") in ("failed", "partial_failed", "timeout_partial")),
    )


@router.get("/{job_id}/results/summary", response_model=JobSummary)
async def get_job_results_summary(request: Request, job_id: str, limit: int = 500, offset: int = 0):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    limit = max(1, min(limit, 2000))
    offset = max(0, offset)
    total_results = await asyncio.to_thread(db.count_results_recursive, job_id)
    results = await asyncio.to_thread(db.get_results_summary_recursive_page, job_id, limit, offset)
    return JobSummary(
        job=await _job_status(job),
        results=[ResultSummaryItem(**normalize_result_for_table(r)) for r in results],
        total_results=total_results,
        limit=limit,
        offset=offset,
        has_more=offset + len(results) < total_results,
    )


@router.get("/{job_id}/results/recent", response_model=JobSummary)
async def get_job_recent_results(request: Request, job_id: str, limit: int = 50, status: str = ""):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    normalized_status = status.strip() if status else ""
    if normalized_status and normalized_status not in RECENT_RESULT_STATUSES:
        raise HTTPException(status_code=400, detail="不支持的结果状态筛选")

    limit = max(1, min(limit, 100))
    results = await asyncio.to_thread(
        db.get_recent_results_recursive,
        job_id,
        limit,
        normalized_status or None,
    )
    return JobSummary(
        job=await _job_status(job),
        results=[ResultSummaryItem(**normalize_result_for_table(r)) for r in results],
        total_results=len(results),
        limit=limit,
        offset=0,
        has_more=False,
    )


@router.get("/{job_id}/results/{result_id}", response_model=ResultItem)
async def get_job_result_detail(request: Request, job_id: str, result_id: int):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = await asyncio.to_thread(db.get_result_full, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="结果不存在")
    if job.get("is_batch"):
        parent_id = await asyncio.to_thread(db.get_parent_job_id, result["job_id"])
        if parent_id != job_id:
            raise HTTPException(status_code=404, detail="结果不存在")
    elif result["job_id"] != job_id:
        raise HTTPException(status_code=404, detail="结果不存在")
    return ResultItem(**normalize_result_for_table(result))


@router.get("/{job_id}/results", response_model=JobDetail)
async def get_job_results(request: Request, job_id: str):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    results = await asyncio.to_thread(db.get_results_recursive, job_id)
    return JobDetail(
        job=await _job_status(job),
        results=[ResultItem(**normalize_result_for_table(r)) for r in results],
    )


@router.post("/{job_id}/retry-all")
async def retry_all_failed(
    request: Request,
    job_id: str,
):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return await _queue_unfinished_job(job)


@router.post("/{job_id}/retry-unfinished")
async def retry_unfinished(
    request: Request,
    job_id: str,
):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return await _queue_unfinished_job(job)


@router.post("/{job_id}/retry/{result_id}")
async def retry_single(
    request: Request,
    job_id: str,
    result_id: int,
):
    """重试单个文件的识别"""
    try:
        job_id = validate_resource_id(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    results = await asyncio.to_thread(db.get_results_recursive, job_id)
    target = None
    for r in results:
        if r["id"] == result_id:
            target = r
            break

    if not target:
        raise HTTPException(status_code=404, detail="结果不存在")

    if target["status"] != "failed":
        raise HTTPException(status_code=400, detail="只有失败的结果可以重试")

    target_job_id = target["job_id"]
    try:
        filepath = _stored_file_path(target_job_id, target["filename"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="文件路径无效，请重新上传") from exc
    if not os.path.exists(filepath):
        raise HTTPException(status_code=400, detail="文件已清理，无法重试，请重新上传")

    await asyncio.to_thread(db.update_result, result_id, status="pending")

    asyncio.create_task(process_single_file(target_job_id, result_id, filepath, target["filename"]))

    return {"status": "retrying"}


@router.delete("/{job_id}")
async def delete_job(request: Request, job_id: str):
    """删除历史任务及其关联数据"""
    try:
        job_id = validate_resource_id(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    children = await asyncio.to_thread(db.get_child_jobs, job_id)
    await asyncio.to_thread(db.delete_job, job_id)

    for child in children:
        try:
            upload_dir = resource_path(db.UPLOAD_DIR, child["id"])
        except ValueError:
            continue
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
    upload_dir = resource_path(db.UPLOAD_DIR, job_id)
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)

    export_dir = resource_path(db.EXPORT_DIR, job_id)
    if os.path.exists(export_dir):
        shutil.rmtree(export_dir)

    return {"status": "deleted"}


@router.get("/{job_id}/stream")
async def stream_job_status(request: Request, job_id: str):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(db.verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_stream():
        last_status = job.get("status")
        last_processed = job.get("processed_files", 0)
        last_emit_at = 0.0
        while True:
            if await request.is_disconnected():
                break
            current = await asyncio.to_thread(db.get_job, job_id)
            if not current:
                break
            current_status = await _job_status(current)
            current_data = current_status.model_dump() if hasattr(current_status, "model_dump") else current_status.dict()
            status = current_data.get("status")
            processed = current_data.get("processed_files", 0)
            now = time.monotonic()
            should_emit = status != last_status or processed != last_processed
            should_emit = should_emit or (status == "queued" and now - last_emit_at >= 5)
            if should_emit:
                last_status = status
                last_processed = processed
                last_emit_at = now
                data = {
                    "status": status,
                    "processed_files": processed,
                    "total_files": current_data.get("total_files", 0),
                    "eta_seconds": current_data.get("eta_seconds"),
                    "avg_time_per_file_ms": current_data.get("avg_time_per_file_ms"),
                    "queue_eta_seconds": current_data.get("queue_eta_seconds"),
                    "queue_ahead_count": current_data.get("queue_ahead_count"),
                    "completed_files": current_data.get("completed_files", 0),
                    "failed_files": current_data.get("failed_files", 0),
                    "pending_files": current_data.get("pending_files", 0),
                    "queue_position": current_data.get("queue_position"),
                }
                yield f"data: {json.dumps(data)}\n\n"
                if status in TERMINAL_STATUSES:
                    break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
