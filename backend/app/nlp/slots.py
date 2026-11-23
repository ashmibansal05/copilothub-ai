"""Slot filling: pull the *target* out of an instruction once the ML model has decided its
intent. These are documented pattern rules, not machine learning. When a rule cannot find a
usable target it returns None and the user is asked to confirm or fill it in."""

import re
from dataclasses import dataclass

# ------------------------------------------------------------------ cleaning
_CLAUSE_CUT = re.compile(r"[,.;!?]|\s[-\u2013\u2014]\s|\s(?:because|since|as it|it is|it's|they are|which)\b", re.I)
_TAILS = [
    re.compile(r"\s+as\s+(?:(?:a|the|your)\s+)?(?:sources?|references?|evidence)\b.*$", re.I),
    re.compile(r"\s+(?:from|in|out of)\s+(?:the|your|this)\s+(?:sources?|report|research|results?|references?)\b.*$", re.I),
    re.compile(r"\s+(?:whenever|when|if)\s+(?:possible|you can)\b.*$", re.I),
    re.compile(r"\s+(?:over|rather than|instead of)\s+.*$", re.I),
]
_LEADING = {"the", "a", "an", "any", "all", "that", "this", "those", "these", "using", "use", "citing",
            "cite", "from", "on", "relying", "rely", "to", "with", "for", "by"}
_TRAILING_FILLER = {"please", "entirely", "anymore", "again", "completely", "altogether", "now", "too"}
_GENERIC_NOUNS = {"source", "sources", "site", "sites", "website", "websites", "page", "pages", "article",
                  "articles", "link", "links", "post", "posts", "thread", "threads", "answer", "answers",
                  "result", "results", "reference", "references", "material", "content"}
_REFERENCE_WORDS = {"it", "them", "that", "this", "those", "these", "one", "ones", "first", "second",
                    "third", "last", "previous", "latest", "next", "other", "another", "same"}
_SINGULAR = {"blogs": "blog", "encyclopedias": "encyclopedia", "forums": "forum", "reports": "report"}
_OFFICIAL = re.compile(
    r"\b(?:official|vendor|provider|first[- ]party)\b.*\b(?:docs?|documentation)\b"
    r"|\b(?:docs?|documentation)\b.*\b(?:official|vendor|provider)\b", re.I)


def _clean_target(raw: str) -> str | None:
    text = _CLAUSE_CUT.split(raw, maxsplit=1)[0]
    changed = True
    while changed:
        changed = False
        for tail in _TAILS:
            new = tail.sub("", text)
            if new != text:
                text, changed = new, True
    text = re.sub(r"^(?:anything|everything|content|material|information|results?)\s+(?:from|on|by)\s+", "", text.strip(), flags=re.I)

    words = text.strip(" \t\"'\u201c\u201d\u2018\u2019.,;:!?()").split()
    while words and words[0].lower() in _LEADING:
        words.pop(0)
    while words and words[-1].lower() in _TRAILING_FILLER | _GENERIC_NOUNS:
        words.pop()
    target = " ".join(words).strip()
    if not target or len(target) < 2:
        return None
    if _OFFICIAL.search(target):
        return "official documentation"
    if target.lower() in _SINGULAR:
        target = _SINGULAR[target.lower()]
    if target.lower() in _REFERENCE_WORDS:
        return None
    return target[:120]


def _first_group(patterns: list[re.Pattern], text: str, group: str = "t") -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            cleaned = _clean_target(match.group(group))
            if cleaned:
                return cleaned
    return None


# ------------------------------------------------------------------ rejecting a source
_REJECT_VERBS = (r"don'?t|do not|never|stop|avoid|exclude|ignore|reject|skip|drop|discard|disregard|remove|no")
_REJECT_OBJECT_VERBS = r"(?:using|use|citing|cite|relying on|rely on|trusting|trust|including|include|consulting|consult|quoting|quote|from)?"
_REJECT_PATTERNS = [
    re.compile(r"(?P<t>.+?)\s+(?:is|are)\s+not\s+(?:a\s+)?(?:valid|reliable|trustworthy|acceptable|good)\b", re.I),
    re.compile(rf"\b(?:{_REJECT_VERBS})\b\s+{_REJECT_OBJECT_VERBS}\s*(?P<t>.+)", re.I),
]


def extract_rejected_source(text: str) -> str | None:
    return _first_group(_REJECT_PATTERNS, text)


# ------------------------------------------------------------------ swapping a source
_CHANGE_PATTERNS = [
    (re.compile(r"instead of\s+(?P<old>.+?),?\s+(?:use|cite|take|rely on|prefer)\s+(?P<new>.+)", re.I)),
    (re.compile(r"rather than\s+(?P<old>.+?),?\s+(?:rely on|use|cite|take|prefer)\s+(?P<new>.+)", re.I)),
    (re.compile(r"(?:change|move|switch)\s+(?:the\s+)?(?:sources?\s+)?from\s+(?P<old>.+?)\s+to\s+(?P<new>.+)", re.I)),
    (re.compile(r"(?:replace|swap|substitute|exchange|switch)\s+(?P<old>.+?)\s+(?:with|for|by)\s+(?P<new>.+)", re.I)),
    (re.compile(r"(?:use|using|prefer|take|cite|rely on|choose)\s+(?P<new>.+?)\s+(?:instead of|rather than|in place of|over)\s+(?P<old>.+)", re.I)),
]


def extract_source_change(text: str) -> tuple[str, str] | None:
    """Returns (old_source, new_source)."""
    for pattern in _CHANGE_PATTERNS:
        match = pattern.search(text)
        if match:
            old = _clean_target(match.group("old"))
            new = _clean_target(re.sub(r"^(?:sources?|content|information|material)\s+from\s+", "", match.group("new"), flags=re.I))
            if old and new:
                return old, new
    return None


