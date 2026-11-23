import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.intent_sample import IntentSample
from app.nlp import classifier as clf_module
from app.nlp.classifier import Prediction
from helpers import create_session, join, make_user

pytestmark = pytest.mark.usefixtures("disable_agent")


class FakeClassifier:
    """Deterministic stand-in so the POLICY and WIRING are tested independently of model quality."""

    def __init__(self, mapping, default=("COMMENT", 0.9)):
        self.mapping, self.default = mapping, default

    def predict(self, texts, embedder):
        out = []
        for t in texts:
            intent, conf = self.mapping.get(t, self.default)
            out.append(Prediction(intent, conf, {intent: conf, "COMMENT": 1 - conf} if intent != "COMMENT" else {"COMMENT": conf}))
        return out


@pytest.fixture()
def fake(monkeypatch):
    def install(mapping, default=("COMMENT", 0.9)):
        monkeypatch.setattr(clf_module, "get_classifier", lambda: FakeClassifier(mapping, default))

    return install


def setup(client):
    owner, _ = make_user(client, "owner")
    editor, _ = make_user(client, "editor1")
    viewer, _ = make_user(client, "viewer1")
    s = create_session(client, owner)
    join(client, editor, s["editor_code"])
    join(client, viewer, s["viewer_code"])
    return s["id"], owner, editor, viewer


