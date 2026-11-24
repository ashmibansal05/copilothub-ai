"""Conservative fixes for CoPilotHub AI issues discovered in manual Sessions 1/2.
Run from repository root: python apply_remaining_copilothub_fixes.py
Creates .fix2.bak backups; refuses to patch an unexpected code version.
Requires prior tool-argument patch to be applied independently.
"""
from __future__ import annotations
import ast
from pathlib import Path
import shutil

ROOT = Path.cwd()
PATCHES: dict[str, list[tuple[str,str,str]]] = {}

def change(path, label, old, new):
    PATCHES.setdefault(path, []).append((label, old, new))

# 1. Convert model JSON arrays to readable Markdown, not Python repr.
change('backend/app/agents/llm_brain.py','report narrative rendering',
'''        return {
            key: str(data.get(key) or "").strip()
            for key in (
                "executive_summary",
                "findings",
                "comparison",
                "conclusion",
            )
        }''',
'''        def readable(value: object) -> str:
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, list):
                return "\\n".join(f"- {item.strip()}" for item in value if isinstance(item, str) and item.strip())
            # Reject unsupported structures rather than printing Python representations.
            return ""

        return {
            key: readable(data.get(key))
            for key in (
                "executive_summary", "findings", "comparison", "conclusion"
            )
        }''')

# 2. Retain the global safety budget, but never imply full research completion.
change('backend/app/agents/orchestrator.py','incomplete plan final review',
'''        round_no = state.get("approval_round", 0)
        await self._emit(EventType.AGENT_MESSAGE, {''',
'''        # Replanning uses the global work budget. Surface the unfinished revised
        # steps to reviewers instead of silently approving a complete-sounding draft.
        if state.get("step_index", 0) < len(state.get("plan", [])):
            missing = state["plan"][state["step_index"]:]
            summary += ("\\n\\nINCOMPLETE RESEARCH: The execution budget was reached. "
                        "These revised-plan steps were not performed: " + "; ".join(missing))

        round_no = state.get("approval_round", 0)
        await self._emit(EventType.AGENT_MESSAGE, {''')
change('backend/app/agents/orchestrator.py','incomplete plan final status',
'''    async def _complete(self, final: AgentGraphState) -> None:
        await self._save_state(current_step="Completed", progress=100)
        await self._generate_final_report()
        if await self._set_status(AgentStatus.COMPLETED, FINISHABLE):
            await self._emit(EventType.COMPLETED, {
                "summary": final.get("summary", ""), "confidence": final.get("confidence"),
            })''',
'''    async def _complete(self, final: AgentGraphState) -> None:
        skipped = final.get("plan", [])[final.get("step_index", 0):]
        incomplete = bool(skipped)
        await self._save_state(
            current_step="Finished with unfinished steps" if incomplete else "Completed",
            progress=95 if incomplete else 100,
        )
        await self._generate_final_report()
        if await self._set_status(AgentStatus.COMPLETED, FINISHABLE):
            await self._emit(EventType.COMPLETED, {
                "summary": final.get("summary", ""),
                "confidence": final.get("confidence"),
                "incomplete_plan": incomplete,
                "skipped_steps": skipped,
            })''')
change('backend/app/agents/orchestrator.py','report final designated',
'''info = await report_service.generate_report(self.session_id, self.brain)''',
'''info = await report_service.generate_report(self.session_id, self.brain, approved_final=True)''')

