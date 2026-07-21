import json
from typing import Any

from app.utils.document_schema import canonical_field_name
from app.utils.ocr_preprocessor import normalize_single_field_name

EXPORT_CACHE_VERSION = "export-format-v10"


def extract_field_value(field_data: Any) -> Any:
    if isinstance(field_data, dict):
        if "value" in field_data:
            value = field_data["value"]
        else:
            value = field_data
    else:
        value = field_data
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def field_confidence(field_data: Any) -> float:
    if isinstance(field_data, dict):
        try:
            return float(field_data.get("confidence", 0))
        except (TypeError, ValueError):
            return 0
    return 0


def field_has_value(field_data: Any) -> bool:
    value = extract_field_value(field_data)
    return value is not None and str(value).strip() != ""


def _equivalent_values(left: Any, right: Any) -> bool:
    left_text = str(extract_field_value(left)).strip()
    right_text = str(extract_field_value(right)).strip()
    if left_text == right_text:
        return True
    try:
        return float(left_text.replace(",", "")) == float(right_text.replace(",", ""))
    except (TypeError, ValueError):
        return False


def _merge_field(existing: Any, incoming: Any) -> tuple[Any, bool]:
    if not field_has_value(existing) and field_has_value(incoming):
        return incoming, False
    if field_has_value(existing) and not field_has_value(incoming):
        return existing, False
    if not field_has_value(existing) and not field_has_value(incoming):
        return existing, False

    if _equivalent_values(existing, incoming):
        if isinstance(existing, dict) and isinstance(incoming, dict):
            merged = dict(existing)
            merged["confidence"] = max(field_confidence(existing), field_confidence(incoming))
            return merged, False
        return existing, False

    if field_confidence(incoming) > field_confidence(existing):
        return incoming, True
    return existing, True


def normalize_fields(fields: Any, doc_type: str = "") -> tuple[dict, list[str]]:
    if not isinstance(fields, dict):
        return {}, []

    normalized = {}
    conflict_fields = []
    for field_name, field_data in fields.items():
        normalized_name = canonical_field_name(normalize_single_field_name(str(field_name)), doc_type)
        if normalized_name in normalized:
            normalized[normalized_name], conflicted = _merge_field(normalized[normalized_name], field_data)
            if conflicted and normalized_name not in conflict_fields:
                conflict_fields.append(normalized_name)
        else:
            normalized[normalized_name] = field_data
    return normalized, conflict_fields


def normalize_field_names(field_names: Any, doc_type: str = "") -> list[str]:
    if not isinstance(field_names, list):
        return []

    normalized = []
    seen = set()
    for field_name in field_names:
        normalized_name = canonical_field_name(normalize_single_field_name(str(field_name)), doc_type)
        if normalized_name not in seen:
            normalized.append(normalized_name)
            seen.add(normalized_name)
    return normalized


def normalize_result_for_table(result: dict) -> dict:
    doc_type = result.get("document_type") or ""
    fields, conflict_fields = normalize_fields(result.get("structured_data", {}), doc_type)
    low_confidence_fields = normalize_field_names(result.get("low_confidence_fields", []), doc_type)
    for field_name in conflict_fields:
        if field_name not in low_confidence_fields:
            low_confidence_fields.append(field_name)

    normalized = dict(result)
    normalized["structured_data"] = fields
    normalized["low_confidence_fields"] = low_confidence_fields
    return normalized
