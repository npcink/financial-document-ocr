import hashlib
import os
import re


_LOG_LABEL_KEY = os.urandom(16)
_SAFE_SUFFIX_RE = re.compile(r"^\.[a-z0-9]{1,8}$")


def _opaque_label(prefix: str, value: object) -> str:
    raw = str(value or "").encode("utf-8", errors="replace")
    digest = hashlib.blake2s(raw, key=_LOG_LABEL_KEY, digest_size=6).hexdigest()
    return f"{prefix}-{digest}"


def safe_file_label(filename: object) -> str:
    """Return a process-local opaque file label with a non-sensitive suffix."""
    raw_name = os.path.basename(str(filename or ""))
    suffix = os.path.splitext(raw_name)[1].lower()
    if not _SAFE_SUFFIX_RE.fullmatch(suffix):
        suffix = ""
    return f"{_opaque_label('file', raw_name)}{suffix}"


def safe_job_label(job_id: object) -> str:
    """Return a process-local opaque label for a job or upload identifier."""
    return _opaque_label("job", job_id)


def safe_exception_label(exc: BaseException) -> str:
    """Describe an exception without including its potentially sensitive message."""
    exception_type = type(exc).__name__
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return f"{exception_type}(status={status_code})"
    return exception_type