# 3. Interim manual snapshots are DRAFT; only the agent-approved report is FINAL.
# Manual regeneration after completion intentionally remains a draft, preserving approval integrity.
change('backend/app/services/report_service.py','save draft versus final',
'''def _store(session_id: uuid.UUID, inputs: ReportInputs, narrative: dict, warnings: list[str]) -> dict:
    sections = assemble_sections(inputs, narrative, warnings + compliance_warnings(inputs.views, narrative))
    title = f"Research report: {inputs.name}"[:200]
    with db_session.SessionLocal() as db:
        report = Report(
            session_id=session_id, title=title, content=render_markdown(title, sections, inputs.engine),
            format="markdown", origin="SYSTEM", status="FINAL", kind="FINAL", engine=inputs.engine, sections=sections,
        )
        db.add(report)
        db.commit()
        return {"report_id": str(report.id), "title": title, "chars": len(report.content), "kind": "FINAL"}''',
'''def _store(session_id: uuid.UUID, inputs: ReportInputs, narrative: dict,
           warnings: list[str], approved_final: bool = False) -> dict:
    sections = assemble_sections(inputs, narrative, warnings + compliance_warnings(inputs.views, narrative))
    kind = "FINAL" if approved_final else "DRAFT"
    title = (f"Research report: {inputs.name}" if approved_final
             else f"Research snapshot: {inputs.name}")[:200]
    with db_session.SessionLocal() as db:
        report = Report(
            session_id=session_id, title=title, content=render_markdown(title, sections, inputs.engine),
            format="markdown", origin="SYSTEM", status=kind, kind=kind,
            engine=inputs.engine, sections=sections,
        )
        db.add(report)
        db.commit()
        return {"report_id": str(report.id), "title": title, "chars": len(report.content), "kind": kind}''')
change('backend/app/services/report_service.py','generation argument',
'''async def generate_report(session_id: uuid.UUID, brain: Any) -> dict:''',
'''async def generate_report(session_id: uuid.UUID, brain: Any, approved_final: bool = False) -> dict:''')
change('backend/app/services/report_service.py','store generation argument',
'''return await asyncio.to_thread(_store, session_id, inputs, narrative, warnings)''',
'''return await asyncio.to_thread(_store, session_id, inputs, narrative, warnings, approved_final)''')
change('backend/app/services/report_service.py','limit accurate wording',
'''        limitations.append("No documents or web results were used: the findings come from the model's general knowledge and may be outdated.")''',
'''        limitations.append("No uploaded documents or real web results supported these findings. The model may rely on general knowledge or simulated search placeholders; verify independently.")''')
change('backend/app/services/report_service.py','explicit evidence warning',
'''    limitations.append("Agent confidence is self-assessed by the model (or simulated in demo mode), not a measured accuracy.")''',
'''    limitations.append("Agent confidence is self-assessed by the model (or simulated in demo mode), not a measured accuracy.")
    limitations.append("Narrative claims, numbers and citations have not been independently fact-checked. Verify them against real primary evidence before use.")''')
change('backend/app/services/report_service.py','flag revised plan omissions',
'''    if i.open_conflicts:
        limitations.append(f"{i.open_conflicts} conflict(s) between human instructions were still open.")''',
'''    if i.plan:
        completed_step_texts = {s["step"] for s in i.steps}
        missing = [p for p in i.plan if p not in completed_step_texts]
        if missing:
            limitations.append("INCOMPLETE revised plan; steps not executed: " + "; ".join(missing))
    if i.open_conflicts:
        limitations.append(f"{i.open_conflicts} conflict(s) between human instructions were still open.")''')
change('backend/app/services/report_service.py','methodology unique versus events',
'''    if i.simulated:
        methodology.append("NOTE: some results come from the built-in SIMULATED demo provider. They are placeholders, not real findings.")''',
'''    methodology.append(f"Unique sources included in this report: {len(i.sources_used)}. Analytics counts source-use records across steps, so its count may be higher.")
    if i.simulated:
        methodology.append("NOTE: some results come from the built-in SIMULATED demo provider. They are placeholders, not real findings.")''')
change('backend/app/services/report_service.py','report prompt caveat',
'''    findings = _narrative(narrative, "findings")''',
'''    findings = _narrative(narrative, "findings")
    if i.simulated and findings:
        findings = "*Demo evidence only; factual claims require independent verification.*\\n\\n" + findings''')

