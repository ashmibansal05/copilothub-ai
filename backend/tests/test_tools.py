import asyncio
import uuid

import httpx
import pytest
from pydantic import Field
from sqlalchemy import select

from app.core.config import get_settings
from app.models.report import Report
from app.services.constraint_manager import ConstraintView
from app.tools import get_registry
from app.tools.base import Tool, ToolArgs, ToolContext, ToolError, ToolResult, describe_tools
from app.tools.calc import CalcError, safe_eval
from app.tools.registry import ToolRegistry
from app.tools.summarize import extractive_summary
from app.tools.web import DemoSearchProvider, SearxngProvider, WebProviderError, get_web_provider
from helpers import create_session, make_user, upload, wait_ready

AWS = b"AWS pricing overview. Amazon Web Services offers a free tier for new accounts with pay as you go pricing for compute storage and databases. Savings plans reduce the cost of steady workloads."
AZURE = b"Azure pricing overview. Microsoft Azure offers free credits for startups and pay as you go pricing for virtual machines. Hybrid benefit reduces the cost for Windows Server licences."


def exclude(target):
    return ConstraintView("1", "EXCLUDE_SOURCE", target, "HIGH", f"Do not use {target}")


def context(session_id=None, views=()):
    return ToolContext(session_id=session_id or uuid.uuid4(), settings=get_settings(), views=list(views))


def run(registry, name, arguments, ctx=None):
    return asyncio.run(registry.execute(name, arguments, ctx or context()))


# ---------------------------------------------------------------- the calculator
@pytest.mark.parametrize("expression,expected", [
    ("2+3*4", 14), ("(10-2)/4", 2.0), ("sqrt(16)", 4.0), ("min(3,1,2)", 1), ("-5 + 2", -3),
    ("10 % 4", 2), ("7 // 2", 3), ("2 ** 10", 1024), ("round(2.567, 1)", 2.6), ("pi * 2", 6.283185307179586),
])
def test_calculator_computes(expression, expected):
    assert safe_eval(expression) == pytest.approx(expected)


@pytest.mark.parametrize("expression", [
    "__import__('os').system('ls')", "open('/etc/passwd')", "a + 1", "1; 2", "2**1000", "10**10**10",
    "1/0", "'text'", "lambda: 1", "[1, 2]", "x.y", "5 ^ 3", "sum([1])", "abs()", "True + 1",
    "(" * 50 + "1" + ")" * 50, "1" + "+1" * 100, "9" * 300, "sqrt(-1)", "2 ** 50",
])
def test_calculator_rejects_anything_else(expression):
    with pytest.raises(CalcError):
        safe_eval(expression)


# ---------------------------------------------------------------- extractive summary
def test_extractive_summary_keeps_relevant_sentences_in_order():
    text = (
        "Cloud pricing depends on compute, storage and network usage for every workload. "
        "The weather in the office was pleasant during the long meeting yesterday morning. "
        "Compute pricing is billed per second and storage pricing is billed per gigabyte each month. "
        "Network pricing includes egress fees that grow with the volume of outgoing data. "
        "Lunch was provided by the catering team for everybody attending the session today. "
        "Savings plans lower compute pricing when usage is committed for one or three years."
    )
    summary = extractive_summary(text, 3)
    assert len(summary) == 3
    assert all("pricing" in s.lower() for s in summary)
    assert [text.index(s) for s in summary] == sorted(text.index(s) for s in summary)
    assert extractive_summary("Too short.", 3) == []


# ---------------------------------------------------------------- registry
class EchoArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=50)
    times: int = Field(default=1, ge=1, le=3)


class EchoTool(Tool):
    name, description, args_model = "echo", "Echo text", EchoArgs

    async def run(self, args, ctx):
        return ToolResult(
            output=args.text * args.times,
            sources=[
                {"title": "Wiki page", "publisher": "Wikipedia", "source_type": "encyclopedia"},
                {"title": "Docs page", "publisher": "Docs Inc", "source_type": "official documentation"},
            ],
        )


