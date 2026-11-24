from app.services.coding_agent import classify_task


def test_research_code_and_hybrid_classification():
    assert classify_task("a c++ program for a simple calculator") == "CODING"
    assert classify_task("Build a student attendance management system using FastAPI") == "CODING"
    assert classify_task("Research the advantages of cloud computing") == "RESEARCH"
    assert classify_task("Compare bubble sort and merge sort, then implement both in Python") == "HYBRID"


def test_start_coding_routes_to_code_generator(client, monkeypatch):
    from helpers import make_user, create_session
    from app.agents.runner import agent_runner
    import app.api.code as code_api
    calls = []

    def fake_auto(sid, task, *, hybrid=False):
        calls.append((str(sid), task, hybrid))
        return True

    async def unexpected_research_start(_sid):
        raise AssertionError("CODING must not start research orchestration")

    monkeypatch.setattr(code_api, "start_automatic_code", fake_auto)
    monkeypatch.setattr(agent_runner, "start", unexpected_research_start)
    auth, _ = make_user(client, "codeowner")
    session = create_session(client, auth, name="Calculator", task="a c++ program for a simple calculator")
    result = client.post(f"/sessions/{session['id']}/start", headers=auth)
    assert result.status_code == 200, result.text
    assert calls == [(session["id"], "a c++ program for a simple calculator", False)]


def test_start_research_keeps_research_orchestrator(client, monkeypatch):
    from helpers import make_user, create_session
    from app.agents.runner import agent_runner
    import app.api.code as code_api
    called = []

    async def fake_research_start(sid):
        called.append(str(sid))
        return True

    def unexpected_code(*args, **kwargs):
        raise AssertionError("RESEARCH must not start code generator")

    monkeypatch.setattr(code_api, "start_automatic_code", unexpected_code)
    monkeypatch.setattr(agent_runner, "start", fake_research_start)
    auth, _ = make_user(client, "researchowner")
    session = create_session(client, auth, name="Cloud", task="Research cloud computing advantages")
    result = client.post(f"/sessions/{session['id']}/start", headers=auth)
    assert result.status_code == 200, result.text
    assert called == [session["id"]]


def test_llm_plain_findings_without_action_are_accepted():
    import asyncio
    from app.agents.brain import FinalAnswer
    from app.agents.llm_brain import LLMBrain

    class Provider:
        name = "fake"
        model = "fake"

        async def generate(self, *_args, **_kwargs):
            return '{"findings":"A calculator can use a switch statement for operations."}'

    result = asyncio.run(LLMBrain(Provider()).next_action(
        "Explain arithmetic", "Explain", [], [], tools=[], force_final=False
    ))
    assert isinstance(result, FinalAnswer)
    assert "switch statement" in result.text


def test_generated_program_files_use_model_output_not_research_tools():
    import asyncio
    from app.services.coding_agent import generate_files

    class Provider:
        async def generate(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "Return ONLY JSON" in prompt:
                return '{"files":["calculator.py","calculator.cpp","README.md"]}'
            if "CURRENT FILE: calculator.py" in prompt:
                return 'print(1 + 2)'
            if "CURRENT FILE: calculator.cpp" in prompt:
                return '#include <iostream>\nint main(){ std::cout << 3; }'
            return '# Calculator\nRun the two programs.'

    output = asyncio.run(generate_files(Provider(), "Write a C++ and Python calculator program", []))
    assert set(output) == {"calculator.py", "calculator.cpp", "README.md"}
    assert output["calculator.py"].strip() == "print(1 + 2)"