# ------------------------------------------------------------------ constraints
_SOURCE_WORDS = re.compile(
    r"\b(?:docs?|documentation|official|vendor|provider|papers?|journals?|academic|primary|secondary|blogs?|"
    r"encyclopedi\w*|wikipedia|reports?|whitepapers?|news|forums?|sources?|reddit|medium|quora)\b", re.I)
_INCLUDE = [
    re.compile(r"(?P<t>.+?)\s+(?:is|are)\s+(?:allowed|fine|ok|okay|acceptable|permitted)\b", re.I),
    re.compile(r"\b(?:allow|permit|you\s+(?:can|may)\s+use)\s+(?P<t>.+)", re.I),
]
_PREFER = re.compile(
    r"\b(?:prefer|preferably|favou?r|rely\s+(?:mainly|mostly|primarily)\s+on|(?:mainly|primarily)\s+use|prioriti[sz]e)\s+(?P<t>.+)", re.I)
_USE = re.compile(r"^(?:please\s+)?(?:always\s+)?use\s+(?P<t>.+)", re.I)
_ADD_PREFIX = re.compile(r"^(?:please\s+)?add\s+(?:a\s+)?(?:rule|constraint)\s*(?:that|:)?\s*", re.I)
_HIGH = re.compile(r"\b(?:must|always|never|strictly|required|essential)\b", re.I)
_LOW = re.compile(r"\b(?:if possible|preferably|ideally|try to|when(?:ever)? possible)\b", re.I)


@dataclass
class ConstraintSlots:
    action: str  # EXCLUDE_SOURCE | INCLUDE_SOURCE | PREFER_SOURCE | INSTRUCTION
    target: str
    priority: str  # LOW | MEDIUM | HIGH


def _priority(text: str) -> str:
    if _LOW.search(text):
        return "LOW"
    return "HIGH" if _HIGH.search(text) else "MEDIUM"


def extract_constraint(text: str) -> ConstraintSlots:
    """Decide what kind of rule this is. Anything that is not clearly about a source
    becomes an advisory INSTRUCTION holding the user's own words."""
    priority = _priority(text)
    for pattern in _INCLUDE:
        match = pattern.search(text)
        if match:
            target = _clean_target(match.group("t"))
            if target and _SOURCE_WORDS.search(target):
                return ConstraintSlots("INCLUDE_SOURCE", target, priority)
    if not re.search(r"\bonly\b", text, re.I):
        for pattern in (_PREFER, _USE):
            match = pattern.search(text)
            if match:
                target = _clean_target(match.group("t"))
                if target and _SOURCE_WORDS.search(target):
                    return ConstraintSlots("PREFER_SOURCE", target, priority)
    instruction = _ADD_PREFIX.sub("", text.strip()).strip()
    return ConstraintSlots("INSTRUCTION", (instruction or text.strip())[:300], priority)


# ------------------------------------------------------------------ modifying the task
_TASK_PATTERNS = [
    re.compile(r"^(?:please\s+)?(?:change|modify|update|alter|revise|redefine|replace|switch)\s+the\s+"
               r"(?:task|goal|objective|assignment|scope|topic|research topic|task description)\s*"
               r"(?:to|so (?:that )?it|:|-|\u2014)?\s*(?P<t>.+)", re.I),
    re.compile(r"^new\s+task\s*[:\-]\s*(?P<t>.+)", re.I),
    re.compile(r"^the\s+task\s+is\s+now\s+(?:to\s+)?(?P<t>.+)", re.I),
]


def extract_new_task(text: str) -> str:
    """The new task text. If no pattern matches, the whole sentence is the task."""
    for pattern in _TASK_PATTERNS:
        match = pattern.search(text.strip())
        if match:
            task = match.group("t").strip()
            if len(task) >= 10:
                return task[0].upper() + task[1:]
    return text.strip()


# ------------------------------------------------------------------ matching a constraint to remove
_WORD = re.compile(r"[a-z0-9]{3,}")
_IGNORED = {"the", "and", "constraint", "rule", "restriction", "remove", "delete", "drop", "cancel", "lift",
            "forget", "undo", "get", "rid", "take", "away", "revoke", "disable", "stop", "enforcing", "about",
            "please", "clear", "again", "for", "that", "this", "last", "preference"}



def match_constraints(text: str, constraints: list) -> list[tuple[object, float]]:
    """Rank active constraints using target-first word matching.

    The constraint target receives the highest importance.
    Description overlap provides additional supporting evidence.
    Returns [(constraint, score)] with scores from 0 to 1.
    """
    wanted = {
        w for w in _WORD.findall(text.lower())
        if w not in _IGNORED
    }

    if not wanted:
        return []

    scored = []

    for c in constraints:
        target_words = {
            w for w in _WORD.findall(c.target.lower())
            if w not in _IGNORED
        }

        description = getattr(c, "description", None) or ""

        description_words = {
            w for w in _WORD.findall(description.lower())
            if w not in _IGNORED
        }

        if not target_words:
            continue

        target_overlap = len(wanted & target_words)

        # Require an explicit target match to avoid unrelated constraints.
        if target_overlap == 0:
            continue

        target_score = target_overlap / len(target_words)

        description_score = (
            len(wanted & description_words) / len(description_words)
            if description_words else 0.0
        )

        # Target matching carries 80% of the score.
        score = (0.8 * target_score) + (0.2 * description_score)

        scored.append((c, round(score, 3)))

    return sorted(scored, key=lambda pair: pair[1], reverse=True)