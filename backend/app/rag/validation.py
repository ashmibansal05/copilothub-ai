import re
from pathlib import Path

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class UploadRejected(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def safe_display_name(filename: str | None) -> str:
    """Strip any path and odd characters. The name is only ever DISPLAYED; files are
    stored under server-generated names."""
    name = Path((filename or "document").replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()]", "_", name).strip()[:200]
    return name or "document"


def validate_upload(filename: str | None, data: bytes) -> str:
    """Checks the extension and the file's actual leading bytes. Returns the extension."""
    ext = Path(safe_display_name(filename)).suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise UploadRejected(415, f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_TYPES))}")
    if not data:
        raise UploadRejected(400, "The file is empty")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise UploadRejected(400, "The file is not a real PDF")
    if ext == ".docx" and not data.startswith(b"PK\x03\x04"):
        raise UploadRejected(400, "The file is not a real DOCX document")
    if ext in (".txt", ".md", ".markdown"):
        if b"\x00" in data:
            raise UploadRejected(400, "The file contains binary data")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise UploadRejected(400, "The file is not valid UTF-8 text")
    return ext