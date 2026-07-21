import os
import hashlib
import json
import shutil
import asyncio
import re
from typing import Any, List, Tuple
from app.services.ocr import ocr_image, ocr_pdf
from app.services.llm import classify_and_extract, extract_fields_only, extract_missing_fields, check_llm_available
from app.services.text_extractor import extract_text
from app.utils.classifier import pre_classify
from app.utils.document_splitter import split_ocr_documents
from app.utils.layout_analyzer import analyze_layout, build_layout_prompt
from app.utils.ocr_preprocessor import quick_preprocess
from app.utils.field_validator import validate_llm_result
from app.utils.document_schema import schema_for, validate_schema_fields
from app.utils.field_normalizer import normalize_fields as normalize_structured_fields
from app.utils.financial_fields import normalize_financial_fields
from app.utils.list_record_extractor import extract_list_records
from app.utils.logging_safety import safe_exception_label, safe_file_label, safe_job_label
from app import db
from app.core import config
from app.db import UPLOAD_DIR, EXPORT_DIR
from app.services.llm import MODEL_NAME as LLM_MODEL_NAME

if config.AI_MODE == "cloud":
    OCR_CONCURRENCY = config.OCR_MAX_WORKERS_CLOUD
    LLM_CONCURRENCY = config.LLM_MAX_WORKERS_CLOUD
else:
    OCR_CONCURRENCY = config.OCR_MAX_WORKERS_LOCAL
    LLM_CONCURRENCY = config.LLM_MAX_WORKERS_LOCAL

_ocr_semaphore = asyncio.Semaphore(OCR_CONCURRENCY)
_llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
print(f"[Pipeline] OCR_CONCURRENCY={OCR_CONCURRENCY}, LLM_CONCURRENCY={LLM_CONCURRENCY} (mode={config.AI_MODE})")

LLM_SCHEMA_VERSION = "documents-v8"
PROMPT_CACHE_VERSION = "prompt-layout-schema-v5"
LAYOUT_CACHE_VERSION = "layout-v2"
FIELD_SCHEMA_CACHE_VERSION = "schema-v2"


def _job_file_worker_count(job: dict, file_count: int) -> int:
    if file_count <= 0:
        return 1
    if file_count <= 10:
        return file_count
    error_message = job.get("error_message") or ""
    if "重新排队" in error_message or "重试" in error_message:
        return min(file_count, 2)
    return min(file_count, 4)


def _is_ocr_error(ocr_result: dict) -> bool:
    full_text = ocr_result.get("full_text", "") if isinstance(ocr_result, dict) else ""
    return full_text.startswith("OCR_ERROR:")


def _is_llm_error(result: dict) -> bool:
    return isinstance(result, dict) and bool(result.get("error"))


def _error_core(raw_text: str, document_type: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "raw_ocr_text": raw_text or "",
        "structured_data": {},
        "confidence": 0.0,
        "low_confidence_fields": [],
        "document_type": document_type or "unknown",
        "error_message": message or "处理失败",
    }


def _is_ocr_text_valid(full_text: str) -> bool:
    text = (full_text or "").strip()
    if len(text) < 8:
        return False

    meaningful_chars = sum(
        1 for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff"
    )
    if meaningful_chars < 3:
        return False

    if text.startswith("OCR_ERROR:"):
        return False

    return True


SUPPORTED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'}
SUPPORTED_PDF_EXT = {'.pdf'}
SUPPORTED_ZIP_EXT = {'.zip'}
SUPPORTED_DOC_EXT = {'.docx', '.xlsx', '.xls', '.html', '.htm', '.xml'}


def get_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in SUPPORTED_IMAGE_EXT:
        return "image"
    elif ext in SUPPORTED_PDF_EXT:
        return "pdf"
    elif ext in SUPPORTED_ZIP_EXT:
        return "zip"
    elif ext in SUPPORTED_DOC_EXT:
        return "doc"
    return "unknown"


def extract_files(upload_dir: str) -> List[Tuple[str, str]]:
    files = []
    for root, dirs, filenames in os.walk(upload_dir):
        for filename in sorted(filenames):
            filepath = os.path.join(root, filename)
            file_type = get_file_type(filename)
            if file_type in ("image", "pdf", "doc"):
                files.append((filepath, filename))
    return files


