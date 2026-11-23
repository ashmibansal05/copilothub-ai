from dataclasses import dataclass

# High-impact actions are NEVER applied from free text without a human confirming them.
ALWAYS_CONFIRM = {"APPROVE", "REJECT", "MODIFY_TASK", "REMOVE_CONSTRAINT"}
# Minimum model confidence to apply an intent automatically (everything else: 0.70).
AUTO_THRESHOLD = {"COMMENT": 0.40, "QUESTION": 0.40}
DEFAULT_AUTO_THRESHOLD = 0.70


@dataclass
class Decision:
    auto: bool
    reason: str | None


def decide(intent: str, confidence: float, complete: bool, auto_enabled: bool = True) -> Decision:
    """Apply automatically, or ask the user first? `complete` is False when a needed detail
    (e.g. the source name) could not be found in the sentence."""
    if intent in ALWAYS_CONFIRM:
        return Decision(False, "This is a high-impact action, so please confirm it first.")
    if not complete:
        return Decision(False, "I could not tell exactly what you mean (a detail is missing). Please check it.")
    if not auto_enabled:
        return Decision(False, "Automatic application is switched off. Please confirm.")
    needed = AUTO_THRESHOLD.get(intent, DEFAULT_AUTO_THRESHOLD)
    if confidence < needed:
        return Decision(False, f"I am only {confidence:.0%} sure what you mean (I need {needed:.0%} to act on my own). Please confirm.")
    return Decision(True, None)