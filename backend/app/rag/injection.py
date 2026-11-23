import re

# A coarse heuristic for text that tries to give the model orders. Retrieved
# documents are ALSO fenced as untrusted data in the prompt; this is an extra layer,
# not a guarantee, and it can produce false positives (flagged chunks are simply not used).
_PATTERNS = [
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?|prompts?)",
    r"disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|system)",
    r"(reveal|show|print|repeat)\s+(your|the)\s+(system\s+)?(prompt|instructions)",
    r"you\s+are\s+now\s+(a|an|the)\b",
    r"new\s+instructions\s*:",
    r"</?\s*(system|instruction|human_constraints|task)\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in _COMPILED)