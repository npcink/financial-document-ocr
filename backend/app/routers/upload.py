import os
import shutil
import uuid
import zipfile
import asyncio
import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse
from app.models.schemas import (
    UploadChunkResponse,
    UploadResponse,
    UploadSessionCreateRequest,
    UploadSessionResponse,
)
from app.db import create_job, verify_job_ownership, get_child_jobs, UPLOAD_DIR

router = APIRouter()

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".pdf", ".zip", ".docx", ".xlsx", ".xls", ".html", ".htm", ".xml"}
MAX_FILE_SIZE = 200 * 1024 * 1024
MAX_BATCH_FILES = int(os.getenv("MAX_BATCH_FILES", "20000"))
CHILD_BATCH_SIZE = int(os.getenv("CHILD_BATCH_SIZE", "300"))
RESUMABLE_UPLOAD_CHUNK_SIZE = int(os.getenv("RESUMABLE_UPLOAD_CHUNK_SIZE", "300"))
UPLOAD_BASE_DIR = UPLOAD_DIR
SESSION_BASE_DIR = os.path.join(UPLOAD_BASE_DIR, "_sessions")


def _is_allowed(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def _unique_path(target_dir: str, filename: str) -> str:
    basename = os.path.basename(filename)
    stem, ext = os.path.splitext(basename)
    candidate = os.path.join(target_dir, basename)
    index = 2
    while os.path.exists(candidate):
        candidate = os.path.join(target_dir, f"{stem}_{index}{ext}")
        index += 1
    return candidate


def _extract_zip(zip_path: str, target_dir: str, max_extract_files: int = MAX_BATCH_FILES) -> List[str]:
    extracted = []
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    real_target = os.path.realpath(target_dir)

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = [m for m in zf.namelist() if not m.startswith(("__MACOSX", ".")) and os.path.basename(m)]
        if len(members) > max_extract_files:
            print(f"[UPLOAD] ZIP 文件数过多 ({len(members)})，只解压前 {max_extract_files} 个")
            members = members[:max_extract_files]

        for member in members:
            basename = os.path.basename(member)
            if not basename or not _is_allowed(basename):
                continue
            ext = os.path.splitext(basename)[1].lower()
            if ext == ".zip":
                continue  # 不解压嵌套 zip
            info = zf.getinfo(member)
            if info.file_size > MAX_FILE_SIZE:
                print(f"[UPLOAD] 跳过超大文件: {basename} ({info.file_size} 字节)")
                continue
            target_path = _unique_path(target_dir, basename)
            real_path = os.path.realpath(target_path)
            if not real_path.startswith(real_target + os.sep):
                print(f"[UPLOAD] 跳过非法路径: {member}")
                continue
            with zf.open(member) as src, open(target_path, "wb") as dst:
                dst.write(src.read())
            extracted.append(target_path)
    return extracted


def _chunk_files(items: list[str], size: int) -> list[list[str]]:
    size = max(1, size)
    return [items[index:index + size] for index in range(0, len(items), size)]


def _session_dir(upload_id: str) -> str:
    return os.path.join(SESSION_BASE_DIR, os.path.basename(upload_id))


def _session_files_dir(upload_id: str) -> str:
    return os.path.join(_session_dir(upload_id), "files")


def _session_manifest_path(upload_id: str) -> str:
    return os.path.join(_session_dir(upload_id), "manifest.json")


def _now() -> str:
    return datetime.now().isoformat()


def _read_manifest(upload_id: str) -> dict:
    manifest_path = _session_manifest_path(upload_id)
    if not os.path.exists(manifest_path):
        raise HTTPException(status_code=404, detail="上传会话不存在")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_manifest(upload_id: str, manifest: dict) -> None:
    manifest["updated_at"] = _now()
    os.makedirs(_session_dir(upload_id), exist_ok=True)
    temp_path = _session_manifest_path(upload_id) + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, _session_manifest_path(upload_id))


def _verify_session_ownership(upload_id: str, api_token: str) -> dict:
    manifest = _read_manifest(upload_id)
    if not api_token or manifest.get("api_token") != api_token:
        raise HTTPException(status_code=404, detail="上传会话不存在或无权访问")
    return manifest


def _completed_chunks(manifest: dict) -> list[int]:
    chunks = manifest.get("chunks", {})
    return sorted(int(index) for index, chunk in chunks.items() if chunk.get("status") == "uploaded")


def _uploaded_file_count(manifest: dict) -> int:
    return sum(len(chunk.get("filenames", [])) for chunk in manifest.get("chunks", {}).values())


def _session_response(upload_id: str, manifest: dict) -> UploadSessionResponse:
    failed_chunks = sorted(
        int(index)
        for index, chunk in manifest.get("chunks", {}).items()
        if chunk.get("status") == "failed"
    )
    return UploadSessionResponse(
        upload_id=upload_id,
        total_files=manifest.get("total_files", 0),
        total_size=manifest.get("total_size", 0),
        total_chunks=manifest.get("total_chunks", 0),
        chunk_size=manifest.get("chunk_size", RESUMABLE_UPLOAD_CHUNK_SIZE),
        completed_chunks=_completed_chunks(manifest),
        failed_chunks=failed_chunks,
        uploaded_files=_uploaded_file_count(manifest),
        status=manifest.get("status", "created"),
    )


