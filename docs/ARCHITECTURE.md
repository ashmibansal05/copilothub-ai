# Architecture

## 1. Layers
| Layer | Responsibility | Code |
|---|---|---|
| UI | Live workspace, dialogs, analytics, reports | `frontend/src` |
| API | REST + WebSocket, authentication, role checks, rate limits | `backend/app/api`, `app/websocket` |
| Services | Interventions, constraints, memory, conflicts, reports, analytics | `backend/app/services` |
| Agent | LangGraph orchestrator, brains (demo / LLM), runner | `backend/app/agents`, `app/llm` |
| Tools | Validated registry and 7 tools | `backend/app/tools` |
| Knowledge | RAG: extraction, chunking, embeddings, FAISS | `backend/app/rag` |
| Intelligence | NLP intent classifier, ML risk predictor | `backend/app/nlp`, `app/ml` |
| Data | PostgreSQL models and migrations | `backend/app/models`, `alembic` |

## 2. One intervention, end to end
```
user types "Do not use Wikipedia."
  → POST /sessions/{id}/instructions
  → NLP: embedding → classifier → REJECT_SOURCE (probability) → slot rule → target "Wikipedia"
  → policy: confident + not high-impact → apply          (otherwise: ask the user to confirm)
  → intervention processor: role check → validate → store Intervention (audit)
        → create Constraint(EXCLUDE_SOURCE, HIGH) + Memory(REJECTED_SOURCE)
        → conflict check against existing constraints
  → events: CONSTRAINT_ADDED, HUMAN_INTERVENTION   (broadcast to everyone in the session)
  → next agent step: constraints rendered into the prompt AND every tool result is filtered in code
```

## 3. Agent graph
```
START → plan → act → observe → evaluate ─┬→ act        (next step or retry)
                                         ├→ plan       (task changed by a human)
                                         └→ finalize ─┬→ END         (approved)
                                                      ├→ finalize    (draft rejected: revise, max rounds)
                                                      └→ plan        (task changed)
```
`act` first waits for a requested review and for unresolved blocking conflicts. In tool mode, `act` runs a bounded
loop: the brain proposes one tool call, the registry validates and runs it, the result goes back (fenced as untrusted data).

## 4. Where the rules are enforced (never only in the prompt)
| Rule | Enforcement point |
|---|---|
| Role permissions | `intervention_service.ROLE_PERMISSIONS`, `require_session_role` (backend) |
| Excluded / preferred sources | `ConstraintManager.filter_sources` after **every** tool call, inside `retrieve_chunks`, and again when the report is built |
| Tool allow-list and arguments | `ToolRegistry.execute` (unknown tool, schema, size, timeout) |
| Contradictions | `ConflictManager` priority rules; ties block the agent until the owner decides |
| Approval | `approval_gate` blocks the graph on a Future that only the intervention API can resolve |
| Limits | steps, retries, timeouts, runtime budget, tool-call budgets, approval rounds, re-plans |

## 5. Real-time events
Server → client only (clients send just `PING`; all mutations use REST so permissions live in one place).
Persisted: `AGENT_STARTED, STATUS_CHANGED, AGENT_MESSAGE, PAUSED, RESUMED, STEP_STARTED, STEP_COMPLETED,
TOOL_STARTED, TOOL_COMPLETED, COMPLETED, FAILED, HUMAN_INTERVENTION, CONSTRAINT_ADDED, CONSTRAINT_REMOVED,
APPROVAL_REQUESTED, APPROVAL_COMPLETED, CONFLICT_DETECTED, CONFLICT_RESOLVED, DOCUMENT_*, REPORT_SAVED, RISK_UPDATED`.
Ephemeral: `CONNECTED, PONG, USER_JOINED, USER_LEFT, MEMBER_JOINED`.

## 6. Data model (summary)
`sessions` 1─* `session_members` (role) · `sessions` 1─* `agent_events` / `agent_actions` / `interventions` /
`approvals` / `constraints` / `memory_items` / `conflicts` / `documents` (1─* `document_chunks`) / `sources` /
`tool_executions` / `reports` / `risk_predictions` · `sessions` 1─1 `agent_states`, `analytics_records` ·
`constraints` ─* `conflicts` (a, b, suggested winner). All session-owned tables cascade on delete.

## 7. Security notes
- **Authentication:** bcrypt hashes; JWT (60 min); tokens issued before a password change are rejected.
- **WebSocket:** first-message `AUTH` (no token in the URL), membership check, origin check, closes at token expiry.
- **Input:** Pydantic validation everywhere; SQLAlchemy parameters (no SQL injection); upload type + magic-byte + size + zip-bomb checks; server-generated storage paths.
- **Prompt injection:** trusted instructions only in the system message; task, constraints, notes, documents and tool results in separate fenced sections; heuristic filter for injected instructions in documents; tools cannot execute anything outside the registry.
- **Output:** report and document text is shown as plain text; HTML export escapes everything; API responses carry `nosniff`, CSP and `no-store`.
- **Abuse:** rate limits on login/register/join/instructions/uploads; request-size limit.
- **Audit:** every human action (`interventions`) and every tool call (`tool_executions`) is stored.
- **Not covered:** HTTPS termination, multi-process rate limiting, secrets management, account recovery. Put the app behind a TLS reverse proxy before any public exposure.

## 8. Key design decisions
1. **Constraints are data, enforced by code**, because a model can ignore a prompt.
2. **The model never resolves conflicts**; deterministic rules apply and ties go to a human.
3. **Honesty labels**: simulated results and synthetic-data models are marked everywhere they appear.
4. **One code path** for features in training and serving; one processor for buttons and free text.
5. **Everything optional fails soft** (risk estimate, report narrative, analytics never fail a run).