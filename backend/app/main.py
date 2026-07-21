import os
import time
import shutil
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app import db
from app.routers import upload, process, export, health, ocr_only
from app.db import init_db, purge_expired_results, DB_PATH, UPLOAD_DIR, EXPORT_DIR
from app.services.job_queue import job_queue

logger = logging.getLogger("app")

CLEANUP_HOURS = int(os.getenv("CLEANUP_HOURS", "72"))
CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "3600"))

_metrics = {
    "jobs_total": 0,
    "jobs_completed": 0,
    "jobs_failed": 0,
    "ocr_cache_hits": 0,
    "ocr_cache_misses": 0,
    "api_calls_total": 0,
    "api_calls_errors": 0,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if os.path.exists(DB_PATH):
        os.chmod(DB_PATH, 0o600)

    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        updated = conn.execute(
            "UPDATE jobs SET status='queued',error_message='服务重启后已重新排队处理' "
            "WHERE status='processing'"
        ).rowcount
        conn.commit()
        conn.close()
        if updated:
            print(f"[Startup] 已重新排队 {updated} 个重启前处理中任务")
    except Exception as e:
        print(f"[Startup] 僵尸任务恢复失败: {e}")

    queued_jobs = await asyncio.to_thread(db.list_jobs_by_status, ["queued", "pending"])
    for queued_job in queued_jobs:
        await job_queue.enqueue(queued_job["id"])
    if queued_jobs:
        print(f"[Startup] 已恢复 {len(queued_jobs)} 个排队任务")
    await job_queue.start()

    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    await job_queue.stop()
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        from app.drivers.ocr_cloud import close_http_client as close_ocr_http_client
        from app.drivers.llm_cloud import close_http_client as close_llm_http_client
        await close_ocr_http_client()
        await close_llm_http_client()
    except Exception:
        pass


app = FastAPI(title="发票智能识别系统", version="1.0.0", lifespan=lifespan)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")


@app.middleware("http")
async def session_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        session_id = request.headers.get("X-Session-ID", "") or request.query_params.get("session_id", "")
        if not session_id:
            return JSONResponse(status_code=401, content={"detail": "缺少会话标识"})
        request.state.session_id = session_id
    response = await call_next(request)

    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or (not path.startswith("/api/") and not path.startswith("/assets/")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(process.router, prefix="/api/process", tags=["process"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(ocr_only.router, prefix="/api/ocr", tags=["ocr"])


@app.get("/api/metrics")
async def get_metrics():
    return JSONResponse(content=_metrics)


async def _cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        now = time.time()
        cutoff_seconds = CLEANUP_HOURS * 3600

        for base in (UPLOAD_DIR, EXPORT_DIR):
            if not os.path.isdir(base):
                continue
            for name in os.listdir(base):
                path = os.path.join(base, name)
                if os.path.isdir(path) and now - os.path.getmtime(path) > cutoff_seconds:
                    shutil.rmtree(path, ignore_errors=True)

        purged = purge_expired_results(CLEANUP_HOURS)
        if purged:
            print(f"[Cleanup] 已清理 {purged} 个过期任务的敏感数据（{CLEANUP_HOURS}小时）")

        from app.db import cleanup_expired_cache
        cleaned = cleanup_expired_cache(CLEANUP_HOURS)
        if cleaned:
            print(f"[Cleanup] 已清理 {cleaned} 条过期缓存")


@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"message": "发票智能识别系统 API", "version": "1.0.0"}


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path in ("docs", "openapi.json"):
        raise HTTPException(status_code=404)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404)
