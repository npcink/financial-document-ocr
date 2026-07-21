import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.utils.document_schema import field_type, schema_for


AMOUNT_FIELD_HINTS = ("金额", "合计", "税额", "小写", "月费", "费用", "月租")
DATE_FIELD_HINTS = ("日期", "时间", "期限")


def normalize_financial_fields(fields: dict, doc_type: str, raw_text: str = "") -> list[str]:
    """Normalize money/time fields and return fields that should be reviewed."""
    if not isinstance(fields, dict):
        return []
    review_fields: list[str] = []
    review_fields.extend(_normalize_amount_fields(fields, doc_type))
    review_fields.extend(_normalize_time_fields(fields, doc_type, raw_text))
    return list(dict.fromkeys(review_fields))


def amount_value(value: Any) -> Optional[Decimal]:
    normalized = normalize_amount_text(value)
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def normalize_amount_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = (
        text.replace("−", "-")
        .replace("—", "-")
        .replace("￥", "")
        .replace("¥", "")
        .replace("人民币", "")
        .replace("港币", "")
        .replace("元", "")
        .replace(",", "")
        .strip()
    )
    text = re.sub(r"\s+", "", text)
    match = re.search(r"(?<!\d)([+-]?\d+(?:\.\d{1,4})?)(?!\d)", text)
    if not match:
        return ""
    try:
        return format(Decimal(match.group(1)), "f")
    except InvalidOperation:
        return ""


def parse_time_text(value: Any) -> dict[str, str]:
    text = str(value or "").strip()
    if not text:
        return {"raw": "", "date": "", "time": "", "timestamp": "", "precision": "empty"}

    normalized = text.replace("年", "-").replace("月", "-").replace("日", " ")
    normalized = normalized.replace("/", "-").replace(".", "-")
    normalized = re.sub(r"\s+", " ", normalized).strip()

    full_match = re.search(
        r"(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+|T)?"
        r"(\d{1,2})[:：](\d{1,2})(?:[:：](\d{1,2}))?",
        normalized,
    )
    if full_match:
        year, month, day, hour, minute, second = full_match.groups()
        date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        timestamp = f"{date} {int(hour):02d}:{int(minute):02d}:{int(second or 0):02d}"
        return {"raw": text, "date": date, "time": timestamp.split(" ", 1)[1], "timestamp": timestamp, "precision": "datetime"}

    date_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", normalized)
    if date_match:
        year, month, day = date_match.groups()
        date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return {"raw": text, "date": date, "time": "", "timestamp": "", "precision": "date"}

    partial_match = re.search(
        r"\b(\d{1,2})[-/](\d{1,2})\s+(\d{1,2})[:：](\d{1,2})(?:[:：](\d{1,2}))?\b",
        text,
    )
    if partial_match:
        month, day, hour, minute, second = partial_match.groups()
        partial = f"{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d}"
        if second:
            partial = f"{partial}:{int(second):02d}"
        return {"raw": text, "date": "", "time": partial, "timestamp": partial, "precision": "partial_datetime"}

    time_match = re.search(r"\b(\d{1,2})[:：](\d{1,2})(?:[:：](\d{1,2}))?\b", text)
    if time_match:
        hour, minute, second = time_match.groups()
        time = f"{int(hour):02d}:{int(minute):02d}:{int(second or 0):02d}"
        return {"raw": text, "date": "", "time": time, "timestamp": time, "precision": "time"}

    return {"raw": text, "date": "", "time": "", "timestamp": "", "precision": "unknown"}


