"""Human-readable project profiles. Heuristics, not unsupported AI claims.

The workspace remains general-purpose. Different fields share the same
collaboration, evidence, file storage, human review and report lifecycle.
Specialized file types/tools can be added without a new agent architecture.
"""
from __future__ import annotations

import re


def profile_for(task: str) -> dict:
    from app.services.coding_agent import classify_task

    text = (task or "").lower()
    patterns = (
        ("Data & Analytics", r"\b(dataset|data analysis|analytics|dashboard|visualization|visualisation|forecast|spreadsheet|csv)\b"),
        ("Engineering & Design", r"\b(iot|circuit|electronic|mechanical|cad|robot|sensor|engineering|prototype|blueprint)\b"),
        ("Business & Planning", r"\b(startup|business|market|sales|marketing|customer|strategy|budget|revenue|proposal)\b"),
        ("Education & Academics", r"\b(curriculum|teaching|lesson|academic|college|university|student project|assignment)\b"),
        ("Writing & Content", r"\b(content|article|blog|story|copywriting|social media|scriptwriting)\b"),
    )
    domain = next((name for name, pattern in patterns if re.search(pattern, text)), None)
    kind = classify_task(task)
    if not domain:
        domain = ("Software Development" if kind in ("CODING", "HYBRID")
                  else "Research & Knowledge Work" if re.search(r"\b(research|study|literature|compare|survey)\b", text)
                  else "General Collaboration")
    if kind == "CODING":
        outputs = ["Source files", "Reviewable revisions", "Approved project package"]
    elif kind == "HYBRID":
        outputs = ["Research findings", "Project files", "Combined approved report"]
    else:
        outputs = ["Findings and working notes", "Team review", "Report and exports"]
    return {"domain": domain, "workflow": kind, "expected_outputs": outputs,
            "description": "AI proposes work based on your goal; final deliverables require team review."}


def research_brief(task: str) -> str:
    """Focus the hybrid research phase on analysis, not on writing source files."""
    return (
        "Research phase for this multi-part project. Examine the ideas and comparisons "
        "needed to support the final implementation. Do not write or compile source code "
        "during this phase; the code-generation phase follows separately. "
        "Do not use a numeric calculator tool unless concrete numeric values are supplied. "
        "Base factual claims on retrieved or provided evidence and clearly state limitations.\n\n"
        f"Original project objective: {task}"
    )
