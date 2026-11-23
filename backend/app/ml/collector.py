"""Turns REAL finished sessions into training rows, from tables the app already fills.

One row per evaluated step. Features: build_step_features() at the moment the step was
evaluated. Label: 1 if a corrective human intervention happened after that step and before
the next step was evaluated (or before the run ended, for the last step)."""

import csv
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.features import CORRECTIVE_TYPES, FEATURE_NAMES, aware, build_step_features
from app.models.agent import AgentAction
from app.models.intervention import Intervention
from app.models.session import AgentSession, AgentStatus

FINISHED = [AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED]
MIN_REAL_ROWS = 200
MIN_PER_CLASS = 30


class InsufficientDataError(Exception):
    """Not enough real sessions yet to train on."""


@dataclass
class Snapshot:
    step_index: int
    at: datetime  # when the step was evaluated (aware, UTC)
    label: int
    window_end: datetime


def label_snapshots(db: Session, session: AgentSession) -> list[Snapshot]:
    rows = db.scalars(
        select(AgentAction)
        .where(AgentAction.session_id == session.id, AgentAction.action_type == "EVALUATE",
               AgentAction.success.is_(True))
        .order_by(AgentAction.created_at)
    ).all()
    if not rows:
        return []
    corrective = [
        aware(i.created_at)
        for i in db.scalars(
            select(Intervention).where(Intervention.session_id == session.id, Intervention.type.in_(CORRECTIVE_TYPES))
        ).all()
    ]
    end_of_run = aware(session.ended_at) if session.ended_at else datetime.now(timezone.utc)
    snapshots = []
    for index, row in enumerate(rows):
        at = aware(row.created_at)
        window_end = aware(rows[index + 1].created_at) if index + 1 < len(rows) else max(end_of_run, at)
        label = int(any(at < ts <= window_end for ts in corrective))
        snapshots.append(Snapshot(row.step_index, at, label, window_end))
    return snapshots


def extract_rows(
    db: Session, session_ids: list[uuid.UUID] | None = None, finished_only: bool = True
) -> list[dict]:
    stmt = select(AgentSession)
    if session_ids is not None:
        stmt = stmt.where(AgentSession.id.in_(session_ids))
    if finished_only:
        stmt = stmt.where(AgentSession.status.in_(FINISHED))
    rows: list[dict] = []
    for session in db.scalars(stmt.order_by(AgentSession.created_at)).all():
        for snap in label_snapshots(db, session):
            features = build_step_features(db, session.id, snap.step_index, snap.at)
            rows.append({
                **features, "label": snap.label, "session_id": str(session.id),
                "step_index": snap.step_index, "snapshot_at": snap.at.isoformat(),
            })
    return rows


def check_enough_real_data(rows: list[dict]) -> None:
    positives = sum(r["label"] for r in rows)
    negatives = len(rows) - positives
    if len(rows) < MIN_REAL_ROWS or positives < MIN_PER_CLASS or negatives < MIN_PER_CLASS:
        raise InsufficientDataError(
            f"Not enough real data to train: {len(rows)} rows ({positives} with an intervention, "
            f"{negatives} without). Need at least {MIN_REAL_ROWS} rows and {MIN_PER_CLASS} of each class. "
            "Keep using the platform, or train on synthetic data with --source synthetic."
        )


def write_csv(rows: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["session_id", "step_index", "snapshot_at", *FEATURE_NAMES, "label"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row[c] for c in columns})