import re
from dataclasses import dataclass
from typing import Optional


TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
DOC_TITLE_RE = re.compile(r"(电子回单|网上银行电子回单|增值税.*发票|收据|转账单|付款凭证)")
DOC_ID_RE = re.compile(r"(电子回单号码|电子回单号|回单编号|回单号码|发票号码|收据编号|交易流水号|流水号)\s*[:：]")


@dataclass
class LayoutDocument:
    text: str
    hints: list[str]
    table_count: int = 0
    title_count: int = 0
    marker_count: int = 0


@dataclass
class OcrBlock:
    text: str
    x1: int
    y1: int
    x2: int
    y2: int


def analyze_layout(text: str, ocr_result: Optional[dict] = None) -> list[LayoutDocument]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    parts = _split_by_layout(cleaned)
    documents = []
    for part in parts:
        hints = _layout_hints(part, ocr_result)
        documents.append(LayoutDocument(
            text=part,
            hints=hints,
            table_count=_table_count(part),
            title_count=len(DOC_TITLE_RE.findall(part)),
            marker_count=len(DOC_ID_RE.findall(part)),
        ))
    return documents


def build_layout_prompt(text: str, layout: LayoutDocument) -> str:
    if not layout.hints:
        return text
    hint_block = "\n".join(f"- {hint}" for hint in layout.hints)
    return f"""[版面结构提示]
{hint_block}

[OCR 文本]
{text}"""


def _split_by_layout(text: str) -> list[str]:
    if _looks_like_single_payment_detail(text):
        return [text]

    by_html_table = _split_html_tables(text)
    if _is_valid_multi_doc_split(by_html_table):
        return by_html_table

    by_title = _split_by_repeated_signal(text, DOC_TITLE_RE)
    if _is_valid_multi_doc_split(by_title):
        return by_title

    by_doc_id = _split_by_repeated_signal(text, DOC_ID_RE)
    if _is_valid_multi_doc_split(by_doc_id):
        return by_doc_id

    by_markdown_table_blocks = _split_markdown_table_blocks(text)
    if _is_valid_multi_doc_split(by_markdown_table_blocks):
        return by_markdown_table_blocks

    return [text]


def _split_html_tables(text: str) -> list[str]:
    matches = list(HTML_TABLE_RE.finditer(text))
    if len(matches) <= 1:
        return [text]
    parts = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        part = text[start:end].strip()
        if _meaningful(part):
            parts.append(part)
    return parts or [text]


def _split_by_repeated_signal(text: str, pattern: re.Pattern) -> list[str]:
    starts = [match.start() for match in pattern.finditer(text)]
    if len(starts) <= 1:
        return [text]
    parts = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        part = text[start:end].strip()
        if _meaningful(part):
            parts.append(part)
    return parts or [text]


def _split_markdown_table_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks = []
    current = []
    for line in lines:
        if TABLE_ROW_RE.match(line):
            current.append(line)
            continue
        if current:
            blocks.append("\n".join(current).strip())
            current = []
    if current:
        blocks.append("\n".join(current).strip())
    if len(blocks) <= 1:
        return [text]
    return [block for block in blocks if _meaningful(block)] or [text]


def _is_valid_multi_doc_split(parts: list[str]) -> bool:
    if len(parts) <= 1:
        return False
    return all(_meaningful(part) for part in parts)


def _layout_hints(text: str, ocr_result: Optional[dict]) -> list[str]:
    hints = []
    table_count = _table_count(text)
    title_count = len(DOC_TITLE_RE.findall(text))
    marker_count = len(DOC_ID_RE.findall(text))
    if table_count:
        hints.append(f"检测到 {table_count} 个表格结构，优先按表格行列关系抽取字段，不要把左右两栏拼成同一个字段。")
    if title_count > 1 or marker_count > 1:
        hints.append("检测到多个单据标题或编号，必须按独立单据输出 documents 数组。")
    if ocr_result and ocr_result.get("pages"):
        hints.append(f"检测到 PDF 共 {ocr_result.get('pages')} 页，保留页面顺序，避免跨页合并无关单据。")
    hints.extend(_coordinate_hints(text, ocr_result))
    if "付款" in text and "收款" in text:
        hints.append("付款方与收款方字段必须分别保留，不要统一成通用账号/户名。")
    return hints


