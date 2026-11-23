import io
import zipfile
from pathlib import Path

from app.rag.chunking import Page

MAX_PDF_PAGES = 300
MAX_DOCX_UNCOMPRESSED = 50 * 1024 * 1024  # zip-bomb guard


class ExtractionError(Exception):
    """A user-presentable reason why text could not be extracted."""


def _pdf(path: Path) -> list[Page]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ExtractionError("Encrypted PDFs are not supported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ExtractionError(f"PDF has more than {MAX_PDF_PAGES} pages")
        pages = [Page(text=(p.extract_text() or "").strip(), number=i + 1) for i, p in enumerate(reader.pages)]
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError) as exc:
        raise ExtractionError(f"The PDF could not be read ({exc.__class__.__name__})") from exc
    if not any(p.text for p in pages):
        raise ExtractionError("The PDF has no extractable text (a scanned document? OCR is not supported)")
    return pages


def _docx(path: Path) -> list[Page]:
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        with zipfile.ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_DOCX_UNCOMPRESSED:
                raise ExtractionError("The DOCX file expands to an unreasonable size")
        document = docx.Document(str(path))
    except ExtractionError:
        raise
    except (zipfile.BadZipFile, PackageNotFoundError, KeyError, ValueError) as exc:
        raise ExtractionError("The DOCX file is corrupt or not a Word document") from exc

    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = "\n\n".join(parts).strip()
    if not text:
        raise ExtractionError("The document contains no text")
    return [Page(text=text, number=None)]


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExtractionError("The file is not valid UTF-8 text") from exc


def _text(path: Path) -> list[Page]:
    text = _decode(path.read_bytes()).strip()
    if not text:
        raise ExtractionError("The file is empty")
    return [Page(text=text, number=None)]


def _markdown(path: Path) -> list[Page]:
    import markdown
    from bs4 import BeautifulSoup

    html = markdown.markdown(_decode(path.read_bytes()))
    text = BeautifulSoup(html, "html.parser").get_text("\n").strip()
    if not text:
        raise ExtractionError("The file is empty")
    return [Page(text=text, number=None)]


def extract_pages(path: Path) -> list[Page]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf(path)
    if ext == ".docx":
        return _docx(path)
    if ext in (".md", ".markdown"):
        return _markdown(path)
    if ext == ".txt":
        return _text(path)
    raise ExtractionError(f"Unsupported file type: {ext or 'unknown'}")