# 4. Add evidence-specific report instructions without permitting model-invented statistics.
change('backend/app/agents/prompts.py','report evidence discipline',
    '    "Never invent numbers, sources or URLs. At most 150 words per section."',
    '    "Never invent numbers, sources or URLs. At most 150 words per section. "\n'
    '    "Never present a numerical statistic as established unless the provided material includes its supporting evidence. "\n'
    '    "When evidence is simulated or insufficient, label conclusions as hypothetical or unverified. "\n'
    '    "Every JSON section value must be a string (not an array or object)."')

# 5. Frontend: a WS token failure must clear its token, not just clear user state.
change('frontend/src/contexts/AuthContext.tsx','remove expired websocket token',
'''    const onExpired = () => setUser(null);''',
'''    const onExpired = () => {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
    };''')

# 5. Report API: update misleading user-facing description.
change('backend/app/api/reports.py','manual snapshot endpoint docs',
'''    """Build a fresh final report from what the session has produced so far (runs in the background)."""''',
'''    """Build a draft research snapshot without bypassing the final approval gate."""''')
change('backend/app/api/reports.py','manual snapshot response text',
'''    return MessageResponse(message="Generating the report. It will appear when it is ready.")''',
'''    return MessageResponse(message="Generating a draft research snapshot. It will appear when ready.")''')

TEST = '''"""Guardrails for regression of confirmed Issues 03-08."""
import ast
import inspect
from pathlib import Path
from app.agents.llm_brain import LLMBrain
from app.services import report_service


def test_report_generation_has_approval_context():
    assert 'approved_final' in inspect.signature(report_service.generate_report).parameters
    assert 'approved_final' in inspect.signature(report_service._store).parameters


def test_interim_snapshot_and_final_are_distinct():
    text = inspect.getsource(report_service._store)
    assert 'kind = "FINAL" if approved_final else "DRAFT"' in text


def test_report_formatting_does_not_stringify_model_lists():
    text = inspect.getsource(LLMBrain.write_report)
    assert '"\\\\n".join' in text or 'join(f"- ' in text
    assert 'str(data.get(key) or "")' not in text


def test_replanning_does_not_reset_global_step_counter():
    from app.agents.orchestrator import AgentOrchestrator
    plan_source = inspect.getsource(AgentOrchestrator.plan_node)
    assert 'steps_executed": 0' not in plan_source
    complete_source = inspect.getsource(AgentOrchestrator._complete)
    assert 'incomplete_plan' in complete_source
'''


def main():
    parsed = {}
    for rel, patches in PATCHES.items():
        path=ROOT/rel
        if not path.is_file(): raise SystemExit(f'Missing {rel}; run from project root. No files modified.')
        orig=path.read_text(encoding='utf-8-sig')
        data=orig
        for label,old,new in patches:
            count=data.count(old)
            if count != 1:
                raise SystemExit(f'{rel} ({label}): expected 1 match, found {count}. Nothing modified.')
            data=data.replace(old,new,1)
        if path.suffix=='.py': ast.parse(data,filename=rel)
        backup=path.with_suffix(path.suffix+'.fix2.bak')
        if backup.exists():raise SystemExit(f'{backup} exists; stopping to avoid overwrite.')
        parsed[path]=data
    test=ROOT/'backend/tests/test_remaining_issues.py'
    if test.exists():raise SystemExit(f'{test} exists; cannot overwrite.')
    ast.parse(TEST)
    for path in parsed:
        shutil.copy2(path,path.with_suffix(path.suffix+'.fix2.bak'))
    for path,data in parsed.items():
        path.write_text(data,encoding='utf-8')
        print('Updated',path.relative_to(ROOT))
    test.parent.mkdir(parents=True,exist_ok=True)
    test.write_text(TEST,encoding='utf-8')
    print('Created',test.relative_to(ROOT))
    print('Backups: *.fix2.bak; run automated tests before restart.')

if __name__=='__main__':main()
