import base64
from io import BytesIO
import tempfile
import unittest
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from app.utils.pdf_renderer import PDF_RENDER_DPI, get_pdf_page_count, render_pdf_pages


ENCRYPTED_SYNTHETIC_PDF = (
    "JVBERi0xLjcKJeLjz9MKMSAwIG9iago8PAovVHlwZSAvUGFnZXMKL0NvdW50IDEKL0tp"
    "ZHMgWyA0IDAgUiBdCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9Qcm9kdWNlciA8YWUwM2Yz"
    "NDc3ZWIzPgo+PgplbmRvYmoKMyAwIG9iago8PAovVHlwZSAvQ2F0YWxvZwovUGFnZXMg"
    "MSAwIFIKPj4KZW5kb2JqCjQgMCBvYmoKPDwKL01lZGlhQm94IFsgMCAwIDcyIDcyIF0K"
    "L1Jlc291cmNlcyA8PAo+PgovUm90YXRlIDAKL1R5cGUgL1BhZ2UKL1BhcmVudCAxIDAg"
    "Ugo+PgplbmRvYmoKNSAwIG9iago8PAovRmlsdGVyIC9TdGFuZGFyZAovViAyCi9MZW5n"
    "dGggMTI4Ci9SIDMKL08gPDU0MjE3OGY5NmE1YWFhZjZmZTBhZmMzM2M1NWUxYzhkNGE3"
    "NjQ5ZWQ2ODQ1NmM0YzI3YjA3OTRkZThjNGU3OWM+Ci9VIDw4YTAxMTNmZThiYzJmZmIz"
    "NjA0OTZjYThjMWY4ZDg4ZjAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwPg"
    "ovUCAyMTQ3NDgzNjQ0Cj4+CmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1"
    "IGYgCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDA3NCAwMDAwMCBuIAowMDAwMDAw"
    "MTIwIDAwMDAwIG4gCjAwMDAwMDAxNjkgMDAwMDAgbiAKMDAwMDAwMDI2NyAwMDAwMCBu"
    "IAp0cmFpbGVyCjw8Ci9TaXplIDYKL1Jvb3QgMyAwIFIKL0luZm8gMiAwIFIKL0lEIFsg"
    "PDIwNjZhNzcwMzFjNGJmNzZlN2ZlNmFmMjMxOTg2NGVmPiA8ZTE0NWYwYzVjNjAyMGEx"
    "OWEwMzBiMWZiNTMxMTM2OGM+IF0KL0VuY3J5cHQgNSAwIFIKPj4Kc3RhcnR4cmVmCjQ4"
    "MgolJUVPRgo="
)


def _create_test_pdf(path: Path) -> None:
    document = pdfium.PdfDocument.new()
    try:
        portrait_page = document.new_page(width=72, height=144)
        portrait_page.close()

        rotated_page = document.new_page(width=200, height=100)
        rotated_page.set_rotation(90)
        rotated_page.close()

        document.save(path)
    finally:
        document.close()


class PdfRendererTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pdf_path = Path(self.temp_dir.name) / "synthetic.pdf"
        _create_test_pdf(self.pdf_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_renders_all_pages_as_png_at_requested_dpi(self):
        source_page_count = get_pdf_page_count(str(self.pdf_path))
        pages = list(render_pdf_pages(str(self.pdf_path), max_pages=50, dpi=144))

        self.assertEqual(source_page_count, 2)
        self.assertEqual([page_number for page_number, _ in pages], [1, 2])

        expected_sizes = [(144, 288), (200, 400)]
        for (_, png_bytes), expected_size in zip(pages, expected_sizes):
            self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
            with Image.open(BytesIO(png_bytes)) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, expected_size)

    def test_limits_rendered_pages_but_reports_source_count(self):
        source_page_count = get_pdf_page_count(str(self.pdf_path))
        pages = list(render_pdf_pages(str(self.pdf_path), max_pages=1))

        self.assertEqual(PDF_RENDER_DPI, 150)
        self.assertEqual(source_page_count, 2)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0][0], 1)
        with Image.open(BytesIO(pages[0][1])) as image:
            self.assertEqual(image.size, (150, 300))
            self.assertEqual(image.convert("RGB").getpixel((0, 0)), (255, 255, 255))

    def test_rejects_invalid_limits(self):
        with self.assertRaisesRegex(ValueError, "max_pages"):
            list(render_pdf_pages(str(self.pdf_path), max_pages=0))

        with self.assertRaisesRegex(ValueError, "dpi"):
            list(render_pdf_pages(str(self.pdf_path), max_pages=1, dpi=0))

    def test_rejects_corrupt_and_password_protected_pdfs(self):
        corrupt_path = Path(self.temp_dir.name) / "corrupt.pdf"
        corrupt_path.write_bytes(b"%PDF-1.7\ntruncated")

        encrypted_path = Path(self.temp_dir.name) / "encrypted.pdf"
        encrypted_path.write_bytes(base64.b64decode(ENCRYPTED_SYNTHETIC_PDF))

        with self.assertRaises(pdfium.PdfiumError):
            get_pdf_page_count(str(corrupt_path))
        with self.assertRaises(pdfium.PdfiumError):
            get_pdf_page_count(str(encrypted_path))


if __name__ == "__main__":
    unittest.main()
