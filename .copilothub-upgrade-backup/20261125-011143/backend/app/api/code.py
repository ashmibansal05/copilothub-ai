"""Shared session code artifacts and background model generation."""
import asyncio
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import SessionContext, get_session_context, require_session_role
from app.db.session import get_db
from app.db import session as db_session
from app.models.report import Report
from app.models.approval import Approval, ApprovalKind, ApprovalStatus
from datetime import datetime, timezone
from app.models.agent import AgentState
from app.models.session import AgentSession, AgentStatus
from app.services.report_service import render_markdown
from app.models.user import UserRole
from app.services import code_service, event_service
from app.services.coding_agent import classify_task, generate_files
from app.agents.runner import agent_runner
from app.websocket.events import EventType

router = APIRouter(prefix="/sessions", tags=["source code"])
log = logging.getLogger("copilothub.code")
CanEdit = Depends(require_session_role(UserRole.OWNER, UserRole.EDITOR))
OwnerOnly = Depends(require_session_role(UserRole.OWNER))
_jobs = {}
_gates: dict[uuid.UUID, asyncio.Event] = {}

class FileUpdate(BaseModel):
    content: str = Field(max_length=262144)
    expected_version: int = Field(ge=0)

class CodeRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)

def _latest_review(db: Session, sid: uuid.UUID) -> Approval | None:
    rows = db.scalars(select(Approval).where(
        Approval.session_id == sid, Approval.kind == ApprovalKind.REVIEW
    ).order_by(Approval.created_at.desc(), Approval.id.desc())).all()
    return next((row for row in rows if (row.payload or {}).get("review_type") == "CODE"), None)


def _expire_reviews(db: Session, sid: uuid.UUID):
    reviews = db.scalars(select(Approval).where(
        Approval.session_id == sid, Approval.kind == ApprovalKind.REVIEW,
        Approval.status == ApprovalStatus.PENDING
    )).all()
    for row in reviews:
        if (row.payload or {}).get("review_type") == "CODE":
            row.status = ApprovalStatus.EXPIRED
    db.flush()


def _request_code_review(db: Session, sid: uuid.UUID):
    """New immutable review request bound to exact file versions."""
    versions = {item["path"]: item["version"] for item in code_service.list_artifacts(db, sid)}
    if not versions:
        raise code_service.CodeError("No generated files to review")
    _expire_reviews(db, sid)
    approval = Approval(session_id=sid, kind=ApprovalKind.REVIEW,
                        status=ApprovalStatus.PENDING,
                        payload={"review_type": "CODE", "versions": versions})
    db.add(approval)
    session = db.get(AgentSession, sid)
    if session and session.status != AgentStatus.CANCELLED:
        session.status = AgentStatus.WAITING_FOR_APPROVAL
        session.ended_at = None
    db.commit()
    db.refresh(approval)
    return approval


def _review_data(db: Session, sid: uuid.UUID) -> dict:
    approval = _latest_review(db, sid)
    if approval is None:
        return {"status": "NONE", "approval_id": None, "versions": {}, "note": None}
    return {"status": approval.status.value, "approval_id": str(approval.id),
            "versions": (approval.payload or {}).get("versions", {}), "note": approval.note}


class ReviewDecision(BaseModel):
    approve: bool
    feedback: str = Field(default="", max_length=2000)


@router.get("/{session_id}/code-review")
def get_code_review(ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)):
    return _review_data(db, ctx.session.id)


@router.post("/{session_id}/code-review/request")
async def request_code_review(ctx: SessionContext = CanEdit, db: Session = Depends(get_db)):
    if ctx.session.status in (AgentStatus.CANCELLED, AgentStatus.RUNNING, AgentStatus.PLANNING):
        raise HTTPException(409, "Review can be requested after code generation finishes")
    approval = _request_code_review(db, ctx.session.id)
    await event_service.publish(db, ctx.session.id, EventType.STATUS_CHANGED,
                                {"previous_status": "PAUSED", "status": "WAITING_FOR_APPROVAL"}, ctx.user)
    await event_service.publish(db, ctx.session.id, EventType.AGENT_MESSAGE,
        {"kind": "system", "text": "Updated source files are awaiting owner approval."}, ctx.user)
    return _review_data(db, ctx.session.id)