def _normalize_amount_fields(fields: dict, doc_type: str) -> list[str]:
    review_fields = []
    schema = schema_for(doc_type)
    for field_name, field_data in list(fields.items()):
        if not _is_amount_field(field_name, doc_type):
            continue
        value = _field_value(field_data)
        if value is None or str(value).strip() == "":
            continue
        normalized = normalize_amount_text(value)
        if not normalized:
            review_fields.append(field_name)
            continue
        if str(value).strip() != normalized:
            if not _field_has_text(fields, "原始金额文本"):
                fields["原始金额文本"] = _wrap_value(value, 0.8)
            _set_field_value(fields, field_name, normalized)
        if doc_type == "subscription_record" or field_name == "月费":
            fields.setdefault("金额类型", _wrap_value("月费", 0.9))
        elif field_name in schema.get("required", []) or field_name == "交易金额":
            fields.setdefault("金额类型", _wrap_value("交易金额", 0.85))
    return review_fields


def _normalize_time_fields(fields: dict, doc_type: str, raw_text: str) -> list[str]:
    review_fields = []
    for field_name, field_data in list(fields.items()):
        if not _is_time_field(field_name, doc_type):
            continue
        value = _field_value(field_data)
        if value is None or str(value).strip() == "":
            continue
        parsed = parse_time_text(value)
        if parsed["precision"] == "datetime":
            if field_name == "时间戳":
                _set_field_value(fields, field_name, parsed["timestamp"])
            if not _field_has_text(fields, "交易日期") and _uses_trade_date(doc_type):
                fields["交易日期"] = _wrap_value(parsed["date"], 0.82)
                fields.setdefault("日期推断来源", _wrap_value("时间戳", 0.82))
        elif parsed["precision"] == "date":
            _set_field_value(fields, field_name, parsed["date"])
        elif parsed["precision"] in {"partial_datetime", "time"}:
            if not _field_has_text(fields, "原始时间文本"):
                fields["原始时间文本"] = _wrap_value(parsed["raw"], 0.8)
            review_fields.append(field_name)

    if _uses_trade_date(doc_type) and _field_has_text(fields, "交易日期") and _field_has_text(fields, "时间戳"):
        parsed_timestamp = parse_time_text(_field_value(fields.get("时间戳")))
        if parsed_timestamp["precision"] in {"partial_datetime", "time"}:
            joined = _join_date_and_time(_field_value(fields.get("交易日期")), parsed_timestamp["timestamp"])
            if joined:
                _set_field_value(fields, "时间戳", joined)
                fields.setdefault("日期推断来源", _wrap_value("交易日期", 0.78))
    return review_fields


def _join_date_and_time(date_value: Any, time_value: Any) -> str:
    parsed_date = parse_time_text(date_value)
    parsed_time = parse_time_text(time_value)
    date = parsed_date.get("date") or ""
    time = parsed_time.get("time") or ""
    if not date or not time:
        return ""
    if re.match(r"\d{2}-\d{2}\s+", time):
        time = time.split(" ", 1)[1]
    return f"{date} {time}"


def _uses_trade_date(doc_type: str) -> bool:
    return doc_type in {"bank_receipt", "transaction_list"}


def _is_amount_field(field_name: str, doc_type: str) -> bool:
    return field_type(field_name, doc_type) == "amount" or any(token in field_name for token in AMOUNT_FIELD_HINTS)


def _is_time_field(field_name: str, doc_type: str) -> bool:
    return field_type(field_name, doc_type) in {"date", "datetime"} or any(token in field_name for token in DATE_FIELD_HINTS)


def _field_value(field_data: Any) -> Any:
    if isinstance(field_data, dict) and "value" in field_data:
        return field_data.get("value")
    return field_data


def _field_has_text(fields: dict, field_name: str) -> bool:
    value = _field_value(fields.get(field_name))
    return value is not None and str(value).strip() != ""


def _set_field_value(fields: dict, field_name: str, value: Any) -> None:
    current = fields.get(field_name)
    if isinstance(current, dict):
        current["value"] = value
        current.setdefault("confidence", 0.8)
    else:
        fields[field_name] = _wrap_value(value, 0.8)


def _wrap_value(value: Any, confidence: float) -> dict[str, Any]:
    return {"value": value, "confidence": confidence}
