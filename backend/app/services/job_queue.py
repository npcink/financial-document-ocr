import asyncio
import itertools
from typing import Set

from app.core import config
from app import db
from app.services.pipeline import process_job


SHORT_JOB_FILE_LIMIT = 10
PRIORITY_SHORT = 0
PRIORITY_NORMAL = 10
PRIORITY_RETRY = 20
DEFERRED_CHILD_DELAY = 0.5


class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = asyncio.PriorityQueue()
        self._queued: Set[str] = set()
        self._active: Set[str] = set()
        self._workers: list[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._sequence = itertools.count()

    async def start(self) -> None:
        if self._workers:
            return
        worker_count = max(1, config.JOB_QUEUE_WORKERS)
        for index in range(worker_count):
            self._workers.append(asyncio.create_task(self._worker(index + 1)))
        print(f"[JobQueue] started workers={worker_count}")

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        print("[JobQueue] stopped")

    async def enqueue(self, job_id: str, priority: int | None = None) -> bool:
        if priority is None:
            priority = await self._priority_for_job(job_id)
        async with self._lock:
            if job_id in self._queued or job_id in self._active:
                return False
            self._queued.add(job_id)
            await self._queue.put((priority, next(self._sequence), job_id))
            print(f"[JobQueue] queued job={job_id} priority={priority} size={self._queue.qsize()}")
            return True

    async def position(self, job_id: str) -> int | None:
        async with self._lock:
            if job_id in self._active:
                return 0
            for index, (_, _, queued_job_id) in enumerate(sorted(self._queue._queue), start=1):
                if queued_job_id == job_id:
                    return index
            return None

    async def snapshot(self) -> dict:
        async with self._lock:
            return {
                "active": list(self._active),
                "queued": [job_id for _, _, job_id in sorted(self._queue._queue)],
            }

    async def _priority_for_job(self, job_id: str) -> int:
        job = await asyncio.to_thread(db.get_job, job_id)
        if not job:
            return PRIORITY_NORMAL
        if job.get("total_files", 0) <= SHORT_JOB_FILE_LIMIT:
            return PRIORITY_SHORT
        error_message = job.get("error_message") or ""
        if "重新排队" in error_message or "重试" in error_message:
            return PRIORITY_RETRY
        return PRIORITY_NORMAL

    async def _worker(self, index: int) -> None:
        while True:
            priority, _, job_id = await self._queue.get()
            if await self._should_defer_for_parent_limit(job_id):
                async with self._lock:
                    self._queued.add(job_id)
                    await self._queue.put((priority, next(self._sequence), job_id))
                self._queue.task_done()
                await asyncio.sleep(DEFERRED_CHILD_DELAY)
                continue
            async with self._lock:
                self._queued.discard(job_id)
                self._active.add(job_id)
            try:
                print(f"[JobQueue] worker={index} start job={job_id}")
                await process_job(job_id)
                print(f"[JobQueue] worker={index} finish job={job_id}")
            except Exception as exc:
                print(f"[JobQueue] worker={index} job={job_id} failed: {exc}")
            finally:
                async with self._lock:
                    self._active.discard(job_id)
                self._queue.task_done()

    async def _should_defer_for_parent_limit(self, job_id: str) -> bool:
        limit = max(1, config.MAX_ACTIVE_CHILDREN_PER_PARENT)
        parent_job_id = await asyncio.to_thread(db.get_parent_job_id, job_id)
        if not parent_job_id:
            return False
        async with self._lock:
            active_siblings = [
                active_id for active_id in self._active
                if active_id != job_id
            ]
        if not active_siblings:
            return False
        sibling_parent_ids = await asyncio.gather(
            *[asyncio.to_thread(db.get_parent_job_id, active_id) for active_id in active_siblings]
        )
        active_same_parent = sum(1 for sibling_parent_id in sibling_parent_ids if sibling_parent_id == parent_job_id)
        if active_same_parent >= limit:
            print(
                f"[JobQueue] defer child={job_id} parent={parent_job_id} "
                f"active_same_parent={active_same_parent} limit={limit}"
            )
            return True
        return False


job_queue = JobQueue()
