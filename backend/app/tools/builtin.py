import asyncio
import re
import uuid

from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, select

from app.db import session as db_session
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.report import Report
from app.rag import service as rag_service
from app.services.constraint_manager import ConstraintManager
from app.tools.base import Tool, ToolArgs, ToolContext, ToolError, ToolResult
from app.tools.calc import CalcError, safe_eval
from app.tools.summarize import extractive_summary
from app.tools.web import get_web_provider


# ------------------------------------------------------------------ helpers
def _resolve_document(db, session_id: uuid.UUID, ident: str) -> Document:
    """A document of THIS session, by id or exact title."""
    doc = None
    try:
        candidate = db.get(Document, uuid.UUID(ident))
        if candidate is not None and candidate.session_id == session_id:
            doc = candidate
    except ValueError:
        matches = db.scalars(
            select(Document).where(
                Document.session_id == session_id,
                func.lower(Document.title) == ident.lower(),
                Document.status == DocumentStatus.READY,
            )
        ).all()
        if len(matches) > 1:
            raise ToolError("More than one document has that title; use its document id instead")
        doc = matches[0] if matches else None
    if doc is None or doc.status != DocumentStatus.READY:
        raise ToolError("Document not found in this session (or it is not ready)")
    return doc


def _check_not_excluded(ctx: ToolContext, doc: Document) -> None:
    _, rejected = ConstraintManager.filter_sources(ctx.views, [rag_service.doc_source(doc)])
    if rejected:
        raise ToolError(f"This source is excluded by a human constraint ('{rejected[0]['rejected_by']}')")


def _doc_source(doc: Document) -> dict:
    return {**rag_service.doc_source(doc), "document_id": str(doc.id), "origin": "document", "simulated": False}


def _document_text(db, doc: Document, limit_chars: int = 30000) -> str:
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc.id, DocumentChunk.flagged.is_(False))
        .order_by(DocumentChunk.chunk_index)
    ).all()
    return "\n\n".join(c.text for c in chunks)[:limit_chars]


# ------------------------------------------------------------------ search_web
class SearchWebArgs(ToolArgs):
    query: str = Field(min_length=2, max_length=200)
    max_results: int = Field(default=5, ge=1, le=8)


class SearchWebTool(Tool):
    name = "search_web"
    description = "Search the web for pages about a topic. Returns titles, publishers and snippets (links are never opened)."
    args_model = SearchWebArgs

    async def run(self, args: SearchWebArgs, ctx: ToolContext) -> ToolResult:
        try:
            provider = get_web_provider()
        except ValueError as exc:
            raise ToolError(f"Web search is not configured: {exc}")
        results = await provider.search(args.query, args.max_results)
        if not results:
            return ToolResult("No web results.", simulated=provider.simulated)
        lines = []
        for n, r in enumerate(results, start=1):
            where = f" {r['url']}" if r.get("url") else ""
            snippet = f"\n    {r['snippet']}" if r.get("snippet") else ""
            lines.append(f"[{n}] {r['title']} ({r['publisher']}){where}{snippet}")
        return ToolResult("\n".join(lines), sources=results, simulated=provider.simulated)


# ------------------------------------------------------------------ retrieve_documents
class RetrieveDocumentsArgs(ToolArgs):
    query: str = Field(min_length=2, max_length=300)
    k: int = Field(default=4, ge=1, le=8)


def _retrieve_sync(ctx: ToolContext, query: str, k: int):
    with db_session.SessionLocal() as db:
        return rag_service.retrieve_chunks(db, ctx.session_id, query, k, ctx.views)


class RetrieveDocumentsTool(Tool):
    name = "retrieve_documents"
    description = "Semantic search over the documents uploaded to this session. Returns the best matching passages with their document ids."
    args_model = RetrieveDocumentsArgs

    async def run(self, args: RetrieveDocumentsArgs, ctx: ToolContext) -> ToolResult:
        chunks = await asyncio.to_thread(_retrieve_sync, ctx, args.query, args.k)
        if not chunks:
            return ToolResult("No matching passages in the uploaded documents (excluded sources are never searched).")
        lines = []
        for n, c in enumerate(chunks, start=1):
            page = f", page {c.page}" if c.page else ""
            lines.append(f"[{n}] {c.title} ({c.source_name}{page}) document_id={c.document_id}\n{c.text[:700]}")
        return ToolResult(
            "\n\n".join(lines), sources=rag_service.document_sources(chunks),
            retrieved_chunks=len(chunks), data={"chunk_ids": [str(c.chunk_id) for c in chunks]},
        )


