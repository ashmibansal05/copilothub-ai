import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_current_user, get_session_context
from app.db.session import get_db
from app.models.user import User
from app.nlp import classifier
from app.nlp.service import interpret
from app.schemas.nlp import InstructionRequest, InstructionResult, NLPStatus

router = APIRouter(tags=["instructions"])


@router.post("/sessions/{session_id}/instructions", response_model=InstructionResult)
async def give_instruction(
    data: InstructionRequest,
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> InstructionResult:
    """Free-text instruction -> classified -> applied as a normal intervention, or proposed
    for confirmation when the classifier is unsure or the action is high-impact."""
    return await interpret(db, ctx, data.text, dry_run=data.dry_run)


@router.get("/nlp/status", response_model=NLPStatus)
def nlp_status(_: User = Depends(get_current_user)) -> NLPStatus:
    """The real evaluation numbers from the last training run (nothing is made up)."""
    path = classifier.metrics_path()
    if not path.exists():
        return NLPStatus(available=False)
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return NLPStatus(available=False)
    return NLPStatus(
        available=True, embedder=m.get("embedder"), trained_at=m.get("trained_at"),
        n_train=m.get("n_train"), n_test=m.get("n_test"),
        cv_accuracy=(m.get("cross_validation") or {}).get("accuracy"),
        cv_macro_f1=(m.get("cross_validation") or {}).get("macro_f1"),
        held_out_accuracy=(m.get("held_out") or {}).get("accuracy"), dataset=m.get("dataset"),
    )