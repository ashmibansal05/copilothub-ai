"""The final research report.

FACTS are assembled by code straight from the database (objective, methodology, evidence,
human decisions, limitations, sources) so a language model cannot invent them. Only four
NARRATIVE sections (executive summary, findings, comparison, conclusion) are written by the
agent's brain, from the collected material, and are then checked against the constraints."""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.db import session as db_session
from app.models.agent import AgentAction, AgentState
from app.models.approval import Approval, ApprovalStatus
from app.models.conflict import Conflict
from app.models.constraint import Constraint
from app.models.document import Document, DocumentStatus
from app.models.intervention import Intervention, InterventionType
from app.models.memory import MemoryItem, MemoryKind
from app.models.report import Report
from app.models.session import AgentSession
from app.models.source import Source
from app.models.tool_execution import ToolExecution
from app.models.user import User
from app.services.conflict_manager import ConflictManager
from app.services.constraint_manager import ConstraintManager, ConstraintView, target_keys
from app.services.readers import describe_constraint

logger = logging.getLogger("copilothub.report")

SECTION_TITLES = [
    ("executive_summary", "Executive Summary"), ("objective", "Research Objective"),
    ("methodology", "Methodology"), ("findings", "Findings"), ("comparison", "Comparison"),
    ("evidence", "Evidence"), ("human_decisions", "Human Decisions"), ("limitations", "Limitations"),
    ("conclusion", "Conclusion"), ("sources", "Sources"),
]

LABELS = {
    "APPROVE": "approved", "REJECT": "rejected", "CORRECT": "corrected the agent", "PAUSE": "paused",
    "RESUME": "resumed", "MODIFY_TASK": "changed the task", "ADD_INFORMATION": "added information",
    "ADD_CONSTRAINT": "added a constraint", "REMOVE_CONSTRAINT": "removed a constraint",
    "REJECT_SOURCE": "rejected a source", "CHANGE_SOURCE": "changed a source",
    "REQUEST_REVIEW": "requested a review", "RESOLVE_CONFLICT": "resolved a conflict",
}

_generating: set[uuid.UUID] = set()


class ReportLimitError(Exception):
    """Too many final reports for this session."""


def is_generating(session_id: uuid.UUID) -> bool:
    return session_id in _generating


@dataclass
class ReportInputs:
    name: str
    task: str
    original_task: str
    engine: str | None
    plan: list[str]
    steps: list[dict]  # {step_index, step, output, sources, rejected_sources}
    tool_counts: dict[str, int]
    tool_problems: int
    simulated: bool
    documents: list[dict]
    flagged_chunks: int
    views: list[ConstraintView]
    constraint_log: list[str]
    interventions: list[str]
    approvals: list[str]
    conflicts: list[str]
    notes: list[str]
    sources_used: list[dict]
    sources_rejected: list[dict]
    draft_summary: str | None
    compare_outputs: list[str]
    open_conflicts: int
    failed_attempts: int
    steps_completed: int
    history: list[dict] = field(default_factory=list)  # shaped like the agent's observations