# ------------------------------------------------------------------ read_document
class ReadDocumentArgs(ToolArgs):
    document: str = Field(min_length=1, max_length=200, description="document id or exact title")
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=3, ge=1, le=10)


def _read_sync(ctx: ToolContext, ident: str, offset: int, limit: int) -> ToolResult:
    with db_session.SessionLocal() as db:
        doc = _resolve_document(db, ctx.session_id, ident)
        _check_not_excluded(ctx, doc)
        base = (DocumentChunk.document_id == doc.id, DocumentChunk.flagged.is_(False))
        total = db.scalar(select(func.count()).select_from(DocumentChunk).where(*base)) or 0
        chunks = db.scalars(
            select(DocumentChunk).where(*base).order_by(DocumentChunk.chunk_index).offset(offset).limit(limit)
        ).all()
        if not chunks:
            raise ToolError(f"No passages at offset {offset} (the document has {total} usable passages)")
        body = "\n\n".join(f"(passage {c.chunk_index + 1}{f', page {c.page}' if c.page else ''}) {c.text}" for c in chunks)
        return ToolResult(
            f"{doc.title} ({doc.source_name}), passages {offset + 1}-{offset + len(chunks)} of {total}:\n\n{body}",
            sources=[_doc_source(doc)], data={"document_id": str(doc.id), "total_chunks": total},
        )


class ReadDocumentTool(Tool):
    name = "read_document"
    description = "Read passages of one uploaded document, by document id or exact title."
    args_model = ReadDocumentArgs

    async def run(self, args: ReadDocumentArgs, ctx: ToolContext) -> ToolResult:
        return await asyncio.to_thread(_read_sync, ctx, args.document, args.offset, args.limit)


# ------------------------------------------------------------------ summarize_document
class SummarizeDocumentArgs(ToolArgs):
    document: str = Field(min_length=1, max_length=200, description="document id or exact title")
    max_sentences: int = Field(default=5, ge=1, le=10)


def _summarize_sync(ctx: ToolContext, ident: str, n: int) -> ToolResult:
    with db_session.SessionLocal() as db:
        doc = _resolve_document(db, ctx.session_id, ident)
        _check_not_excluded(ctx, doc)
        sentences = extractive_summary(_document_text(db, doc), n)
        if not sentences:
            raise ToolError("The document has no usable text")
        bullets = "\n".join(f"- {s}" for s in sentences)
        return ToolResult(
            f"Extractive summary of '{doc.title}' (selected sentences, not written by a language model):\n{bullets}",
            sources=[_doc_source(doc)],
        )


class SummarizeDocumentTool(Tool):
    name = "summarize_document"
    description = "Summarize one uploaded document by selecting its most informative sentences (extractive)."
    args_model = SummarizeDocumentArgs

    async def run(self, args: SummarizeDocumentArgs, ctx: ToolContext) -> ToolResult:
        return await asyncio.to_thread(_summarize_sync, ctx, args.document, args.max_sentences)


# ------------------------------------------------------------------ compare_sources
class CompareSourcesArgs(ToolArgs):
    topics: list[str] = Field(min_length=2, max_length=5)
    criteria: list[str] = Field(default=["overview"], min_length=1, max_length=6)

    @field_validator("topics", "criteria")
    @classmethod
    def items_are_short(cls, items: list[str]) -> list[str]:
        cleaned = [i.strip() for i in items]
        if any(not i or len(i) > 60 for i in cleaned):
            raise ValueError("every item must be 1-60 characters")
        return cleaned

    @model_validator(mode="after")
    def not_too_many_pairs(self):
        if len(self.topics) * len(self.criteria) > 12:
            raise ValueError("at most 12 topic/criterion pairs")
        return self