@router.post("/{session_id}/code-review/decision")
async def decide_code_review(body: ReviewDecision, ctx: SessionContext = OwnerOnly,
                             db: Session = Depends(get_db)):
    sid = ctx.session.id
    approval = db.scalar(select(Approval).where(
        Approval.session_id == sid, Approval.kind == ApprovalKind.REVIEW,
        Approval.status == ApprovalStatus.PENDING).order_by(Approval.created_at.desc()).with_for_update())
    if approval is None or (approval.payload or {}).get("review_type") != "CODE":
        raise HTTPException(409, "No pending code review")
    if ctx.session.status != AgentStatus.WAITING_FOR_APPROVAL:
        raise HTTPException(409, "Session is not waiting for code approval")
    current = {item["path"]: item["version"] for item in code_service.list_artifacts(db, sid)}
    if current != (approval.payload or {}).get("versions", {}):
        approval.status = ApprovalStatus.EXPIRED
        db.commit()
        raise HTTPException(409, "Code changed since review was requested; request a new review")
    if not body.approve and len(body.feedback.strip()) < 3:
        raise HTTPException(422, "Please explain the required changes")
    approval.status = ApprovalStatus.APPROVED if body.approve else ApprovalStatus.REJECTED
    approval.decided_by = ctx.user.id
    approval.decided_at = datetime.now(timezone.utc)
    approval.note = body.feedback.strip() or None
    previous = ctx.session.status.value
    if body.approve:
        # Only an approved, immutable version of these files enters the FINAL report.
        existing = db.scalar(select(Report).where(Report.session_id == sid, Report.kind == "FINAL")
                             .order_by(Report.created_at.desc()).limit(1))
        engine = (existing.engine if existing else None) or "ollama"
        report = _draft_code_report(db, sid, ctx.session.task, engine)
        if report is None:
            raise HTTPException(409, "No code files available")
        row = db.get(Report, uuid.UUID(report["report_id"]))
        row.kind = "FINAL"
        row.status = "FINAL"
        ctx.session.status = AgentStatus.COMPLETED
        ctx.session.ended_at = datetime.now(timezone.utc)
    else:
        # Run a bounded revision in the same shared workspace, using reviewer feedback.
        if sid in _jobs and not _jobs[sid].done():
            raise HTTPException(409, "Code generation is already in progress")
        ctx.session.status = AgentStatus.RUNNING
        ctx.session.ended_at = None
    db.commit()
    await event_service.publish(db, sid, EventType.APPROVAL_COMPLETED,
        {"approval_id": str(approval.id), "approved": body.approve, "kind": "CODE", "note": approval.note}, ctx.user)
    await event_service.publish(db, sid, EventType.STATUS_CHANGED,
        {"previous_status": previous, "status": ctx.session.status.value}, ctx.user)
    if body.approve:
        _set_code_state(db, sid, step="Approved project completed (runtime not tested)", progress=100, finished=True)
        await event_service.publish(db, sid, EventType.REPORT_SAVED,
            {"report": {"report_id": str(row.id), "kind": "FINAL", "title": row.title}}, ctx.user)
        await event_service.publish(db, sid, EventType.COMPLETED,
            {"summary": "Approved source versions finalized with a project report."}, ctx.user)
    else:
        _set_code_state(db, sid, step="Revising source code from reviewer feedback", progress=5)
        await event_service.publish(db, sid, EventType.AGENT_MESSAGE,
            {"kind": "system", "text": "Changes requested; AI is revising source files: " + body.feedback.strip()}, ctx.user)
        _jobs[sid] = asyncio.create_task(_background(sid, ctx.session.task, body.feedback.strip()))
    return _review_data(db, sid)


