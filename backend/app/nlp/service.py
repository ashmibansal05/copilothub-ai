import asyncio
import logging
import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import SessionContext
from app.core.config import get_settings
from app.models.constraint import ConstraintAction
from app.models.intent_sample import IntentSample
from app.models.intervention import InterventionType as T
from app.models.intervention import Priority
from app.models.user import UserRole
from app.nlp import classifier as classifier_module
from app.nlp import slots
from app.nlp.classifier import Prediction
from app.nlp.policy import decide
from app.rag.embeddings import get_embedder
from app.schemas.intervention import InterventionCreate
from app.schemas.nlp import Alternative, Candidate, InstructionResult, Proposal
from app.services.constraint_manager import ConstraintManager
from app.services.intervention_service import ROLE_PERMISSIONS, process_intervention

logger = logging.getLogger("copilothub.nlp")

INTENT_TO_TYPE: dict[str, T] = {
    "APPROVE": T.APPROVE, "REJECT": T.REJECT, "CORRECT": T.CORRECT, "PAUSE": T.PAUSE, "RESUME": T.RESUME,
    "MODIFY_TASK": T.MODIFY_TASK, "ADD_CONSTRAINT": T.ADD_CONSTRAINT, "REMOVE_CONSTRAINT": T.REMOVE_CONSTRAINT,
    "ADD_INFORMATION": T.ADD_INFORMATION, "REJECT_SOURCE": T.REJECT_SOURCE, "CHANGE_SOURCE": T.CHANGE_SOURCE,
    "QUESTION": T.COMMENT,  # ASK_AGENT does not exist yet: questions are kept as comments
    "COMMENT": T.COMMENT,
}

_RULE_PAUSE = re.compile(r"^\s*(?:please\s+)?pause(?:\s+(?:the\s+)?(?:agent|research|it))?\s*[.!]*\s*$", re.I)
_RULE_RESUME = re.compile(r"^\s*(?:please\s+)?(?:resume|unpause)(?:\s+(?:the\s+)?(?:agent|research|it))?\s*[.!]*\s*$", re.I)


def rule_fallback(text: str) -> Prediction | None:
    """Deterministic safety net, used ONLY when the classifier is unavailable: the exact
    one-word commands "pause" / "resume"."""
    if _RULE_PAUSE.match(text):
        return Prediction("PAUSE", 1.0, {"PAUSE": 1.0})
    if _RULE_RESUME.match(text):
        return Prediction("RESUME", 1.0, {"RESUME": 1.0})
    return None


async def _predict(text: str) -> tuple[Prediction, str]:
    try:
        classifier = await asyncio.to_thread(classifier_module.get_classifier)
        prediction = (await asyncio.to_thread(classifier.predict, [text], get_embedder()))[0]
        return prediction, "model"
    except Exception:
        logger.warning("Intent classifier unavailable", exc_info=True)
        fallback = rule_fallback(text)
        if fallback is not None:
            return fallback, "rule"
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The instruction classifier is unavailable. Use the buttons, or run `python -m app.nlp.train`.",
        )


def build_proposal(intent: str, text: str, constraints: list) -> tuple[Proposal, bool]:
    """Turn (intent, sentence) into a structured proposal. Returns (proposal, complete)."""
    itype = INTENT_TO_TYPE[intent]
    p = Proposal(type=itype)
    complete = True
    if intent in ("REJECT", "CORRECT", "ADD_INFORMATION", "COMMENT", "QUESTION"):
        p.content = text
    elif intent == "MODIFY_TASK":
        p.content = slots.extract_new_task(text)
    elif intent == "REJECT_SOURCE":
        p.target = slots.extract_rejected_source(text)
        complete = p.target is not None
    elif intent == "CHANGE_SOURCE":
        change = slots.extract_source_change(text)
        if change:
            p.target, p.content = change
        complete = change is not None
    elif intent == "ADD_CONSTRAINT":
        found = slots.extract_constraint(text)
        p.action, p.target = ConstraintAction(found.action), found.target
        p.priority = Priority(found.priority)
    elif intent == "REMOVE_CONSTRAINT":
        ranked = slots.match_constraints(text, constraints)
        p.candidates = [
            Candidate(
                id=c.id,
                description=getattr(c, "description", None) or str(c.target),
            )
            for c, _ in ranked[:3]
        ]
        if ranked and ranked[0][1] >= 0.5 and (len(ranked) == 1 or ranked[1][1] < ranked[0][1] * 0.8):
            p.constraint_id = ranked[0][0].id
        complete = p.constraint_id is not None
    return p, complete


def _to_create(p: Proposal, text: str) -> InterventionCreate:
    return InterventionCreate(
        type=p.type, content=p.content, target=p.target, action=p.action, priority=p.priority,
        constraint_id=p.constraint_id, origin_text=text,
    )


async def interpret(db: Session, ctx: SessionContext, text: str, dry_run: bool = False) -> InstructionResult:
    """Free text -> structured intervention. Applies it through the SAME processor the buttons
    use (permissions, audit, events) when the policy allows, otherwise returns a proposal."""
    if ctx.role == UserRole.VIEWER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewers cannot give instructions")
    settings = get_settings()
    text = text.strip()

    prediction, method = await _predict(text)
    active = ConstraintManager.active(db, ctx.session.id)
    proposal, complete = build_proposal(prediction.intent, text, active)
    allowed = proposal.type in ROLE_PERMISSIONS[ctx.role]
    decision = decide(prediction.intent, prediction.confidence, complete, settings.nlp_auto_apply)
    reason = decision.reason
    if not allowed:
        reason = f"Your role ({ctx.role.value.lower()}) may not perform this action ({proposal.type.value})."

    sample = IntentSample(
        session_id=ctx.session.id, user_id=ctx.user.id, text=text, predicted_intent=prediction.intent,
        confidence=prediction.confidence, method=method, outcome="DRY_RUN" if dry_run else "PROPOSED",
        proposed_type=proposal.type.value,
    )
    db.add(sample)
    db.commit()

    applied, intervention = False, None
    if decision.auto and allowed and not dry_run:
        try:
            intervention = await process_intervention(db, ctx, _to_create(proposal, text))
            applied = True
            sample.outcome = "AUTO_APPLIED"
        except HTTPException as exc:  # e.g. 409: the session state does not allow it right now
            reason = str(exc.detail)
            sample.outcome = "FAILED"
        db.commit()

    top = sorted(prediction.probabilities.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return InstructionResult(
        text=text, intent=prediction.intent, confidence=round(prediction.confidence, 4), method=method,
        alternatives=[Alternative(intent=i, confidence=round(c, 4)) for i, c in top],
        proposal=proposal, allowed=allowed,
        needs_confirmation=(not applied) and allowed and not dry_run,
        reason=None if applied else reason,
        note="Questions to the agent are saved as comments for now." if prediction.intent == "QUESTION" else None,
        applied=applied, intervention=intervention,
    )