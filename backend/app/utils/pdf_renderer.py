from io import BytesIO
from typing import Iterator, Tuple

import pypdfium2 as pdfium


PDF_RENDER_DPI = 150


def get_pdf_page_count(pdf_path: str) -> int:
    document = pdfium.PdfDocument(pdf_path)
    try:
        return len(document)
    finally:
        document.close()


def render_pdf_pages(
    pdf_path: str,
    *,
    max_pages: int,
    dpi: int = PDF_RENDER_DPI,
) -> Iterator[Tuple[int, bytes]]:
    """Yield up to ``max_pages`` PDF pages as PNG byte strings.

    Page numbers are one-based. Each page's native PDF rotation is preserved.
    Resources used by one page are released before the next page is yielded.
    """
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    if dpi < 1:
        raise ValueError("dpi must be at least 1")

    document = pdfium.PdfDocument(pdf_path)
    try:
        page_count = min(len(document), max_pages)

        for page_index in range(page_count):
            page = document[page_index]
            try:
                bitmap = page.render(scale=dpi / 72)
                try:
                    image = bitmap.to_pil()
                    try:
                        buffer = BytesIO()
                        image.save(buffer, format="PNG")
                        png_bytes = buffer.getvalue()
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()

            yield page_index + 1, png_bytes
    finally:
        document.close()