@router.get("/{session_id}/code")
def list_code(ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)):
    return {"task_type":classify_task(ctx.session.task), "review":_review_data(db, ctx.session.id), "files":code_service.list_artifacts(db, ctx.session.id),
            "generating":bool(_jobs.get(ctx.session.id) and not _jobs[ctx.session.id].done())}

@router.get("/{session_id}/code/{artifact_id}")
def get_code(artifact_id: uuid.UUID, version: int | None = Query(None, ge=1),
             ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)):
    obj = code_service.get_file(db, ctx.session.id, artifact_id, version)
    if obj is None: raise HTTPException(404, "Source file not found")
    return obj

@router.get("/{session_id}/code/{artifact_id}/versions")
def code_versions(artifact_id: uuid.UUID, ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)):
    return code_service.versions(db, ctx.session.id, artifact_id)

@router.put("/{session_id}/code/{artifact_id}")
async def update_code(artifact_id: uuid.UUID, body: FileUpdate, ctx: SessionContext = CanEdit,
                      db: Session = Depends(get_db)):
    if ctx.session.id in _jobs and not _jobs[ctx.session.id].done():
        raise HTTPException(409, "Code generation is still active")
    art = code_service.get_file(db, ctx.session.id, artifact_id)
    if art is None: raise HTTPException(404, "Source file not found")
    try:
        result = code_service.save_file(db, ctx.session.id, art["path"], body.content,
                                        ctx.user.id, expected_version=body.expected_version, origin="HUMAN")
    except code_service.CodeError as exc:
        raise HTTPException(409 if "conflict" in str(exc) else 422, str(exc)) from exc
    _expire_reviews(db, ctx.session.id)
    if ctx.session.status == AgentStatus.COMPLETED:
        ctx.session.status = AgentStatus.PAUSED
        ctx.session.ended_at = None
    db.commit()
    await event_service.publish(db, ctx.session.id, EventType.CODE_UPDATED,
                                {"id":result["id"], "path":result["path"], "version":result["version"]}, ctx.user)
    return result

@router.get("/{session_id}/code/{artifact_id}/download")
def download_code(artifact_id: uuid.UUID, ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)):
    obj = code_service.get_file(db, ctx.session.id, artifact_id)
    if obj is None: raise HTTPException(404, "Source file not found")
    return Response(obj["content"].encode("utf-8"), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition":f'attachment; filename="{obj["path"].split("/")[-1]}"',
                             "X-Content-Type-Options":"nosniff"})

@router.get("/{session_id}/code-export")
def download_zip(complete: bool = False, ctx: SessionContext = Depends(get_session_context),
                 db: Session = Depends(get_db)):
    report = None
    if complete:
        report = db.scalar(select(Report).where(Report.session_id == ctx.session.id,
             Report.kind == "FINAL").order_by(Report.created_at.desc()).limit(1))
        if report is None:
            raise HTTPException(409, "Approve source code before downloading the complete project package")
    try: data = code_service.build_zip(db, ctx.session.id, ctx.session.name, report)
    except code_service.CodeError as exc: raise HTTPException(409, str(exc)) from exc
    filename = "complete-project.zip" if complete else "source-code.zip"
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition":f'attachment; filename="{filename}"', "X-Content-Type-Options":"nosniff"})

def _set_code_state(db: Session, sid: uuid.UUID, *, engine: str | None = None,
                    step: str, progress: int, finished: bool = False):
    row = db.scalar(select(AgentState).where(AgentState.session_id == sid))
    if row is None:
        row = AgentState(session_id=sid)
        db.add(row)
    if engine:
        row.engine = engine
    row.current_step = step
    row.progress = progress
    row.total_steps = 1
    row.step_index = 1 if finished else 0
    row.plan = ["Generate complete source files and documentation"]
    db.commit()


