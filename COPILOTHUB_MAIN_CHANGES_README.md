# CoPilotHub AI — Unified Workflow & Usability Upgrade

This is a consolidated upgrade based on the source ZIP provided in this conversation. It includes the previous file-integrity/usability fixes **plus** the coordinated workflow changes. It is not a rewrite from scratch.

## Implemented in this package

- **One shared team workspace:** retained existing roles, real-time events, source versions, intervention history, existing AI providers and report exporters.
- **Domain profiles:** identify software, data/analytics, engineering/design, business/planning, education, content and general research. The workflow and expected deliverables are described in everyday language. These profiles are heuristics, **not separate specialist models**.
- **Sequential hybrid work:** research and coding no longer start at the same time. Hybrid sessions research first (up to three planning steps), then generate project files, then wait for owner review.
- **Durable collaborator change requests:** new `workflow_requests` database table; requests can be submitted while research or code generation runs. They are processed sequentially, versioned as before, and restored to the pending queue after a backend restart. On restart, interrupted projects pause rather than silently claiming success; select **Resume** to continue. This is a **single-backend-process** coordinator, not a distributed multi-worker queue.
- **Plain-language team requests:** a prominent **Ask your AI teammate** field routes code changes to the queue, while research/business input is retained as a shared project fact or comment. It does not depend on the optional trained NLP intent classifier.
- **Review-controlled delivery:** source versions require owner approval. If files change after approval, the review appears outdated. A HYBRID final report includes the research sections and the approved source snapshot.
- **Report visibility:** the Report page shows the latest saved working draft when no final report exists; it labels drafts plainly and only offers the complete-project download for approved coding/hybrid projects.
- **Safer generated files:** extracts unambiguous code fences, rejects mixed C++/Python source signatures, retries malformed per-file outputs once, and checks Python/JSON syntax. It does **not** execute untrusted generated code or compile C++.
- **Simpler interface:** activity, tool traces, risk details and memory history are collapsed by default; user-facing status and review labels are clearer.
- **Existing optional model failover:** preserved from the uploaded code. The fallback remains disabled unless a genuine second provider is configured.

## Limitations (important)

- Full automated backend/frontend suites and a live Ollama workflow **were not run in the packaging environment**. Python compilation, TypeScript syntax parsing, and isolated generation/profile checks succeeded. The full suites must run in your Docker environment.
- This is a **single-process implementation**. Do not scale the backend to multiple Uvicorn/Gunicorn workers without distributed locking, durable worker leases, and idempotent jobs.
- Queued user instructions survive restarts, but in-progress inference cannot resume from the exact token. Affected coding/hybrid sessions are paused for explicit **Resume**. Saved files/versions are preserved.
- Actual external web-search/research quality requires a working research provider; simulated search results are not verified evidence.
- Business, engineering, analytics and writing projects can use the general planning, evidence, notes, review and document workflow. Native CAD, spreadsheet generation, slide editing, and field-specific tool integrations are **not** implemented by this upgrade.
- AI-generated C++/Java/JS code is **not** compiled or runtime-tested by the backend. Approval records a human's review, not proof of correctness.
- Optional fallback provider credentials/settings must be configured separately. A second local Ollama model on the same CPU may also time out.

## Required migration

The update adds `backend/alembic/versions/0014_workflow_requests.py`. The standard Docker startup applies Alembic migrations automatically; confirm migration revision `0014` after rebuilding.

## Apply safely on Windows

1. Make sure no AI job is running and create a backup or commit your working tree first.
2. Download the **patch ZIP** to Desktop, extract to a temporary folder, and run `apply_upgrade.py` from there. The installer backs up every overwritten file into `.copilothub-upgrade-backup/` in the project root.
3. From the project root, rebuild and test:

```powershell
docker compose up -d --build backend frontend
docker compose exec backend alembic current
docker compose exec backend python -m pytest -q
cd frontend
npm test -- --run
npm run build
cd ..
docker compose ps
```

4. For a focused run before the full suite:

```powershell
docker compose exec backend python -m pytest -q tests/test_workflow_foundation.py tests/test_automatic_code_routing.py tests/test_code_review_workflow.py tests/test_source_file_integrity.py
```

5. Do not commit/push unless these tests pass. If something fails, share the **first failing test plus traceback**, not just the summary.

## End-to-end acceptance checks

1. **CODING:** Generate a Python calculator; confirm file versions, review request, reject once with feedback, regenerate, approve, final report, and ZIP.
2. **HYBRID:** Ask to compare Python/C++ and implement calculators. Confirm research starts first and code starts afterwards. While research runs, request a Java version from **Ask your AI teammate**; confirm it is queued. Approve the final code and check the report includes research + code.
3. **MULTI-DOMAIN:** Create a market analysis or engineering-planning task. Confirm the field profile, shared instructions, working report, and correct evidence caveats. No irrelevant code should be required.
4. **RESTART:** While a coding session is working, restart backend. Confirm saved files and queued requests remain, session displays **PAUSED**, and **Resume** restarts work from saved artifacts.
5. **FALLBACK:** Test an intentionally unreachable primary model **only after configuring a real fallback**, and verify the alternative is used. Model fallback does not guarantee correct content.

## How to revert

Restore affected files from `.copilothub-upgrade-backup/` and rebuild. Database migration `0014` can be rolled back with `alembic downgrade 0013` **only if no workflow requests need retaining**; data in that table will be deleted. Prefer a database backup before any migration.
