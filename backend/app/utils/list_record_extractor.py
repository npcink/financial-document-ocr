import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TextBlock:
    text: str
    x1: int = 0
    y1: int = 0
    x2: int = 0
    y2: int = 0


def extract_list_records(
    raw_text: str,
    ocr_result: Optional[dict] = None,
    filename: str = "",
    filepath: str = "",
) -> list[dict[str, Any]]:
    """Extract repeated list-style mobile screenshots into one document per row."""
    blocks = _text_blocks(ocr_result, raw_text)
    records = _extract_transaction_records(blocks, raw_text, filename, filepath)
    if records:
        return records
    return _extract_subscription_records(blocks, raw_text)


def _extract_transaction_records(
    blocks: list[TextBlock],
    raw_text: str,
    filename: str,
    filepath: str,
) -> list[dict[str, Any]]:
    block_records = _extract_transaction_records_from_blocks(blocks, filename, filepath)
    if block_records:
        return block_records

    lines = _clean_lines_from_blocks(blocks) or _clean_lines(raw_text)
    starts = []
    for index, line in enumerate(lines):
        if _transaction_head(line):
            starts.append(index)
    if len(starts) < 2:
        return []

    year_month = _infer_year_month(filename, filepath)
    records = []
    for item_index, start in enumerate(starts):
        end = starts[item_index + 1] if item_index + 1 < len(starts) else len(lines)
        group = lines[start:end]
        head = _transaction_head(group[0])
        if not head:
            continue
        title, amount = head
        merchant = _first_non_label(group[1:], exclude_time=True)
        time_text = _first_time_text(group)
        fields = {
            "交易类型": _field(title, 0.9),
            "交易对象": _field(merchant, 0.82) if merchant else _field("", 0.0),
            "交易金额": _field(amount, 0.92),
            "原始时间文本": _field(time_text, 0.9) if time_text else _field("", 0.0),
            "原始文本": _field("\n".join(group), 0.8),
        }
        if time_text:
            inferred = _normalize_partial_datetime(time_text, year_month)
            if inferred:
                fields["时间戳"] = _field(inferred["timestamp"], 0.72)
                fields["交易日期"] = _field(inferred["date"], 0.72)
                fields["日期推断来源"] = _field(inferred["source"], 0.72)
            else:
                fields["时间戳"] = _field(time_text, 0.55)
                fields["日期推断来源"] = _field("", 0.0)
        records.append(_document("transaction_list", fields, 0.86))

    return records if len(records) >= 2 else []


def _extract_transaction_records_from_blocks(
    blocks: list[TextBlock],
    filename: str,
    filepath: str,
) -> list[dict[str, Any]]:
    positioned = [block for block in blocks if block.x2 > block.x1 and block.y2 > block.y1 and block.text]
    amount_blocks = [block for block in positioned if _amount_only(block.text)]
    if len(amount_blocks) < 2:
        return []

    title_blocks = [
        block for block in positioned
        if (
            not _amount_only(block.text)
            and not _partial_time(block.text)
            and block.text not in {"image", "text", "title", "table"}
            and not any(token in block.text for token in ("订购时间", "有效期限", "退订时间"))
        )
    ]
    records = []
    year_month = _infer_year_month(filename, filepath)
    sorted_amounts = sorted(amount_blocks, key=lambda item: (item.y1, item.x1))
    for amount_index, amount_block in enumerate(sorted_amounts):
        same_row_titles = [
            block for block in title_blocks
            if block.x1 < amount_block.x1 and abs(_center_y(block) - _center_y(amount_block)) <= max(45, _height(amount_block) * 1.2)
        ]
        if not same_row_titles:
            continue
        title_block = sorted(same_row_titles, key=lambda item: abs(_center_y(item) - _center_y(amount_block)))[0]
        next_title_y = sorted_amounts[amount_index + 1].y1 if amount_index + 1 < len(sorted_amounts) else 10**9
        below = [
            block for block in positioned
            if block.y1 > title_block.y1 and block.y1 < next_title_y and block.x1 < amount_block.x1
        ]
        merchant = ""
        time_text = ""
        for block in sorted(below, key=lambda item: (item.y1, item.x1)):
            if _partial_time(block.text):
                time_text = _partial_time(block.text)
            elif block.text not in {title_block.text, amount_block.text} and not _amount_only(block.text):
                merchant = merchant or block.text

        fields = {
            "交易类型": _field(title_block.text, 0.9),
            "交易对象": _field(merchant, 0.82) if merchant else _field("", 0.0),
            "交易金额": _field(_amount_only(amount_block.text) or amount_block.text, 0.92),
            "原始时间文本": _field(time_text, 0.9) if time_text else _field("", 0.0),
            "原始文本": _field("\n".join(filter(None, [title_block.text, merchant, time_text, amount_block.text])), 0.8),
        }
        if time_text:
            inferred = _normalize_partial_datetime(time_text, year_month)
            if inferred:
                fields["时间戳"] = _field(inferred["timestamp"], 0.72)
                fields["交易日期"] = _field(inferred["date"], 0.72)
                fields["日期推断来源"] = _field(inferred["source"], 0.72)
            else:
                fields["时间戳"] = _field(time_text, 0.55)
        records.append(_document("transaction_list", fields, 0.86))

    return records if len(records) >= 2 else []