def _draft_code_report(db: Session, sid: uuid.UUID, task: str, engine: str):
    """A coding report is a DRAFT; it has not passed human approval."""
    from app.services.code_service import source_section
    code_section = source_section(db, sid)
    if code_section is None:
        return None
    session = db.get(AgentSession, sid)
    sections = [
        {"key":"summary", "title":"Executive Summary",
         "body":"This project contains generated source files. Review and validate them before submission."},
        {"key":"objective", "title":"Project Objective", "body":task},
        {"key":"implementation", "title":"Implementation and Project Files",
         "body":"Source files, language labels, versions, and static validation results follow. "
                "See the Source Code tab to revise or download them."},
        {"key":"limitations", "title":"Validation and Limitations",
         "body":"Generated files have not been executed or compiled unless explicitly indicated. "
                "Review security, runtime behavior, and correctness before submitting."},
        code_section,
    ]
    title = (f"Project report: {session.name}" if session else "Project report")[:200]
    report = Report(session_id=sid, title=title, format="markdown", origin="SYSTEM",
                    status="DRAFT", kind="DRAFT", engine=engine, sections=sections,
                    content=render_markdown(title, sections, engine))
    db.add(report)
    db.commit()
    return {"report_id":str(report.id), "title":title, "kind":"DRAFT"}


async def _background(sid: uuid.UUID, task: str, instruction: str, automatic: bool = False,
                      hybrid: bool = False):
    try:
        brain, notice = await agent_runner.brain_factory()
        provider = getattr(brain, "provider", None)
        if provider is None:
            raise code_service.CodeError(notice or "Coding requires an available real LLM (demo mode disabled)")
        engine = getattr(brain, "engine", "ollama")
        if not hybrid:
            with db_session.SessionLocal() as db:
                _set_code_state(db, sid, engine=engine, step="Generating source code", progress=5)
                await event_service.publish(db, sid, EventType.AGENT_MESSAGE,
                    {"kind":"system", "text":"Coding task detected automatically. Generating full project source files."})
        with db_session.SessionLocal() as db:
            previous = code_service.snapshot(db, sid)
        async def announce(stage: str, index: int, total: int, path: str):
            if automatic and not hybrid:
                await _gates[sid].wait()
            label = ("Planning source files" if stage == "planning" else
                     f"Generating {path} ({index}/{total})")
            progress = 5 if stage == "planning" else 10 + int(75 * (index - 1) / max(total, 1))
            with db_session.SessionLocal() as db:
                if not hybrid:
                    _set_code_state(db, sid, engine=engine, step=label, progress=progress)
                await event_service.publish(db, sid, EventType.STEP_STARTED,
                    {"step":label, "step_index":index, "progress":progress, "engine":engine, "total_steps":total or 1})

        async def save_one(path: str, content: str, index: int, total: int):
            if automatic and not hybrid:
                await _gates[sid].wait()
            with db_session.SessionLocal() as db:
                session = db.get(AgentSession, sid)
                if automatic and session and session.status == AgentStatus.CANCELLED:
                    raise asyncio.CancelledError()
                result = code_service.save_file(db, sid, path, content, origin="AI")
                progress = 10 + int(80 * index / max(total, 1))
                if not hybrid:
                    _set_code_state(db, sid, engine=engine,
                        step=f"Saved {path} ({index}/{total})", progress=progress)
                await event_service.publish(db, sid, EventType.CODE_UPDATED,
                    {"id":result["id"], "path":path, "version":result["version"]})
                await event_service.publish(db, sid, EventType.STEP_COMPLETED,
                    {"completed_steps":index, "total_steps":total,
                     "progress":progress, "file":path})
                log.info("Generated code file %s (%d/%d) for session %s", path, index, total, sid)

        output = await generate_files(provider, task, previous, instruction,
                                      on_progress=announce, on_file=save_one)
        if not output:
            raise code_service.CodeError("No source files generated")
        if automatic and not hybrid:
            await _gates[sid].wait()
        with db_session.SessionLocal() as db:
            session = db.get(AgentSession, sid)
            if session and session.status != AgentStatus.CANCELLED and not hybrid:
                previous_status = session.status.value
                _set_code_state(db, sid, step="Awaiting human code review", progress=95)
                approval = _request_code_review(db, sid)
                await event_service.publish(db, sid, EventType.STATUS_CHANGED,
                    {"status": "WAITING_FOR_APPROVAL", "previous_status": previous_status})
                await event_service.publish(db, sid, EventType.APPROVAL_REQUESTED,
                    {"approval_id": str(approval.id), "kind": "CODE", "files": len(output)})
                await event_service.publish(db, sid, EventType.AGENT_MESSAGE,
                    {"kind": "system", "text": "Source files are saved. Owner approval is required before the final report."})
            await event_service.publish(db, sid, EventType.AGENT_MESSAGE,
                {"kind":"agent", "text":f"Generated {len(output)} code file(s). Validate before use; code was not executed."})
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.exception("Code generation failed")
        with db_session.SessionLocal() as db:
            session = db.get(AgentSession, sid)
            if not hybrid and session and session.status not in (AgentStatus.CANCELLED, AgentStatus.COMPLETED):
                previous_status = session.status.value
                session.status = AgentStatus.FAILED
                from datetime import datetime, timezone
                session.ended_at = datetime.now(timezone.utc)
                db.commit()
                _set_code_state(db, sid, step="Code generation failed", progress=0)
                await event_service.publish(db, sid, EventType.STATUS_CHANGED,
                    {"status":"FAILED", "previous_status":previous_status})
                await event_service.publish(db, sid, EventType.FAILED,
                    {"error":f"Code generation failed: {str(exc)[:250]}"})
            await event_service.publish(db, sid, EventType.AGENT_MESSAGE,
                {"kind":"warning", "text":f"Code generation incomplete: {type(exc).__name__}: {str(exc)[:180]}"})
    finally:
        _jobs.pop(sid, None)
        _gates.pop(sid, None)


