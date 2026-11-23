import re
from dataclasses import dataclass


@dataclass
class Page:
    text: str
    number: int | None  # PDF page number; None for formats without pages


@dataclass
class ChunkDraft:
    text: str
    page: int | None


def _split_long(paragraph: str, size: int) -> list[str]:
    """Split an over-long paragraph on sentence boundaries (hard-split as a last resort)."""
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
        while len(sentence) > size:  # a single enormous 'sentence'
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:size])
            sentence = sentence[size:]
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= size:
            current += " " + sentence
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Paragraph-aware chunking of roughly `size` characters, with a short overlap
    carried from the end of one chunk into the next so ideas are not cut in half."""
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    if not text:
        return []
    units: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend([paragraph] if len(paragraph) <= size else _split_long(paragraph, size))

    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + 2 + len(unit) <= size:
            current += "\n\n" + unit
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            if " " in tail:
                tail = tail[tail.index(" ") + 1 :]  # start on a word boundary
            current = f"{tail} {unit}".strip() if tail else unit
    if current:
        chunks.append(current)
    return chunks


def chunk_pages(pages: list[Page], size: int, overlap: int) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for page in pages:
        drafts.extend(ChunkDraft(text=t, page=page.number) for t in chunk_text(page.text, size, overlap))
    return drafts