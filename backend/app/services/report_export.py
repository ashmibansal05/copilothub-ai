import html
import io
import re

from app.models.report import Report


def safe_filename(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "report"


def _sections(report: Report) -> list[dict]:
    return report.sections or [{"key": "content", "title": "Report", "body": report.content}]


def to_markdown(report: Report) -> bytes:
    return report.content.encode("utf-8")


def _body_html(body: str) -> str:
    # Render fenced code as escaped <pre> blocks, preserving all indentation.
    pieces = re.split(r"(`{3,})[^\n]*\n(.*?)\n?\1", body, flags=re.S)
    if len(pieces) > 1:
        return "".join(_body_html(pieces[n]) if n % 3 == 0 else
                       f"<pre><code>{html.escape(pieces[n])}</code></pre>" if n % 3 == 2 else ""
                       for n in range(len(pieces)))
    out, bullets = [], []

    def flush():
        if bullets:
            out.append("<ul>" + "".join(f"<li>{html.escape(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for block in re.split(r"\n\s*\n", body.strip()):
        for line in block.split("\n"):
            if line.startswith("- "):
                bullets.append(line[2:])
            else:
                flush()
                if line.strip():
                    heading = re.match(r"^#{3,5}\s+(.+)$", line)
                    if heading:
                        out.append(f"<h3>{html.escape(heading.group(1))}</h3>")
                    else:
                        out.append(f"<p>{html.escape(line)}</p>")
        flush()
    return "".join(out)


def to_html(report: Report) -> bytes:
    """Every piece of text is escaped: report content is never interpreted as HTML."""
    parts = "".join(
        f"<h2>{n}. {html.escape(s['title'])}</h2>{_body_html(s['body'])}" for n, s in enumerate(_sections(report), 1)
    )
    engine = f"<p><em>Engine: {html.escape(report.engine)}</em></p>" if report.engine else ""
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(report.title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:48rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "h1{margin-bottom:.25rem}h2{margin-top:2rem;border-bottom:1px solid #ddd}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f4f6;padding:1rem}</style></head>"
        f"<body><h1>{html.escape(report.title)}</h1>{engine}{parts}</body></html>"
    )
    return page.encode("utf-8")


def to_docx(report: Report) -> bytes:
    import docx

    document = docx.Document()
    document.add_heading(report.title, level=0)
    if report.engine:
        document.add_paragraph(f"Engine: {report.engine}")
    for n, section in enumerate(_sections(report), 1):
        document.add_heading(f"{n}. {section['title']}", level=1)
        in_code = False
        for line in section["body"].split("\n"):
            if re.match(r"^`{3,}", line):
                in_code = not in_code
                continue
            if in_code:
                paragraph = document.add_paragraph()
                run = paragraph.add_run(line)
                run.font.name = "Consolas"
                from docx.shared import Pt
                run.font.size = Pt(8)
            elif re.match(r"^#{3,5}\s+", line):
                document.add_heading(re.sub(r"^#{3,5}\s+", "", line).strip(), level=2)
            elif line.startswith("- "):
                document.add_paragraph(line[2:], style="List Bullet")
            elif line.strip():
                document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


EXPORTERS = {
    "md": ("text/markdown; charset=utf-8", to_markdown),
    "html": ("text/html; charset=utf-8", to_html),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", to_docx),
}