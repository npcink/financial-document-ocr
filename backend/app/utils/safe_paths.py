import os
import re
import unicodedata


_RESOURCE_ID_RE = re.compile(r"^[0-9a-f]{12}(?:_[0-9]{4})?$")
_SAFE_FILENAME_PUNCTUATION = frozenset(" ._-()（）[]【】")


def validate_resource_id(value: object) -> str:
    """Return a server-generated job/upload identifier or reject it."""
    identifier = str(value or "")
    if not _RESOURCE_ID_RE.fullmatch(identifier):
        raise ValueError("invalid resource identifier")
    return identifier


def sanitize_filename(value: object) -> str:
    """Return a display-friendly filename that cannot contain a path."""
    raw = unicodedata.normalize("NFKC", str(value or "")).replace("\\", "/")
    basename = raw.rsplit("/", 1)[-1]
    cleaned = "".join(
        char if char.isalnum() or char in _SAFE_FILENAME_PUNCTUATION else "_"
        for char in basename
    ).strip()
    cleaned = cleaned.lstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("invalid filename")

    if len(cleaned) > 240:
        stem, suffix = os.path.splitext(cleaned)
        cleaned = f"{stem[: max(1, 240 - len(suffix))]}{suffix[:16]}"
    return cleaned


def resolve_under(root: str, *parts: object) -> str:
    """Resolve a path and prove it remains strictly below a trusted root."""
    if not parts:
        raise ValueError("path must contain a child component")

    real_root = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(real_root, *(str(part) for part in parts)))
    try:
        contained = os.path.commonpath((real_root, candidate)) == real_root
    except ValueError as exc:
        raise ValueError("path is outside trusted root") from exc
    if not contained or candidate == real_root:
        raise ValueError("path is outside trusted root")
    return candidate


def resource_path(root: str, resource_id: object, *parts: object) -> str:
    """Resolve a path below a validated server-generated resource directory."""
    identifier = validate_resource_id(resource_id)
    return resolve_under(root, identifier, *parts)
