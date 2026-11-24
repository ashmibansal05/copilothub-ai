# CoPilotHub AI — Code Approval → Revision → Final Report Patch

This is a **focused patch**, designed to apply **after** the earlier Phase 16–19, automatic-coding, and progress-speed ZIPs. It does NOT replace `coding_agent.py` or your existing task-classifier fix.

## What changes

- Automatic coding tasks now stop at **WAITING_FOR_APPROVAL**, not COMPLETED.
- Generated source files are saved and visible in the **Source Code** tab before approval.
- A **Code Review** panel shows the owner: **Approve code and finalize report** or **Request changes** with mandatory feedback.
- **Request changes** starts an AI revision automatically using reviewer feedback, then returns to approval after regeneration. The existing versions remain available.
- **Approve** locks a snapshot of the approved code into a **FINAL** project report, then marks the session COMPLETED.
- File edits invalidate outstanding approvals; completed reports remain immutable. A new review is needed for later edits.
- Complete-project ZIP is available only after a FINAL report exists, and refuses to mix previously approved report text with newer source versions.
- Pending code approvals survive backend restarts. Running generation interrupted by a restart may still fail and must be retried.
- Report tab explains that the owner must approve source files before the FINAL report is available.
- Coding timeline no longer shows `Step undefined/2`.
- No database migrations are needed: the existing Approval and Report models are reused.

## Installation (PowerShell, from repository root)

1. Ensure no source-generation job is running; avoid modifying files mid-job.
2. Make a new local backup or Git commit of your current work, and stay on `feature/phase-16-19-code-workspace`.
3. Extract the ZIP over your existing repo (the patch contains only changed files):

```powershell
cd C:\Users\bansa\Desktop\copilothub-ai
Expand-Archive -LiteralPath "$env:USERPROFILE\Desktop\copilothub_code_approval_patch.zip" -DestinationPath . -Force
```

4. Rebuild and run tests:

```powershell
docker compose up -d --build backend frontend
docker compose exec backend python -m pytest -q tests/test_code_review_workflow.py
docker compose exec backend python -m pytest -q
cd frontend
npm test -- --run
npm run build
cd ..
```

## Manual acceptance scenario

1. Start a NEW C++ calculator session. Confirm the code appears and the session changes to `WAITING_FOR_APPROVAL` (progress near 95%), **without** a FINAL report.
2. Use **Request changes** (e.g., `Use int choice instead of double choice; fix the C++ switch compilation error`). Confirm AI revises and requests approval again. The model is CPU-bound and may take time.
3. Owner clicks **Approve code and finalize report**. Confirm session `COMPLETED`, Source Code status APPROVED, Report tab showing the FINAL report, and complete-project ZIP downloads.
4. Editor edits the file afterward. Verify the old report still contains the approved version, while a new approval is required. Old approved report and new source are never mixed into a downloadable complete-project package.
5. Verify a viewer cannot approve the code or modify the files.

## Limitations

- User approval is **not** code compilation/testing. C++ remains `NOT_VALIDATED` unless a secure compiler-validation service is added.
- This patch covers the `CODING` workflow. Full `HYBRID` coordinated approval and report generation still requires additional integration.
- Background code jobs are in-process; restarts during code generation cannot resume the exact LLM call. Pending human approvals **are** persistent.
- Reports are generated from a deterministic structure and the stored source, not independently fact-checked. The old research agent remains unchanged.
- Backend and frontend automated suites need to be run in your Docker/Windows environment; the local packaging environment lacks the original project's `faiss` and `langgraph` dependencies.
