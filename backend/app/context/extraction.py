"""Bounded content validation and extraction; no OCR, macros or external resources."""

import re
import unicodedata
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

from defusedxml import ElementTree

from app.context.pdf import pdf_text

MAX_UPLOAD = 5 * 1024 * 1024
MAX_TEXT = 200_000
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class InvalidDocument(ValueError):
    pass


def safe_name(value: str) -> str:
    name = PurePosixPath(value.replace("\\", "/")).name
    name = "".join(
        c
        for c in unicodedata.normalize("NFKC", name)
        if not unicodedata.category(c).startswith("C")
    )
    name = name.strip().strip(".")
    if not name or len(name) > 180:
        raise InvalidDocument("Use a document name between 1 and 180 characters.")
    return name


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in "\n\t" or not unicodedata.category(c).startswith("C"))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def docx_text(content: bytes) -> str:
    with ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (
            len(entries) > 1000
            or len(names) != len(set(names))
            or sum(e.file_size for e in entries) > 20 * 1024 * 1024
            or any(e.file_size > 100 * max(e.compress_size, 1) for e in entries)
            or any(e.flag_bits & 1 for e in entries)
            or any("vbaproject" in name.lower() for name in names)
            or not {"[Content_Types].xml", "word/document.xml"}.issubset(names)
        ):
            raise InvalidDocument("Unsupported or oversized DOCX package.")
        types = ElementTree.fromstring(archive.read("[Content_Types].xml"))
        if not any(
            node.get("PartName") == "/word/document.xml"
            and node.get("ContentType") == DOCX_TYPE + ".main+xml"
            for node in types
        ):
            raise InvalidDocument("Not a Word DOCX document.")
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        if root.tag != WORD + "document":
            raise InvalidDocument("Invalid Word document.")
        paragraphs = []
        for paragraph in root.iter(WORD + "p"):
            parts = []
            for node in paragraph.iter():
                if node.tag == WORD + "t":
                    parts.append(node.text or "")
                elif node.tag in {WORD + "tab", WORD + "br", WORD + "cr"}:
                    parts.append("\n" if node.tag != WORD + "tab" else "\t")
            paragraphs.append("".join(parts))
        return "\n".join(paragraphs)


def extract(content: bytes, name: str) -> tuple[str, str]:
    if not content:
        raise InvalidDocument("The document is empty.")
    if len(content) > MAX_UPLOAD:
        raise InvalidDocument("Maximum upload size is 5 MB.")
    extension = PurePosixPath(name).suffix.lower()
    try:
        if extension == ".pdf" and content.startswith(b"%PDF-"):
            text, media = pdf_text(content, MAX_TEXT), "application/pdf"
        elif extension == ".docx" and content.startswith(b"PK\x03\x04"):
            text, media = docx_text(content), DOCX_TYPE
        elif extension == ".txt":
            text = content.decode("utf-8-sig", errors="strict")
            if any(unicodedata.category(c) == "Cc" and c not in "\r\n\t" for c in text):
                raise InvalidDocument("TXT must contain UTF-8 text, not binary data.")
            if text.lstrip().lower().startswith(("%pdf-", "<html", "<!doctype", "<?xml")):
                raise InvalidDocument("TXT must be plain text.")
            text, media = text, "text/plain"
        else:
            raise InvalidDocument("Upload a valid PDF, DOCX or UTF-8 TXT file.")
    except InvalidDocument:
        raise
    except Exception:
        # Parser errors can contain file content. Never expose or log them.
        raise InvalidDocument(
            "Unable to read this document. It may be malformed or encrypted."
        ) from None
    text = normalize(text)
    if not text or not any(c.isalnum() for c in text):
        raise InvalidDocument("No readable text found. Scanned documents need a text-based export.")
    if len(text) > MAX_TEXT:
        raise InvalidDocument("Document text exceeds the processing limit.")
    return text, media
