# Demonstration guide (19 steps)

## Before you present
- [ ] `docker compose up` (or the local setup) is running. `python scripts/smoke_test.py` passes.
- [ ] **Offline-safe:** set `EMBEDDING_BACKEND=hashing` *or* open the app once online so the embedding model is cached.
- [ ] Choose the engine: `DEMO_MODE=true` (reliable, scripted) or `DEMO_MODE=false` with Ollama running and `qwen3` pulled.
- [ ] Run `python -m app.nlp.train` and `python -m app.ml.train` once so the first click is fast.
- [ ] Open **three browser profiles** (normal, private window, another browser): Alice (owner), Bob (editor), Carol (viewer). A fourth person, Dave, helps with the conflict.
- [ ] Say it out loud: demo mode and the risk model use simulated/synthetic data and are labelled as such.

## Script
| # | Do | Expect |
|---|---|---|
| 1 | Alice registers and logs in | Dashboard |
| 2 | **New session**: "Prepare a report comparing AWS, Microsoft Azure and Google Cloud for a small startup." | Workspace opens; Alice is OWNER |
| 3 | Copy the **editor** and **viewer** links | Two different invite links |
| 4 | Bob opens the editor link, Carol the viewer link | Everyone appears in *Collaborators* with a green dot; Carol has no buttons |
| 5 | Alice clicks **Start agent** | Status RUNNING → PLANNING → RUNNING; a 7-step plan |
| 6 | Watch all three windows | Same steps, tool calls, sources, confidence, live; the **risk card** updates after each step |
| 7 | Point at **Tool activity** and **Retrieved sources** | Calls with arguments; demo results badged *simulated* |
| 8 | Bob types `Do not use Wikipedia.` | Applied at once |
| 9 | Show the classifier's answer | "Applied (xx% sure: reject source)" |
| 10 | Show **Active constraints** | `Do not use sources from or about "Wikipedia"` · HIGH · by @bob |
| 11 | Wait for the next step | Wikipedia sources are struck through, "filtered N source(s)" |
| 12 | Dave (or Bob) types `Prefer official cloud provider documentation.` | New PREFER constraint; official sources ranked first, marked *preferred* |
| 13 | Show the agent obeying | Later steps and the final draft contain no Wikipedia |
| 14 | Dave adds *Explicitly allow a source: Wikipedia* (High) via **Add constraint** | Red **Conflicting instructions** card with both sides and the rule |
| 15 | Alice clicks **Keep A** | Conflict closes; the losing constraint disappears; the agent continues (it had waited) |
| 16 | The agent finishes the research | Yellow **waiting for human approval** card with the draft |
| 17 | Alice clicks **Approve** (Carol cannot) | "Generating the final report…" |
| 18 | Open **Report** | 10 sections; Sources lists Wikipedia only under *rejected*; Human Decisions lists who did what |
| 19 | Open **Analytics** | Duration, interventions by type, confidence, tool usage, approvals, conflicts, completion; predictor behaviour |

Bonus: reject the draft with a note (it revises using your note) · **Modify task** (it re-plans) · **Request review** ·
upload a PDF and use **Search** · type a vague sentence to show the confirmation dialog · **Settings → System status**.

## If something goes wrong
- Agent seems stuck at "waiting": it is waiting for *you* (approval or conflict card).
- No updates: check the **Live** badge; refresh. Ollama slow: raise `AGENT_STEP_TIMEOUT_SECONDS`, or use `DEMO_MODE=true`.
- Always have a recorded run or screenshots as a fallback.