def _compare_sync(ctx: ToolContext, topics: list[str], criteria: list[str]) -> ToolResult:
    used: dict[uuid.UUID, rag_service.RetrievedChunk] = {}
    found = 0
    sections = []

    def criterion_matches(criterion: str, passage: str) -> bool:
        """Check whether the passage explicitly discusses the criterion."""
        stopwords = {
            "the", "and", "for", "with", "from",
            "that", "this", "about", "into", "their", "using",
        }

        terms = {
            word
            for word in re.findall(r"[a-z0-9]+", criterion.lower())
            if word not in stopwords
        }

        passage_terms = set(re.findall(r"[a-z0-9]+", passage.lower()))

        return bool(terms) and terms.issubset(passage_terms)

    with db_session.SessionLocal() as db:
        for topic in topics:
            lines = [f"### {topic}"]

            for criterion in criteria:
                hits = rag_service.retrieve_chunks(
                    db,
                    ctx.session_id,
                    f"{topic} {criterion}",
                    5,
                    ctx.views,
                )

                relevant_hit = next(
                    (
                        hit
                        for hit in hits
                        if criterion_matches(criterion, hit.text)
                    ),
                    None,
                )

                if relevant_hit is not None:
                    found += 1
                    used[relevant_hit.document_id] = relevant_hit

                    lines.append(
                        f"- {criterion}: {relevant_hit.text[:300]} "
                        f"[{relevant_hit.title}, {relevant_hit.source_name}]"
                    )
                else:
                    lines.append(
                        f"- {criterion}: no evidence in the uploaded documents"
                    )

            sections.append("\n".join(lines))

    return ToolResult(
        "\n\n".join(sections),
        sources=rag_service.document_sources(list(used.values())),
        retrieved_chunks=found,
        data={
            "evidence_found": found,
            "pairs": len(topics) * len(criteria),
        },
    )



class CompareSourcesTool(Tool):
    name = "compare_sources"
    description = "Compare topics against criteria using evidence from the uploaded documents. Reports the best passage per pair, or says there is no evidence."
    args_model = CompareSourcesArgs

    async def run(self, args: CompareSourcesArgs, ctx: ToolContext) -> ToolResult:
        return await asyncio.to_thread(_compare_sync, ctx, args.topics, args.criteria)


# ------------------------------------------------------------------ calculate
class CalculateArgs(ToolArgs):
    expression: str = Field(min_length=1, max_length=200)


class CalculateTool(Tool):
    name = "calculate"
    description = "Evaluate plain arithmetic (+ - * / // % **, parentheses, sqrt, abs, round, min, max, log, pi, e). No variables or code."
    args_model = CalculateArgs

    async def run(self, args: CalculateArgs, ctx: ToolContext) -> ToolResult:
        try:
            value = safe_eval(args.expression)
        except CalcError as exc:
            raise ToolError(str(exc))
        shown = format(value, ".10g") if isinstance(value, float) else str(value)
        return ToolResult(f"{args.expression} = {shown}", data={"value": value})


# ------------------------------------------------------------------ save_report
class SaveReportArgs(ToolArgs):
    title: str = Field(min_length=3, max_length=120)
    content: str = Field(min_length=10, max_length=20000)


def _save_report_sync(ctx: ToolContext, title: str, content: str) -> ToolResult:
    title = re.sub(r"[\x00-\x1f\x7f]", " ", title).strip()
    with db_session.SessionLocal() as db:
        count = db.scalar(select(func.count()).select_from(Report).where(Report.session_id == ctx.session_id)) or 0
        if count >= ctx.settings.max_reports_per_session:
            raise ToolError(f"A session can hold at most {ctx.settings.max_reports_per_session} saved reports")
        report = Report(session_id=ctx.session_id, title=title, content=content, origin="AGENT", status="DRAFT")
        db.add(report)
        db.commit()
        return ToolResult(
            f"Saved draft report '{title}' ({len(content)} characters).",
            data={"report_id": str(report.id), "title": title, "chars": len(content)},
        )


class SaveReportTool(Tool):
    name = "save_report"
    description = "Save a draft report (Markdown text) to this session. Drafts are visible to all collaborators; the number of saved reports is limited."
    args_model = SaveReportArgs
    side_effects = True

    async def run(self, args: SaveReportArgs, ctx: ToolContext) -> ToolResult:
        return await asyncio.to_thread(_save_report_sync, ctx, args.title, args.content)


BUILTIN_TOOLS: list[type[Tool]] = [
    SearchWebTool, RetrieveDocumentsTool, ReadDocumentTool, SummarizeDocumentTool,
    CompareSourcesTool, CalculateTool, SaveReportTool,
]