# ----------------------------------------------------------------------- collecting
def _dedupe(sources: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for s in sources:
        key = (s.get("title"), s.get("publisher"), s.get("document_id") or s.get("url"))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def collect_inputs(db: Session, session_id: uuid.UUID) -> ReportInputs:
    session = db.get(AgentSession, session_id)
    views = ConstraintManager.to_views(ConflictManager.effective_constraints(db, session_id))

    plan_row = db.scalar(select(AgentAction).where(
        AgentAction.session_id == session_id, AgentAction.action_type == "PLAN", AgentAction.success.is_(True)
    ).order_by(AgentAction.created_at.desc()).limit(1))
    plan = list((plan_row.output_data or {}).get("plan", [])) if plan_row else []

    steps_by_text: dict[str, dict] = {}
    for a in db.scalars(select(AgentAction).where(
        AgentAction.session_id == session_id, AgentAction.action_type == "TOOL_CALL"
    ).order_by(AgentAction.created_at)).all():
        out = a.output_data or {}
        steps_by_text[(a.input_data or {}).get("step", f"step {a.step_index}")] = {
            "step_index": a.step_index, "step": (a.input_data or {}).get("step", f"step {a.step_index}"),
            "output": out.get("output", ""), "sources": out.get("sources", []),
            "rejected_sources": out.get("rejected_sources", []),
        }
    steps = list(steps_by_text.values())

    # Re-apply TODAY's constraints to everything collected, exactly as the agent does.
    history, all_used, newly_rejected = [], [], []
    for s in steps:
        allowed, rejected = ConstraintManager.filter_sources(views, s["sources"])
        history.append({"step_index": s["step_index"], "step": s["step"], "finding": s["output"],
                        "success": True, "sources": allowed})
        all_used += allowed
        newly_rejected += rejected + s["rejected_sources"]
    rejected_rows = db.scalars(select(Source).where(Source.session_id == session_id, Source.status == "REJECTED")).all()
    rejected_all = _dedupe(newly_rejected + [
        {"title": r.title, "publisher": r.publisher, "rejected_by": r.rejected_by} for r in rejected_rows
    ])
    used = _dedupe(all_used)
    used_keys = {(s.get("title"), s.get("publisher")) for s in used}
    rejected_all = [r for r in rejected_all if (r.get("title"), r.get("publisher")) not in used_keys]

    tool_rows = db.execute(select(ToolExecution.tool_name, ToolExecution.status, ToolExecution.simulated).where(
        ToolExecution.session_id == session_id)).all()
    tool_counts: dict[str, int] = {}
    for name, _, _ in tool_rows:
        tool_counts[name] = tool_counts.get(name, 0) + 1
    simulated = any(sim for _, _, sim in tool_rows) or bool(db.scalar(
        select(func.count()).select_from(Source).where(Source.session_id == session_id, Source.origin == "SIMULATED")))
    compare_outputs = [o for (o,) in db.execute(select(ToolExecution.output_summary).where(
        ToolExecution.session_id == session_id, ToolExecution.tool_name == "compare_sources",
        ToolExecution.status == "SUCCESS").order_by(ToolExecution.created_at.desc()).limit(2)).all() if o]

    interventions, original_task = [], session.task
    for iv in db.scalars(select(Intervention).options(joinedload(Intervention.user)).where(
        Intervention.session_id == session_id, Intervention.type != InterventionType.COMMENT
    ).order_by(Intervention.created_at)).all():
        who = f"@{iv.user.username}" if iv.user else "someone"
        detail = iv.content or iv.target or ""
        interventions.append(f"{who} {LABELS.get(iv.type.value, iv.type.value.lower())}" + (f": {detail[:200]}" if detail else ""))
        if iv.type == InterventionType.MODIFY_TASK and original_task == session.task:
            original_task = (iv.details or {}).get("old_task", original_task)

    constraint_log = []
    for c in db.scalars(select(Constraint).options(joinedload(Constraint.creator)).where(
        Constraint.session_id == session_id).order_by(Constraint.created_at)).all():
        who = f"@{c.creator.username}" if c.creator else "someone"
        constraint_log.append(f"[{c.priority.value}] {describe_constraint(c.action.value, c.target)} ({who}, {c.status.value.lower()})")

    approvals = []
    for a in db.scalars(select(Approval).where(Approval.session_id == session_id, Approval.status != ApprovalStatus.PENDING)
                        .order_by(Approval.created_at)).all():
        who = db.get(User, a.decided_by) if a.decided_by else None
        what = "Final draft" if a.kind.value == "FINAL_REPORT" else "Review request"
        approvals.append(f"{what}: {a.status.value.lower()}" + (f" by @{who.username}" if who else "") + (f" ({a.note})" if a.note else ""))

    conflicts, open_conflicts = [], 0
    for c in db.scalars(select(Conflict).where(Conflict.session_id == session_id).order_by(Conflict.created_at)).all():
        read = ConflictManager.to_read(db, c)
        outcome = (read.resolution.value.lower().replace("_", " ") if read.resolution else "open")
        open_conflicts += int(read.resolution is None)
        conflicts.append(f"\"{read.constraint_a.description}\" vs \"{read.constraint_b.description}\": {outcome}")

    notes = [
        f"[{m.kind.value.lower()}{' by ' + m.author if m.author else ''}] {m.content}"
        for m in db.scalars(select(MemoryItem).where(
            MemoryItem.session_id == session_id, MemoryItem.is_active.is_(True),
            MemoryItem.kind.in_([MemoryKind.CORRECTION, MemoryKind.FACT, MemoryKind.DECISION])
        ).order_by(MemoryItem.created_at.desc()).limit(10)).all()
    ]
    docs = db.scalars(select(Document).where(Document.session_id == session_id, Document.status == DocumentStatus.READY)).all()
    finalize = db.scalar(select(AgentAction).where(AgentAction.session_id == session_id, AgentAction.action_type == "FINALIZE")
                         .order_by(AgentAction.created_at.desc()).limit(1))
    state = db.scalar(select(AgentState).where(AgentState.session_id == session_id))
    evaluated = db.scalar(select(func.count(func.distinct(AgentAction.step_index))).where(
        AgentAction.session_id == session_id, AgentAction.action_type == "EVALUATE", AgentAction.success.is_(True))) or 0

    return ReportInputs(
        name=session.name, task=session.task, original_task=original_task, engine=state.engine if state else None,
        plan=plan, steps=steps, tool_counts=tool_counts,
        tool_problems=sum(1 for _, status, _ in tool_rows if status != "SUCCESS"), simulated=simulated,
        documents=[{"title": d.title, "source_name": d.source_name, "source_type": d.source_type, "chunks": d.chunk_count} for d in docs],
        flagged_chunks=sum(d.flagged_chunks for d in docs), views=views, constraint_log=constraint_log,
        interventions=interventions, approvals=approvals, conflicts=conflicts, notes=notes,
        sources_used=used, sources_rejected=rejected_all,
        draft_summary=(finalize.output_data or {}).get("summary") if finalize else None,
        compare_outputs=compare_outputs, open_conflicts=open_conflicts, failed_attempts=db.scalar(
            select(func.count()).select_from(AgentAction).where(AgentAction.session_id == session_id, AgentAction.success.is_(False))) or 0,
        steps_completed=evaluated, history=history,
    )


# ----------------------------------------------------------------------- assembling
def _bullets(lines: list[str], empty: str = "None.") -> str:
    return "\n".join(f"- {line}" for line in lines) if lines else empty


def _source_line(s: dict) -> str:
    extras = [s.get("source_type"), "uploaded document" if s.get("origin") == "document" else None,
              "simulated" if s.get("simulated") else None,
              f"relevance {s['score']}" if s.get("score") is not None else None,
              f"page {s['page']}" if s.get("page") else None, s.get("url")]
    detail = ", ".join(str(e) for e in extras if e)
    return f"{s.get('title', 'Untitled')} — {s.get('publisher', 'unknown')}" + (f" ({detail})" if detail else "")


def _narrative(narrative: dict, key: str) -> str:
    return str(narrative.get(key) or "").strip()[:2500]


def compliance_warnings(views: list[ConstraintView], narrative: dict[str, str]) -> list[str]:
    """If the written text mentions a source a human excluded, say so in the report."""
    text = " ".join(narrative.values()).lower()
    warnings = []
    for v in views:
        if v.action != "EXCLUDE_SOURCE":
            continue
        if any(re.search(rf"\b{re.escape(k)}\b", text) for k in target_keys(v.target)):
            warnings.append(f"The narrative text mentions \"{v.target}\", which a human excluded as a source. Please review it before relying on it.")
    return warnings


def assemble_sections(inputs: ReportInputs, narrative: dict[str, str], warnings: list[str]) -> list[dict]:
    i = inputs
    summary = _narrative(narrative, "executive_summary") or i.draft_summary or "No summary is available."

    objective = [f"Task: {i.task}", f"Session: {i.name}"]
    if i.original_task != i.task:
        objective.append(f"The task was changed during the run. Original task: {i.original_task}")

    tools = (", ".join(f"{name} ×{n}" for name, n in sorted(i.tool_counts.items()))
             if i.tool_counts else "none (single-step reasoning without the tool loop)")
    methodology = [
        f"Engine: {i.engine or 'unknown'}",
        f"Plan ({len(i.plan)} steps): " + "; ".join(f"{n}. {s}" for n, s in enumerate(i.plan, 1)) if i.plan else "Plan: not recorded",
        f"Tools used: {tools}" + (f" ({i.tool_problems} call(s) failed or were rejected)" if i.tool_problems else ""),
        ("Uploaded documents: " + "; ".join(f"{d['title']} ({d['source_name']}, {d['source_type']})" for d in i.documents))
        if i.documents else "No documents were uploaded.",
        f"Human constraints recorded: {len(i.constraint_log)}",
    ]
    methodology.append(f"Unique sources included in this report: {len(i.sources_used)}. Analytics counts source-use records across steps, so its count may be higher.")
    if i.simulated:
        methodology.append("NOTE: some results come from the built-in SIMULATED demo provider. They are placeholders, not real findings.")

    findings = _narrative(narrative, "findings")
    if i.simulated and findings:
        findings = "*Demo evidence only; factual claims require independent verification.*\n\n" + findings
    step_notes = _bullets([f"{s['step']}: {s['output'][:300]}" for s in i.steps], "No step notes.")
    comparison = _narrative(narrative, "comparison") or "Not available."
    if i.compare_outputs:
        comparison += "\n\nEvidence matrix from the uploaded documents:\n" + i.compare_outputs[0][:1500]

    evidence = _bullets([_source_line(s) for s in i.sources_used], "No sources were used.")
    approved = [f"{c}" for c in i.constraint_log if "explicitly allowed" in c]
    if approved:
        evidence += "\n\nSources a human explicitly approved:\n" + _bullets(approved)

    decisions = "\n\n".join([
        "Interventions:\n" + _bullets(i.interventions, "No human interventions."),
        "Approvals:\n" + _bullets(i.approvals, "No approvals were requested."),
        "Conflicts between instructions:\n" + _bullets(i.conflicts, "None."),
        "Constraints (history):\n" + _bullets(i.constraint_log, "None."),
        "Corrections and facts remembered:\n" + _bullets(i.notes, "None."),
    ])

    limitations = [f"Narrative sections were written by: {i.engine or 'unknown'}. Verify claims against the evidence."]
    if i.simulated:
        limitations.append("Part of the evidence is simulated demo data.")
    if i.engine and i.engine != "demo" and not any(s.get("origin") in ("document", "web") for s in i.sources_used):
        limitations.append("No uploaded documents or real web results supported these findings. The model may rely on general knowledge or simulated search placeholders; verify independently.")
    limitations.append("Agent confidence is self-assessed by the model (or simulated in demo mode), not a measured accuracy.")
    limitations.append("Narrative claims, numbers and citations have not been independently fact-checked. Verify them against real primary evidence before use.")
    if i.sources_rejected:
        limitations.append(f"{len(i.sources_rejected)} source(s) were rejected by human constraints and are not used.")
    if i.tool_problems or i.failed_attempts:
        limitations.append(f"{i.tool_problems} tool call(s) failed or were rejected; {i.failed_attempts} model/tool attempt(s) failed.")
    if i.plan:
        completed_step_texts = {s["step"] for s in i.steps}
        missing = [p for p in i.plan if p not in completed_step_texts]
        if missing:
            limitations.append("INCOMPLETE revised plan; steps not executed: " + "; ".join(missing))
    if i.open_conflicts:
        limitations.append(f"{i.open_conflicts} conflict(s) between human instructions were still open.")
    if i.flagged_chunks:
        limitations.append(f"{i.flagged_chunks} document passage(s) looked like injected instructions and were excluded.")
    limitations += warnings

    sources = ("Sources used:\n" + ("\n".join(f"[{n}] {_source_line(s)}" for n, s in enumerate(i.sources_used, 1)) or "None.")
               + "\n\nSources rejected (not used):\n"
               + _bullets([f"{s.get('title', '')} — {s.get('publisher', '')}" + (f": rejected by constraint \"{s['rejected_by']}\"" if s.get("rejected_by") else "")
                           for s in i.sources_rejected], "None."))

    bodies = {
        "executive_summary": summary, "objective": "\n".join(objective), "methodology": _bullets(methodology),
        "findings": (findings + "\n\n" if findings else "") + "Step notes:\n" + step_notes,
        "comparison": comparison, "evidence": evidence, "human_decisions": decisions,
        "limitations": _bullets(limitations), "conclusion": _narrative(narrative, "conclusion") or "Not available.",
        "sources": sources,
    }
    return [{"key": k, "title": t, "body": bodies[k]} for k, t in SECTION_TITLES]


def render_markdown(title: str, sections: list[dict], engine: str | None) -> str:
    parts = [f"# {title}", f"*Generated by CoPilotHub AI" + (f" (engine: {engine})" if engine else "") + "*"]
    for n, s in enumerate(sections, 1):
        parts.append(f"## {n}. {s['title']}\n\n{s['body']}")
    return "\n\n".join(parts) + "\n"


# ----------------------------------------------------------------------- generating
def _store(session_id: uuid.UUID, inputs: ReportInputs, narrative: dict,
           warnings: list[str], approved_final: bool = False) -> dict:
    sections = assemble_sections(inputs, narrative, warnings + compliance_warnings(inputs.views, narrative))
    # Snapshot full code content into this report at creation time.
    with db_session.SessionLocal() as code_db:
        from app.services.code_service import source_section
        code_section = source_section(code_db, session_id)
    if code_section:
        sections.append(code_section)
    kind = "FINAL" if approved_final else "DRAFT"
    title = (f"Research report: {inputs.name}" if approved_final
             else f"Research snapshot: {inputs.name}")[:200]
    with db_session.SessionLocal() as db:
        report = Report(
            session_id=session_id, title=title, content=render_markdown(title, sections, inputs.engine),
            format="markdown", origin="SYSTEM", status=kind, kind=kind,
            engine=inputs.engine, sections=sections,
        )
        db.add(report)
        db.commit()
        return {"report_id": str(report.id), "title": title, "chars": len(report.content), "kind": kind}


def _collect_sync(session_id: uuid.UUID) -> ReportInputs:
    with db_session.SessionLocal() as db:
        existing = db.scalar(select(func.count()).select_from(Report).where(Report.session_id == session_id, Report.kind == "FINAL")) or 0
        if existing >= get_settings().max_final_reports_per_session:
            raise ReportLimitError(f"A session can hold at most {get_settings().max_final_reports_per_session} final reports")
        return collect_inputs(db, session_id)


async def generate_report(session_id: uuid.UUID, brain: Any, approved_final: bool = False) -> dict:
    """Collect facts, ask the brain for the narrative, assemble, store. Returns a small summary."""
    _generating.add(session_id)
    try:
        inputs = await asyncio.to_thread(_collect_sync, session_id)
        warnings: list[str] = []
        narrative: dict[str, str] = {}
        try:
            narrative = await asyncio.wait_for(
                brain.write_report(inputs.task, inputs.history, ConstraintManager.prompt_lines(inputs.views), inputs.notes),
                timeout=get_settings().agent_step_timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Narrative generation failed: %s", exc, exc_info=True)
            warnings.append(f"The narrative could not be generated ({exc.__class__.__name__}); the facts below were assembled from the collected data only.")
        return await asyncio.to_thread(_store, session_id, inputs, narrative, warnings, approved_final)
    finally:
        _generating.discard(session_id)