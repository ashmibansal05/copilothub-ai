"""Placeholder sources for DEMO mode. Nothing here comes from the internet."""

OFFICIAL = "official documentation"

SOURCE_BANK: dict[str, list[tuple[str, str, str]]] = {
    "aws": [
        ("Cloud cost tips for founders", "Startup blog", "blog"),
        ("AWS pricing overview", "Amazon Web Services", OFFICIAL),
        ("AWS Free Tier summary", "Amazon Web Services", OFFICIAL),
        ("Amazon Web Services - Wikipedia", "Wikipedia", "encyclopedia"),
    ],
    "azure": [
        ("Azure vs the rest: a founder's view", "Startup blog", "blog"),
        ("Azure pricing overview", "Microsoft", OFFICIAL),
        ("Azure for startups summary", "Microsoft", OFFICIAL),
        ("Microsoft Azure - Wikipedia", "Wikipedia", "encyclopedia"),
    ],
    "google": [
        ("Google Cloud in five minutes", "Startup blog", "blog"),
        ("Google Cloud pricing overview", "Google Cloud", OFFICIAL),
        ("Google Cloud free program summary", "Google Cloud", OFFICIAL),
        ("Google Cloud Platform - Wikipedia", "Wikipedia", "encyclopedia"),
    ],
    "criteria": [
        ("Cloud computing - Wikipedia", "Wikipedia", "encyclopedia"),
        ("Choosing a cloud provider: startup guide", "Industry blog", "blog"),
    ],
    "compare": [("Cloud provider comparison notes", "Analyst blog", "analyst")],
    "default": [
        ("Background overview", "Wikipedia", "encyclopedia"),
        ("Topic explainer", "Industry blog", "blog"),
    ],
}


def bank_key(text: str) -> str:
    s = text.lower()
    if "aws" in s:
        return "aws"
    if "azure" in s:
        return "azure"
    if "google" in s:
        return "google"
    if "criteria" in s or "identify" in s:
        return "criteria"
    if "compare" in s or "analyse" in s:
        return "compare"
    return "default"


def demo_sources(text: str) -> list[dict]:
    return [
        {"title": t, "publisher": p, "source_type": st, "simulated": True}
        for t, p, st in SOURCE_BANK[bank_key(text)]
    ]