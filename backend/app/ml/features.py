"""Feature engineering for the intervention-risk predictor.

THE SAME function (build_step_features) is used to build training rows from past sessions
and to score a live session, so training and serving can never drift apart. Every query is
limited to events at or before `cutoff`, so nothing from the future leaks into a feature."""

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.agent import AgentAction
from app.models.conflict import Conflict
from app.models.constraint import Constraint, ConstraintStatus
from app.models.intervention import Intervention
from app.models.intervention import InterventionType as T
from app.models.session import AgentSession
from app.models.source import Source
from app.models.tool_execution import ToolExecution

FEATURE_NAMES = [
    "task_length_words", "task_complexity_cues", "plan_steps", "step_number", "progress_fraction",
    "agent_confidence", "min_confidence_so_far", "tool_failures_so_far", "tool_failures_this_step",
    "retries_so_far", "sources_used_so_far", "source_rejection_rate", "retrieval_uncertainty",
    "has_retrieval", "open_conflicts", "human_corrections_so_far", "human_interventions_so_far",
    "active_constraints",
]

FEATURE_LABELS = {
    "task_length_words": "Task length (words)",
    "task_complexity_cues": "Task complexity (comparisons, lists, numbers)",
    "plan_steps": "Number of planned steps",
    "step_number": "Current step number",
    "progress_fraction": "Progress through the plan",
    "agent_confidence": "Agent confidence on this step",
    "min_confidence_so_far": "Lowest confidence so far",
    "tool_failures_so_far": "Tool failures so far",
    "tool_failures_this_step": "Tool failures on this step",
    "retries_so_far": "Retries so far",
    "sources_used_so_far": "Sources used so far",
    "source_rejection_rate": "Share of sources rejected",
    "retrieval_uncertainty": "Retrieval uncertainty",
    "has_retrieval": "Documents were retrieved on this step",
    "open_conflicts": "Open instruction conflicts",
    "human_corrections_so_far": "Human corrections so far",
    "human_interventions_so_far": "Human interventions so far",
    "active_constraints": "Active constraints",
}

# A step counts as "needed a human" when one of these happened after it, before the next
# step finished. (Comments, approvals, pause/resume and administrative actions do not.)
CORRECTIVE_TYPES = [
    T.CORRECT, T.REJECT, T.REJECT_SOURCE, T.CHANGE_SOURCE, T.MODIFY_TASK,
    T.REQUEST_REVIEW, T.ADD_CONSTRAINT, T.ADD_INFORMATION,
]

_COMPLEXITY = re.compile(
    r"\b(?:compar\w*|versus|vs\.?|between|trade-?offs?|evaluat\w*|analy[sz]\w*|recommend\w*|cost|pricing)\b", re.I)


def aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; PostgreSQL returns aware ones. Normalise to UTC-aware."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def task_stats(task: str) -> tuple[int, int]:
    """(word count, complexity cues). Cues = comparison/analysis words + commas + 'and' + numbers."""
    cues = (
        len(_COMPLEXITY.findall(task)) + task.count(",")
        + len(re.findall(r"\band\b", task, re.I)) + len(re.findall(r"\d+", task))
    )
    return len(task.split()), cues