def _extract_subscription_records(blocks: list[TextBlock], raw_text: str) -> list[dict[str, Any]]:
    lines = _clean_lines_from_blocks(blocks) or _clean_lines(raw_text)
    if not any("订购时间" in line for line in lines) or not any("有效期限" in line for line in lines):
        return []

    starts = []
    for index, line in enumerate(lines):
        if _subscription_title(line):
            starts.append(index)
    if not starts:
        return []

    records = []
    for item_index, start in enumerate(starts):
        end = starts[item_index + 1] if item_index + 1 < len(starts) else len(lines)
        group = lines[start:end]
        title_line = group[0]
        title, inline_status = _split_subscription_title(title_line)
        status = _subscription_status(group) or inline_status
        order_date = _match_value(group, r"订购时间[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})")
        valid_line = _line_with(group, "有效期限")
        valid_start = ""
        valid_end = ""
        if valid_line:
            valid_match = re.search(r"有效期限[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s*至\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", valid_line)
            if valid_match:
                valid_start = _normalize_date(valid_match.group(1))
                valid_end = _normalize_date(valid_match.group(2))
        unsubscribe_date = _match_value(group, r"退订时间[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})")
        monthly_fee = _monthly_fee(group)
        fields = {
            "产品名称": _field(title, 0.9),
            "订购状态": _field(status, 0.82) if status else _field("", 0.0),
            "订购时间": _field(_normalize_date(order_date), 0.9) if order_date else _field("", 0.0),
            "有效期开始": _field(valid_start, 0.88) if valid_start else _field("", 0.0),
            "有效期结束": _field(valid_end, 0.88) if valid_end else _field("", 0.0),
            "退订时间": _field(_normalize_date(unsubscribe_date), 0.86) if unsubscribe_date else _field("", 0.0),
            "月费": _field(monthly_fee, 0.9) if monthly_fee else _field("", 0.0),
            "计费周期": _field("月", 0.9) if monthly_fee else _field("", 0.0),
            "原始文本": _field("\n".join(group), 0.8),
        }
        records.append(_document("subscription_record", fields, 0.86))

    return records if records else []


def _document(doc_type: str, fields: dict[str, Any], confidence: float) -> dict[str, Any]:
    return {
        "document_type": doc_type,
        "fields": {key: value for key, value in fields.items() if _field_text(value)},
        "confidence": confidence,
    }


def _field(value: Any, confidence: float) -> dict[str, Any]:
    return {"value": value, "confidence": confidence}


def _field_text(field_data: Any) -> str:
    value = field_data.get("value") if isinstance(field_data, dict) else field_data
    return "" if value is None else str(value).strip()


def _text_blocks(ocr_result: Optional[dict], fallback_text: str) -> list[TextBlock]:
    raw = ""
    if isinstance(ocr_result, dict):
        raw = ocr_result.get("raw_response") or ocr_result.get("full_text") or ""
    raw = raw or fallback_text or ""
    pattern = re.compile(
        r"(?:<\|ref\|>|<ref>)(.*?)(?:<\|/ref\|>|</ref>)\s*"
        r"(?:<\|det\|>|<det>)\s*(?:\[\[)?([0-9,\s]+)(?:\]\])?\s*(?:<\|/det\|>|</det>)",
        re.DOTALL,
    )
    matches = list(pattern.finditer(raw))
    blocks: list[TextBlock] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        label = _strip_markup(match.group(1))
        trailing = _strip_markup(raw[match.end():next_start])
        text = trailing if trailing and label in {"text", "image", "title", "table"} else label
        text = _clean_line(text.splitlines()[0] if text else "")
        if text in {"image", "text", "title", "table"}:
            continue
        numbers = _coordinate_numbers(match.group(2))
        if not text or len(numbers) < 4:
            continue
        x1, y1, x2, y2 = numbers[:4]
        blocks.append(TextBlock(text, x1, y1, x2, y2))
    if blocks:
        return sorted(blocks, key=lambda block: (block.y1, block.x1))
    return [TextBlock(line) for line in _clean_lines(raw)]


def _clean_lines_from_blocks(blocks: list[TextBlock]) -> list[str]:
    return [_clean_line(block.text) for block in blocks if _clean_line(block.text)]


def _clean_lines(text: str) -> list[str]:
    return [_clean_line(line) for line in (text or "").splitlines() if _clean_line(line)]


def _strip_markup(text: str) -> str:
    text = re.sub(r"<.*?>", "", text or "")
    return _clean_line(text)


def _clean_line(line: str) -> str:
    line = re.sub(r"^\s*#+\s*", "", line or "")
    line = line.replace("**", "").replace("／", "/")
    return re.sub(r"\s+", " ", line).strip()


def _transaction_head(line: str) -> Optional[tuple[str, str]]:
    match = re.search(r"^(.+?)\s+([+-]?\d{1,9}(?:,\d{3})*(?:\.\d{1,2}))$", line)
    if not match:
        return None
    title = match.group(1).strip()
    if any(token in title for token in ("有效期限", "退订时间", "订购时间")):
        return None
    return title, match.group(2).replace(",", "")


