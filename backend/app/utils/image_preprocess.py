import os
import uuid
from PIL import Image

MAX_IMAGE_WIDTH = 1500
JPEG_QUALITY = 85


def preprocess_image(image_path: str) -> str:
    filename = os.path.basename(image_path)
    ext = os.path.splitext(filename)[1].lower()

    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"[Preprocess] 打开图片失败 {filename}: {e}，使用原始图片")
        return image_path

    original_size = os.path.getsize(image_path)
    width, height = img.size

    if ext in (".jpg", ".jpeg") and width < MAX_IMAGE_WIDTH:
        print(f"[Preprocess] {filename}: JPEG 尺寸合适，跳过预处理")
        img.close()
        return image_path

    if width < MAX_IMAGE_WIDTH and img.mode == "L":
        print(f"[Preprocess] {filename}: 图片已满足条件，跳过预处理")
        img.close()
        return image_path

    if width > MAX_IMAGE_WIDTH:
        ratio = MAX_IMAGE_WIDTH / width
        new_size = (MAX_IMAGE_WIDTH, int(height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    img = img.convert("L")

    temp_filename = f"preprocessed_{uuid.uuid4().hex}.jpg"
    temp_path = os.path.join("/tmp", temp_filename)
    img.save(temp_path, "JPEG", quality=JPEG_QUALITY)

    processed_size = os.path.getsize(temp_path)
    print(f"[Preprocess] {filename}: {original_size} → {processed_size}")

    return temp_path
