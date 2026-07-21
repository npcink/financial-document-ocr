import asyncio
import random
import time
from collections import deque
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable, TypeVar

import httpx

from app.core import config

T = TypeVar("T")

_rpm_lock = asyncio.Lock()
_request_times: dict[str, deque[float]] = {
    "ocr": deque(),
    "llm": deque(),
}


def _rpm_for_bucket(bucket: str) -> int:
    if bucket == "ocr":
        return config.SILICONFLOW_OCR_RPM
    if bucket == "llm":
        return config.SILICONFLOW_LLM_RPM
    return config.SILICONFLOW_CHAT_RPM


def _retry_delays() -> list[float]:
    delays = []
    for raw in config.SILICONFLOW_RETRY_DELAYS.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            delays.append(float(raw))
        except ValueError:
            continue
    return delays or [5.0, 15.0, 45.0, 120.0, 240.0]


async def wait_for_rpm_slot(bucket: str) -> None:
    rpm = _rpm_for_bucket(bucket)
    if rpm <= 0:
        return

    request_times = _request_times.setdefault(bucket, deque())
    while True:
        async with _rpm_lock:
            now = time.monotonic()
            while request_times and now - request_times[0] >= 60:
                request_times.popleft()
            if len(request_times) < rpm:
                request_times.append(now)
                return
            sleep_for = max(0.1, 60 - (now - request_times[0]))
        await asyncio.sleep(sleep_for)


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        return max(0.0, retry_at.timestamp() - time.time())
    except Exception:
        return None


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


async def siliconflow_request_with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    label: str,
    bucket: str = "llm",
) -> T:
    delays = _retry_delays()
    max_retries = max(1, config.SILICONFLOW_MAX_RETRIES)
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            await wait_for_rpm_slot(bucket)
            return await func()
        except Exception as exc:
            last_exception = exc
            if attempt >= max_retries - 1 or not _is_retryable(exc):
                break

            retry_after = None
            if isinstance(exc, httpx.HTTPStatusError):
                retry_after = _retry_after_seconds(exc.response)

            fallback_delay = delays[min(attempt, len(delays) - 1)]
            delay = retry_after if retry_after is not None else fallback_delay
            delay += random.uniform(0, min(1.0, delay * 0.1))
            print(f"[SiliconFlow] {label} retry {attempt + 1}/{max_retries - 1} after {delay:.1f}s: {exc}")
            await asyncio.sleep(delay)

    raise last_exception
