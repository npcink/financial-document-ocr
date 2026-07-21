import re
import httpx
import json
import base64
import os
import mimetypes
import asyncio
from typing import Dict, Any

from app.core import config
from app.services.rate_limit import siliconflow_request_with_retry
from app.utils.image_preprocess import preprocess_image
from app.utils.logging_safety import safe_exception_label, safe_file_label
from app.utils.pdf_renderer import get_pdf_page_count, render_pdf_pages

_http_client: httpx.AsyncClient = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )
    return _http_client


async def close_http_client():
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


class _CloudClient:
    async def list(self):
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{config.SILICONFLOW_BASE_URL}/models",
                headers={"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"},
            )
            resp.raise_for_status()
            return resp.json()


def get_ocr_client():
    return _CloudClient()


def _guess_mime_type(image_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(image_path)
    return mime_type or "image/png"


async def ocr_image(image_path: str) -> Dict[str, Any]:
    processed_path = preprocess_image(image_path)
    file_label = safe_file_label(image_path)
    try:
        with open(processed_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        mime_type = _guess_mime_type(processed_path)

        headers = {
            "Authorization": f"Bearer {config.SILICONFLOW_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config.OCR_MODEL_CLOUD,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                        {"type": "text", "text": "<|grounding|>Convert the document to markdown."},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        print(f"[OCR] 开始识别: {file_label}, 图片大小: {os.path.getsize(image_path)} 字节")

        async def _do_request():
            client = get_http_client()
            response = await client.post(
                f"{config.SILICONFLOW_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

        data = await siliconflow_request_with_retry(
            _do_request,
            label="OCR image",
            bucket="ocr",
        )
        full_text = data["choices"][0]["message"]["content"]
        lines = [line.strip() for line in full_text.split("\n") if line.strip()]
        cleaned_lines = [re.sub(r'^\d+[\.\)]\s+', '', line) for line in lines]
        cleaned_full = "\n".join(cleaned_lines)
        print(f"[OCR] 识别完成: {len(cleaned_lines)} 行, {len(full_text)} 字符")
        return {
            "texts": cleaned_lines,
            "full_text": cleaned_full,
            "raw_response": full_text,
            "confidence": 0.85,
            "word_count": len(cleaned_lines),
        }
    except Exception as exc:
        error_label = safe_exception_label(exc)
        print(f"[OCR] 识别失败: {file_label} error={error_label}")
        return {
            "texts": [],
            "full_text": f"OCR_ERROR: {error_label}",
            "confidence": 0.0,
            "word_count": 0,
        }
    finally:
        if processed_path != image_path:
            os.remove(processed_path)


MAX_PDF_PAGES = 50


async def _ocr_image_bytes(image_bytes: bytes) -> Dict[str, Any]:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {config.SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config.OCR_MODEL_CLOUD,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    {"type": "text", "text": "<|grounding|>Convert the document to markdown."},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    async def _do_request():
        client = get_http_client()
        response = await client.post(
            f"{config.SILICONFLOW_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    data = await siliconflow_request_with_retry(_do_request, label="OCR pdf page", bucket="ocr")
    full_text = data["choices"][0]["message"]["content"]

    lines = [line.strip() for line in full_text.split("\n") if line.strip()]
    cleaned_lines = [re.sub(r'^\d+[\.\)]\s+', '', line) for line in lines]
    cleaned_full = "\n".join(cleaned_lines)
    return {
        "texts": cleaned_lines,
        "full_text": cleaned_full,
        "raw_response": full_text,
        "confidence": 0.85,
        "word_count": len(cleaned_lines),
    }


async def ocr_pdf(pdf_path: str) -> Dict[str, Any]:
    source_page_count = get_pdf_page_count(pdf_path)
    page_data = list(render_pdf_pages(pdf_path, max_pages=MAX_PDF_PAGES))
    total_pages = len(page_data)
    if source_page_count > MAX_PDF_PAGES:
        print(
            f"[OCR] PDF 超过 {MAX_PDF_PAGES} 页 ({source_page_count})，"
            f"只处理前 {MAX_PDF_PAGES} 页"
        )

    pdf_semaphore = asyncio.Semaphore(config.PDF_OCR_CONCURRENCY)

    async def _ocr_page(page_num, png_bytes):
        async with pdf_semaphore:
            result = await _ocr_image_bytes(png_bytes)
            return page_num, result

    page_tasks = [_ocr_page(pn, data) for pn, data in page_data]
    page_results = await asyncio.gather(*page_tasks)
    page_results.sort(key=lambda x: x[0])

    all_texts = []
    total_confidence = 0.0
    for _, result in page_results:
        all_texts.extend(result["texts"])
        total_confidence += result["confidence"]

    avg_confidence = total_confidence / total_pages if total_pages > 0 else 0.0

    return {
        "texts": all_texts,
        "full_text": "\n".join(all_texts),
        "confidence": avg_confidence,
        "word_count": len(all_texts),
        "pages": total_pages,
    }
