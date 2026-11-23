# CoPilotHub AI

**A collaborative human-in-the-loop platform for controlling AI agents.**

Several people join the same live AI-agent session, watch the agent work in real time, and steer it
*while it is running*. Their feedback does not stay a chat message: it becomes **structured
interventions and constraints** (for example `{"type":"CONSTRAINT","action":"EXCLUDE_SOURCE","target":"Wikipedia","priority":"HIGH"}`)
that the agent is *forced* to respect.

Everything runs **locally with free and open-source software**. No paid API and no API key is needed.

## Problem statement
Long-running AI agents act on their own for minutes or hours. Chat-style feedback is easy to ignore,
hard to audit, and breaks down when several people give contradicting instructions. Teams need to
supervise an agent *during* execution, with clear roles, enforceable rules, explicit approvals and a record of
who decided what.

## Objectives
1. Let multiple users share and observe one running agent session in real time.
2. Turn human feedback into structured, enforceable, auditable constraints and decisions.
3. Detect contradicting instructions and make a human resolve them, never the model.
4. Require human approval at key checkpoints (final report, reviews).
5. Keep the agent safe: approved tools only, validated inputs, no shell, prompt-injection defences.
6. Collect the data needed to study whether structured human intervention improves agent reliability.

## Features
- Real-time shared sessions (WebSockets), roles **Owner / Editor / Viewer** enforced on the backend.
- Agent loop **plan → act → observe → evaluate → continue/complete**, built with LangGraph, with limits, retries, timeouts and escalation.
- Interventions: approve, reject, correct, pause, resume, modify task, add information, constraints, reject/change source, request review, comment.
- Free-text instructions classified by an ML model (with confirmation for low confidence or high-impact actions).
- Structured **constraints** enforced in code (exclude, prefer, allow sources) plus structured **memory** with selective retrieval.
- **Conflict detection and resolution** with priority rules and explicit owner decisions.
- **RAG**: upload PDF/DOCX/TXT/Markdown, Sentence-Transformer embeddings, FAISS search, source metadata, rejected-source filtering.
- **Seven approved tools** with a validating registry and a full audit log.
- **ML intervention-risk predictor** (Logistic Regression, Random Forest, XGBoost; honestly labelled synthetic until real data exists).
- **Final research report** (10 sections; facts assembled from the database), downloadable as Markdown, HTML, Word.
- **Analytics dashboard** and research-metrics export (CSV).
- Security: JWT, bcrypt, RBAC, rate limiting, security headers, WebSocket auth with token expiry, upload validation, audit logging.
- Demo mode (no LLM needed) and local LLM mode (Ollama + Qwen3).

## Architecture
```
 React UI (Vite, Tailwind, Recharts) ── REST + WebSocket ──► FastAPI
                                                              │
        ┌──────────────┬─────────────┬────────────────────────┼──────────────────────┐
        ▼              ▼             ▼                        ▼                      ▼
  Intervention     Constraint    Conflict              Agent orchestrator       RAG service
  processor        manager +     manager               (LangGraph)              (FAISS +
  (+ NLP intent    memory                              │                        Sentence-
   classifier)                                         ├─► Brain: Qwen3 via     Transformers)
        │                                              │   Ollama, or demo
        └──────────────► PostgreSQL ◄──────────────────┤
                                                       └─► Tool registry ─► search_web · retrieve_documents ·
                                                           (validated)       read_document · summarize_document ·
                                                                             compare_sources · calculate · save_report
```
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology stack (all free / open source)
React · TypeScript · Vite · Tailwind CSS · React Router · Axios · Lucide · Recharts ·
Python · FastAPI · Pydantic · SQLAlchemy · Alembic · WebSockets · PostgreSQL ·
LangGraph · Ollama + Qwen3 · Sentence-Transformers · FAISS · PyTorch ·
scikit-learn · XGBoost · pandas · NumPy · pypdf · python-docx · BeautifulSoup · Markdown ·
JWT · bcrypt · Docker · Docker Compose · pytest · Vitest · GitHub Actions.

## System workflow
1. A user creates a session (task + invite links for editors and viewers).
2. Others join through `/join/CODE`. The invite code decides the role.
3. The owner starts the agent. It plans, then runs each step with tools, and everybody sees steps, tool calls, sources and confidence live.
4. People intervene with buttons or plain English. Each intervention is permission-checked, stored, and applied.
5. Contradicting instructions create a **conflict**; the owner resolves it.
6. The agent asks for **approval** of its final draft; on approval it writes the final report.
7. Analytics and a research snapshot are stored.

## AI / ML components
| Component | Technique | Where |
|---|---|---|
| Agent reasoning, report narrative | Local LLM (Qwen3 via Ollama) or demo script | `app/agents`, `app/llm` |
| **NLP**: free text → intent | Sentence-Transformer embedding → Logistic Regression (13 intents) + rule-based slot filling | `app/nlp` |
| **RAG**: semantic document search | Sentence-Transformer embeddings → FAISS | `app/rag` |
| Memory relevance | Embedding cosine similarity + importance + recency | `app/services/memory_manager.py` |
| **Intervention predictor** | Logistic Regression / Random Forest / XGBoost on 18 session features | `app/ml` |