async def _process_text_core(
    raw_text: str,
    preprocessed_text: str,
    filename: str,
    requirement: str = "",
    api_token: str = "",
    template_type: str = "general",
    llm_text: str = "",
    expected_document_count: int = 1,
    bypass_llm_cache: bool = False,
) -> list[dict[str, Any]]:
    file_label = safe_file_label(filename)
    prompt_text = llm_text or preprocessed_text
    pre_type, pre_conf = pre_classify(preprocessed_text, threshold=config.PRECLASSIFY_THRESHOLD)
    hash_payload = "\n".join([
        LLM_SCHEMA_VERSION,
        f"mode={config.AI_MODE}",
        f"model={LLM_MODEL_NAME}",
        f"prompt={PROMPT_CACHE_VERSION}",
        f"layout={LAYOUT_CACHE_VERSION}",
        f"schema={FIELD_SCHEMA_CACHE_VERSION}",
        f"template={template_type or 'general'}",
        f"requirement={requirement or ''}",
        prompt_text,
    ])
    text_hash = hashlib.md5(hash_payload.encode()).hexdigest()
    llm_cached = None if bypass_llm_cache else await asyncio.to_thread(db.get_llm_cache, text_hash, api_token)
    doc_type = pre_type or "unknown"
    cache_miss = llm_cached is None
    if llm_cached is not None:
        llm_result = llm_cached["llm_result"]
        doc_type = llm_result.get("document_type", pre_type or "unknown")
        print(f"[LLM Cache] HIT: {file_label}")
    else:
        async with _llm_semaphore:
            if pre_conf >= config.PRECLASSIFY_THRESHOLD:
                llm_result = await extract_fields_only(prompt_text, pre_type, requirement)
                doc_type = pre_type
            else:
                llm_result = await classify_and_extract(prompt_text, requirement)
                doc_type = llm_result.get("document_type", "unknown")
            print(f"[LLM Cache] {'BYPASS' if bypass_llm_cache else 'MISS'}: {file_label}")

    if _is_llm_error(llm_result):
        message = llm_result.get("error") or "LLM 处理失败"
        print(f"[LLM Error] {file_label}: failed")
        return [_error_core(raw_text, doc_type, message)]

    documents = _normalize_llm_documents(llm_result, doc_type)
    if not documents:
        message = "LLM 未返回可导出的结构化字段"
        print(f"[LLM Schema] {file_label}: {message}")
        return [_error_core(raw_text, doc_type, message)]

    quality_error = _llm_quality_error(preprocessed_text, documents, expected_document_count)
    if quality_error:
        print(f"[LLM Quality Gate] {file_label}: rejected")
        return [_error_core(raw_text, doc_type, quality_error)]

    cores: list[dict[str, Any]] = []
    cacheable = True
    for doc_index, document in enumerate(documents, start=1):
        document_type = document.get("document_type") or doc_type or "unknown"
        fields = document.get("fields") if isinstance(document.get("fields"), dict) else {}
        document_type = _override_document_type(document_type, fields, preprocessed_text)
        fields, conflict_fields = _normalize_fields(fields, filename, document_type)
        _enrich_fields_from_text(fields, document_type, preprocessed_text)
        financial_review_fields = normalize_financial_fields(fields, document_type, preprocessed_text)
        repaired_fields = await _repair_missing_or_low_confidence_fields(
            preprocessed_text,
            document_type,
            fields,
            requirement,
            filename,
        )
        if repaired_fields:
            fields.update(repaired_fields)
            fields, repair_conflicts = _normalize_fields(fields, filename, document_type)
            conflict_fields.extend([field for field in repair_conflicts if field not in conflict_fields])
            _enrich_fields_from_text(fields, document_type, preprocessed_text)
            financial_review_fields.extend(normalize_financial_fields(fields, document_type, preprocessed_text))
        if not _has_extractable_fields(fields):
            message = f"第 {doc_index} 张单据没有可导出的字段"
            print(f"[LLM Schema] {file_label} document={doc_index}: {message}")
            cores.append(_error_core(raw_text, document_type, message))
            continue
        confidence = document.get("confidence", llm_result.get("confidence", 0.0))
        low_confidence_fields = [
            fn for fn, fd in fields.items()
            if isinstance(fd, dict) and fd.get("confidence", 1.0) < 0.8
        ]
        low_confidence_fields.extend(conflict_fields)
        low_confidence_fields.extend(financial_review_fields)
        low_confidence_fields = list(set(low_confidence_fields))

        validation_payload = {"fields": fields, "document_type": document_type}
        validation = validate_llm_result(validation_payload, document_type)
        if validation.get('auto_fixed'):
            print(
                f"[Field Validator] {file_label} document={doc_index} "
                f"auto_fixed_count={len(validation['auto_fixed'])}"
            )
        if validation.get('needs_review'):
            print(
                f"[Field Validator] {file_label} document={doc_index} "
                f"review_count={len(validation['needs_review'])}"
            )
            low_confidence_fields.extend(validation['needs_review'])
            low_confidence_fields = list(set(low_confidence_fields))
        schema_validation = validate_schema_fields(fields, document_type)
        warning_messages = []
        if schema_validation.get("needs_review"):
            print(
                f"[Schema Validator] {file_label} document={doc_index} "
                f"review_count={len(schema_validation['needs_review'])}"
            )
            low_confidence_fields.extend(schema_validation["needs_review"])
            low_confidence_fields = list(set(low_confidence_fields))
            if schema_validation.get("missing_required"):
                warning_messages.append(f"缺少必填字段: {', '.join(schema_validation['missing_required'])}")
                cacheable = False
            if schema_validation.get("type_errors"):
                warning_messages.append(f"字段格式异常: {', '.join(schema_validation['type_errors'])}")
                cacheable = False

        cores.append({
            "status": "completed",
            "raw_ocr_text": raw_text,
            "structured_data": fields,
            "confidence": confidence,
            "low_confidence_fields": low_confidence_fields,
            "document_type": document_type,
            "error_message": "；".join(warning_messages),
        })

    if cache_miss and cacheable and all(core["status"] == "completed" for core in cores):
        await asyncio.to_thread(db.set_llm_cache, text_hash, llm_result, api_token)
    elif cache_miss:
        print(f"[LLM Cache] SKIP low-quality result: {file_label}")

    return cores


