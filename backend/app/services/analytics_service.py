"""Metrics, all computed from stored data. Nothing here is estimated or invented."""

import logging
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import session as db_session
from app.ml.collector import label_snapshots
from app.ml.features import CORRECTIVE_TYPES, aware
from app.models.agent import AgentAction, AgentState
from app.models.code_artifact import CodeArtifact, CodeArtifactVersion
from app.models.approval import ApprovalKind
from app.models.analytics_record import AnalyticsRecord
from app.models.approval import Approval
from app.models.conflict import Conflict
from app.models.document import Document
from app.models.intervention import Intervention, InterventionType
from app.models.risk_prediction import RiskPrediction
from app.models.session import AgentSession, AgentStatus, SessionMember
from app.models.source import Source
from app.models.tool_execution import ToolExecution
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsOverview, ConfidencePoint, HistogramBucket, Research, ResearchGroup, RiskPoint,
    RiskSummary, SessionAnalytics, SessionRow, ToolStat, ProjectMetrics,
)

logger = logging.getLogger("copilothub.analytics")
FINISHED = {AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED}


def _ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def compute(db: Session, session: AgentSession) -> tuple[SessionAnalytics, list[tuple[float, int]]]:
    """Metrics for one session, plus (predicted probability, actual outcome) pairs."""
    sid = session.id
    now = datetime.now(timezone.utc)
    duration = None
    if session.started_at:
        duration = ((aware(session.ended_at) if session.ended_at else now) - aware(session.started_at)).total_seconds()

    evaluations = db.scalars(select(AgentAction).where(
        AgentAction.session_id == sid, AgentAction.action_type == "EVALUATE", AgentAction.success.is_(True)
    ).order_by(AgentAction.created_at)).all()
    latest: dict[int, float] = {}
    for e in evaluations:
        value = (e.output_data or {}).get("confidence")
        if isinstance(value, (int, float)):
            latest[e.step_index] = float(value)
    series = [ConfidencePoint(step_index=k, confidence=v) for k, v in sorted(latest.items())]
    plan_row = db.scalar(select(AgentAction).where(
        AgentAction.session_id == sid, AgentAction.action_type == "PLAN", AgentAction.success.is_(True)
    ).order_by(AgentAction.created_at.desc()).limit(1))
    failed_attempts = db.scalar(select(func.count()).select_from(AgentAction).where(
        AgentAction.session_id == sid, AgentAction.success.is_(False))) or 0

    by_type = Counter()
    by_user = Counter()
    corrective_values = {t.value for t in CORRECTIVE_TYPES}
    corrective = 0
    for iv_type, username in db.execute(
        select(Intervention.type, User.username).join(User, User.id == Intervention.user_id, isouter=True)
        .where(Intervention.session_id == sid)
    ).all():
        by_type[iv_type.value] += 1
        if iv_type != InterventionType.COMMENT:
            by_user[username or "unknown"] += 1
        corrective += int(iv_type.value in corrective_values)
    comments = by_type.get("COMMENT", 0)

    tool_rows = db.execute(select(ToolExecution.tool_name, ToolExecution.status).where(ToolExecution.session_id == sid)).all()
    per_tool: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for name, status in tool_rows:
        per_tool[name][0] += 1
        per_tool[name][1] += int(status != "SUCCESS")
    tool_calls = len(tool_rows)
    tool_failures = sum(v[1] for v in per_tool.values())

    approvals = Counter(s.value for (s,) in db.execute(select(Approval.status).where(Approval.session_id == sid)).all())
    conflicts = db.execute(select(Conflict.status).where(Conflict.session_id == sid)).all()
    conflicts_open = sum(1 for (s,) in conflicts if s.value == "OPEN")

    source_rows = db.execute(select(Source.status, Source.origin).where(Source.session_id == sid)).all()
    used = sum(1 for s, _ in source_rows if s == "USED")
    rejected = sum(1 for s, _ in source_rows if s == "REJECTED")
    origins = Counter(o for s, o in source_rows if s == "USED")

    predictions = db.scalars(select(RiskPrediction).where(RiskPrediction.session_id == sid).order_by(RiskPrediction.created_at)).all()
    outcomes = {s.at: s.label for s in label_snapshots(db, session)} if predictions else {}
    pairs = [(p.probability, outcomes[aware(p.snapshot_at)]) for p in predictions if aware(p.snapshot_at) in outcomes]
    probs = [p.probability for p in predictions]
    risk = RiskSummary(
        data_source=predictions[-1].data_source if predictions else None, n=len(predictions),
        mean=_mean(probs), max=max(probs) if probs else None, last=probs[-1] if probs else None,
        history=[RiskPoint(step_index=p.step_index, probability=p.probability, level=p.level) for p in predictions],
        observed_n=len(pairs),
        mean_when_intervened=_mean([p for p, label in pairs if label == 1]),
        mean_when_not=_mean([p for p, label in pairs if label == 0]),
    )
    state = db.scalar(select(AgentState).where(AgentState.session_id == sid))
    approved, rejected_approvals = approvals.get("APPROVED", 0), approvals.get("REJECTED", 0)
    artifact_rows = db.scalars(select(CodeArtifact).where(CodeArtifact.session_id == sid)).all()
    project_metrics = None
    if artifact_rows:
        statuses = Counter(a.validation_status for a in artifact_rows)
        artifact_ids = [a.id for a in artifact_rows]
        all_versions = db.scalar(select(func.count()).select_from(CodeArtifactVersion).where(
            CodeArtifactVersion.artifact_id.in_(artifact_ids))) or 0
        review_rows = db.scalars(select(Approval).where(Approval.session_id == sid,
            Approval.kind == ApprovalKind.REVIEW).order_by(Approval.created_at)).all()
        code_reviews = [a for a in review_rows if (a.payload or {}).get("review_type") == "CODE"]
        recent = code_reviews[-1] if code_reviews else None
        approval_status = recent.status.value if recent else "NONE"
        if recent and approval_status == "APPROVED":
            current = {a.path: a.current_version for a in artifact_rows}
            if current != (recent.payload or {}).get("versions", {}):
                approval_status = "OUTDATED"
        project_metrics = ProjectMetrics(
            files=len(artifact_rows), versions_saved=all_versions,
            syntax_validated=statuses.get("SYNTAX_VALIDATED", 0),
            validation_failed=statuses.get("VALIDATION_FAILED", 0),
            not_validated=statuses.get("NOT_VALIDATED", 0),
            code_reviews=len(code_reviews),
            revisions_requested=sum(a.status.value == "REJECTED" for a in code_reviews),
            approval_status=approval_status,
            runtime_tested=False,
        )
    analytics = SessionAnalytics(
        session_id=sid, name=session.name, status=session.status.value, engine=state.engine if state else None,
        created_at=session.created_at, duration_seconds=duration,
        steps_planned=len((plan_row.output_data or {}).get("plan", [])) if plan_row else 0, steps_completed=len(latest),
        confidence_series=series, avg_confidence=_mean(list(latest.values())),
        final_confidence=series[-1].confidence if series else None, min_confidence=min(latest.values()) if latest else None,
        interventions_total=sum(by_user.values()), comments=comments, corrective=corrective,
        interventions_by_type=dict(by_type), interventions_by_user=dict(by_user),
        tool_calls=tool_calls, tool_failures=tool_failures, tool_failure_rate=_ratio(tool_failures, tool_calls),
        tools=[ToolStat(tool=k, calls=v[0], failures=v[1]) for k, v in sorted(per_tool.items())],
        failed_attempts=failed_attempts, repeat_evaluations=len(evaluations) - len(latest),
        recovered=failed_attempts > 0 and session.status == AgentStatus.COMPLETED,
        approvals_requested=sum(approvals.values()), approvals_approved=approved,
        approvals_rejected=rejected_approvals, approvals_expired=approvals.get("EXPIRED", 0),
        approval_rate=_ratio(approved, approved + rejected_approvals),
        conflicts_total=len(conflicts), conflicts_open=conflicts_open, conflicts_resolved=len(conflicts) - conflicts_open,
        sources_used=used, sources_rejected=rejected, source_rejection_rate=_ratio(rejected, used + rejected),
        sources_by_origin=dict(origins),
        documents=db.scalar(select(func.count()).select_from(Document).where(Document.session_id == sid)) or 0,
        risk=risk, project_metrics=project_metrics,
    )
    return analytics, pairs


