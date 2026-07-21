import re


BANK_RECEIPT_MARKER = re.compile(r"电子回单号码\s*[:：]")
GENERIC_DOCUMENT_MARKERS = [
    re.compile(r"(?=(?:电子回单号码|电子回单号|回单编号|回单号码)\s*[:：])"),
    re.compile(r"(?=(?:交易流水号|交易流水|流水号)\s*[:：])"),
    re.compile(r"(?=(?:发票号码|发票代码)\s*[:：])"),
    re.compile(r"(?=(?:收据编号|收据号码|凭证号)\s*[:：])"),
]
HTML_TABLE_MARKER = re.compile(r"(?=<table\b)", re.IGNORECASE)


def split_ocr_documents(text: str) -> list[str]:
    """Split OCR text when one image/page contains multiple independent receipts."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if _looks_like_single_payment_detail(cleaned):
        return [cleaned]

    by_receipt_number = _split_by_marker(cleaned, BANK_RECEIPT_MARKER)
    if len(by_receipt_number) > 1:
        return by_receipt_number

    for marker in GENERIC_DOCUMENT_MARKERS:
        by_generic_marker = _split_by_marker(cleaned, marker)
        if _looks_like_multiple_documents(cleaned, by_generic_marker):
            return by_generic_marker

    by_table = _split_by_marker(cleaned, HTML_TABLE_MARKER)
    if _looks_like_multiple_documents(cleaned, by_table):
        return by_table

    return [cleaned]


def _split_by_marker(text: str, marker: re.Pattern) -> list[str]:
    starts = [match.start() for match in marker.finditer(text)]
    if len(starts) <= 1:
        return [text]

    parts = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        part = text[start:end].strip()
        if _is_meaningful_part(part):
            parts.append(part)
    return parts or [text]


def _looks_like_multiple_bank_receipts(text: str, parts: list[str]) -> bool:
    return _looks_like_multiple_documents(text, parts)


def _looks_like_multiple_documents(text: str, parts: list[str]) -> bool:
    if len(parts) <= 1:
        return False
    receipt_signals = len(BANK_RECEIPT_MARKER.findall(text))
    bank_title_signals = text.count("中国工商银行") + text.count("网上银行电子回单") + text.count("电子回单")
    invoice_signals = text.count("发票号码") + text.count("发票代码")
    receipt_title_signals = text.count("收据") + text.count("收款收据")
    table_signals = len(HTML_TABLE_MARKER.findall(text))
    signal_count = receipt_signals + bank_title_signals + invoice_signals + receipt_title_signals + table_signals
    return signal_count > 1 and all(_is_meaningful_part(part) for part in parts)


def _is_meaningful_part(part: str) -> bool:
    meaningful_chars = sum(1 for ch in part if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    return meaningful_chars >= 20


def _looks_like_single_payment_detail(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
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
