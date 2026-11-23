"""Smoke test for a running CoPilotHub AI stack.

    python scripts/smoke_test.py                      # backend at http://localhost:8000
    python scripts/smoke_test.py --base http://localhost:8000 --timeout 180

Needs only `httpx` (pip install httpx). Creates a throw-away user and session, runs the agent,
approves the final draft if asked, and checks the report and analytics."""
import argparse
import sys
import time
import uuid

import httpx

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=180, help="seconds to wait for the agent")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.base, timeout=20)

    try:
        health = client.get("/health")
    except httpx.HTTPError as exc:
        print(f"Cannot reach {args.base}: {exc}")
        return 2
    check("backend is up", health.status_code == 200)
    check("database is connected", client.get("/health/db").status_code == 200)

    tag = uuid.uuid4().hex[:8]
    email, password = f"smoke_{tag}@example.com", "SmokeTest123"
    r = client.post("/auth/register", json={"email": email, "username": f"smoke_{tag}", "full_name": "Smoke Test", "password": password})
    check("registration", r.status_code == 201, r.text)
    r = client.post("/auth/login", json={"email": email, "password": password})
    check("login", r.status_code == 200, r.text)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    check("current user", client.get("/auth/me", headers=headers).json().get("email") == email)
    check("wrong password is refused", client.post("/auth/login", json={"email": email, "password": "WrongPass123"}).status_code == 401)
    check("anonymous access is refused", client.get("/sessions").status_code == 401)

    status = client.get("/system/status", headers=headers).json()
    print(f"      engine: {'demo' if status.get('demo_mode') else status['llm']['provider'] + '/' + status['llm']['model']}, "
          f"approval required: {status.get('require_final_approval')}")

    r = client.post("/sessions", headers=headers, json={
        "name": f"Smoke {tag}", "task": "Prepare a report comparing AWS, Microsoft Azure and Google Cloud for a small startup"})
    check("session created", r.status_code == 201, r.text)
    sid = r.json()["id"]
    check("invite codes issued", len(r.json()["editor_code"]) == 8 and len(r.json()["viewer_code"]) == 8)

    r = client.post(f"/sessions/{sid}/interventions", headers=headers, json={"type": "REJECT_SOURCE", "target": "Wikipedia"})
    check("structured constraint created", r.status_code == 201, r.text)
    check("constraint is active", [c["target"] for c in client.get(f"/sessions/{sid}/constraints", headers=headers).json()] == ["Wikipedia"])

    check("agent started", client.post(f"/sessions/{sid}/start", headers=headers).status_code == 200)
    deadline, approved, state = time.time() + args.timeout, False, {}
    while time.time() < deadline:
        state = client.get(f"/sessions/{sid}/state", headers=headers).json()
        if state["status"] == "WAITING_FOR_APPROVAL" and state.get("pending_approval") and not approved:
            check("agent asks for approval of the final draft", True)
            approved = client.post(f"/sessions/{sid}/interventions", headers=headers, json={"type": "APPROVE"}).status_code == 201
            check("approval accepted", approved)
        if state["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    check("agent completed", state.get("status") == "COMPLETED", f"last status: {state.get('status')}")

    events = client.get(f"/sessions/{sid}/events?limit=500", headers=headers).json()
    used = [s for e in events if e["type"] == "TOOL_COMPLETED" for s in e["payload"].get("sources", [])]
    check("rejected source never used", all(s.get("publisher") != "Wikipedia" for s in used))
    r = client.get(f"/sessions/{sid}/report", headers=headers)
    if r.status_code == 200:
        check("final report has 10 sections", len(r.json()["sections"]) == 10)
    else:
        print("[SKIP] final report (AGENT_GENERATE_FINAL_REPORT may be off)")
    analytics = client.get(f"/sessions/{sid}/analytics", headers=headers)
    check("analytics available", analytics.status_code == 200 and analytics.json()["steps_completed"] > 0)
    check("session deleted", client.delete(f"/sessions/{sid}", headers=headers).status_code == 204)

    print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} CHECK(S) FAILED: " + ", ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())