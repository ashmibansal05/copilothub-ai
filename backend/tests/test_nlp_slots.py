import pytest

from app.nlp import slots
from app.nlp.dataset import INTENTS, TEST, TRAIN, TEST_EXAMPLES, TRAIN_EXAMPLES


@pytest.mark.parametrize("text,expected", [
    ("Don't use Wikipedia.", "Wikipedia"), ("Stop using Wikipedia.", "Wikipedia"), ("Do not cite Reddit.", "Reddit"),
    ("Exclude blogs from the sources.", "blog"), ("Ignore the Medium article, it is unreliable.", "Medium"),
    ("Never use Quora as a source.", "Quora"), ("Remove Wikipedia from the sources.", "Wikipedia"),
    ("No Wikipedia please.", "Wikipedia"), ("Do not rely on Stack Overflow answers.", "Stack Overflow"),
    ("Skip the Forbes article.", "Forbes"), ("Stop citing social media.", "social media"),
    ("Disregard anything from Wikipedia.", "Wikipedia"), ("Wikipedia is not a valid source for this report.", "Wikipedia"),
    ("Drop the blog posts as sources.", "blog"), ("Skip Wikipedia entirely.", "Wikipedia"), ("Don't trust Medium posts.", "Medium"),
])
def test_rejected_source_targets(text, expected):
    assert slots.extract_rejected_source(text) == expected


@pytest.mark.parametrize("text", [
    "Don't use it.", "Reject the first source, it is biased.", "I don't trust that source, discard it.",
    "That website is not trustworthy, do not use it.", "Stop.",
])
def test_vague_references_give_no_target(text):
    assert slots.extract_rejected_source(text) is None


@pytest.mark.parametrize("text,expected", [
    ("Replace Wikipedia with official documentation.", ("Wikipedia", "official documentation")),
    ("Use official documentation instead of blogs.", ("blog", "official documentation")),
    ("Swap the blog posts for vendor documentation.", ("blog", "official documentation")),
    ("Instead of Wikipedia, use the cloud provider docs.", ("Wikipedia", "official documentation")),
    ("Switch from Reddit to peer reviewed articles.", ("Reddit", "peer reviewed")),
    ("Use AWS documentation rather than Medium articles.", ("Medium", "AWS documentation")),
    ("Substitute Quora with Stack Overflow.", ("Quora", "Stack Overflow")),
    ("Instead of Wikipedia take Britannica.", ("Wikipedia", "Britannica")),
    ("Change the source from the blog to the official pricing page.", ("blog", "official pricing")),
])
def test_source_changes(text, expected):
    assert slots.extract_source_change(text) == expected


def test_source_change_needs_both_sides():
    assert slots.extract_source_change("Use better sources.") is None
    assert slots.extract_source_change("Replace it with something.") is None


@pytest.mark.parametrize("text,action,target,priority", [
    ("Use official cloud provider documentation.", "PREFER_SOURCE", "official documentation", "MEDIUM"),
    ("Prefer official documentation as sources.", "PREFER_SOURCE", "official documentation", "MEDIUM"),
    ("Always prefer official docs.", "PREFER_SOURCE", "official documentation", "HIGH"),
    ("Rely mainly on vendor documentation.", "PREFER_SOURCE", "official documentation", "MEDIUM"),
    ("Use primary sources whenever possible.", "PREFER_SOURCE", "primary", "LOW"),
    ("Wikipedia is allowed as a source.", "INCLUDE_SOURCE", "Wikipedia", "MEDIUM"),
    ("Keep the report under 500 words.", "INSTRUCTION", "Keep the report under 500 words.", "MEDIUM"),
    ("Only use English sources.", "INSTRUCTION", "Only use English sources.", "MEDIUM"),
    ("Always cite your sources.", "INSTRUCTION", "Always cite your sources.", "HIGH"),
    ("Use bullet points.", "INSTRUCTION", "Use bullet points.", "MEDIUM"),
    ("Add a rule: no speculation.", "INSTRUCTION", "no speculation.", "MEDIUM"),
    ("Use Wikipedia.", "PREFER_SOURCE", "Wikipedia", "MEDIUM"),
])
def test_constraint_slots(text, action, target, priority):
    found = slots.extract_constraint(text)
    assert (found.action, found.target, found.priority) == (action, target, priority)


@pytest.mark.parametrize("text,expected", [
    ("Change the task to compare only pricing.", "Compare only pricing."),
    ("New task: compare managed databases on the three clouds.", "Compare managed databases on the three clouds."),
    ("The task is now to compare machine learning platforms.", "Compare machine learning platforms."),
    ("Narrow the task to serverless offerings only.", "Narrow the task to serverless offerings only."),  # no pattern: whole sentence
])
def test_new_task_text(text, expected):
    assert slots.extract_new_task(text) == expected


class FakeConstraint:
    def __init__(self, target, description):
        self.target, self.description = target, description


def test_matching_the_constraint_to_remove():
    wiki = FakeConstraint("Wikipedia", 'Do not use sources from or about "Wikipedia".')
    docs = FakeConstraint("official documentation", 'Prefer sources from "official documentation".')
    ranked = slots.match_constraints("Remove the constraint about Wikipedia.", [docs, wiki])
    assert ranked[0][0] is wiki and ranked[0][1] >= 0.5 and all(c is not docs for c, _ in ranked)
    assert slots.match_constraints("Remove the last constraint.", [docs, wiki]) == []


def test_dataset_is_clean_and_documented():
    assert set(TRAIN) == set(TEST) == set(INTENTS) and len(INTENTS) == 13
    assert all(len(texts) >= 15 for texts in TRAIN.values()) and all(len(t) >= 3 for t in TEST.values())
    train_texts = [t.lower() for t, _ in TRAIN_EXAMPLES]
    assert len(train_texts) == len(set(train_texts)), "duplicate training sentences"
    assert not set(train_texts) & {t.lower() for t, _ in TEST_EXAMPLES}, "test sentences leaked into training"
    assert all(t.strip() for t, _ in TRAIN_EXAMPLES + TEST_EXAMPLES)