def _rule_document_cores(raw_text: str, documents: list[dict[str, Any]], filename: str) -> list[dict[str, Any]]:
    file_label = safe_file_label(filename)
    cores = []
    for doc_index, document in enumerate(documents, start=1):
        document_type = document.get("document_type") or "unknown"
        fields = document.get("fields") if isinstance(document.get("fields"), dict) else {}
        fields, conflict_fields = _normalize_fields(fields, filename, document_type)
        financial_review_fields = normalize_financial_fields(fields, document_type, raw_text)
        low_confidence_fields = [
            fn for fn, fd in fields.items()
            if isinstance(fd, dict) and fd.get("confidence", 1.0) < 0.8
        ]
        low_confidence_fields.extend(conflict_fields)
        low_confidence_fields.extend(financial_review_fields)
        validation_payload = {"fields": fields, "document_type": document_type}
        validation = validate_llm_result(validation_payload, document_type)
        if validation.get("auto_fixed"):
            print(
                f"[Rule Extractor] {file_label} document={doc_index} "
                f"auto_fixed_count={len(validation['auto_fixed'])}"
            )
        if validation.get("needs_review"):
            low_confidence_fields.extend(validation["needs_review"])

        schema_validation = validate_schema_fields(fields, document_type)
        warning_messages = []
        if schema_validation.get("needs_review"):
            low_confidence_fields.extend(schema_validation["needs_review"])
            if schema_validation.get("missing_required"):
                warning_messages.append(f"缺少必填字段: {', '.join(schema_validation['missing_required'])}")
            if schema_validation.get("type_errors"):
                warning_messages.append(f"字段格式异常: {', '.join(schema_validation['type_errors'])}")

        cores.append({
            "status": "completed",
            "raw_ocr_text": raw_text,
            "structured_data": fields,
            "confidence": document.get("confidence", 0.82),
            "low_confidence_fields": list(set(low_confidence_fields)),
            "document_type": document_type,
            "error_message": "；".join(warning_messages),
        })
    return cores


def _llm_quality_error(preprocessed_text: str, documents: list[dict[str, Any]], expected_document_count: int) -> str:
    if expected_document_count > 1 and len(documents) < expected_document_count:
        return f"OCR/版面检测到至少 {expected_document_count} 张独立单据，但 LLM 只返回 {len(documents)} 张，疑似把多列/多单据合并"

    for index, document in enumerate(documents, start=1):
        fields = document.get("fields") if isinstance(document.get("fields"), dict) else {}
        merged_fields = _numeric_suffix_merge_fields(fields)
        if merged_fields:
            return f"第 {index} 张结果包含疑似横向合并字段: {', '.join(merged_fields[:6])}"

    signal_count = _multi_document_signal_count(preprocessed_text)
    if signal_count > 1 and len(documents) == 1 and not _looks_pre_split(preprocessed_text):
        return f"OCR 文本包含 {signal_count} 个多单据信号，但 LLM 只返回 1 张，疑似错列合并"

    return ""


