from app.models.memory import MemoryKind
from app.services.constraint_manager import ConstraintManager, ConstraintView
from app.services.memory_manager import MemoryManager
from helpers import make_running_session

WIKI = {"title": "Cloud computing - Wikipedia", "publisher": "Wikipedia", "source_type": "encyclopedia"}
DOCS = {"title": "AWS pricing", "publisher": "Amazon Web Services", "source_type": "official documentation"}
BLOG = {"title": "Cloud tips", "publisher": "Startup blog", "source_type": "blog"}


def view(action, target, priority="MEDIUM"):
    return ConstraintView(id="x", action=action, target=target, priority=priority, description="")


def test_matching_handles_names_domains_and_urls():
    for target in ["Wikipedia", "WIKIPEDIA", "wikipedia.org", "https://en.wikipedia.org/wiki/Cloud"]:
        assert ConstraintManager.matches(target, WIKI), target
    assert not ConstraintManager.matches("AWS", {"title": "Laws of cloud", "publisher": "Blog"})
    assert ConstraintManager.matches("official documentation", DOCS)
    assert not ConstraintManager.matches("official documentation", BLOG)


def test_exclude_filters_and_prefer_ranks_first():
    views = [view("EXCLUDE_SOURCE", "Wikipedia", "HIGH"), view("PREFER_SOURCE", "official documentation")]
    allowed, rejected = ConstraintManager.filter_sources(views, [WIKI, BLOG, DOCS])
    assert [s["publisher"] for s in allowed] == ["Amazon Web Services", "Startup blog"]
    assert allowed[0]["preferred"] is True and "preferred" not in allowed[1]
    assert [s["publisher"] for s in rejected] == ["Wikipedia"]
    assert rejected[0]["rejected_by"] == "Wikipedia"


def test_exclude_wins_over_include_until_conflict_resolution_exists():
    views = [view("INCLUDE_SOURCE", "Wikipedia"), view("EXCLUDE_SOURCE", "Wikipedia")]
    allowed, rejected = ConstraintManager.filter_sources(views, [WIKI])
    assert allowed == [] and len(rejected) == 1


def test_no_constraints_changes_nothing():
    allowed, rejected = ConstraintManager.filter_sources([], [WIKI, DOCS])
    assert [s["publisher"] for s in allowed] == ["Wikipedia", "Amazon Web Services"] and rejected == []


def test_prompt_lines_sorted_by_priority():
    lines = ConstraintManager.prompt_lines([
        ConstraintView("1", "INSTRUCTION", "x", "LOW", "low one"),
        ConstraintView("2", "EXCLUDE_SOURCE", "y", "HIGH", "high one"),
    ])
    assert lines == ["[HIGH] high one", "[LOW] low one"]


def test_memory_retrieval_is_selective_and_relevant(client):
    sid = make_running_session(client)
    with client.session_factory() as db:
        M = MemoryManager.remember
        M(db, sid, MemoryKind.FACT, "The startup has a monthly budget of 500 dollars for hosting", importance=3)
        M(db, sid, MemoryKind.FACT, "The founders prefer vegetarian lunch options", importance=1)
        M(db, sid, MemoryKind.CORRECTION, "Pricing must use euros not dollars", importance=5)
        M(db, sid, MemoryKind.REJECTED_SOURCE, "Source rejected: Wikipedia", key="Wikipedia", importance=4)
        gone = M(db, sid, MemoryKind.FACT, "Old fact that was withdrawn", importance=5)
        gone.is_active = False
        db.commit()

        top = MemoryManager.retrieve(db, sid, "hosting budget for the startup", k=2)
        assert len(top) == 2
        assert "budget" in top[0] or "euros" in top[0]
        joined = " ".join(MemoryManager.retrieve(db, sid, "anything", k=10))
        assert "withdrawn" not in joined  # inactive items are never retrieved
        assert "Wikipedia" not in joined  # source memory is enforced via constraints, not notes
        assert MemoryManager.retrieve(db, sid, "hosting", k=10, char_budget=60) != []
        assert len(" ".join(MemoryManager.retrieve(db, sid, "hosting", k=10, char_budget=60))) <= 120