def start_automatic_code(sid: uuid.UUID, task: str, *, hybrid: bool = False):
    """Start exactly one generation job for a new CODING/HYBRID session."""
    job = _jobs.get(sid)
    if job is not None and not job.done():
        return False
    _gates[sid] = asyncio.Event()
    _gates[sid].set()
    _jobs[sid] = asyncio.create_task(_background(sid, task, "", automatic=True, hybrid=hybrid),
                                     name=f"code-{sid}")
    return True


def cancel_automatic_code(sid: uuid.UUID):
    job = _jobs.get(sid)
    if job and not job.done():
        job.cancel()

@router.post("/{session_id}/code/generate", status_code=202)
async def generate_code(body: CodeRequest, ctx: SessionContext = CanEdit):
    sid = ctx.session.id
    if sid in _jobs and not _jobs[sid].done(): raise HTTPException(409, "Code generation already running")
    if agent_runner.is_active(sid): raise HTTPException(409, "Wait for the active research agent to finish before generating code")
    if ctx.session.status == AgentStatus.CANCELLED:
        raise HTTPException(409, "Cancelled sessions cannot generate code")
    if ctx.session.status == AgentStatus.WAITING_FOR_APPROVAL:
        raise HTTPException(409, "Please approve or request changes before regenerating")
    if ctx.session.status in (AgentStatus.PAUSED, AgentStatus.COMPLETED):
        ctx.session.status = AgentStatus.RUNNING
        db_state = db_session.SessionLocal()
        try:
            row = db_state.get(AgentSession, sid)
            row.status = AgentStatus.RUNNING
            row.ended_at = None
            db_state.commit()
        finally:
            db_state.close()
    _jobs[sid] = asyncio.create_task(_background(sid, ctx.session.task, body.instruction))
    return {"message":"Code generation started", "task_type":classify_task(ctx.session.task)}


def pause_automatic_code(sid: uuid.UUID):
    gate = _gates.get(sid)
    if gate:
        gate.clear()


def resume_automatic_code(sid: uuid.UUID):
    gate = _gates.get(sid)
    if gate:
        gate.set()