class SlowTool(Tool):
    name, description, args_model = "slow", "Sleeps", ToolArgs

    async def run(self, args, ctx):
        await asyncio.sleep(5)


class BrokenTool(Tool):
    name, description, args_model = "broken", "Crashes", ToolArgs

    async def run(self, args, ctx):
        raise RuntimeError("secret internal detail /srv/app/db.py")


class PoliteFailTool(Tool):
    name, description, args_model = "polite", "Fails politely", ToolArgs

    async def run(self, args, ctx):
        raise ToolError("nothing found")


class BigTool(Tool):
    name, description, args_model = "big", "Large output", ToolArgs

    async def run(self, args, ctx):
        return ToolResult(output="x" * 100000)


@pytest.fixture()
def registry():
    return ToolRegistry([EchoTool(), SlowTool(), BrokenTool(), PoliteFailTool(), BigTool()])


def test_valid_call_succeeds_and_returns_sources(registry):
    outcome = run(registry, "echo", {"text": "hi", "times": 2})
    assert outcome.ok and outcome.status == "SUCCESS" and outcome.output == "hihi"
    assert len(outcome.sources) == 2 and outcome.rejected_sources == []


def test_unknown_and_disabled_tools_are_rejected(registry):
    for name in ["rm", "shell", "", None, 123, "ECHO"]:
        outcome = run(registry, name, {})
        assert outcome.status == "REJECTED" and not outcome.ok and "Unknown or disabled tool" in outcome.error
    limited = ToolRegistry([EchoTool(), CalcOnly()], enabled={"calc"})
    assert limited.names() == ["calc"]
    assert run(limited, "echo", {"text": "x"}).status == "REJECTED"


class CalcOnly(Tool):
    name, description, args_model = "calc", "Calc", ToolArgs

    async def run(self, args, ctx):
        return ToolResult(output="ok")


def test_arguments_are_validated_strictly(registry):
    for bad in [{}, {"text": ""}, {"text": "x" * 51}, {"text": "x", "times": 9}, {"text": "x", "times": "two"},
                {"text": "x", "extra": 1}, {"text": 5}]:
        outcome = run(registry, "echo", bad)
        assert outcome.status == "REJECTED" and "Invalid arguments" in outcome.error, bad
    assert run(registry, "echo", ["not", "a", "dict"]).status == "REJECTED"
    assert run(registry, "echo", {"text": "x" * 6000}).status == "REJECTED"


def test_errors_never_leak_internals_and_timeouts_are_enforced(registry, monkeypatch):
    broken = run(registry, "broken", {})
    assert broken.status == "ERROR" and "secret" not in broken.output and "/srv" not in (broken.error or "")
    polite = run(registry, "polite", {})
    assert polite.status == "ERROR" and polite.error == "nothing found"
    monkeypatch.setattr(get_settings(), "tool_timeout_seconds", 0.1)
    assert run(registry, "slow", {}).status == "TIMEOUT"


def test_output_is_truncated(registry):
    outcome = run(registry, "big", {})
    assert outcome.ok and len(outcome.output) == get_settings().tool_output_max_chars


def test_current_constraints_filter_every_tools_sources(registry):
    outcome = run(registry, "echo", {"text": "hi"}, context(views=[exclude("Wikipedia")]))
    assert [s["publisher"] for s in outcome.sources] == ["Docs Inc"]
    assert outcome.rejected_sources[0]["publisher"] == "Wikipedia" and outcome.rejected_sources[0]["rejected_by"] == "Wikipedia"


def test_the_default_registry_has_exactly_the_approved_tools():
    names = set(get_registry().names())
    assert names == {"search_web", "retrieve_documents", "read_document", "summarize_document",
                     "compare_sources", "calculate", "save_report"}
    assert not any(bad in n for n in names for bad in ("shell", "exec", "bash", "file", "fetch", "url", "http"))
    specs = {s.name: s for s in get_registry().specs()}
    assert specs["save_report"].side_effects and not specs["calculate"].side_effects
    assert "query: string" in describe_tools([specs["search_web"]])