def _table_count(text: str) -> int:
    html_count = len(HTML_TABLE_RE.findall(text))
    markdown_rows = len([line for line in text.splitlines() if TABLE_ROW_RE.match(line)])
    return html_count + (1 if markdown_rows >= 2 else 0)


def _meaningful(text: str) -> bool:
    meaningful_chars = sum(1 for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    return meaningful_chars >= 12


def _coordinate_hints(text: str, ocr_result: Optional[dict]) -> list[str]:
    blocks = _ocr_blocks(ocr_result)
    if len(blocks) < 4:
        return []

    hints = []
    xs = [int((block.x1 + block.x2) / 2) for block in blocks]
    ys = [int((block.y1 + block.y2) / 2) for block in blocks]
    width = max(block.x2 for block in blocks) - min(block.x1 for block in blocks)
    height = max(block.y2 for block in blocks) - min(block.y1 for block in blocks)
    left = sum(1 for x in xs if x < min(xs) + width * 0.5)
    right = sum(1 for x in xs if x >= min(xs) + width * 0.5)

    if left >= 2 and right >= 2:
        hints.append("OCR 坐标显示文本分布为左右两栏，左侧通常是字段名，右侧通常是字段值；抽取时按同一行或相邻行配对。")
    if height > width * 1.15 and _looks_like_single_payment_detail(text):
        hints.append("OCR 坐标显示这是纵向长截图支付详情，应作为单笔交易处理，不要按上下区域拆成多张单据。")
    if _has_large_top_amount(blocks):
        hints.append("OCR 坐标显示顶部存在大号金额文本；若为独立负数或金额样式，应优先作为交易金额。")

    return hints


def _ocr_blocks(ocr_result: Optional[dict]) -> list[OcrBlock]:
    raw = ""
    if isinstance(ocr_result, dict):
        raw = ocr_result.get("raw_response") or ocr_result.get("full_text") or ""
    if not raw:
        return []

    pattern = re.compile(
        r"(?:<\|ref\|>|<ref>)(.*?)(?:<\|/ref\|>|</ref>)\s*"
        r"(?:<\|det\|>|<det>)\s*\[\[([0-9,\s]+)\]\]\s*(?:<\|/det\|>|</det>)",
        re.DOTALL,
    )
    blocks: list[OcrBlock] = []
    matches = list(pattern.finditer(raw))
    for index, match in enumerate(matches):
        label = re.sub(r"<.*?>", "", match.group(1)).strip()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        trailing_text = re.sub(r"<.*?>", "", raw[match.end():next_start]).strip()
        if trailing_text and label in {"text", "image", "title", "table"}:
            label = trailing_text.splitlines()[0].strip()
        numbers = [int(num) for num in re.findall(r"\d+", match.group(2))]
        if len(numbers) < 4:
            continue
        x1, y1, x2, y2 = numbers[:4]
        if x2 <= x1 or y2 <= y1:
            continue
        blocks.append(OcrBlock(label, x1, y1, x2, y2))
    return blocks


def _has_large_top_amount(blocks: list[OcrBlock]) -> bool:
    if not blocks:
        return False
    min_y = min(block.y1 for block in blocks)
    max_y = max(block.y2 for block in blocks)
    top_limit = min_y + (max_y - min_y) * 0.35
    for block in blocks:
        text = block.text.replace("−", "-").replace("—", "-")
        if block.y1 <= top_limit and re.fullmatch(r"-?\d+(?:\.\d{1,2})", text):
            return True
    return False


def _looks_like_single_payment_detail(text: str) -> bool:
    """Mobile wallet/bank payment detail pages are one transaction, not multiple receipts."""
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False

    payment_signals = [
        "支付时间",
        "当前状态",
        "支付方式",
        "交易单号",
        "商户单号",
        "商户全称",
        "收单机构",
    ]
    signal_count = sum(1 for signal in payment_signals if signal in compact)
    has_amount = bool(re.search(r"[-−—]\d+(?:\.\d{1,2})", compact))
    has_order = "交易单号" in compact or "商户单号" in compact
    return signal_count >= 3 and (has_order or has_amount)