def _numeric_suffix_merge_fields(fields: dict) -> list[str]:
    bases: dict[str, list[str]] = {}
    for field_name in fields.keys():
        match = re.match(r"^(.+?)(?:[_-]?\d+)$", str(field_name).strip())
        if not match:
            continue
        base = match.group(1)
        if len(base) < 2:
            continue
        bases.setdefault(base, []).append(field_name)
    suspicious = []
    for names in bases.values():
        if len(names) >= 2:
            suspicious.extend(names)
    return suspicious


def _multi_document_signal_count(text: str) -> int:
    patterns = [
        r"电子回单号码\s*[:：]",
        r"电子回单号\s*[:：]",
        r"回单编号\s*[:：]",
        r"交易流水号\s*[:：]",
        r"发票号码\s*[:：]",
        r"收据编号\s*[:：]",
    ]
    return sum(len(re.findall(pattern, text or "")) for pattern in patterns)


def _looks_pre_split(text: str) -> bool:
    return (text or "").count("[版面结构提示]") <= 1 and _multi_document_signal_count(text) <= 1


def _normalize_llm_documents(llm_result: dict, default_doc_type: str) -> list[dict[str, Any]]:
    if not isinstance(llm_result, dict):
        return []

    documents = llm_result.get("documents")
    if isinstance(documents, list):
        normalized = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            fields = _coerce_fields(document.get("fields"))
            if fields:
                next_doc = dict(document)
                next_doc["fields"] = fields
                next_doc["document_type"] = next_doc.get("document_type") or default_doc_type
                normalized.append(next_doc)
        if normalized:
            return normalized

    fields = _coerce_fields(llm_result.get("fields"))
    if fields:
        return [{
            "document_type": llm_result.get("document_type", default_doc_type),
            "fields": fields,
            "confidence": llm_result.get("confidence", 0.0),
        }]

    return []


def _coerce_fields(fields: Any) -> dict:
    if not isinstance(fields, dict):
        return {}

    normalized = {}
    for field_name, field_data in fields.items():
        if not field_name:
            continue
        if isinstance(field_data, dict):
            if "value" in field_data:
                value = field_data.get("value")
                confidence = field_data.get("confidence", 0.8)
            elif len(field_data) == 1:
                value = next(iter(field_data.values()))
                confidence = 0.6
            else:
                value = json.dumps(field_data, ensure_ascii=False)
                confidence = 0.6
            normalized[field_name] = {
                "value": value,
                "confidence": _bounded_confidence(confidence),
            }
        else:
            normalized[field_name] = {
                "value": field_data,
                "confidence": 0.7,
            }
    return normalized


def _bounded_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.8
    return max(0.0, min(1.0, confidence))


def _has_extractable_fields(fields: dict) -> bool:
    for field_data in fields.values():
        value = field_data.get("value") if isinstance(field_data, dict) else field_data
        if value is None:
            continue
        if str(value).strip():
            return True
    return False


def _normalize_fields(fields: dict, filename: str, doc_type: str = "") -> tuple[dict, list[str]]:
    normalized_fields, conflict_fields = normalize_structured_fields(fields, doc_type)
    file_label = safe_file_label(filename)

    if normalized_fields != fields:
        print(
            f"[Field Normalizer] {file_label} normalized "
            f"input_count={len(fields)} output_count={len(normalized_fields)}"
        )
    if conflict_fields:
        print(f"[Field Normalizer] {file_label} conflict_count={len(conflict_fields)}")
    return normalized_fields, conflict_fields


async def _repair_missing_or_low_confidence_fields(
    text: str,
    document_type: str,
    fields: dict,
    requirement: str,
    filename: str,
) -> dict:
    file_label = safe_file_label(filename)
    target_fields = _repair_target_fields(document_type, fields)
    if not target_fields:
        return {}
    if len((text or "").strip()) < 40:
        return {}

    async with _llm_semaphore:
        repair_result = await extract_missing_fields(
            text,
            document_type,
            fields,
            target_fields,
            requirement,
        )
    if _is_llm_error(repair_result):
        print(f"[LLM Repair] {file_label}: failed")
        return {}

    repaired = _coerce_fields(repair_result.get("fields"))
    repaired = {
        field_name: field_data
        for field_name, field_data in repaired.items()
        if field_name in target_fields and _field_value_text(field_data)
    }
    if repaired:
        print(f"[LLM Repair] {file_label}: filled_count={len(repaired)}")
    return repaired