def _user_sessions(db: Session, user: User, limit: int = 200) -> list[AgentSession]:
    return list(db.scalars(
        select(AgentSession).join(SessionMember, SessionMember.session_id == AgentSession.id)
        .where(SessionMember.user_id == user.id).order_by(AgentSession.created_at.desc()).limit(limit)
    ).all())


def overview(db: Session, user: User) -> AnalyticsOverview:
    sessions = _user_sessions(db, user)
    items = [compute(db, s) for s in sessions]
    metrics = [m for m, _ in items]
    status = Counter(m.status for m in metrics)
    finished = [m for m in metrics if AgentStatus(m.status) in FINISHED]
    completed = [m for m in metrics if m.status == "COMPLETED"]

    by_type: Counter = Counter()
    tools: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for m in metrics:
        by_type.update(m.interventions_by_type)
        for t in m.tools:
            tools[t.tool][0] += t.calls
            tools[t.tool][1] += t.failures
    all_conf = [p.confidence for m in metrics for p in m.confidence_series]
    buckets = [HistogramBucket(label=f"{i / 5:.1f}-{(i + 1) / 5:.1f}", count=0) for i in range(5)]
    for c in all_conf:
        buckets[min(4, int(c * 5))].count += 1

    calls, failures = sum(m.tool_calls for m in metrics), sum(m.tool_failures for m in metrics)
    approved, rejected_ap = sum(m.approvals_approved for m in metrics), sum(m.approvals_rejected for m in metrics)
    used, rejected = sum(m.sources_used for m in metrics), sum(m.sources_rejected for m in metrics)
    pairs = [p for _, ps in items for p in ps]
    probs = [p.probability for m in metrics for p in m.risk.history]
    sources_of_predictions = {m.risk.data_source for m in metrics if m.risk.data_source}
    prediction = RiskSummary(
        data_source="/".join(sorted(sources_of_predictions)) or None, n=len(probs), mean=_mean(probs),
        max=max(probs) if probs else None, last=None, observed_n=len(pairs),
        mean_when_intervened=_mean([p for p, label in pairs if label == 1]),
        mean_when_not=_mean([p for p, label in pairs if label == 0]),
    )

    def group(label: str, members: list[SessionAnalytics]) -> ResearchGroup:
        return ResearchGroup(
            label=label, sessions=len(members),
            completion_rate=_ratio(sum(m.status == "COMPLETED" for m in members), len(members)),
            avg_duration_seconds=_mean([m.duration_seconds for m in members if m.duration_seconds is not None]),
            avg_final_confidence=_mean([m.final_confidence for m in members if m.final_confidence is not None]),
        )

    with_corrections = [m for m in finished if m.corrective > 0]
    without = [m for m in finished if m.corrective == 0]
    steps = sum(m.steps_completed for m in metrics)
    had_trouble = [m for m in finished if m.failed_attempts > 0]
    research = Research(
        task_completion_rate=_ratio(len(completed), len(finished)),
        human_correction_rate=_ratio(sum(m.corrective for m in metrics), steps),
        incorrect_actions_per_session=_ratio(sum(m.corrective + m.approvals_rejected for m in finished), len(finished)),
        agent_recovery_rate=_ratio(sum(m.recovered for m in had_trouble), len(had_trouble)),
        avg_time_to_completion_seconds=_mean([m.duration_seconds for m in completed if m.duration_seconds is not None]),
        source_rejection_rate=_ratio(rejected, used + rejected), tool_failure_rate=_ratio(failures, calls),
        conflicts_per_session=_ratio(sum(m.conflicts_total for m in metrics), len(metrics)),
        groups=[group("Sessions with at least one corrective intervention", with_corrections),
                group("Sessions without corrective interventions", without)],
        notes=("Observational numbers from your own sessions, usually with small samples. The two groups are NOT a "
               "controlled experiment (people choose when to intervene), so differences must not be read as proof "
               "that interventions help or hurt."),
    )

    return AnalyticsOverview(
        generated_at=datetime.now(timezone.utc), sessions_total=len(metrics),
        sessions_completed=status.get("COMPLETED", 0), sessions_failed=status.get("FAILED", 0),
        sessions_cancelled=status.get("CANCELLED", 0),
        sessions_active=len(metrics) - len(finished) - 0,
        success_rate=_ratio(len(completed), len(finished)),
        avg_duration_seconds=_mean([m.duration_seconds for m in finished if m.duration_seconds is not None]),
        interventions_total=sum(m.interventions_total for m in metrics),
        interventions_corrective=sum(m.corrective for m in metrics),
        interventions_per_session=_ratio(sum(m.interventions_total for m in metrics), len(metrics)),
        interventions_by_type=dict(by_type), avg_confidence=_mean(all_conf),
        avg_final_confidence=_mean([m.final_confidence for m in metrics if m.final_confidence is not None]),
        confidence_histogram=buckets, tool_calls=calls, tool_failures=failures, tool_failure_rate=_ratio(failures, calls),
        tools=[ToolStat(tool=k, calls=v[0], failures=v[1]) for k, v in sorted(tools.items())],
        approvals_requested=sum(m.approvals_requested for m in metrics), approvals_approved=approved,
        approvals_rejected=rejected_ap, approval_rate=_ratio(approved, approved + rejected_ap),
        conflicts_total=sum(m.conflicts_total for m in metrics), conflicts_open=sum(m.conflicts_open for m in metrics),
        sources_used=used, sources_rejected=rejected, source_rejection_rate=_ratio(rejected, used + rejected),
        prediction=prediction, research=research,
        recent_sessions=[
            SessionRow(id=m.session_id, name=m.name, status=m.status, created_at=m.created_at,
                       duration_seconds=m.duration_seconds, interventions=m.interventions_total, corrective=m.corrective,
                       tool_failures=m.tool_failures, conflicts=m.conflicts_total, final_confidence=m.final_confidence)
            for m in metrics[:20]
        ],
    )