async def _save_upload_file_to_dir(f: UploadFile, target_dir: str, remaining_capacity: int) -> list[str]:
    if not f.filename or remaining_capacity <= 0 or not _is_allowed(f.filename):
        return []

    filename = os.path.basename(f.filename)
    ext = os.path.splitext(filename)[1].lower()
    saved_path = _unique_path(target_dir, filename)

    if ext == ".zip":
        temp_zip = saved_path + ".tmp"
        with open(temp_zip, "wb") as dst:
            while True:
                chunk = await f.read(8192)
                if not chunk:
                    break
                dst.write(chunk)
        if os.path.getsize(temp_zip) > MAX_FILE_SIZE:
            os.remove(temp_zip)
            return []
        extracted = _extract_zip(temp_zip, target_dir, remaining_capacity)
        os.remove(temp_zip)
        return [os.path.basename(p) for p in extracted]

    with open(saved_path, "wb") as dst:
        while True:
            chunk = await f.read(8192)
            if not chunk:
                break
            dst.write(chunk)
    if os.path.getsize(saved_path) > MAX_FILE_SIZE:
        os.remove(saved_path)
        return []
    return [os.path.basename(saved_path)]


async def _create_job_from_saved_files(job_id: str, saved_files: list[str], api_token: str) -> None:
    total_files = len(saved_files)
    if total_files > CHILD_BATCH_SIZE:
        child_chunks = _chunk_files(saved_files, CHILD_BATCH_SIZE)
        await asyncio.to_thread(create_job, job_id, "", "general", total_files, api_token, None, True, 0)
        for index, chunk in enumerate(child_chunks, start=1):
            child_id = f"{job_id}_{index:04d}"
            child_dir = os.path.join(UPLOAD_BASE_DIR, child_id)
            os.makedirs(child_dir, exist_ok=True)
            for filename in chunk:
                src = os.path.join(UPLOAD_BASE_DIR, job_id, filename)
                if os.path.exists(src):
                    shutil.move(src, os.path.join(child_dir, filename))
            await asyncio.to_thread(create_job, child_id, "", "general", len(chunk), api_token, job_id, False, index)
        shutil.rmtree(os.path.join(UPLOAD_BASE_DIR, job_id), ignore_errors=True)
    else:
        await asyncio.to_thread(create_job, job_id, "", "general", total_files, api_token)


@router.post("/", response_model=UploadResponse)
async def upload_files(request: Request):
    form = await request.form(max_files=MAX_BATCH_FILES, max_fields=MAX_BATCH_FILES)
    files = [
        value for _, value in form.multi_items()
        if isinstance(value, UploadFile) or getattr(value, "filename", None)
    ]
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")

    api_token = getattr(request.state, "session_id", "")

    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    saved_files: List[str] = []
    total_files = 0

    for f in files:
        if not f.filename:
            continue

        remaining = max(0, MAX_BATCH_FILES - total_files)
        saved_names = await _save_upload_file_to_dir(f, job_dir, remaining)
        saved_files.extend(saved_names)
        total_files += len(saved_names)

        if total_files >= MAX_BATCH_FILES:
            break

    if total_files == 0:
        shutil.rmtree(job_dir)
        raise HTTPException(status_code=400, detail="未找到支持的文件格式")

    await _create_job_from_saved_files(job_id, saved_files, api_token)

    return UploadResponse(
        job_id=job_id,
        total_files=total_files,
        filenames=saved_files[:500],
    )