def _amount_only(text: str) -> str:
    cleaned = (text or "").replace(",", "").strip()
    if re.fullmatch(r"[+-]?\d{1,9}(?:\.\d{1,2})", cleaned):
        return cleaned
    return ""


def _center_y(block: TextBlock) -> float:
    return (block.y1 + block.y2) / 2


def _height(block: TextBlock) -> int:
    return max(1, block.y2 - block.y1)


def _coordinate_numbers(raw: str) -> list[int]:
    numbers = [int(num) for num in re.findall(r"\d+", raw or "")]
    if len(numbers) >= 4:
        return numbers[:4]
    compact = re.sub(r"\D", "", raw or "")
    if len(compact) < 4:
        return []
    parsed = _split_compact_coordinates(compact)
    return parsed or numbers


def _split_compact_coordinates(compact: str) -> list[int]:
    best = None
    best_score = 10**9
    length = len(compact)
    for i in range(1, length - 2):
        for j in range(i + 1, length - 1):
            for k in range(j + 1, length):
                values = [int(compact[:i]), int(compact[i:j]), int(compact[j:k]), int(compact[k:])]
                x1, y1, x2, y2 = values
                if not (0 <= x1 < x2 <= 3000 and 0 <= y1 < y2 <= 5000):
                    continue
                width = x2 - x1
                height = y2 - y1
                if width < 5 or height < 5:
                    continue
                score = abs(width - 140) + abs(height - 42)
                if score < best_score:
                    best = values
                    best_score = score
    return best or []


def _first_non_label(lines: list[str], exclude_time: bool = False) -> str:
    for line in lines:
        if exclude_time and _partial_time(line):
            continue
        if not _transaction_head(line):
            return line
    return ""


def _first_time_text(lines: list[str]) -> str:
    for line in lines:
        match = _partial_time(line)
        if match:
            return match
    return ""


def _partial_time(line: str) -> str:
    match = re.search(r"\b(\d{1,2})[-/](\d{1,2})\s+(\d{1,2})[:：](\d{1,2})(?:[:：](\d{1,2}))?\b", line)
    if not match:
        return ""
    month, day, hour, minute, second = match.groups()
    if second:
        return f"{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d}:{int(second):02d}"
    return f"{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d}"


def _infer_year_month(filename: str, filepath: str) -> Optional[tuple[int, int, str]]:
    source = f"{filepath} {filename}"
    patterns = [
        r"(20\d{2})[\\/](\d{1,2})月",
        r"(20\d{2})年[\\/ ]*(\d{1,2})月",
        r"(20\d{2})[-_/](\d{1,2})(?:[-_/]|月)",
    ]
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            return int(match.group(1)), int(match.group(2)), "文件路径"
    return None


def _normalize_partial_datetime(time_text: str, year_month: Optional[tuple[int, int, str]]) -> Optional[dict[str, str]]:
    if not year_month:
        return None
    match = re.search(r"(\d{1,2})[-/](\d{1,2})\s+(\d{1,2})[:：](\d{1,2})(?:[:：](\d{1,2}))?", time_text)
    if not match:
        return None
    month, day, hour, minute, second = match.groups()
    year, source_month, source = year_month
    if int(month) != source_month:
        return None
    date_value = f"{year:04d}-{int(month):02d}-{int(day):02d}"
    timestamp = f"{date_value} {int(hour):02d}:{int(minute):02d}:{int(second or 0):02d}"
    return {"date": date_value, "timestamp": timestamp, "source": source}


def _subscription_title(line: str) -> bool:
    if any(token in line for token in ("订购时间", "有效期限", "退订时间")):
        return False
    if line in {"即将失效", "已退订", "退订"}:
        return False
    return any(token in line for token in ("会员", "月包", "畅玩包", "套餐", "流量包", "元"))


def _split_subscription_title(line: str) -> tuple[str, str]:
    statuses = ["即将失效", "已退订", "已失效", "生效中"]
    status = ""
    title = line
    for item in statuses:
        if item in title:
            status = item
            title = title.replace(item, "").strip()
    title = re.sub(r"\s+", " ", title).strip(" -")
    return title, status


def _subscription_status(lines: list[str]) -> str:
    for line in lines:
        if line in {"即将失效", "已退订", "已失效", "生效中"}:
            return line
    for line in lines:
        for status in ("即将失效", "已退订", "已失效", "生效中"):
            if status in line:
                return status
    return ""


def _match_value(lines: list[str], pattern: str) -> str:
    for line in lines:
        match = re.search(pattern, line)
        if match:
            return match.group(1)
    return ""


def _line_with(lines: list[str], token: str) -> str:
    for line in lines:
        if token in line:
            return line
    return ""


def _monthly_fee(lines: list[str]) -> str:
    text = "\n".join(lines)
    match = re.search(r"(\d+(?:\.\d{1,2})?)\s*元\s*/\s*月", text)
    if match:
        return match.group(1)
    return ""


def _normalize_date(value: str) -> str:
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value or "")
    if not match:
        return value or ""
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