def say(client, headers, sid, text, dry_run=False):
    r = client.post(f"/sessions/{sid}/instructions", json={"text": text, "dry_run": dry_run}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def constraints(client, headers, sid):
    return client.get(f"/sessions/{sid}/constraints", headers=headers).json()


def test_confident_reject_source_is_applied_as_a_structured_constraint(client, fake):
    sid, owner, editor, _ = setup(client)
    text = "Do not use Wikipedia."
    fake({text: ("REJECT_SOURCE", 0.95)})
    r = say(client, editor, sid, text)
    assert r["applied"] and not r["needs_confirmation"] and r["method"] == "model" and r["intent"] == "REJECT_SOURCE"
    assert r["proposal"]["target"] == "Wikipedia" and r["intervention"]["details"]["origin_text"] == text
    (c,) = constraints(client, owner, sid)
    assert (c["action"], c["target"], c["priority"], c["status"], c["created_by_username"]) == (
        "EXCLUDE_SOURCE", "Wikipedia", "HIGH", "ACTIVE", "editor1")
    with client.session_factory() as db:
        sample = db.scalar(select(IntentSample))
        assert (sample.text, sample.predicted_intent, sample.final_type, sample.outcome) == (text, "REJECT_SOURCE", "REJECT_SOURCE", "AUTO_APPLIED")


def test_low_confidence_asks_instead_of_acting(client, fake):
    sid, owner, editor, _ = setup(client)
    fake({"Maybe skip Wikipedia?": ("REJECT_SOURCE", 0.5)})
    r = say(client, editor, sid, "Maybe skip Wikipedia?")
    assert not r["applied"] and r["needs_confirmation"] and "50%" in r["reason"]
    assert r["proposal"]["type"] == "REJECT_SOURCE" and r["proposal"]["target"] == "Wikipedia"
    assert constraints(client, owner, sid) == []


def test_high_impact_intents_always_need_confirmation(client, fake):
    sid, owner, editor, _ = setup(client)
    fake({"Looks good, approved.": ("APPROVE", 0.999), "Change the task to compare only pricing.": ("MODIFY_TASK", 0.99)})
    approve = say(client, owner, sid, "Looks good, approved.")
    assert approve["needs_confirmation"] and not approve["applied"] and "confirm" in approve["reason"]
    modify = say(client, owner, sid, "Change the task to compare only pricing.")
    assert modify["needs_confirmation"] and modify["proposal"]["content"] == "Compare only pricing."
    assert client.get(f"/sessions/{sid}", headers=owner).json()["task"].startswith("Prepare a report")


def test_missing_detail_requires_confirmation(client, fake):
    sid, owner, editor, _ = setup(client)
    fake({"Don't use it.": ("REJECT_SOURCE", 0.99)})
    r = say(client, editor, sid, "Don't use it.")
    assert r["needs_confirmation"] and r["proposal"]["target"] is None and "missing" in r["reason"]
    assert constraints(client, owner, sid) == []


def test_dry_run_never_applies(client, fake):
    sid, owner, editor, _ = setup(client)
    fake({"Stop using Wikipedia.": ("REJECT_SOURCE", 0.99)})
    r = say(client, editor, sid, "Stop using Wikipedia.", dry_run=True)
    assert not r["applied"] and not r["needs_confirmation"] and r["proposal"]["target"] == "Wikipedia"
    assert constraints(client, owner, sid) == []


def test_roles_are_enforced(client, fake):
    sid, owner, editor, viewer = setup(client)
    fake({"Change the task to compare pricing only.": ("MODIFY_TASK", 0.99)})
    assert client.post(f"/sessions/{sid}/instructions", json={"text": "Pause please"}, headers=viewer).status_code == 403
    r = say(client, editor, sid, "Change the task to compare pricing only.")
    assert not r["allowed"] and not r["needs_confirmation"] and "may not perform" in r["reason"]


def test_preferences_and_swaps_become_structured_constraints(client, fake):
    sid, owner, editor, _ = setup(client)
    fake({
        "Use official cloud provider documentation.": ("ADD_CONSTRAINT", 0.9),
        "Replace Wikipedia with official documentation.": ("CHANGE_SOURCE", 0.9),
    })
    assert say(client, editor, sid, "Use official cloud provider documentation.")["applied"]
    assert say(client, owner, sid, "Replace Wikipedia with official documentation.")["applied"]
    found = {(c["action"], c["target"]) for c in constraints(client, owner, sid)}
    assert found == {("PREFER_SOURCE", "official documentation"), ("EXCLUDE_SOURCE", "Wikipedia")}


def test_contradictory_free_text_creates_a_conflict(client, fake):
    sid, owner, editor, _ = setup(client)
    editor2, _ = make_user(client, "editor2")
    code = client.get(f"/sessions/{sid}", headers=owner).json()["editor_code"]
    join(client, editor2, code)
    fake({"Use Wikipedia.": ("ADD_CONSTRAINT", 0.9), "Do not use Wikipedia.": ("REJECT_SOURCE", 0.95)})
    assert say(client, editor, sid, "Use Wikipedia.")["applied"]
    assert say(client, editor2, sid, "Do not use Wikipedia.")["applied"]
    conflicts = client.get(f"/sessions/{sid}/conflicts?status=OPEN", headers=owner).json()
    assert len(conflicts) == 1 and conflicts[0]["constraint_a"]["action"] == "PREFER_SOURCE"


def test_remove_constraint_is_matched_confirmed_and_learned_from(client, fake):
    sid, owner, editor, _ = setup(client)
    client.post(f"/sessions/{sid}/constraints", json={"action": "EXCLUDE_SOURCE", "target": "Wikipedia"}, headers=owner)
    client.post(f"/sessions/{sid}/constraints", json={"action": "PREFER_SOURCE", "target": "official documentation"}, headers=owner)
    text = "Remove the constraint about Wikipedia."
    fake({text: ("REMOVE_CONSTRAINT", 0.97)})
    r = say(client, owner, sid, text)
    assert r["needs_confirmation"] and not r["applied"] and r["proposal"]["constraint_id"]
    assert len(constraints(client, owner, sid)) == 2

    body = {"type": "REMOVE_CONSTRAINT", "constraint_id": r["proposal"]["constraint_id"], "origin_text": text}
    assert client.post(f"/sessions/{sid}/interventions", json=body, headers=owner).status_code == 201
    assert [c["target"] for c in constraints(client, owner, sid)] == ["official documentation"]
    with client.session_factory() as db:
        assert db.scalar(select(IntentSample)).final_type == "REMOVE_CONSTRAINT"  # the real outcome was recorded


def test_pause_and_resume_apply_to_a_running_session(client, fake):
    sid, owner, editor, _ = setup(client)
    client.post(f"/sessions/{sid}/start", headers=owner)
    fake({"Pause the research for now.": ("PAUSE", 0.9), "Resume": ("RESUME", 0.9)})
    assert say(client, editor, sid, "Pause the research for now.")["applied"]
    assert client.get(f"/sessions/{sid}", headers=owner).json()["status"] == "PAUSED"
    assert say(client, editor, sid, "Resume")["applied"]
    assert client.get(f"/sessions/{sid}", headers=owner).json()["status"] == "RUNNING"


def test_a_state_conflict_is_reported_not_raised(client, fake):
    sid, owner, editor, _ = setup(client)  # not started: nothing to pause
    fake({"Pause": ("PAUSE", 0.95)})
    r = say(client, editor, sid, "Pause")
    assert not r["applied"] and r["needs_confirmation"] and "Cannot pause" in r["reason"]


def test_questions_are_kept_as_comments(client, fake):
    sid, owner, editor, _ = setup(client)
    fake({"Why did you choose AWS first?": ("QUESTION", 0.8)})
    r = say(client, editor, sid, "Why did you choose AWS first?")
    assert r["applied"] and r["intervention"]["type"] == "COMMENT" and "saved as comments" in r["note"]


def test_auto_apply_can_be_switched_off(client, fake, monkeypatch):
    sid, owner, editor, _ = setup(client)
    monkeypatch.setattr(get_settings(), "nlp_auto_apply", False)
    fake({"Stop using Wikipedia.": ("REJECT_SOURCE", 0.99)})
    r = say(client, editor, sid, "Stop using Wikipedia.")
    assert r["needs_confirmation"] and "switched off" in r["reason"] and constraints(client, owner, sid) == []


def test_classifier_failure_falls_back_to_exact_commands_only(client, monkeypatch):
    sid, owner, editor, _ = setup(client)
    client.post(f"/sessions/{sid}/start", headers=owner)

    def broken():
        raise RuntimeError("model missing")

    monkeypatch.setattr(clf_module, "get_classifier", broken)
    r = say(client, editor, sid, "Pause")
    assert r["method"] == "rule" and r["applied"] and r["confidence"] == 1.0
    assert client.get(f"/sessions/{sid}", headers=owner).json()["status"] == "PAUSED"
    failure = client.post(f"/sessions/{sid}/instructions", json={"text": "Stop using Wikipedia."}, headers=editor)
    assert failure.status_code == 503 and "unavailable" in failure.json()["detail"]


def test_nlp_status_reports_real_numbers_or_nothing(client, tmp_path, monkeypatch):
    owner, _ = make_user(client, "owner")
    monkeypatch.setattr(clf_module, "model_dir", lambda: tmp_path)
    assert client.get("/nlp/status").status_code == 401
    assert client.get("/nlp/status", headers=owner).json() == {"available": False, **{k: None for k in [
        "embedder", "trained_at", "n_train", "n_test", "cv_accuracy", "cv_macro_f1", "held_out_accuracy", "dataset"]}}
    monkeypatch.setattr(clf_module, "_cached", None)
    clf_module.get_classifier()  # trains with the hashing backend and writes the metrics file
    status = client.get("/nlp/status", headers=owner).json()
    assert status["available"] and status["embedder"] == "hashing-lexical" and status["n_train"] == 234
    assert 0.0 <= status["held_out_accuracy"] <= 1.0 and 0.0 <= status["cv_accuracy"] <= 1.0