"""Security-conscious versioned source storage and deterministic exports."""
import ast
import hashlib
import io
import json
import posixpath
import re
import uuid
import zipfile
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.code_artifact import CodeArtifact, CodeArtifactVersion

MAX_FILES = 80
MAX_FILE_BYTES = 256 * 1024
MAX_PROJECT_BYTES = 3 * 1024 * 1024

class CodeError(ValueError):
    pass

def safe_path(path: str) -> str:
    if not isinstance(path, str) or not path or len(path) > 320 or "\\" in path or "\x00" in path:
        raise CodeError("Invalid file path")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise CodeError("Absolute paths are not allowed")
    parts = path.split("/")
    if any(part in ("", ".", "..") or part.startswith(".") and part in (".env", ".git") for part in parts):
        raise CodeError("Unsafe file path")
    if any(part in ("node_modules", "__pycache__", ".git") for part in parts):
        raise CodeError("Reserved file path")
    if parts[-1].lower() in (".env", "id_rsa", "id_ed25519") or parts[-1].endswith((".key", ".pem")):
        raise CodeError("Sensitive filename not allowed")
    return path

def language_for(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {"py":"python", "cpp":"cpp", "cc":"cpp", "h":"cpp", "hpp":"cpp", "java":"java", "js":"javascript", "jsx":"javascript", "ts":"typescript", "tsx":"typescript", "html":"html", "css":"css", "sql":"sql", "json":"json", "md":"markdown"}.get(ext, "text")

def validate_static(path: str, content: str) -> tuple[str, str]:
    if language_for(path) == "python":
        try:
            ast.parse(content)
            return "SYNTAX_VALIDATED", "Python AST syntax validation passed (not executed)."
        except SyntaxError as exc:
            return "VALIDATION_FAILED", f"Python syntax error: {exc.msg} at line {exc.lineno}"
    if language_for(path) == "json":
        try:
            json.loads(content)
            return "SYNTAX_VALIDATED", "JSON syntax valid."
        except ValueError as exc:
            return "VALIDATION_FAILED", str(exc)[:300]
    return "NOT_VALIDATED", "No isolated compiler/test runner configured; generated content has not been executed."

def _version(db: Session, art: CodeArtifact) -> CodeArtifactVersion:
    row = db.scalar(select(CodeArtifactVersion).where(CodeArtifactVersion.artifact_id == art.id,
        CodeArtifactVersion.version == art.current_version))
    if row is None: raise CodeError("Artifact version missing")
    return row

def list_artifacts(db: Session, sid: uuid.UUID) -> list[dict]:
    rows = db.scalars(select(CodeArtifact).where(CodeArtifact.session_id == sid).order_by(CodeArtifact.path)).all()
    return [dict(id=str(a.id), path=a.path, language=a.language, version=a.current_version,
                 validation_status=a.validation_status, updated_at=a.updated_at.isoformat() if a.updated_at else None)
            for a in rows]

def save_file(db: Session, sid: uuid.UUID, path: str, content: str, creator: uuid.UUID | None = None,
              expected_version: int | None = None, origin: str = "AI") -> dict:
    path = safe_path(path)
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise CodeError("File exceeds the 256 KiB limit")
    art = db.scalar(select(CodeArtifact).where(CodeArtifact.session_id == sid, CodeArtifact.path == path).with_for_update())
    if art is None:
        if expected_version not in (None, 0): raise CodeError("File version conflict")
        if len(list_artifacts(db, sid)) >= MAX_FILES: raise CodeError("Project file limit reached")
        art = CodeArtifact(session_id=sid, path=path, language=language_for(path), current_version=1)
        db.add(art)
        db.flush()
    else:
        if expected_version is not None and art.current_version != expected_version:
            raise CodeError("File version conflict")
        art.current_version += 1
    validation, details = validate_static(path, content)
    art.validation_status = validation
    row = CodeArtifactVersion(artifact_id=art.id, version=art.current_version, content=content,
                              created_by=creator, origin=origin, validation_status=validation,
                              validation_details=details)
    db.add(row)
    db.commit()
    db.refresh(art)
    return dict(id=str(art.id), path=path, version=art.current_version, language=art.language,
                validation_status=validation, validation_details=details)

def get_file(db: Session, sid: uuid.UUID, aid: uuid.UUID, version: int | None = None) -> dict | None:
    art = db.scalar(select(CodeArtifact).where(CodeArtifact.id == aid, CodeArtifact.session_id == sid))
    if not art: return None
    ver = version if version is not None else art.current_version
    row = db.scalar(select(CodeArtifactVersion).where(CodeArtifactVersion.artifact_id == aid, CodeArtifactVersion.version == ver))
    if not row: return None
    return dict(id=str(art.id), path=art.path, language=art.language, version=ver, content=row.content,
                validation_status=row.validation_status, validation_details=row.validation_details,
                created_at=row.created_at.isoformat() if row.created_at else None)

def versions(db: Session, sid: uuid.UUID, aid: uuid.UUID) -> list[dict]:
    art = db.scalar(select(CodeArtifact).where(CodeArtifact.id == aid, CodeArtifact.session_id == sid))
    if art is None: return []
    rows = db.scalars(select(CodeArtifactVersion).where(CodeArtifactVersion.artifact_id == aid).order_by(CodeArtifactVersion.version.desc())).all()
    return [dict(version=v.version, origin=v.origin, validation_status=v.validation_status,
                 created_at=v.created_at.isoformat() if v.created_at else None) for v in rows]

def snapshot(db: Session, sid: uuid.UUID) -> list[dict]:
    return [get_file(db, sid, uuid.UUID(item["id"])) for item in list_artifacts(db, sid)]

def source_section(db: Session, sid: uuid.UUID) -> dict | None:
    files = snapshot(db, sid)
    if not files: return None
    parts = ["Source files saved in the shared project workspace.",
             "Validation states describe static checks only; code was not executed unless separately recorded.",
             "Files: " + ", ".join(f["path"] for f in files)]
    for f in files:
        # Use a dynamic fence to keep embedded backtick sequences from closing code blocks.
        fence = "`" * max(3, max((len(x) for x in re.findall(r"`+", f["content"])), default=0) + 1)
        parts.append(f"### {f['path']} (v{f['version']}; {f['validation_status']})\n\n{fence}{f['language']}\n{f['content']}\n{fence}")
    return {"key":"source_code", "title":"Source Code and Implementation", "body":"\n\n".join(parts)}

def build_zip(db: Session, sid: uuid.UUID, title: str, report=None) -> bytes:
    files = snapshot(db, sid)
    if not files: raise CodeError("No source code available")
    if report and any(section.get("key") == "source_code" for section in (report.sections or [])):
        # Report is an immutable approved snapshot; do not silently combine it with newer code.
        section = next(x for x in report.sections if x.get("key") == "source_code")
        current = source_section(db, sid)
        if current and current["body"] != section["body"]:
            raise CodeError("Source files changed after report approval; request a new review")
    total = sum(len(f["content"].encode("utf-8")) for f in files)
    if total > MAX_PROJECT_BYTES: raise CodeError("Project export exceeds the size limit")
    manifest = {"session_id":str(sid), "project":title,
                "generated_at":datetime.now(timezone.utc).isoformat(), "files":[]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            content = f["content"].encode("utf-8")
            name = ("source-code/" if report else "") + safe_path(f["path"])
            z.writestr(name, content)
            manifest["files"].append({"path":f["path"], "version":f["version"],
                "sha256":hashlib.sha256(content).hexdigest(), "validation_status":f["validation_status"]})
        if report:
            from app.services.report_export import to_markdown, to_docx
            from app.services.report_service import render_markdown
            from types import SimpleNamespace
            sections = list(report.sections or [])
            if not any(x.get("key") == "source_code" for x in sections):
                section = source_section(db, sid)
                if section: sections.append(section)
            merged = SimpleNamespace(title=report.title, engine=report.engine, sections=sections,
                 content=render_markdown(report.title, sections, report.engine))
            z.writestr("reports/Project_Report.md", to_markdown(merged))
            z.writestr("reports/Project_Report.docx", to_docx(merged))
        z.writestr("project-manifest.json", json.dumps(manifest, indent=2))
    return buf.getvalue()