# ---------------------------------------------------------------- durable snapshot for research export
def record_session_end(session_id: uuid.UUID) -> None:
    """Upsert the AnalyticsRecord of a session (idempotent). Called when a session ends."""
    with db_session.SessionLocal() as db:
        session = db.get(AgentSession, session_id)
        if session is None:
            return
        m, _ = compute(db, session)
        record = db.scalar(select(AnalyticsRecord).where(AnalyticsRecord.session_id == session_id))
        if record is None:
            record = AnalyticsRecord(session_id=session_id)
            db.add(record)
        record.status = m.status
        record.duration_seconds = m.duration_seconds
        record.steps_completed = m.steps_completed
        record.interventions = m.interventions_total
        record.corrective = m.corrective
        record.tool_calls = m.tool_calls
        record.tool_failures = m.tool_failures
        record.conflicts = m.conflicts_total
        record.approvals_requested = m.approvals_requested
        record.approvals_approved = m.approvals_approved
        record.sources_used = m.sources_used
        record.sources_rejected = m.sources_rejected
        record.final_confidence = m.final_confidence
        record.avg_confidence = m.avg_confidence
        record.metrics = m.model_dump(mode="json")
        db.commit()


CSV_COLUMNS = [
    "session_id", "status", "duration_seconds", "steps_completed", "interventions", "corrective", "tool_calls",
    "tool_failures", "conflicts", "approvals_requested", "approvals_approved", "sources_used", "sources_rejected",
    "final_confidence", "avg_confidence", "recorded_at",
]


def export_rows(db: Session, user: User) -> list[dict]:
    rows = db.scalars(
        select(AnalyticsRecord).join(SessionMember, SessionMember.session_id == AnalyticsRecord.session_id)
        .where(SessionMember.user_id == user.id).order_by(AnalyticsRecord.created_at)
    ).all()
    return [
        {**{c: getattr(r, c) for c in CSV_COLUMNS if c not in ("session_id", "recorded_at")},
         "session_id": str(r.session_id), "recorded_at": r.updated_at.isoformat()}
        for r in rows
    ]