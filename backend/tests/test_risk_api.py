import pytest

from app.core.config import get_settings
from app.ml import service as risk_service
from helpers import ScriptedBrain, create_session, make_running_session, make_user, read_until
from seed import seed_history

pytestmark = pytest.mark.usefixtures("ml_sandbox")


def test_risk_endpoint_for_a_seeded_session(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "risk_prediction_enabled", True)
    sid = make_running_session(client)
    seed_history(client, sid)
    headers, _ = make_user(client, "owner")
    r = client.get(f"/sessions/{sid}/risk", headers=headers).json()
    assert r["available"] and 0.0 <= r["probability"] <= 1.0 and r["level"] in ("LOW", "MEDIUM", "HIGH")
    assert r["step_index"] == 3 and r["data_source"] == "synthetic" and "SYNTHETIC" in r["warning"]
    assert r["model"] in ("logistic_regression", "random_forest", "xgboost")
    assert all({"feature", "label", "effect", "value"} <= set(f) for f in r["factors"])


def test_risk_endpoint_edge_cases(client, monkeypatch):
    headers, _ = make_user(client, "owner")
    s = create_session(client, headers)
    monkeypatch.setattr(get_settings(), "risk_prediction_enabled", False)
    assert client.get(f"/sessions/{s['id']}/risk", headers=headers).json()["reason"] == "Risk prediction is switched off"
    monkeypatch.setattr(get_settings(), "risk_prediction_enabled", True)
    assert "No step" in client.get(f"/sessions/{s['id']}/risk", headers=headers).json()["reason"]
    stranger, _ = make_user(client, "stranger")
    assert client.get(f"/sessions/{s['id']}/risk", headers=stranger).status_code == 404
    assert client.get(f"/sessions/{s['id']}/risk").status_code == 401


def test_the_agent_estimates_the_risk_after_every_step(client, monkeypatch, set_brain):
    monkeypatch.setattr(get_settings(), "risk_prediction_enabled", True)
    set_brain(ScriptedBrain(steps=3))
    headers, token = make_user(client, "owner")
    s = create_session(client, headers)
    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        ws.receive_json()
        client.post(f"/sessions/{s['id']}/start", headers=headers)
        seen = read_until(ws, {"COMPLETED", "FAILED"})
    assert seen[-1] == "COMPLETED" and seen.count("RISK_UPDATED") == 3

    events = client.get(f"/sessions/{s['id']}/events?limit=500", headers=headers).json()
    updates = [e["payload"] for e in events if e["type"] == "RISK_UPDATED"]
    assert sorted(u["step_index"] for u in updates) == [1, 2, 3] and all(u["data_source"] == "synthetic" for u in updates)
    analytics = client.get(f"/sessions/{s['id']}/analytics", headers=headers).json()
    assert analytics["risk"]["n"] == 3 and analytics["risk"]["data_source"] == "synthetic"


def test_a_failing_model_never_breaks_the_run(client, monkeypatch, set_brain):
    monkeypatch.setattr(get_settings(), "risk_prediction_enabled", True)
    monkeypatch.setattr(get_settings(), "risk_auto_train", False)  # no model and no training: estimates fail
    risk_service.reset_cache()
    set_brain(ScriptedBrain(steps=2))
    headers, token = make_user(client, "owner")
    s = create_session(client, headers)
    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        ws.receive_json()
        client.post(f"/sessions/{s['id']}/start", headers=headers)
        seen = read_until(ws, {"COMPLETED", "FAILED"})
    assert seen[-1] == "COMPLETED" and "RISK_UPDATED" not in seen


def test_ml_status_reports_the_real_comparison(client):
    headers, _ = make_user(client, "owner")
    assert client.get("/ml/status").status_code == 401
    assert client.get("/ml/status", headers=headers).json()["available"] is False
    risk_service.get_model()  # trains on synthetic data and writes the metrics file
    status = client.get("/ml/status", headers=headers).json()
    assert status["available"] and status["data_source"] == "synthetic" and "SYNTHETIC" in status["warning"]
    assert status["selected_model"] in status["models"] and status["n_rows"] == 600
    assert 0.0 <= status["models"][status["selected_model"]]["test"]["roc_auc"] <= 1.0
    assert "rule" in status["baseline"]