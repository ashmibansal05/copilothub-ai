# CoPilotHub AI: Phases 16–19 implementation package (initial integrated build)

This patch adds real source-code storage, revisions, model generation, collaborative APIs,
Source Code UI, ZIP downloads, report source listings, and static Python/JSON syntax checks.
This is **not** a verified complete implementation of all Phase 16–19 requirements.

## What is included

- New Alembic migration `0013_code_artifacts.py` adds code-artifact and immutable-version tables.
- Source-code REST API with session membership/role enforcement, optimistic version checks,
  individual downloads, complete source ZIP and optional report-inclusive ZIP.
- Ollama-backed per-file code generation/revisions via `POST /sessions/{id}/code/generate`.
  It runs asynchronously and emits `CODE_UPDATED` events to the existing WebSocket room.
- Source Code panel in the existing session workspace. The owner/editor can generate,
  view, edit, copy, download and revise code; viewers can read and download.
- Complete source file content is included in Section 11 of newly generated reports and
  in dynamically rendered legacy report downloads (the stored approved report remains intact).
- HTML exports escape generated code; DOCX code uses monospaced paragraphs.
- Python `ast.parse()` and JSON syntax validation. Other languages remain NOT_VALIDATED.
- New backend API/test cases and frontend component test.

## How to apply (Windows PowerShell)

Before applying, check Git and save a restore point:

```powershell
cd C:\Users\bansa\Desktop\copilothub-ai
git status
git switch -c feature/phase-16-19-code-workspace
```

Unzip the patch **at the repository root** (it contains `backend/` and `frontend/` paths):

```powershell
Expand-Archive -LiteralPath "C:\path\to\copilothub_phase16_19_patch.zip" -DestinationPath . -Force
```

Review changes before database migration:

```powershell
git diff --stat
git status
```

Start/rebuild your existing Docker stack (make sure Docker Desktop and Ollama are running):

```powershell
docker compose up -d --build
# Use the existing backend service name from docker-compose.yml.
docker compose exec backend alembic upgrade head
docker compose exec backend pytest -q
cd frontend
npm test -- --run
npm run build
```

Depending on your Docker container working directory, migration command may require
`docker compose exec backend sh -c "cd /app && alembic upgrade head"`.

**Important**: Migration creates new tables. Always take a database backup before
migrating a database that contains important session data.

## How to use

1. Open the session workspace at `http://localhost:5173` and open Source Code.
2. Create a new session with `Write C++ and Python code for a calculator`.
3. To avoid confusing research tools, generate code using the new **Generate Source Code** button
   after completing/stopping the old research workflow, or before starting it.
4. The code generator uses the real Ollama provider; `DEMO_MODE=true` will prevent it.
5. Wait for code generation events. The code panel refreshes while generation is active.
6. View, download and version files; the editor can make changes with optimistic locking.
7. Download Source ZIP or Project ZIP. View/download a report to see Section 11.

## API endpoints

- GET `/sessions/{id}/code` — metadata and generation progress
- POST `/sessions/{id}/code/generate` — start bounded model generation/revision
- GET `/sessions/{id}/code/{artifact_id}` — full file content and validation status
- GET `/sessions/{id}/code/{artifact_id}/versions` — file version history
- PUT `/sessions/{id}/code/{artifact_id}` — optimistic concurrency revision
- GET `/sessions/{id}/code/{artifact_id}/download` — file download
- GET `/sessions/{id}/code-export?complete=false` — sources ZIP
- GET `/sessions/{id}/code-export?complete=true` — source and latest FINAL report ZIP

## Known limitations / not yet complete

- The existing research orchestrator **has not** been replaced with full automatic coding
  routing: clicking Start still invokes the old research flow. Use the Source Code button
  explicitly for code generation. This protects Phases 1–15 but means Phase 16 is partial.
- Model file manifests and content may be unreliable using `llama3.2`; generated programs
  must be reviewed. Long multi-file projects may be incomplete or inconsistent.
- File-by-file generation is bounded, but does not implement a durable job queue. Jobs in
  progress are lost when backend restarts; saved earlier files remain.
- No secure runtime sandbox; arbitrary generated code is **not executed**. Python and JSON
  syntax checks are available; C++/Java/JS/TS compilation and tests are not yet implemented.
- No autonomous compiler-feedback revision or complete task-status redesign.
- The intervention-risk model is still experimental and trained on synthetic data.
- Report delivery merges **current** code into an older report when downloaded. This is
  clearly a convenience view, not a fixed approved snapshot of code as of report approval.
- A real production deployment should add export size/CPU limits, rate limits, a durable
  task queue, data retention, auditing, and per-file conflict-safe atomic writes.
- Frontend code viewer uses plain `<pre>` rather than syntax highlighting.

## Verification in this execution environment

- Python source and migration `compileall`: passed.
- Isolated SQLAlchemy schema creation and basic path/classification checks: passed.
- Full backend pytest suite: **not runnable here** because `faiss` and `langgraph`
  dependencies are missing and external package downloads are unavailable.
- Frontend typecheck/build: **not runnable here** because `node_modules` is absent.
- Ollama live integration: **not run here**. Must be tested on the user's system.
- New regression tests were authored but have not been executed in full.

Please run all commands and share test failures before deploying or merging.
