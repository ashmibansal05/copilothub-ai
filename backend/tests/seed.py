"""A hand-built session history with exact timestamps, so feature extraction, labels and
analytics can be checked against numbers worked out by hand."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.agent import AgentAction
from app.models.approval import Approval, ApprovalKind, ApprovalStatus
from app.models.conflict import Conflict, ConflictKind, ConflictStatus
from app.models.constraint import Constraint, ConstraintAction, ConstraintStatus
from app.models.intervention import Intervention, InterventionStatus, InterventionType, Priority
from app.models.risk_prediction import RiskPrediction
from app.models.session import AgentSession, AgentStatus
from app.models.source import Source
from app.models.tool_execution import ToolExecution
from app.models.user import User

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
TASK = "Compare AWS, Azure and Google Cloud pricing for 3 startups"


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def seed_history(client, sid: uuid.UUID, with_predictions: bool = False) -> None:
    """Timeline (minutes): plan 0 | step1 evaluated 2 | step2 evaluated 4 | step3 evaluated 6 | ended 7.
    A CORRECT intervention at 4.5 means: step 1 -> no human, step 2 -> human, step 3 -> no human."""
    with client.session_factory() as db:
        owner = db.scalar(select(User).where(User.username == "owner"))
        session = db.get(AgentSession, sid)
        session.task, session.status = TASK, AgentStatus.COMPLETED
        session.started_at, session.ended_at = at(0), at(7)

        def action(kind, step, minutes, out=None, inp=None, success=True):
            db.add(AgentAction(session_id=sid, step_index=step, action_type=kind, input_data=inp or {},
                               output_data=out or {}, success=success, created_at=at(minutes)))

        action("PLAN", 0, 0, {"plan": ["a", "b", "c"]})
        action("TOOL_CALL", 1, 1, {"output": "found A", "sources": [], "rejected_sources": []}, {"step": "a"})
        action("EVALUATE", 1, 2, {"confidence": 0.9, "ok": True})
        action("ACT", 2, 2.5, success=False)  # one failed model/tool attempt
        action("EVALUATE", 2, 4, {"confidence": 0.5, "ok": True})
        action("EVALUATE", 3, 6, {"confidence": 0.8, "ok": True})

        def tool(name, status, step, minutes):
            db.add(ToolExecution(session_id=sid, step_index=step, tool_name=name, arguments={}, status=status,
                                 simulated=False, duration_ms=10, sources_count=0, rejected_count=0, created_at=at(minutes)))

        tool("calculate", "SUCCESS", 1, 1)
        tool("search_web", "SUCCESS", 2, 3)
        tool("retrieve_documents", "ERROR", 2, 3)

        def source(step, title, status, score=None, origin="DOCUMENT", rejected_by=None):
            db.add(Source(session_id=sid, step_index=step, title=title, publisher="Pub", origin=origin, status=status,
                          score=score, rejected_by=rejected_by, created_at=at(3)))

        source(2, "Doc A", "USED", 0.8)
        source(2, "Doc B", "USED", 0.6)
        source(2, "Wiki", "REJECTED", origin="SIMULATED", rejected_by="Wikipedia")

        def intervention(kind, minutes, content=None):
            db.add(Intervention(session_id=sid, user_id=owner.id, type=kind, content=content, priority=Priority.MEDIUM,
                                status=InterventionStatus.APPLIED, details={}, created_at=at(minutes)))

        intervention(InterventionType.COMMENT, 3.5, "looks fine")
        intervention(InterventionType.CORRECT, 4.5, "Use euros")
        intervention(InterventionType.APPROVE, 6.5)

        def constraint(action_, target, created, removed=None, status=ConstraintStatus.ACTIVE):
            c = Constraint(session_id=sid, action=action_, target=target, priority=Priority.HIGH, status=status,
                           created_by=owner.id, created_at=at(created), removed_at=at(removed) if removed else None)
            db.add(c)
            return c

        c1 = constraint(ConstraintAction.EXCLUDE_SOURCE, "Wikipedia", 0.5, removed=5, status=ConstraintStatus.REMOVED)
        c2 = constraint(ConstraintAction.PREFER_SOURCE, "official documentation", 1)
        c3 = constraint(ConstraintAction.INCLUDE_SOURCE, "Wikipedia", 6.5)
        db.flush()

        for a, b, created, resolved, status in [(c1, c2, 5, 5.5, ConflictStatus.RESOLVED), (c2, c3, 5.8, None, ConflictStatus.OPEN)]:
            db.add(Conflict(session_id=sid, kind=ConflictKind.SOURCE_POLICY, status=status, constraint_a_id=a.id,
                            constraint_b_id=b.id, requires_resolution=True, rule_applied="tie", created_at=at(created),
                            resolved_at=at(resolved) if resolved else None))

        db.add(Approval(session_id=sid, kind=ApprovalKind.FINAL_REPORT, status=ApprovalStatus.APPROVED, payload={}, created_at=at(6)))
        db.add(Approval(session_id=sid, kind=ApprovalKind.REVIEW, status=ApprovalStatus.REJECTED, payload={}, created_at=at(2)))

        if with_predictions:
            for step, minutes, p in [(1, 2, 0.2), (2, 4, 0.8), (3, 6, 0.3)]:
                db.add(RiskPrediction(session_id=sid, step_index=step, snapshot_at=at(minutes), probability=p,
                                      level="LOW", model_name="random_forest", data_source="synthetic", features={}))
        db.commit()