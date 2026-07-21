import ollama
import base64
import os
import asyncio
from typing import Dict, Any

from app.core import config
from app.utils.image_preprocess import preprocess_image

_ocr_client = None


def get_ocr_client() -> ollama.Client:
    global _ocr_client
    if _ocr_client is None:
        _ocr_client = ollama.Client(host=config.OLLAMA_HOST)
    return _ocr_client


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def _with_retry_async(func, max_retries=3):
    last_exception = None
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
    raise last_exception


def _ocr_image_sync(image_path: str) -> Dict[str, Any]:
    processed_path = preprocess_image(image_path)
    try:
        client = get_ocr_client()
        image_b64 = _encode_image(processed_path)

        prompt = """请识别这张图片中的所有文字内容，按阅读顺序输出。
对于表格类内容，请按行列结构输出。
对于发票/收据/回单，请保留所有关键字段信息。
只输出识别的文字，不要添加任何解释。"""

        response = client.chat(
            model=config.OCR_MODEL_LOCAL,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }],
            options={
                "temperature": 0.1,
                "num_ctx": 4096,
                "num_predict": 4096,
            },
        )
        full_text = response["message"]["content"]
        lines = [line.strip() for line in full_text.split("\n") if line.strip()]

        return {
            "texts": lines,
            "full_text": full_text,
            "confidence": 0.85,
            "word_count": len(lines),
        }
    except Exception as e:
        return {
            "texts": [],
            "full_text": f"OCR_ERROR: {str(e)}",
            "confidence": 0.0,
            "word_count": 0,
        }
    finally:
        if processed_path != image_path:
            os.remove(processed_path)


async def ocr_image(image_path: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_ocr_image_sync, image_path)


MAX_PDF_PAGES = 50


async def ocr_pdf(pdf_path: str) -> Dict[str, Any]:
    import fitz
    import tempfile
    import shutil

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    if total_pages > MAX_PDF_PAGES:
        print(f"[OCR] PDF 超过 {MAX_PDF_PAGES} 页 ({total_pages})，只处理前 {MAX_PDF_PAGES} 页")
        total_pages = MAX_PDF_PAGES
    doc.close()

    temp_dir = tempfile.mkdtemp(prefix="ocr_pdf_")
    temp_paths = []

    try:
        doc = fitz.open(pdf_path)
        for page_num in range(1, total_pages + 1):
            page = doc.load_page(page_num - 1)
            pix = page.get_pixmap(dpi=150)
            temp_path = os.path.join(temp_dir, f"page_{page_num}.png")
            pix.save(temp_path)
            temp_paths.append((page_num, temp_path))
        doc.close()

        pdf_semaphore = asyncio.Semaphore(4)

        async def _ocr_page(page_num, path):
            async with pdf_semaphore:
                result = await ocr_image(path)
                os.remove(path)
                return page_num, result

        page_tasks = [_ocr_page(pn, path) for pn, path in temp_paths]
        page_results = await asyncio.gather(*page_tasks)
        page_results.sort(key=lambda x: x[0])

        all_texts = []
        total_confidence = 0.0
        for _, result in page_results:
            all_texts.extend(result["texts"])
            total_confidence += result["confidence"]

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    avg_confidence = total_confidence / total_pages if total_pages > 0 else 0.0

    return {
        "texts": all_texts,
        "full_text": "\n".join(all_texts),
        "confidence": avg_confidence,
        "word_count": len(all_texts),
        "pages": total_pages,
    }
