"""轻量文本提取器：支持 docx/xlsx/html/xml 格式"""

import os
from typing import Dict, Any


def extract_text(filepath: str) -> Dict[str, Any]:
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".docx":
            return _extract_docx(filepath)
        elif ext in (".xlsx", ".xls"):
            return _extract_xlsx(filepath)
        elif ext in (".html", ".htm"):
            return _extract_html(filepath)
        elif ext == ".xml":
            return _extract_xml(filepath)
        else:
            return {"full_text": "", "texts": []}
    except Exception as e:
        return {"full_text": f"EXTRACT_ERROR: {str(e)}", "texts": []}


def _extract_docx(filepath: str) -> Dict[str, Any]:
    from docx import Document
    doc = Document(filepath)
    texts = [p.text for p in doc.paragraphs if p.text.strip()]
    return {"full_text": "\n".join(texts), "texts": texts, "confidence": 1.0}


def _extract_xlsx(filepath: str) -> Dict[str, Any]:
    import openpyxl
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    texts = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            line = " | ".join(str(c) for c in row if c is not None)
            if line.strip():
                texts.append(line)
    wb.close()
    return {"full_text": "\n".join(texts), "texts": texts, "confidence": 1.0}


def _extract_html(filepath: str) -> Dict[str, Any]:
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.result = []
            self.skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.skip = False

        def handle_data(self, data):
            if not self.skip and data.strip():
                self.result.append(data.strip())

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    parser = TextExtractor()
    parser.feed(content)
    return {"full_text": "\n".join(parser.result), "texts": parser.result, "confidence": 1.0}


def _extract_xml(filepath: str) -> Dict[str, Any]:
    import xml.etree.ElementTree as ET
    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    tree = ET.parse(filepath, parser)
    root = tree.getroot()
    texts = [elem.text for elem in root.iter() if elem.text and elem.text.strip()]
    return {"full_text": "\n".join(texts), "texts": texts, "confidence": 1.0}