@router.post("/session", response_model=UploadSessionResponse)
async def create_upload_session(request: Request, body: UploadSessionCreateRequest):
    api_token = getattr(request.state, "session_id", "")
    if body.total_files <= 0:
        raise HTTPException(status_code=400, detail="文件数不能为空")
    if body.total_files > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"单次最多 {MAX_BATCH_FILES} 个文件")

    upload_id = uuid.uuid4().hex[:12]
    os.makedirs(_session_files_dir(upload_id), exist_ok=True)
    chunk_size = max(1, min(body.chunk_size or RESUMABLE_UPLOAD_CHUNK_SIZE, 1000))
    total_chunks = body.total_chunks or ((body.total_files + chunk_size - 1) // chunk_size)
    manifest = {
        "upload_id": upload_id,
        "api_token": api_token,
        "total_files": body.total_files,
        "total_size": body.total_size,
        "total_chunks": total_chunks,
        "chunk_size": chunk_size,
        "status": "created",
        "chunks": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write_manifest(upload_id, manifest)
    return _session_response(upload_id, manifest)


@router.get("/session/{upload_id}", response_model=UploadSessionResponse)
async def get_upload_session(request: Request, upload_id: str):
    api_token = getattr(request.state, "session_id", "")
    manifest = _verify_session_ownership(upload_id, api_token)
    return _session_response(upload_id, manifest)


@router.post("/session/{upload_id}/chunks/{chunk_index}", response_model=UploadChunkResponse)
async def upload_session_chunk(
    request: Request,
    upload_id: str,
    chunk_index: int,
    files: List[UploadFile] = File(...),
):
    api_token = getattr(request.state, "session_id", "")
    manifest = _verify_session_ownership(upload_id, api_token)
    if manifest.get("status") not in ("created", "uploading"):
        raise HTTPException(status_code=400, detail=f"上传会话状态为 {manifest.get('status')}，不能继续上传")
    if chunk_index < 0 or chunk_index >= int(manifest.get("total_chunks") or 0):
        raise HTTPException(status_code=400, detail="分片序号超出范围")

    session_files_dir = _session_files_dir(upload_id)
    os.makedirs(session_files_dir, exist_ok=True)
    chunks = manifest.setdefault("chunks", {})
    old_chunk = chunks.get(str(chunk_index), {})
    for old_filename in old_chunk.get("filenames", []):
        old_path = os.path.join(session_files_dir, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    uploaded_before = _uploaded_file_count(manifest) - len(old_chunk.get("filenames", []))
    saved_files: list[str] = []
    try:
        for f in files:
            remaining = max(0, MAX_BATCH_FILES - uploaded_before - len(saved_files))
            saved_files.extend(await _save_upload_file_to_dir(f, session_files_dir, remaining))
            if uploaded_before + len(saved_files) >= MAX_BATCH_FILES:
                break
        if not saved_files:
            raise HTTPException(status_code=400, detail="该分片没有可上传的有效文件")
        chunks[str(chunk_index)] = {
            "status": "uploaded",
            "filenames": saved_files,
            "file_count": len(saved_files),
            "uploaded_at": _now(),
        }
        manifest["status"] = "uploading"
        _write_manifest(upload_id, manifest)
    except HTTPException:
        raise
    except Exception as exc:
        chunks[str(chunk_index)] = {
            "status": "failed",
            "filenames": [],
            "file_count": 0,
            "error_message": f"{type(exc).__name__}: {exc}",
            "uploaded_at": _now(),
        }
        _write_manifest(upload_id, manifest)
        raise

    return UploadChunkResponse(
        upload_id=upload_id,
        chunk_index=chunk_index,
        file_count=len(saved_files),
        uploaded_files=_uploaded_file_count(manifest),
        completed_chunks=_completed_chunks(manifest),
    )


@router.post("/session/{upload_id}/complete", response_model=UploadResponse)
async def complete_upload_session(request: Request, upload_id: str):
    api_token = getattr(request.state, "session_id", "")
    manifest = _verify_session_ownership(upload_id, api_token)
    completed = set(_completed_chunks(manifest))
    expected = set(range(int(manifest.get("total_chunks") or 0)))
    missing = sorted(expected - completed)
    if missing:
        raise HTTPException(status_code=400, detail=f"还有 {len(missing)} 个分片未上传完成")

    session_files_dir = _session_files_dir(upload_id)
    saved_files = []
    for index in sorted(manifest.get("chunks", {}).keys(), key=lambda item: int(item)):
        saved_files.extend(manifest["chunks"][index].get("filenames", []))
    saved_files = saved_files[:MAX_BATCH_FILES]
    if not saved_files:
        raise HTTPException(status_code=400, detail="未找到支持的文件格式")

    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    final_filenames = []
    for filename in saved_files:
        src = os.path.join(session_files_dir, filename)
        if not os.path.exists(src):
            continue
        dst = _unique_path(job_dir, filename)
        shutil.move(src, dst)
        final_filenames.append(os.path.basename(dst))
    if not final_filenames:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="上传文件已丢失，请重新上传")

    await _create_job_from_saved_files(job_id, final_filenames, api_token)
    manifest["status"] = "completed"
    manifest["job_id"] = job_id
    _write_manifest(upload_id, manifest)
    shutil.rmtree(_session_dir(upload_id), ignore_errors=True)

    return UploadResponse(
        job_id=job_id,
        total_files=len(final_filenames),
        filenames=final_filenames[:500],
        upload_id=upload_id,
    )


@router.get("/{job_id}/{filename}")
async def get_uploaded_file(request: Request, job_id: str, filename: str):
    api_token = getattr(request.state, "session_id", "")
    job = await asyncio.to_thread(verify_job_ownership, job_id, api_token)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或无权访问")
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(UPLOAD_BASE_DIR, job_id, safe_filename)
    if not os.path.exists(filepath):
        children = await asyncio.to_thread(get_child_jobs, job_id)
        for child in children:
            child_path = os.path.join(UPLOAD_BASE_DIR, child["id"], safe_filename)
            if os.path.exists(child_path):
                filepath = child_path
                break
    real_path = os.path.realpath(filepath)
    real_base = os.path.realpath(UPLOAD_BASE_DIR)
    if not real_path.startswith(real_base + os.sep):
        raise HTTPException(status_code=403, detail="非法路径")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(filepath)