def _count(db: Session, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


def build_step_features(
    db: Session, session_id: uuid.UUID, step_index: int, cutoff: datetime
) -> dict[str, float]:
    """The 18 features describing the session right after step `step_index` was evaluated."""
    cutoff = aware(cutoff)
    session = db.get(AgentSession, session_id)
    words, cues = task_stats(session.task)

    plan_row = db.scalar(
        select(AgentAction)
        .where(AgentAction.session_id == session_id, AgentAction.action_type == "PLAN",
               AgentAction.success.is_(True), AgentAction.created_at <= cutoff)
        .order_by(AgentAction.created_at.desc()).limit(1)
    )
    plan_steps = len((plan_row.output_data or {}).get("plan", [])) if plan_row else 0

    evaluations = db.scalars(
        select(AgentAction)
        .where(AgentAction.session_id == session_id, AgentAction.action_type == "EVALUATE",
               AgentAction.success.is_(True), AgentAction.created_at <= cutoff)
        .order_by(AgentAction.created_at)
    ).all()
    confidence_by_step: dict[int, float] = {}
    for row in evaluations:
        value = (row.output_data or {}).get("confidence")
        if isinstance(value, (int, float)):
            confidence_by_step[row.step_index] = float(value)
    all_conf = list(confidence_by_step.values())
    confidence = confidence_by_step.get(step_index, all_conf[-1] if all_conf else 0.5)
    min_confidence = min(all_conf) if all_conf else confidence
    repeat_evaluations = len(evaluations) - len(confidence_by_step)

    failed_attempts = _count(db, AgentAction, AgentAction.session_id == session_id,
                             AgentAction.success.is_(False), AgentAction.created_at <= cutoff)
    act_failures = _count(db, AgentAction, AgentAction.session_id == session_id,
                          AgentAction.action_type == "ACT", AgentAction.success.is_(False),
                          AgentAction.created_at <= cutoff)
    act_failures_step = _count(db, AgentAction, AgentAction.session_id == session_id,
                               AgentAction.action_type == "ACT", AgentAction.success.is_(False),
                               AgentAction.step_index == step_index, AgentAction.created_at <= cutoff)
    tool_problems = _count(db, ToolExecution, ToolExecution.session_id == session_id,
                           ToolExecution.status != "SUCCESS", ToolExecution.created_at <= cutoff)
    tool_problems_step = _count(db, ToolExecution, ToolExecution.session_id == session_id,
                                ToolExecution.status != "SUCCESS", ToolExecution.step_index == step_index,
                                ToolExecution.created_at <= cutoff)

    used = _count(db, Source, Source.session_id == session_id, Source.status == "USED", Source.created_at <= cutoff)
    rejected = _count(db, Source, Source.session_id == session_id, Source.status == "REJECTED", Source.created_at <= cutoff)
    scores = [
        s for (s,) in db.execute(
            select(Source.score).where(
                Source.session_id == session_id, Source.step_index == step_index, Source.status == "USED",
                Source.origin == "DOCUMENT", Source.score.is_not(None), Source.created_at <= cutoff)
        ).all()
    ]
    has_retrieval = 1.0 if scores else 0.0
    uncertainty = 1.0 - sum(min(1.0, max(0.0, s)) for s in scores) / len(scores) if scores else 0.5

    open_conflicts = _count(
        db, Conflict, Conflict.session_id == session_id, Conflict.created_at <= cutoff,
        or_(Conflict.resolved_at.is_(None), Conflict.resolved_at > cutoff))
    corrections = _count(db, Intervention, Intervention.session_id == session_id,
                         Intervention.type.in_(CORRECTIVE_TYPES), Intervention.created_at <= cutoff)
    interventions = _count(db, Intervention, Intervention.session_id == session_id,
                           Intervention.type != T.COMMENT, Intervention.created_at <= cutoff)
    constraints = _count(
        db, Constraint, Constraint.session_id == session_id, Constraint.created_at <= cutoff,
        Constraint.status != ConstraintStatus.SUPERSEDED,
        or_(Constraint.removed_at.is_(None), Constraint.removed_at > cutoff))

    return {
        "task_length_words": float(words),
        "task_complexity_cues": float(cues),
        "plan_steps": float(plan_steps),
        "step_number": float(step_index),
        "progress_fraction": min(1.0, step_index / plan_steps) if plan_steps else 0.0,
        "agent_confidence": confidence,
        "min_confidence_so_far": min_confidence,
        "tool_failures_so_far": float(tool_problems + act_failures),
        "tool_failures_this_step": float(tool_problems_step + act_failures_step),
        "retries_so_far": float(failed_attempts + repeat_evaluations),
        "sources_used_so_far": float(used),
        "source_rejection_rate": rejected / (used + rejected) if (used + rejected) else 0.0,
        "retrieval_uncertainty": uncertainty,
        "has_retrieval": has_retrieval,
        "open_conflicts": float(open_conflicts),
        "human_corrections_so_far": float(corrections),
        "human_interventions_so_far": float(interventions),
        "active_constraints": float(constraints),
    }