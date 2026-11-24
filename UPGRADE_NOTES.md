# CoPilotHub AI — First Usability & File Integrity Increment

Source: the uploaded `copilothub-ai-latest.zip`. The patch contains exactly five source/test files; no database migrations or dependencies.

## Improvements implemented
- Detect mixed-language/model-formatted output before persisting a source file; extract an unambiguous requested language block and never save a mixed output.
- Retry a malformed generated file exactly once. Validate Python and JSON syntax before saving newly generated AI files. This is **not** C++ compilation or runtime testing.
- Make the session UI more approachable: project activity, technical tool traces, AI notes and project history are collapsed by default. The main task, progress, source files, approval and report controls remain visible.
- Replace several implementation-oriented labels in the Source Code panel with user-oriented text.
- Add 5 regression tests for mixed-language extraction, invalid source files and retries; update one UI label assertion.

## Not implemented by this incremental patch
- Unified multi-domain coordinator; hybrid tasks still run research and code concurrently.
- Persistent task queue, restart-resume, asynchronous revision queuing, or multi-provider configuration beyond the existing optional fallback.
- Real C++ compilation/testing and sandboxed execution.
- Automatic final reporting for general non-code domains.

## Apply on Windows (only when no AI generation is active)
1. Make a backup or commit your working tree.
2. Extract `copilothub_ai_first_improvements.zip` into your project **root**, selecting overwrite for the five listed paths.
3. Run:
   `docker compose up -d --build backend frontend`
   `docker compose exec backend python -m pytest -q tests/test_source_file_integrity.py tests/test_code_generation_progress.py tests/test_automatic_code_routing.py`
   `docker compose exec backend python -m pytest -q`
   `cd frontend; npm test -- --run; npm run build; cd ..`
4. Re-test a C++ + Python calculator request and inspect each saved file before approval.

## Verification carried out for this patch
Python syntax compilation succeeded; isolated source-cleaning and retry checks ran successfully. Full backend pytest is blocked in this environment by missing `faiss`; frontend npm dependency installation stalled, so React tests/build must be confirmed locally. No live Ollama run was performed here.