def _repair_target_fields(document_type: str, fields: dict) -> list[str]:
    schema = schema_for(document_type)
    if not schema:
        return []

    targets: list[str] = []
    priority_fields = list(schema.get("required", []))
    if document_type == "bank_receipt":
        priority_fields.extend(["交易流水号", "时间戳"])

    for field_name in priority_fields:
        if field_name in targets:
            continue
        if not _field_has_text(fields, field_name):
            targets.append(field_name)
            continue
        try:
            confidence = float(fields.get(field_name, {}).get("confidence", 1.0))
        except (TypeError, ValueError, AttributeError):
            confidence = 1.0
        if confidence < 0.65:
            targets.append(field_name)

    for field_name in schema.get("recommended", []):
        if field_name in targets or not _field_has_text(fields, field_name):
            continue
        try:
            confidence = float(fields.get(field_name, {}).get("confidence", 1.0))
        except (TypeError, ValueError, AttributeError):
            confidence = 1.0
        if confidence < 0.65:
            targets.append(field_name)

    return targets[:6]


def _override_document_type(document_type: str, fields: dict, text: str) -> str:
    if document_type == "invoice":
        return document_type
    if _looks_like_payment_detail(text, fields):
        return "bank_receipt"
    return document_type


def _looks_like_payment_detail(text: str, fields: dict | None = None) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    field_names = "".join(str(name) for name in (fields or {}).keys())
    joined = compact + field_names
    signals = [
        "支付时间",
        "当前状态",
        "支付方式",
        "交易单号",
        "商户单号",
        "商户全称",
        "收单机构",
        "付款凭证",
    ]
    signal_count = sum(1 for signal in signals if signal in joined)
    return signal_count >= 3 and ("交易单号" in joined or "商户单号" in joined or "支付时间" in joined)


def _enrich_fields_from_text(fields: dict, document_type: str, text: str) -> None:
    if document_type != "bank_receipt":
        return

    if not _field_has_text(fields, "时间戳") and _looks_like_payment_detail(text, fields):
        timestamp = _payment_timestamp_from_text(text)
        if timestamp:
            fields["时间戳"] = {"value": timestamp, "confidence": 0.75}

    if not _field_has_text(fields, "交易日期") and _field_has_text(fields, "时间戳"):
        date_value = _date_from_text(_field_value_text(fields.get("时间戳")))
        if date_value:
            fields["交易日期"] = {"value": date_value, "confidence": 0.8}

    if not _field_has_text(fields, "交易金额") and _looks_like_payment_detail(text, fields):
        amount = _primary_payment_amount(text)
        if amount:
            fields["交易金额"] = {"value": amount, "confidence": 0.65}


def _field_has_text(fields: dict, field_name: str) -> bool:
    return bool(_field_value_text(fields.get(field_name)))


def _field_value_text(field_data: Any) -> str:
    if isinstance(field_data, dict):
        value = field_data.get("value")
    else:
        value = field_data
    return "" if value is None else str(value).strip()


def _date_from_text(value: str) -> str:
    match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})", value or "")
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _payment_timestamp_from_text(text: str) -> str:
    match = re.search(
        r"(?:支付时间|交易时间|付款时间)[^\d]{0,20}"
        r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日]?\s*"
        r"(\d{1,2})[:：](\d{1,2})(?:[:：](\d{1,2}))?",
        text or "",
        re.DOTALL,
    )
    if not match:
        return ""
    year, month, day, hour, minute, second = match.groups()
    return (
        f"{int(year):04d}-{int(month):02d}-{int(day):02d} "
        f"{int(hour):02d}:{int(minute):02d}:{int(second or 0):02d}"
    )


def _primary_payment_amount(text: str) -> str:
    normalized_text = (text or "").replace("−", "-").replace("—", "-")
    negative_match = re.search(r"(?<![\d.])- ?\d{1,9}(?:,\d{3})*(?:\.\d{1,2})", normalized_text)
    if negative_match:
        return negative_match.group(0).replace(" ", "").replace(",", "")

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = line.replace("−", "-").replace("—", "-").replace("￥", "").replace("¥", "")
        line = re.sub(r"\s+", "", line)
        if re.fullmatch(r"-?\d{1,9}(?:,\d{3})*(?:\.\d{1,2})", line):
            return line.replace(",", "")
    return ""


