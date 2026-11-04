# CoPilotHub AI

A collaborative human-in-the-loop platform for controlling AI agents.
Multiple users join the same live agent session, watch it work, and turn
their feedback into structured interventions and constraints that change
the agent's future behaviour.

> Status: Phase 1 (foundation) and Phase 2 (authentication) complete.

## Technology stack (free / open-source only)
React, TypeScript, Vite, Tailwind CSS · FastAPI, SQLAlchemy, Alembic ·
PostgreSQL · JWT + bcrypt · Docker Compose.
Later phases add LangGraph, Ollama + Qwen3, Sentence Transformers, FAISS,
scikit-learn and XGBoost. No paid APIs are required anywhere.

## Quick start (Docker)
```bash
cp .env.example .env        # then edit SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
```
- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

## Local development (without Docker for the app)
```bash
# 1. database only
docker compose up -d db

# 2. backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # edit values
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. frontend (new terminal)
cd frontend
npm install
npm run dev
```

## Tests
```bash
cd backend && pytest -v
```

## Git
```bash
git init
git add .
git commit -m "Phase 1-2: foundation and authentication"
git branch -M main
git remote add origin https://github.com/<your-username>/copilothub-ai.git
git push -u origin main
```

## Roadmap
15 phases: foundation, auth, sessions, WebSockets, agent, local LLM,
interventions, constraints and memory, conflicts, RAG, tools, NLP classifier,
ML predictor, reports and analytics, final polish.