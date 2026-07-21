"""SQLite 数据库操作封装 - 连接池版本"""

import os
import sqlite3
import json
import threading
from queue import Queue, Empty
from datetime import datetime, timedelta
from typing import Optional

DATA_DIR = os.getenv("DATA_DIR", ".")
DB_PATH = os.path.join(DATA_DIR, "jobs.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
POOL_SIZE = 10

_pool: Queue = None
_pool_lock = threading.Lock()


def _create_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    return conn


def _init_pool():
    global _pool
    if _pool is not None:
        return
    with _pool_lock:
        if _pool is None:
            _pool = Queue(maxsize=POOL_SIZE)
            for _ in range(POOL_SIZE):
                _pool.put(_create_connection())


def get_db() -> sqlite3.Connection:
    _init_pool()
    try:
        return _pool.get(timeout=5)
    except Empty:
        return _create_connection()


def return_db(conn: sqlite3.Connection):
    global _pool
    if _pool is not None and not _pool.full():
        try:
            _pool.put_nowait(conn)
            return
        except Exception:
            pass
    conn.close()


class DbConnection:
    def __init__(self):
        self.conn = None

    def __enter__(self):
        self.conn = get_db()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None:
                try:
                    self.conn.commit()
                except Exception:
                    self.conn.rollback()
                    raise
            else:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
            return_db(self.conn)
        return False


def init_db():
    with DbConnection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                requirement TEXT DEFAULT '',
                template_type TEXT DEFAULT 'general',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                total_files INTEGER DEFAULT 0,
                processed_files INTEGER DEFAULT 0,
                error_message TEXT DEFAULT NULL,
                checkpoint TEXT DEFAULT '[]',
                parent_job_id TEXT DEFAULT NULL,
                is_batch INTEGER DEFAULT 0,
                batch_index INTEGER DEFAULT 0
            )
        """)
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN started_at TEXT DEFAULT NULL")
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                document_type TEXT DEFAULT 'unknown',
                raw_ocr_text TEXT DEFAULT '',
                structured_data TEXT DEFAULT '{}',
                confidence REAL DEFAULT 0.0,
                low_confidence_fields TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                error_message TEXT DEFAULT '',
                source_document_index INTEGER DEFAULT 1,
                source_document_count INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            )
        """)
        try:
            conn.execute("ALTER TABLE results ADD COLUMN document_type TEXT DEFAULT 'unknown'")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE results ADD COLUMN error_message TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE results ADD COLUMN source_document_index INTEGER DEFAULT 1")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE results ADD COLUMN source_document_count INTEGER DEFAULT 1")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN checkpoint TEXT DEFAULT '[]'")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN api_token TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN parent_job_id TEXT DEFAULT NULL")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN is_batch INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN batch_index INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.execute("DROP TABLE IF EXISTS ocr_cache")
        conn.execute("DROP TABLE IF EXISTS llm_cache")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ocr_cache (
                file_hash TEXT NOT NULL,
                api_token TEXT NOT NULL DEFAULT '',
                ocr_result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (file_hash, api_token)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                text_hash TEXT NOT NULL,
                api_token TEXT NOT NULL DEFAULT '',
                llm_result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (text_hash, api_token)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_results_job ON results(job_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_job_id)")


def create_job(
    job_id: str,
    requirement: str,
    template_type: str,
    total_files: int,
    api_token: str = "",
    parent_job_id: str = None,
    is_batch: bool = False,
    batch_index: int = 0,
) -> dict:
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        conn.execute(
            "INSERT INTO jobs (id, status, requirement, template_type, created_at, updated_at, total_files, api_token, parent_job_id, is_batch, batch_index) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, "uploaded", requirement, template_type, now, now, total_files, api_token, parent_job_id, 1 if is_batch else 0, batch_index),
        )
    return get_job(job_id)


def update_job_template(job_id: str, template_type: str, requirement: str):
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        conn.execute(
            "UPDATE jobs SET template_type=?, requirement=?, updated_at=? WHERE id=?",
            (template_type, requirement, now, job_id),
        )


def update_job_status(job_id: str, status: str, error_message: Optional[str] = None):
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        if error_message:
            conn.execute(
                "UPDATE jobs SET status=?, updated_at=?, error_message=? WHERE id=?",
                (status, now, error_message, job_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
                (status, now, job_id),
            )


def update_job_started_at(job_id: str):
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        conn.execute("UPDATE jobs SET started_at=? WHERE id=?", (now, job_id))


def set_processed_files(job_id: str, processed_files: int):
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        conn.execute(
            "UPDATE jobs SET processed_files=?, updated_at=? WHERE id=?",
            (processed_files, now, job_id),
        )


def increment_processed(job_id: str):
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        conn.execute(
            "UPDATE jobs SET processed_files = processed_files + 1, updated_at=? WHERE id=?",
            (now, job_id),
        )


def get_job(job_id: str) -> Optional[dict]:
    with DbConnection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def verify_job_ownership(job_id: str, api_token: str) -> Optional[dict]:
    if not api_token:
        return None
    with DbConnection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id=? AND api_token=?",
            (job_id, api_token),
        ).fetchone()
        return dict(row) if row else None


def list_jobs(limit: int = 20, api_token: str = "", offset: int = 0) -> list[dict]:
    if not api_token:
        return []
    with DbConnection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE api_token = ? AND parent_job_id IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (api_token, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def list_jobs_by_status(statuses: list[str]) -> list[dict]:
    if not statuses:
        return []
    placeholders = ",".join("?" * len(statuses))
    with DbConnection() as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({placeholders}) AND is_batch = 0 ORDER BY created_at",
            statuses,
        ).fetchall()
        return [dict(r) for r in rows]


def get_child_jobs(parent_job_id: str) -> list[dict]:
    with DbConnection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE parent_job_id=? ORDER BY batch_index, created_at",
            (parent_job_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def count_active_children(parent_job_id: str) -> int:
    with DbConnection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM jobs WHERE parent_job_id=? AND status='processing'",
            (parent_job_id,),
        ).fetchone()
        return int(row["count"] or 0) if row else 0


def get_child_job_summaries(parent_job_id: str) -> list[dict]:
    with DbConnection() as conn:
        rows = conn.execute(
            """
            SELECT
                j.*,
                COALESCE(SUM(CASE WHEN r.status='completed' THEN 1 ELSE 0 END), 0) AS completed_files,
                COALESCE(SUM(CASE WHEN r.status='failed' THEN 1 ELSE 0 END), 0) AS failed_files,
                COALESCE(SUM(CASE WHEN r.status='pending' THEN 1 ELSE 0 END), 0) AS pending_files
            FROM jobs j
            LEFT JOIN results r ON r.job_id = j.id
            WHERE j.parent_job_id=?
            GROUP BY j.id
            ORDER BY j.batch_index, j.created_at
            """,
            (parent_job_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recursive_updated_at(job_id: str) -> Optional[str]:
    job = get_job(job_id)
    if not job:
        return None
    if not job.get("is_batch"):
        return job.get("updated_at")
    with DbConnection() as conn:
        row = conn.execute(
            "SELECT MAX(updated_at) AS updated_at FROM jobs WHERE id=? OR parent_job_id=?",
            (job_id, job_id),
        ).fetchone()
        return row["updated_at"] if row else job.get("updated_at")


def get_parent_job_id(job_id: str) -> Optional[str]:
    with DbConnection() as conn:
        row = conn.execute("SELECT parent_job_id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        return row["parent_job_id"]


def create_result(job_id: str, filename: str, document_type: str = "unknown") -> int:
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        cursor = conn.execute(
            "INSERT INTO results (job_id, filename, document_type, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, filename, document_type, "pending", now),
        )
        return cursor.lastrowid


def update_result(
    result_id: int,
    raw_ocr_text: str = "",
    structured_data: dict = None,
    confidence: float = 0.0,
    low_confidence_fields: list = None,
    status: str = "completed",
    document_type: str = None,
    error_message: str = "",
    source_document_index: int = 1,
    source_document_count: int = 1,
):
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        if document_type is not None:
            conn.execute(
                "UPDATE results SET raw_ocr_text=?, structured_data=?, confidence=?, "
                "low_confidence_fields=?, status=?, document_type=?, error_message=?, "
                "source_document_index=?, source_document_count=? WHERE id=?",
                (
                    raw_ocr_text,
                    json.dumps(structured_data or {}, ensure_ascii=False),
                    confidence,
                    json.dumps(low_confidence_fields or [], ensure_ascii=False),
                    status,
                    document_type,
                    error_message or "",
                    source_document_index,
                    source_document_count,
                    result_id,
                ),
            )
        else:
            conn.execute(
                "UPDATE results SET raw_ocr_text=?, structured_data=?, confidence=?, "
                "low_confidence_fields=?, status=?, error_message=?, "
                "source_document_index=?, source_document_count=? WHERE id=?",
                (
                    raw_ocr_text,
                    json.dumps(structured_data or {}, ensure_ascii=False),
                    confidence,
                    json.dumps(low_confidence_fields or [], ensure_ascii=False),
                    status,
                    error_message or "",
                    source_document_index,
                    source_document_count,
                    result_id,
                ),
            )
        conn.execute(
            "UPDATE jobs SET updated_at=? WHERE id=(SELECT job_id FROM results WHERE id=?)",
            (now, result_id),
        )


def delete_results_for_file_except(job_id: str, filename: str, keep_result_id: int) -> int:
    with DbConnection() as conn:
        cursor = conn.execute(
            "DELETE FROM results WHERE job_id=? AND filename=? AND id<>?",
            (job_id, filename, keep_result_id),
        )
        conn.execute(
            "UPDATE jobs SET updated_at=? WHERE id=?",
            (datetime.now().isoformat(), job_id),
        )
        return cursor.rowcount


def get_results(job_id: str) -> list[dict]:
    with DbConnection() as conn:
        rows = conn.execute(
            "SELECT * FROM results WHERE job_id=? ORDER BY id", (job_id,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["structured_data"] = json.loads(d["structured_data"])
            d["low_confidence_fields"] = json.loads(d["low_confidence_fields"])
            results.append(d)
        return results


def get_results_recursive(job_id: str) -> list[dict]:
    job = get_job(job_id)
    if not job or not job.get("is_batch"):
        return get_results(job_id)
    results = []
    for child in get_child_jobs(job_id):
        results.extend(get_results(child["id"]))
    return results


def get_results_by_status(job_id: str, statuses: list[str]) -> list[dict]:
    if not statuses:
        return []
    placeholders = ",".join("?" * len(statuses))
    with DbConnection() as conn:
        rows = conn.execute(
            f"SELECT * FROM results WHERE job_id=? AND status IN ({placeholders}) ORDER BY id",
            [job_id, *statuses],
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["structured_data"] = json.loads(d["structured_data"])
            d["low_confidence_fields"] = json.loads(d["low_confidence_fields"])
            results.append(d)
        return results


def get_result_counts(job_id: str) -> dict[str, int]:
    with DbConnection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM results WHERE job_id=? GROUP BY status",
            (job_id,),
        ).fetchall()
        counts = {row["status"]: row["count"] for row in rows}
    return {
        "completed_files": counts.get("completed", 0),
        "failed_files": counts.get("failed", 0),
        "pending_files": counts.get("pending", 0),
    }


def get_result_counts_recursive(job_id: str) -> dict[str, int]:
    job = get_job(job_id)
    if not job or not job.get("is_batch"):
        return get_result_counts(job_id)
    counts = {"completed": 0, "failed": 0, "pending": 0}
    with DbConnection() as conn:
        rows = conn.execute(
            """
            SELECT r.status, COUNT(*) AS count
            FROM results r
            JOIN jobs j ON r.job_id = j.id
            WHERE j.parent_job_id=?
            GROUP BY r.status
            """,
            (job_id,),
        ).fetchall()
        for row in rows:
            counts[row["status"]] = row["count"]
    return {
        "completed_files": counts.get("completed", 0),
        "failed_files": counts.get("failed", 0),
        "pending_files": counts.get("pending", 0),
    }


def get_results_summary(job_id: str) -> list[dict]:
    with DbConnection() as conn:
        rows = conn.execute(
            "SELECT id, job_id, filename, document_type, structured_data, confidence, "
            "low_confidence_fields, status, created_at, error_message, "
            "source_document_index, source_document_count "
            "FROM results WHERE job_id=? ORDER BY id", (job_id,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["structured_data"] = json.loads(d["structured_data"])
            d["low_confidence_fields"] = json.loads(d["low_confidence_fields"])
            results.append(d)
        return results


def get_results_summary_recursive(job_id: str) -> list[dict]:
    job = get_job(job_id)
    if not job or not job.get("is_batch"):
        return get_results_summary(job_id)
    results = []
    for child in get_child_jobs(job_id):
        results.extend(get_results_summary(child["id"]))
    return results


def count_results_recursive(job_id: str) -> int:
    job = get_job(job_id)
    with DbConnection() as conn:
        if job and job.get("is_batch"):
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM results r
                JOIN jobs j ON r.job_id = j.id
                WHERE j.parent_job_id=?
                """,
                (job_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM results WHERE job_id=?",
                (job_id,),
            ).fetchone()
        return int(row["count"] or 0) if row else 0


def get_results_summary_recursive_page(job_id: str, limit: int = 500, offset: int = 0) -> list[dict]:
    limit = max(1, min(int(limit or 500), 2000))
    offset = max(0, int(offset or 0))
    job = get_job(job_id)
    if not job or not job.get("is_batch"):
        query = (
            "SELECT id, job_id, filename, document_type, structured_data, confidence, "
            "low_confidence_fields, status, created_at, error_message, "
            "source_document_index, source_document_count "
            "FROM results WHERE job_id=? ORDER BY id LIMIT ? OFFSET ?"
        )
        params = (job_id, limit, offset)
    else:
        query = (
            "SELECT r.id, r.job_id, r.filename, r.document_type, r.structured_data, r.confidence, "
            "r.low_confidence_fields, r.status, r.created_at, r.error_message, "
            "r.source_document_index, r.source_document_count "
            "FROM results r JOIN jobs j ON r.job_id=j.id "
            "WHERE j.parent_job_id=? ORDER BY j.batch_index, r.id LIMIT ? OFFSET ?"
        )
        params = (job_id, limit, offset)
    with DbConnection() as conn:
        rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["structured_data"] = json.loads(d["structured_data"])
            d["low_confidence_fields"] = json.loads(d["low_confidence_fields"])
            results.append(d)
        return results


def get_recent_results_recursive(job_id: str, limit: int = 50, status: Optional[str] = None) -> list[dict]:
    limit = max(1, min(int(limit or 50), 100))
    job = get_job(job_id)
    params: list = []
    status_clause = ""
    if status:
        status_clause = " AND r.status=?"
        params.append(status)

    if not job or not job.get("is_batch"):
        query = (
            "SELECT r.id, r.job_id, r.filename, r.document_type, r.structured_data, r.confidence, "
            "r.low_confidence_fields, r.status, r.created_at, r.error_message, "
            "r.source_document_index, r.source_document_count "
            "FROM results r WHERE r.job_id=?"
            f"{status_clause} ORDER BY r.id DESC LIMIT ?"
        )
        params = [job_id, *params, limit]
    else:
        query = (
            "SELECT r.id, r.job_id, r.filename, r.document_type, r.structured_data, r.confidence, "
            "r.low_confidence_fields, r.status, r.created_at, r.error_message, "
            "r.source_document_index, r.source_document_count "
            "FROM results r JOIN jobs j ON r.job_id=j.id "
            "WHERE j.parent_job_id=?"
            f"{status_clause} ORDER BY r.id DESC LIMIT ?"
        )
        params = [job_id, *params, limit]

    with DbConnection() as conn:
        rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["structured_data"] = json.loads(d["structured_data"])
            d["low_confidence_fields"] = json.loads(d["low_confidence_fields"])
            results.append(d)
        return results


def iter_results_recursive(job_id: str, chunk_size: int = 1000):
    offset = 0
    while True:
        rows = get_results_summary_recursive_page(job_id, chunk_size, offset)
        if not rows:
            break
        yield rows
        offset += len(rows)


def get_result_full(result_id: int) -> Optional[dict]:
    with DbConnection() as conn:
        row = conn.execute(
            "SELECT * FROM results WHERE id=?", (result_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["structured_data"] = json.loads(d["structured_data"])
        d["low_confidence_fields"] = json.loads(d["low_confidence_fields"])
        return d


def save_checkpoint(job_id: str, processed_ids: list[int]):
    with DbConnection() as conn:
        conn.execute(
            "UPDATE jobs SET checkpoint=? WHERE id=?",
            (json.dumps(processed_ids, ensure_ascii=False), job_id),
        )


def get_checkpoint(job_id: str) -> list[int]:
    with DbConnection() as conn:
        row = conn.execute("SELECT checkpoint FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or row["checkpoint"] is None:
            return []
        try:
            return json.loads(row["checkpoint"])
        except (json.JSONDecodeError, TypeError):
            return []


def get_ocr_cache(file_hash: str, api_token: str = "") -> Optional[dict]:
    with DbConnection() as conn:
        row = conn.execute(
            "SELECT ocr_result, created_at FROM ocr_cache WHERE file_hash=? AND api_token=?",
            (file_hash, api_token),
        ).fetchone()
        if row is None:
            return None
        return {"ocr_result": row["ocr_result"], "created_at": row["created_at"]}


def set_ocr_cache(file_hash: str, ocr_result: dict, api_token: str = "") -> None:
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ocr_cache (file_hash, api_token, ocr_result, created_at) VALUES (?, ?, ?, ?)",
            (file_hash, api_token, json.dumps(ocr_result, ensure_ascii=False), now),
        )


def cleanup_expired_cache(hours: int = 24) -> int:
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with DbConnection() as conn:
        conn.execute("DELETE FROM ocr_cache WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM llm_cache WHERE created_at < ?", (cutoff,))
        return conn.total_changes


def get_llm_cache(text_hash: str, api_token: str = "") -> Optional[dict]:
    with DbConnection() as conn:
        row = conn.execute(
            "SELECT llm_result, created_at FROM llm_cache WHERE text_hash=? AND api_token=?",
            (text_hash, api_token),
        ).fetchone()
        if row is None:
            return None
        return {"llm_result": json.loads(row["llm_result"]), "created_at": row["created_at"]}


def set_llm_cache(text_hash: str, llm_result: dict, api_token: str = "") -> None:
    now = datetime.now().isoformat()
    with DbConnection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (text_hash, api_token, llm_result, created_at) VALUES (?, ?, ?, ?)",
            (text_hash, api_token, json.dumps(llm_result, ensure_ascii=False), now),
        )


def delete_job(job_id: str):
    with DbConnection() as conn:
        child_rows = conn.execute("SELECT id FROM jobs WHERE parent_job_id=?", (job_id,)).fetchall()
        child_ids = [row["id"] for row in child_rows]
        for child_id in child_ids:
            conn.execute("DELETE FROM results WHERE job_id=?", (child_id,))
        conn.execute("DELETE FROM results WHERE job_id=?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE parent_job_id=?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))


def purge_expired_results(hours: int = 72) -> int:
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with DbConnection() as conn:
        expired_jobs = conn.execute(
            "SELECT id FROM jobs WHERE status IN "
            "('completed', 'queued', 'pending', 'processing', 'partial_failed', 'timeout_partial', 'failed', 'expired') "
            "AND updated_at < ?",
            (cutoff,),
        ).fetchall()
        if not expired_jobs:
            return 0
        job_ids = [row["id"] for row in expired_jobs]
        placeholders = ",".join("?" * len(job_ids))
        # Results must be removed before their jobs. The previous implementation
        # scrubbed result fields and then deleted jobs, leaving inaccessible
        # orphan rows after every retention pass.
        conn.execute(
            f"DELETE FROM results WHERE job_id IN ({placeholders})",
            job_ids,
        )
        conn.execute(
            f"DELETE FROM jobs WHERE id IN ({placeholders})",
            job_ids,
        )
        conn.execute(
            "DELETE FROM ocr_cache WHERE created_at < ?",
            (cutoff,),
        )
        return len(job_ids)
