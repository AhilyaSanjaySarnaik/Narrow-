"""Import local text files and public web pages into the local Markdown KB."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import ssl
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi

_MAX_BYTES = 20 * 1024 * 1024
_SUPPORTED_SUFFIXES = {
    ".md", ".markdown", ".txt", ".html", ".htm", ".pdf", ".docx", ".pptx", ".xlsx",
    ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".py", ".js", ".ts", ".java",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".php", ".rb", ".ps1", ".sh",
    ".sql", ".log", ".ini", ".cfg", ".conf", ".rtf",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".flac",
}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
_MEDIA_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".flac"}


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        elif self.skip_depth == 0 and tag in {"p", "br", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        elif self.skip_depth == 0 and tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)


def _clean_html(content: str) -> str:
    parser = _ArticleParser()
    parser.feed(content)
    text = html.unescape("".join(parser.parts))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _extract_office_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("Install project dependencies to import Word documents.") from exc
        document = Document(str(path))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
        return "\n".join(parts)
    if path.suffix.lower() == ".pptx":
        try:
            from pptx import Presentation
        except ImportError as exc:
            raise RuntimeError("Install project dependencies to import PowerPoint files.") from exc
        parts: list[str] = []
        for slide_number, slide in enumerate(Presentation(str(path)).slides, start=1):
            parts.append(f"Slide {slide_number}")
            parts.extend(shape.text for shape in slide.shapes if hasattr(shape, "text"))
        return "\n".join(parts)
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("Install project dependencies to import Excel files.") from exc
    workbook = load_workbook(str(path), read_only=True, data_only=True)
    parts = []
    for sheet in workbook.worksheets:
        parts.append(f"Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            values = [str(value) for value in row if value is not None]
            if values:
                parts.append(" | ".join(values))
    return "\n".join(parts)


def _extract_media_text(path: Path) -> str:
    if path.suffix.lower() in _IMAGE_SUFFIXES:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Install project dependencies to inspect image files.") from exc
        with Image.open(path) as image:
            parts = [f"Image format: {image.format}", f"Image size: {image.width}x{image.height}"]
            try:
                import pytesseract

                ocr = pytesseract.image_to_string(image).strip()
            except (ImportError, OSError):
                ocr = ""
            if ocr:
                parts.extend(["OCR text:", ocr])
            else:
                parts.append("OCR text: unavailable; install Tesseract OCR to read text in this image.")
            return "\n".join(parts)

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=format_name,duration,size", "-of", "default=noprint_wrappers=1", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return (
            f"Media file: {path.name}\n"
            f"Media type: {path.suffix.lower()}\n"
            "Media metadata: install FFmpeg/FFprobe for details."
        )
    metadata = result.stdout.strip() if result.returncode == 0 else ""
    return (
        f"Media file: {path.name}\n"
        f"Media type: {path.suffix.lower()}\n"
        f"Media metadata:\n{metadata or 'unavailable; FFprobe could not read this file.'}\n"
        "Transcript: not available; add a speech-to-text model to analyze spoken content."
    )


def _validate_url(source: str) -> None:
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source must be a local text file or an http(s) URL")
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        raise ValueError("local and private network URLs are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise ValueError("local and private network URLs are not allowed")


def _read_source(source: str | Path) -> tuple[str, str]:
    source_text = str(source)
    if source_text.startswith(("http://", "https://")):
        _validate_url(source_text)
        request = Request(source_text, headers={"User-Agent": "Narrow/0.1"})
        context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=15, context=context) as response:  # noqa: S310 - URL is validated above.
            content_type = response.headers.get_content_type()
            payload = response.read(_MAX_BYTES + 1)
        if len(payload) > _MAX_BYTES:
            raise ValueError("source is larger than the 5 MB import limit")
        text = payload.decode("utf-8", errors="replace")
        return source_text, _clean_html(text) if content_type == "text/html" else text

    path = Path(source).expanduser().resolve()
    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise ValueError(
            "unsupported file type; supported: PDF, Word, PowerPoint, Excel, text, data, and source-code files"
        )
    if path.stat().st_size > _MAX_BYTES:
        raise ValueError("source is larger than the 5 MB import limit")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Install the project dependencies to import PDF files.") from exc
        text = "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    elif suffix in {".docx", ".pptx", ".xlsx"}:
        text = _extract_office_text(path)
    elif suffix in _IMAGE_SUFFIXES or suffix in _MEDIA_SUFFIXES:
        text = _extract_media_text(path)
    else:
        text = path.read_text(encoding="utf-8")
    return str(path), _clean_html(text) if suffix in {".html", ".htm"} else text


def ingest_source(source: str | Path, root: str | Path = "kb") -> Path:
    """Import one local file or public URL and return the created Markdown path."""
    origin, text = _read_source(source)
    if not text.strip():
        raise ValueError("source contained no readable text")
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(origin.encode("utf-8")).hexdigest()[:12]
    title = Path(urlparse(origin).path).stem if origin.startswith(("http://", "https://")) else Path(origin).stem
    title = re.sub(r"[^a-zA-Z0-9_-]+", "-", title).strip("-") or "imported-source"
    destination = root_path / f"{title}-{digest}.md"
    destination.write_text(f"# Imported source\n\nSource: {origin}\n\n{text.strip()}\n", encoding="utf-8")
    return destination