async def _process_file_core(
    result_id: int,
    filepath: str,
    filename: str,
    ocr_result: dict,
    requirement: str = "",
    api_token: str = "",
    template_type: str = "general",
    bypass_llm_cache: bool = False,
) -> list[dict[str, Any]]:
    file_label = safe_file_label(filename)
    raw_text = ocr_result["full_text"]

    preprocessed_text = quick_preprocess(raw_text)
    if preprocessed_text != raw_text:
        print(f"[OCR Preprocess] {file_label}: cleaned {len(raw_text)} -> {len(preprocessed_text)} chars")

    list_records = extract_list_records(raw_text, ocr_result, filename, filepath)
    if list_records:
        print(f"[Rule Extractor] {file_label}: records={len(list_records)}")
        return _rule_document_cores(raw_text, list_records, filename)

    layout_documents = analyze_layout(preprocessed_text, ocr_result)
    if len(layout_documents) > 1:
        print(f"[Layout Analyzer] {file_label}: split into {len(layout_documents)} layout documents")
    layout_parts = [document.text for document in layout_documents] or [preprocessed_text]

    parts = []
    for layout_part in layout_parts:
        split_parts = split_ocr_documents(layout_part)
        parts.extend(split_parts)
    if len(parts) > 1:
        print(f"[Document Splitter] {file_label}: split into {len(parts)} documents")

    expected_total = _expected_document_count(preprocessed_text, layout_documents, parts)
    cores: list[dict[str, Any]] = []
    for index, part in enumerate(parts, start=1):
        label = f"{filename}#{index}" if len(parts) > 1 else filename
        layout = _matching_layout(part, layout_documents)
        llm_part = build_layout_prompt(part, layout) if layout else part
        expected_for_part = 1 if len(parts) > 1 else expected_total
        cores.extend(await _process_text_core(
            part,
            part,
            label,
            requirement,
            api_token,
            template_type,
            llm_part,
            expected_for_part,
            bypass_llm_cache,
        ))

    return cores


def _matching_layout(part: str, layout_documents: list) -> Any:
    for layout in layout_documents:
        if part == layout.text or part in layout.text or layout.text in part:
            return layout
    return None


def _expected_document_count(text: str, layout_documents: list, parts: list[str]) -> int:
    if len(parts) > 1:
        return len(parts)
    marker_count = _multi_document_signal_count(text)
    layout_marker_count = max([getattr(layout, "marker_count", 0) for layout in layout_documents] or [0])
    return max(1, marker_count, layout_marker_count)


