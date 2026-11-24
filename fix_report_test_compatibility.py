"""Align on-demand report limit and tests with interim DRAFT snapshots.
Run from the CoPilotHub AI repository root, after apply_remaining_copilothub_fixes.py.
"""
from pathlib import Path
import ast
import shutil

ROOT = Path.cwd()
changes = {
    'backend/app/api/reports.py': [
        (
            '    existing = db.scalar(select(func.count()).select_from(Report).where(Report.session_id == sid, Report.kind == "FINAL")) or 0\n'
            '    if existing >= get_settings().max_final_reports_per_session:\n'
            '        raise HTTPException(status.HTTP_409_CONFLICT, f"A session can hold at most {get_settings().max_final_reports_per_session} final reports")',
            '    existing = db.scalar(select(func.count()).select_from(Report).where(Report.session_id == sid, Report.kind == "DRAFT")) or 0\n'
            '    if existing >= get_settings().max_reports_per_session:\n'
            '        raise HTTPException(status.HTTP_409_CONFLICT, f"A session can hold at most {get_settings().max_reports_per_session} draft reports")',
        )
    ],
    'backend/tests/test_reports.py': [
        (
            'def wait_for_reports(client, headers, sid, count, timeout=15.0):',
            'def wait_for_reports(client, headers, sid, count, timeout=15.0, kind="FINAL"):',
        ),
        (
            '        if len([r for r in found if r["kind"] == "FINAL"]) >= count:',
            '        if len([r for r in found if r["kind"] == kind]) >= count:',
        ),
        (
            '    wait_for_reports(client, headers, sid, 1)\n\n'
            '    monkeypatch.setattr(get_settings(), "max_final_reports_per_session", 1)',
            '    found = wait_for_reports(client, headers, sid, 1, kind="DRAFT")\n'
            '    assert any(r["kind"] == "DRAFT" for r in found)\n\n'
            '    monkeypatch.setattr(get_settings(), "max_reports_per_session", 1)',
        ),
    ],
}

prepared = {}
for rel, replacements in changes.items():
    p = ROOT / rel
    if not p.is_file():
        raise SystemExit(f'Missing {p}. Run script from project root. No changes made.')
    original = p.read_text(encoding='utf-8-sig')
    updated = original
    for before, after in replacements:
        count = updated.count(before)
        if count != 1:
            raise SystemExit(f'Expected 1 occurrence in {rel}, found {count}. No changes made.')
        updated = updated.replace(before, after, 1)
    ast.parse(updated, filename=rel)
    backup = p.with_name(p.name + '.report-test.bak')
    if backup.exists():
        raise SystemExit(f'Backup exists: {backup}. No changes made.')
    prepared[p] = (original, updated, backup)

for p, (original, updated, backup) in prepared.items():
    shutil.copy2(p, backup)
    p.write_text(updated, encoding='utf-8')
    print('Updated:', p.relative_to(ROOT))
print('Done. Run focused backend report tests, then full backend tests.')
