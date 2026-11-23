# API reference

Interactive documentation: `http://localhost:8000/docs` (hidden when `ENVIRONMENT=production`).
All endpoints except `/health*`, `/auth/register` and `/auth/login` need `Authorization: Bearer <token>`.
Errors use `{"detail": "..."}`. Roles: **O** owner, **E** editor, **V** viewer (members only; non-members get 404).

## Auth
| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | `{email, username, full_name, password}` → user (role EDITOR). Rate limited |
| POST | `/auth/login` | `{email, password}` → `{access_token, expires_in}`. Rate limited per IP and per email |
| GET | `/auth/me` | current user |
| POST | `/auth/logout` | client discards the token |
| POST | `/auth/change-password` | `{current_password, new_password}` → new token; all older tokens revoked |

## System
`GET /health`, `GET /health/db`, `GET /system/status`, `GET /llm/status`, `GET /tools` (approved tools),
`GET /nlp/status`, `GET /ml/status` (the real training metrics).

## Sessions
| Method | Path | Roles |
|---|---|---|
| GET / POST | `/sessions` | list mine / create (creator = owner) |
| GET | `/sessions/invite/{code}` | preview an invite |
| POST | `/sessions/join` | `{code}`: the code decides the role (editor or viewer) |
| GET | `/sessions/{id}` | members (invite codes only visible to the owner) |
| DELETE | `/sessions/{id}` | O: deletes everything incl. files |
| GET | `/sessions/{id}/events` | persisted event history |
| POST | `/sessions/{id}/start` · `/stop` | O |
| POST | `/sessions/{id}/pause` · `/resume` | O, E |
| GET | `/sessions/{id}/state` | agent state, constraints, interventions, pending approval, open conflicts |
| GET | `/sessions/{id}/actions` | agent action log |

## Human control
| Method | Path | Notes |
|---|---|---|
| POST | `/sessions/{id}/interventions` | `{type, content?, target?, priority?, action?, constraint_id?, conflict_id?, winner_constraint_id?, origin_text?}`. Types: APPROVE, REJECT, CORRECT, PAUSE, RESUME, MODIFY_TASK (O), ADD_INFORMATION, ADD_CONSTRAINT, REMOVE_CONSTRAINT, REJECT_SOURCE, CHANGE_SOURCE, REQUEST_REVIEW, COMMENT, RESOLVE_CONFLICT (O) |
| GET | `/sessions/{id}/interventions` | audit list |
| GET / POST | `/sessions/{id}/constraints` | list active / add (E, O) |
| DELETE | `/sessions/{id}/constraints/{cid}` | remove (E, O) |
| GET | `/sessions/{id}/memory` | constraints + remembered items |
| POST | `/sessions/{id}/instructions` | `{text, dry_run?}` free text → classified → applied or proposed. Rate limited |
| GET | `/sessions/{id}/conflicts?status=all\|OPEN\|RESOLVED` | |
| POST | `/sessions/{id}/conflicts/{cid}/resolve` | O: `{winner_constraint_id|null, note?}` |

## Documents and sources
`POST /sessions/{id}/documents` (multipart `file`, `title?`, `source_name?`, `source_type?`; E, O; ≤ `MAX_UPLOAD_MB`),
`GET /sessions/{id}/documents`, `GET …/documents/{did}/chunks`, `DELETE …/documents/{did}` (E, O),
`POST /sessions/{id}/documents/search` `{query, k}`, `GET /sessions/{id}/sources`.

## Tools, reports, ML, analytics
| Method | Path |
|---|---|
| GET | `/sessions/{id}/tools` (tool-call audit log) |
| GET | `/sessions/{id}/reports`, `/sessions/{id}/report` (latest final), `/sessions/{id}/reports/{rid}` |
| POST | `/sessions/{id}/report/generate` (E, O) |
| GET | `/sessions/{id}/reports/{rid}/download?format=md\|html\|docx` |
| GET | `/sessions/{id}/risk` (intervention-risk estimate) |
| GET | `/sessions/{id}/analytics`, `/analytics/overview`, `/analytics/export.csv` |

## WebSocket `/ws/sessions/{session_id}`
1. Connect, then send **within 5 s**: `{"type":"AUTH","token":"<JWT>"}`.
2. Receive `CONNECTED` `{my_role, status, online_users}`, then live events `{id, session_id, type, payload, user_id, created_at}`.
3. Send `{"type":"PING"}` every ~25 s → `PONG`. Clients cannot send anything else.
4. Close codes: **4401** bad or expired token, **4403** not a member or origin refused, **4404** session deleted.

## Limits
Login 20/min per IP and 8/min per email · register 10/min · join 20/min · invite preview 30/min · instructions 30/min ·
uploads 20/min · password change 5/min. Exceeded → `429` with `Retry-After`.