async def process_job(job_id: str):
    job_label = safe_job_label(job_id)
    try:
        job = await asyncio.to_thread(db.get_job, job_id)
        if not job:
            await asyncio.to_thread(db.update_job_status, job_id, "failed", "Job not found")
            return

        # Crash recovery: load checkpoint if job was previously processing (crashed)
        checkpoint = []
        if job.get("status") == "processing":
            checkpoint = await asyncio.to_thread(db.get_checkpoint, job_id)

        await asyncio.to_thread(db.update_job_status, job_id, "processing")
        await asyncio.to_thread(db.update_job_started_at, job_id)

        upload_dir = os.path.join(UPLOAD_DIR, job_id)
        if not os.path.exists(upload_dir):
            await asyncio.to_thread(db.update_job_status, job_id, "failed", "Upload directory not found")
            return

        files = extract_files(upload_dir)
        if not files:
            await asyncio.to_thread(db.update_job_status, job_id, "failed", "No supported files found")
            return

        await asyncio.to_thread(db.update_job_status, job_id, "processing", None)

        # Get existing results to map filenames to source-document result groups.
        existing_results = await asyncio.to_thread(db.get_results, job_id)
        filename_to_results: dict[str, list[dict]] = {}
        for result in existing_results:
            filename_to_results.setdefault(result["filename"], []).append(result)

        requirement = job.get("requirement", "")
        template_type = job.get("template_type", "general")
        api_token = job.get("api_token", "")
        bypass_llm_cache = "重新排队" in (job.get("error_message") or "") or "重试" in (job.get("error_message") or "")
        checkpoint_lock = asyncio.Lock()

        async def _process_one(filepath: str, filename: str, existing_for_file: list[dict] = None) -> None:
            file_label = safe_file_label(filename)
            existing_for_file = sorted(existing_for_file or [], key=lambda item: item["id"])
            if existing_for_file and all(item.get("status") == "completed" for item in existing_for_file):
                return
            existing_result_id = existing_for_file[0]["id"] if existing_for_file else None
            if existing_result_id is not None and existing_result_id in checkpoint:
                return

            if existing_result_id is not None:
                result_id = existing_result_id
                await asyncio.to_thread(db.delete_results_for_file_except, job_id, filename, result_id)
                await asyncio.to_thread(db.update_result, result_id, status="pending", source_document_index=1, source_document_count=1)
            else:
                result_id = await asyncio.to_thread(db.create_result, job_id, filename)
            try:
                h = hashlib.sha256()
                with open(filepath, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        h.update(chunk)
                file_hash = h.hexdigest()

                cached = await asyncio.to_thread(db.get_ocr_cache, file_hash, api_token)
                if cached is not None:
                    ocr_result = json.loads(cached["ocr_result"])
                    print(f"[Cache] HIT: {file_label}")
                else:
                    file_type = get_file_type(filename)
                    async with _ocr_semaphore:
                        if file_type == "image":
                            ocr_result = await ocr_image(filepath)
                        elif file_type == "pdf":
                            ocr_result = await ocr_pdf(filepath)
                        elif file_type == "doc":
                            ocr_result = await asyncio.to_thread(extract_text, filepath)
                        else:
                            await asyncio.to_thread(
                                db.update_result,
                                result_id,
                                status="failed",
                                error_message="不支持的文件类型",
                            )
                            await asyncio.to_thread(db.increment_processed, job_id)
                            return

                    if file_type != "doc" and (_is_ocr_error(ocr_result) or not _is_ocr_text_valid(ocr_result.get("full_text", ""))):
                        error_message = ocr_result.get("full_text", "").replace("OCR_ERROR:", "").strip() or "OCR 未识别出有效文本"
                        await asyncio.to_thread(
                            db.update_result, result_id,
                            raw_ocr_text=ocr_result.get("full_text", ""), status="failed",
                            error_message=error_message,
                        )
                        await asyncio.to_thread(db.increment_processed, job_id)
                        return

                    await asyncio.to_thread(db.set_ocr_cache, file_hash, ocr_result, api_token)
                    print(f"[Cache] MISS: {file_label}")

                cores = await _process_file_core(
                    result_id,
                    filepath,
                    filename,
                    ocr_result,
                    requirement,
                    api_token,
                    template_type,
                    bypass_llm_cache,
                )
                result_ids = [result_id]
                for _ in range(max(0, len(cores) - 1)):
                    result_ids.append(await asyncio.to_thread(db.create_result, job_id, filename))

                document_count = max(1, len(cores))
                for doc_index, (core, target_result_id) in enumerate(zip(cores, result_ids), start=1):
                    if core["status"] == "failed":
                        await asyncio.to_thread(
                            db.update_result, target_result_id,
                            raw_ocr_text=core.get("raw_ocr_text", ""),
                            status="failed",
                            document_type=core.get("document_type", "unknown"),
                            error_message=core.get("error_message", "处理失败"),
                            source_document_index=doc_index,
                            source_document_count=document_count,
                        )
                    else:
                        await asyncio.to_thread(
                            db.update_result, target_result_id,
                            raw_ocr_text=core["raw_ocr_text"],
                            structured_data=core["structured_data"],
                            confidence=core["confidence"],
                            low_confidence_fields=core["low_confidence_fields"],
                            status="completed",
                            document_type=core["document_type"],
                            error_message=core.get("error_message", ""),
                            source_document_index=doc_index,
                            source_document_count=document_count,
                        )
                    async with checkpoint_lock:
                        checkpoint.append(target_result_id)
                        if len(checkpoint) % 5 == 0:
                            await asyncio.to_thread(db.save_checkpoint, job_id, checkpoint)

            except Exception as exc:
                message = safe_exception_label(exc)
                print(f"[Pipeline Error] {job_label}/{file_label}: {message}")
                await asyncio.to_thread(
                    db.update_result,
                    result_id,
                    status="failed",
                    error_message=message,
                )

            await asyncio.to_thread(db.increment_processed, job_id)

        work_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        for filepath, filename in files:
            work_queue.put_nowait((filepath, filename))

        async def _worker() -> None:
            while True:
                try:
                    filepath, filename = work_queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    await _process_one(filepath, filename, filename_to_results.get(filename))
                finally:
                    work_queue.task_done()

        worker_count = _job_file_worker_count(job, len(files))
        print(f"[Pipeline] Job {job_label} file_workers={worker_count}, files={len(files)}")
        tasks = [_worker() for _ in range(worker_count)]
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=config.JOB_TIMEOUT)
        except asyncio.TimeoutError:
            print(f"[Pipeline] Job {job_label} 超时（{config.JOB_TIMEOUT}s），已完成文件可导出")
            results = await asyncio.to_thread(db.get_results, job_id)
            finished = [r for r in results if r["status"] in ("completed", "failed")]
            status = "timeout_partial" if finished else "failed"
            await asyncio.to_thread(
                db.update_job_status,
                job_id,
                status,
                f"处理超时（{config.JOB_TIMEOUT}秒），已完成文件可正常导出",
            )
            await asyncio.to_thread(db.save_checkpoint, job_id, checkpoint)
            return

        results = await asyncio.to_thread(db.get_results, job_id)
        failed_count = sum(1 for r in results if r["status"] == "failed")
        pending_count = sum(1 for r in results if r["status"] == "pending")
        completed_count = sum(1 for r in results if r["status"] == "completed")
        if failed_count or pending_count:
            status = "partial_failed" if completed_count else "failed"
            message = f"部分文件处理失败（成功 {completed_count}，失败 {failed_count}，未完成 {pending_count}）"
            await asyncio.to_thread(db.update_job_status, job_id, status, message)
        else:
            await asyncio.to_thread(db.update_job_status, job_id, "completed")
        await asyncio.to_thread(db.save_checkpoint, job_id, [])

    except Exception as exc:
        message = safe_exception_label(exc)
        print(f"[Pipeline Error] {job_label}: {message}")
        await asyncio.to_thread(db.update_job_status, job_id, "failed", message)

    finally:
        cleanup_job(job_id)


