# Research evaluation guide

**Research question.** Can structured human interventions improve the reliability and controllability of
long-running AI agents compared with agents operating without human intervention?

This platform *collects the data*. It does not contain results. Do not quote numbers you did not measure.

## What is measured (all computed from stored data)
| Metric (your brief) | Where it comes from |
|---|---|
| Task completion rate | sessions COMPLETED / finished (`/analytics/overview`) |
| Intervention count | `interventions` (comments excluded), by type and by user |
| Incorrect actions | corrective interventions + rejected approvals per session |
| Source rejection rate | `sources` REJECTED / (USED + REJECTED) |
| Tool failure rate | `tool_executions` not SUCCESS / all |
| Conflict rate | `conflicts` per session |
| Agent recovery rate | sessions with failed attempts that still completed |
| Human correction rate | corrective interventions per completed step |
| Time to completion | `duration_seconds` of completed sessions |
Export: `GET /analytics/export.csv` (one row per ended session), and `python -m app.ml.train --export-real file.csv` (one row per step).

## Suggested protocol
1. Fix a set of tasks (for example 10 research prompts) and a model (`OLLAMA_MODEL`).
2. **Condition A: no intervention.** Run each task with nobody intervening (approve the final draft only).
3. **Condition B: with intervention.** Run each task again with scripted human guidance (the same rules for every task, e.g. reject a named source, add one fact, one correction).
4. Randomise the order, repeat each task several times, and record the model and settings.
5. Judge report quality **blind** (hide the condition) with a small rubric: factual errors, use of rejected sources, coverage.
6. Compare completion rate, quality score, time and failures between A and B.

## Threats to validity (write these in the report)
- The built-in comparison on the Analytics page is **observational**: humans choose when to intervene, so it is not a controlled experiment.
- Small samples; local models vary run to run; confidence is self-reported by the model.
- The NLP dataset and the risk predictor's initial training data are synthetic; report them as such.
- Interventions change the task (extra information and constraints), so conditions are not identical by design.