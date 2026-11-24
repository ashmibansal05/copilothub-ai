"""Build evidence-based coding reports from versioned saved artifacts.

No LLM-generated claims are added here. Approval is an editorial decision,
not a claim that the generated programs were compiled or executed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.approval import Approval, ApprovalKind, ApprovalStatus
from app.models.agent import AgentState
from app.models.code_artifact import CodeArtifact, CodeArtifactVersion
from app.models.report import Report
from app.models.session import AgentSession
from app.services.code_service import snapshot, source_section


def assemble(db: Session, sid, task: str, *, include_source: bool = True) -> tuple[str, list[dict]] | tuple[None, None]:
    session = db.get(AgentSession, sid)
    files = snapshot(db, sid)
    if not files:
        return None, None
    title = (f"Project report: {session.name}" if session else "Project report")[:200]
    state = db.scalar(select(AgentState).where(AgentState.session_id == sid))
    versions = [f"- `{f['path']}` — v{f['version']} ({f['language']}; {f['validation_status']})" for f in files]
    syntax_ok = [f for f in files if f['validation_status'] == 'SYNTAX_VALIDATED']
    failed = [f for f in files if f['validation_status'] == 'VALIDATION_FAILED']
    unchecked = [f for f in files if f['validation_status'] == 'NOT_VALIDATED']
    source = source_section(db, sid)
    main_files = [f for f in files if f['language'] not in ('markdown', 'text')]
    readme = next((f for f in files if f['path'].lower() == 'readme.md'), None)

    validation = [
        f"- Saved files: {len(files)}",
        f"- Syntax-validated files: {len(syntax_ok)}",
        f"- Files requiring further checks: {len(unchecked)}",
        f"- Files reporting validation failures: {len(failed)}",
        "- Compilation or execution: not performed by CoPilotHub AI in this workflow.",
    ]
    validation.extend(
        f"- `{f['path']}`: {f['validation_status']} — {f['validation_details']}" for f in files
    )
    reviews = db.scalars(select(Approval).where(Approval.session_id == sid,
        Approval.kind == ApprovalKind.REVIEW).order_by(Approval.created_at)).all()
    code_reviews = [r for r in reviews if (r.payload or {}).get('review_type') == 'CODE']
    decisions = [f"- Review {i}: {r.status.value.lower()}" +
                 (f"; note: {r.note}" if r.note else "")
                 for i, r in enumerate(code_reviews, 1)] or ['- No code review decision recorded.']
    sections = [
        {'key':'summary','title':'Executive Summary',
         'body': f"This deliverable contains {len(files)} saved project files for the requested task. "
                 f"{len(syntax_ok)} file(s) passed supported static syntax checks. "
                 "The files were not compiled or executed by this workflow. "
                 "Review decisions are recorded separately from technical verification."},
        {'key':'objective','title':'Project Objective','body':task},
        {'key':'deliverables','title':'Deliverables and File Inventory','body':'\n'.join(versions)},
        {'key':'approach','title':'Implementation Approach','body':
         'CoPilotHub generated or revised individual source files, saved version history, and allowed collaborative review. '
         'The final report represents the saved file versions recorded when approval was granted.\n\n' +
         (f"Engine recorded for this session: {state.engine}." if state and state.engine else
          'AI engine not recorded for this session.')},
        {'key':'run','title':'Setup and Usage','body':
         ("The project includes a README. Its saved instructions are shown below; confirm that commands match the actual files.\n\n" + readme['content'][:10000])
         if readme else 'No README was saved. Consult the source files for project-specific setup instructions.'},
        {'key':'verification','title':'Validation and Verification','body':'\n'.join(validation)},
        {'key':'review','title':'Collaboration and Human Review','body':'\n'.join(decisions)},
        {'key':'limitations','title':'Known Limitations and Next Steps','body':
         '- Static syntax checks do not demonstrate correct runtime behavior.\n'
         '- Validate functionality with appropriate test cases in a trusted environment.\n'
         '- Review error handling, dependencies, input validation, and security before deployment.\n'
         '- Approval means the reviewer accepted the saved version; it is not automated test certification.\n'
         + ('- Resolve reported validation failures before use.\n' if failed else '')},
    ]
    if include_source and source:
        sections.append(source)
    return title, sections