async def process_single_file(job_id: str, result_id: int, filepath: str, filename: str):
    job_label = safe_job_label(job_id)
    file_label = safe_file_label(filename)
    try:
        job = await asyncio.to_thread(db.get_job, job_id)
        requirement = job.get("requirement", "") if job else ""
        template_type = job.get("template_type", "general") if job else "general"
        api_token = job.get("api_token", "") if job else ""
        await asyncio.to_thread(db.delete_results_for_file_except, job_id, filename, result_id)
        await asyncio.to_thread(db.update_result, result_id, status="pending", source_document_index=1, source_document_count=1)

        file_type = get_file_type(filename)
        if file_type == "image":
            ocr_result = await ocr_image(filepath)
        elif file_type == "pdf":
            ocr_result = await ocr_pdf(filepath)
        elif file_type == "doc":
            ocr_result = await asyncio.to_thread(extract_text, filepath)
        else:
            await asyncio.to_thread(db.update_result, result_id, status="failed", error_message="不支持的文件类型")
            return

        if file_type != "doc" and (_is_ocr_error(ocr_result) or not _is_ocr_text_valid(ocr_result.get("full_text", ""))):
            error_message = ocr_result.get("full_text", "").replace("OCR_ERROR:", "").strip() or "OCR 未识别出有效文本"
            await asyncio.to_thread(
                db.update_result, result_id,
                raw_ocr_text=ocr_result.get("full_text", ""), status="failed",
                error_message=error_message,
            )
            return

        cores = await _process_file_core(
            result_id,
            filepath,
            filename,
            ocr_result,
            requirement,
            api_token,
            template_type,
            bypass_llm_cache=True,
        )
        result_ids = [result_id]
        for _ in range(max(0, len(cores) - 1)):
            result_ids.append(await asyncio.to_thread(db.create_result, job_id, filename))

        document_count = max(1, len(cores))
        for doc_index, (core, target_result_id) in enumerate(zip(cores, result_ids), start=1):
            if core["status"] == "failed":
                await asyncio.to_thread(
                    db.update_result, target_result_id,
                    raw_ocr_text=core.get("raw_ocr_text", ""),
                    status="failed",
                    document_type=core.get("document_type", "unknown"),
                    error_message=core.get("error_message", "处理失败"),
                    source_document_index=doc_index,
                    source_document_count=document_count,
                )
            else:
                await asyncio.to_thread(
                    db.update_result, target_result_id,
                    raw_ocr_text=core["raw_ocr_text"],
                    structured_data=core["structured_data"],
                    confidence=core["confidence"],
                    low_confidence_fields=core["low_confidence_fields"],
                    status="completed",
                    document_type=core["document_type"],
                    error_message=core.get("error_message", ""),
                    source_document_index=doc_index,
                    source_document_count=document_count,
                )
    except Exception as exc:
        message = safe_exception_label(exc)
        print(f"[Pipeline Error] retry {job_label}/{file_label}: {message}")
        await asyncio.to_thread(db.update_result, result_id, status="failed", error_message=message)


def cleanup_job(job_id: str):
    """清理任务相关文件，保留数据库记录"""
    # 仅清理导出的 Excel，上传文件保留以供重试（每日清理线程会处理旧文件）
    export_dir = os.path.join(EXPORT_DIR, job_id)
    if os.path.exists(export_dir):
        shutil.rmtree(export_dir)