*Honesty notes:* demo mode is a scripted agent, not a model. The NLP dataset is small, synthetic and
hand-written. The risk predictor trains on **synthetic** data until real sessions exist. Training scripts print
the real evaluation; no figure in this project is invented. Run `python -m app.nlp.train` and `python -m app.ml.train`.

## Agent architecture
LangGraph graph: `plan → act → observe → evaluate → (act | plan | finalize)`; `finalize → (END | finalize | plan)`.
Before acting, the agent waits for pending reviews or unresolved conflicts. Limits: max steps, per-step timeout,
runtime budget (human waiting time excluded), retries, max tool calls per step and per run, max approval rounds, max re-plans.

## Database architecture
PostgreSQL via SQLAlchemy/Alembic (12 migrations). Main tables: `users`, `sessions`, `session_members`,
`agent_states`, `agent_actions`, `agent_events`, `interventions`, `approvals`, `constraints`, `memory_items`,
`conflicts`, `documents`, `document_chunks`, `sources`, `tool_executions`, `reports`, `intent_samples`,
`risk_predictions`, `analytics_records`. Foreign keys cascade from `sessions`.

## Security
JWT + bcrypt; roles checked **on the server** for every action; WebSocket authenticated by a first message
(token never in the URL) and closed at token expiry; password change revokes older tokens; rate limiting; security
headers; request-size limit; strict CORS; upload validation (type, magic bytes, size, zip-bomb guard); prompt-injection
defences (separated and fenced prompt sections, tool results treated as data, heuristic filtering); no shell or URL-fetch tools;
validated tool arguments; audit log; escaped exports. See the security notes in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Installation
**Full step-by-step guide for Windows, macOS and Linux: [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md).** In short:
```bash
cp .env.example .env                 # then set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build            # frontend: http://localhost:5173   API docs: http://localhost:8000/docs
```

## Environment variables
Root `.env` (used by Docker) and `backend/.env` (used when running locally). The important ones:

| Variable | Meaning | Default |
|---|---|---|
| `SECRET_KEY` | signs login tokens (**generate your own**, 32+ chars) | none |
| `DATABASE_URL` | PostgreSQL connection | none |
| `DEMO_MODE` | `true` = scripted demo agent, `false` = use the local LLM | `true` |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | local LLM server and model | `http://localhost:11434`, `qwen3` |
| `EMBEDDING_BACKEND` | `sentence_transformers` or `hashing` (offline) | `sentence_transformers` |
| `WEB_SEARCH_PROVIDER` | `demo`, `searxng`, `duckduckgo` | `demo` |
| `AGENT_REQUIRE_FINAL_APPROVAL` | human approval before finishing | `true` |
| `RATE_LIMIT_ENABLED` | request throttling | `true` |

All variables are listed in `backend/.env.example`. **No variable needs an API key.**

## Local LLM, Ollama and Qwen3
Install Ollama (https://ollama.com), then `ollama pull qwen3` (or `qwen3:4b` / `qwen3:1.7b` on small machines),
set `DEMO_MODE=false`, restart the backend, and check `GET /llm/status`. See the setup guide.

## Running, testing
```bash
# backend (from backend/)         pytest -q
# frontend (from frontend/)       npm test
# running stack                   python scripts/smoke_test.py
# files present?                  python scripts/check_files.py
```

## Demo workflow
[docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) is a 19-step script for the evaluation. The automated version is `backend/tests/test_integration_flow.py`.

## Project limitations
- Single backend process (in-memory WebSocket rooms, agent tasks, rate limits). Scaling out needs Redis or similar.
- The demo agent is scripted; its web results are simulated and labelled. Real search is optional (SearXNG / DuckDuckGo).
- Local models (especially small ones) can ignore the tool or JSON protocol; the system retries and reports failures.
- NLP classifier: small synthetic dataset, English only, one instruction at a time. Risk predictor: synthetic until real data exists.
- Conflict detection covers source-policy contradictions only, not contradictions between free-text instructions.
- No OCR for scanned PDFs, no HTTPS or reverse proxy included, no email, no password reset flow.
- Reports are as good as the engine; facts come from records but the narrative can be wrong. Humans must review it.
- Not hardened for exposure to the public internet.

## Future scope
Redis-backed rooms and horizontal scaling · OAuth/SSO and password reset · semantic detection of contradicting
instructions · calibrated, retrained risk models on real sessions · `ASK_AGENT` (questions answered mid-run) · OCR and
more document types · richer tools (code sandbox, spreadsheets) with per-tool approvals · multi-agent sessions ·
controlled experiments (with/without human intervention) · PDF export and shareable read-only report links · i18n.

## Git and GitHub
```bash
git init
git add .
git commit -m "CoPilotHub AI"
git branch -M main
git remote add origin https://github.com/<your-username>/copilothub-ai.git
git push -u origin main
```
Never commit `.env` (it is in `.gitignore`).