"""纯 OCR 识别接口（跳过 LLM，直接返回原始文本）"""

import os
import shutil
import uuid
import zipfile
from typing import List

from fastapi import APIRouter, File, UploadFile, HTTPException
from app.services.ocr import ocr_image, ocr_pdf
from app.db import UPLOAD_DIR

router = APIRouter()

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".pdf", ".zip"}
MAX_FILE_SIZE = 200 * 1024 * 1024
UPLOAD_BASE_DIR = UPLOAD_DIR


def _is_allowed(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def _extract_images_from_zip(zip_path: str, target_dir: str) -> List[str]:
    extracted = []
    MAX_EXTRACT_FILES = 300
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = [m for m in zf.namelist() if not m.startswith(("__MACOSX", ".")) and os.path.basename(m)]
        if len(members) > MAX_EXTRACT_FILES:
            print(f"[OCR] ZIP 文件数过多 ({len(members)})，只解压前 {MAX_EXTRACT_FILES} 个")
            members = members[:MAX_EXTRACT_FILES]

        for member in members:
            basename = os.path.basename(member)
            if not basename or not _is_allowed(basename):
                continue
            ext = os.path.splitext(basename)[1].lower()
            if ext == ".zip":
                continue  # 不解压嵌套 zip
            info = zf.getinfo(member)
            if info.file_size > MAX_FILE_SIZE:
                print(f"[OCR] 跳过超大文件: {basename} ({info.file_size} 字节)")
                continue
            target_path = os.path.join(target_dir, basename)
            with zf.open(member) as src, open(target_path, "wb") as dst:
                dst.write(src.read())
            extracted.append(target_path)
    return extracted


def _get_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".pdf"}:
        return "pdf"
    if ext in ALLOWED_EXTENSIONS - {".zip", ".pdf"}:
        return "image"
    return "unknown"


@router.post("/")
async def ocr_recognize(files: List[UploadFile] = File(...)):
    """上传单张或多张图片/PDF/ZIP，同步返回 OCR 识别结果 JSON"""
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")

    job_id = uuid.uuid4().hex[:8]
    job_dir = os.path.join(UPLOAD_BASE_DIR, f"ocr_{job_id}")
    os.makedirs(job_dir, exist_ok=True)

    saved_files = []
    total_files = 0

    for f in files:
        if not f.filename or not _is_allowed(f.filename):
            continue

        content = await f.read()
        filename = os.path.basename(f.filename)

        if len(content) > MAX_FILE_SIZE:
            continue

        ext = os.path.splitext(filename)[1].lower()
        saved_path = os.path.join(job_dir, filename)
        with open(saved_path, "wb") as dst:
            dst.write(content)

        if ext == ".zip":
            extracted = _extract_images_from_zip(saved_path, job_dir)
            os.remove(saved_path)
            saved_files.extend([os.path.basename(p) for p in extracted])
            total_files += len(extracted)
        else:
            saved_files.append(filename)
            total_files += 1

    if total_files == 0:
        shutil.rmtree(job_dir)
        raise HTTPException(status_code=400, detail="未找到支持的文件格式（支持 png/jpg/pdf/zip）")

    # 同步 OCR 识别
    results = []
    for filename in sorted(os.listdir(job_dir)):
        filepath = os.path.join(job_dir, filename)
        if not os.path.isfile(filepath):
            continue

        file_type = _get_file_type(filename)
        try:
            if file_type == "pdf":
                ocr_result = await ocr_pdf(filepath)
            else:
                ocr_result = await ocr_image(filepath)

            results.append({
                "filename": filename,
                "type": file_type,
                "ocr_text": ocr_result.get("full_text", ""),
                "lines": ocr_result.get("texts", []),
                "word_count": ocr_result.get("word_count", 0),
                "pages": ocr_result.get("pages", 1),
            })
        except Exception as e:
            results.append({
                "filename": filename,
                "type": file_type,
                "ocr_text": f"ERROR: {str(e)}",
                "lines": [],
                "word_count": 0,
                "pages": 1,
            })

    # 清理临时文件
    shutil.rmtree(job_dir)

    return {
        "total_files": len(results),
        "results": results,
    }