# ---------------------------------------------------------------- web providers
def test_demo_provider_is_simulated_and_deterministic():
    provider = DemoSearchProvider()
    first = asyncio.run(provider.search("Gather information on AWS", 3))
    assert first == asyncio.run(provider.search("Gather information on AWS", 3))
    assert len(first) == 3 and all(s["simulated"] for s in first) and provider.simulated


def test_searxng_provider_parses_filters_and_fails_safely():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search" and request.url.params["format"] == "json"
        return httpx.Response(200, json={"results": [
            {"title": "Pricing", "url": "https://www.example.com/pricing", "content": "All about pricing"},
            {"title": "Evil", "url": "javascript:alert(1)", "content": "x"},
            {"title": "Local", "url": "file:///etc/passwd", "content": "x"},
            {"title": "Docs", "url": "https://docs.example.org/a", "content": "Docs"},
        ]})

    provider = SearxngProvider("http://searx.test", transport=httpx.MockTransport(handler))
    results = asyncio.run(provider.search("pricing", 5))
    assert [r["publisher"] for r in results] == ["example.com", "docs.example.org"]  # only http(s), www. stripped
    assert all(r["origin"] == "web" and not r["simulated"] for r in results)

    for response in (httpx.Response(500), httpx.Response(200, json={"nope": 1}), httpx.Response(200, text="<html>")):
        broken = SearxngProvider("http://searx.test", transport=httpx.MockTransport(lambda r, resp=response: resp))
        with pytest.raises(WebProviderError):
            asyncio.run(broken.search("x", 3))

    def down(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(WebProviderError):
        asyncio.run(SearxngProvider("http://searx.test", transport=httpx.MockTransport(down)).search("x", 3))


def test_web_provider_configuration(monkeypatch):
    settings = get_settings()
    get_web_provider.cache_clear()
    try:
        assert get_web_provider().name == "demo"
        monkeypatch.setattr(settings, "web_search_provider", "searxng")
        monkeypatch.setattr(settings, "searxng_url", "")
        get_web_provider.cache_clear()
        with pytest.raises(ValueError):
            get_web_provider()
        # the search tool reports a misconfiguration instead of crashing
        outcome = run(get_registry(), "search_web", {"query": "aws pricing"})
        assert outcome.status == "ERROR" and "not configured" in outcome.error
    finally:
        get_web_provider.cache_clear()


# ---------------------------------------------------------------- built-in tools on real data
@pytest.fixture(autouse=True)
def relaxed_threshold(monkeypatch):
    monkeypatch.setattr(get_settings(), "rag_min_score", 0.05)


def session_with_docs(client):
    owner, _ = make_user(client, "owner")
    s = create_session(client, owner)
    sid = s["id"]
    docs = {}
    for name, content, source in [("aws.txt", AWS, "Amazon Web Services"), ("azure.txt", AZURE, "Microsoft")]:
        r = upload(client, owner, sid, name=name, content=content, source_name=source, source_type="official documentation", title=name[:-4].upper())
        docs[name] = wait_ready(client, owner, sid, r.json()["id"])
    return uuid.UUID(sid), owner, docs


def test_retrieve_read_and_summarize_documents(client):
    sid, owner, docs = session_with_docs(client)
    registry = get_registry()
    ctx = context(sid)

    found = run(registry, "retrieve_documents", {"query": "free tier pay as you go Amazon"}, ctx)
    assert found.ok and found.retrieved_chunks >= 1 and "Amazon Web Services" in found.output
    assert found.sources[0]["origin"] == "document"

    by_title = run(registry, "read_document", {"document": "aws"}, ctx)  # titles are case-insensitive
    assert by_title.ok and "free tier" in by_title.output
    by_id = run(registry, "read_document", {"document": docs["azure.txt"]["id"]}, ctx)
    assert by_id.ok and "Azure" in by_id.output
    assert run(registry, "read_document", {"document": "aws", "offset": 50}, ctx).status == "ERROR"
    assert run(registry, "read_document", {"document": "nonexistent"}, ctx).status == "ERROR"

    summary = run(registry, "summarize_document", {"document": "AZURE", "max_sentences": 2}, ctx)
    assert summary.ok and "not written by a language model" in summary.output


def test_documents_of_other_sessions_and_excluded_sources_are_unreachable(client):
    sid, owner, docs = session_with_docs(client)
    other = uuid.UUID(create_session(client, owner, name="Other session")["id"])
    registry = get_registry()
    assert run(registry, "read_document", {"document": docs["aws.txt"]["id"]}, context(other)).status == "ERROR"
    assert run(registry, "retrieve_documents", {"query": "pricing"}, context(other)).retrieved_chunks == 0

    blocked = context(sid, views=[exclude("Amazon Web Services")])
    outcome = run(registry, "read_document", {"document": "aws"}, blocked)
    assert outcome.status == "ERROR" and "excluded by a human constraint" in outcome.error
    assert run(registry, "summarize_document", {"document": "aws"}, blocked).status == "ERROR"
    hits = run(registry, "retrieve_documents", {"query": "pricing"}, blocked)
    assert all(s["publisher"] != "Amazon Web Services" for s in hits.sources)


def test_compare_sources_reports_evidence_and_gaps(client):
    sid, owner, _ = session_with_docs(client)
    outcome = run(get_registry(), "compare_sources",
                  {"topics": ["AWS", "Azure"], "criteria": ["pricing", "quantum computing"]}, context(sid))
    assert outcome.ok and "### AWS" in outcome.output and "### Azure" in outcome.output
    assert "pricing:" in outcome.output and outcome.data["pairs"] == 4
    assert "no evidence in the uploaded documents" in outcome.output  # honest about gaps
    assert run(get_registry(), "compare_sources", {"topics": ["only one"]}, context(sid)).status == "REJECTED"
    assert run(get_registry(), "compare_sources", {"topics": list("abcde"), "criteria": list("123")}, context(sid)).status == "REJECTED"


def test_calculate_and_save_report_tools(client, monkeypatch):
    sid, owner, _ = session_with_docs(client)
    registry = get_registry()
    assert run(registry, "calculate", {"expression": "12 * (3 + 4)"}).output == "12 * (3 + 4) = 84"
    assert run(registry, "calculate", {"expression": "__import__('os')"}).status == "ERROR"

    monkeypatch.setattr(get_settings(), "max_reports_per_session", 2)
    ctx = context(sid)
    for n in range(2):
        saved = run(registry, "save_report", {"title": f"Draft {n}", "content": "A short draft of the report."}, ctx)
        assert saved.ok and "report_id" in saved.data
    third = run(registry, "save_report", {"title": "Draft 3", "content": "A short draft of the report."}, ctx)
    assert third.status == "ERROR" and "at most 2" in third.error
    with client.session_factory() as db:
        assert len(db.scalars(select(Report).where(Report.session_id == sid)).all()) == 2

    listed = client.get(f"/sessions/{sid}/reports", headers=owner).json()
    assert [r["title"] for r in listed] == ["Draft 0", "Draft 1"] and listed[0]["chars"] > 10
    detail = client.get(f"/sessions/{sid}/reports/{listed[0]['id']}", headers=owner).json()
    assert detail["content"] == "A short draft of the report."
    stranger, _ = make_user(client, "stranger")
    assert client.get(f"/sessions/{sid}/reports", headers=stranger).status_code == 404


def test_tool_listing_endpoints(client):
    owner, _ = make_user(client, "owner")
    assert client.get("/tools").status_code == 401
    names = {t["name"] for t in client.get("/tools", headers=owner).json()}
    assert "calculate" in names and "save_report" in names and len(names) == 7
    s = create_session(client, owner)
    assert client.get(f"/sessions/{s['id']}/tools", headers=owner).json() == []
    stranger, _ = make_user(client, "stranger")
    assert client.get(f"/sessions/{s['id']}/tools", headers=stranger).status_code == 404