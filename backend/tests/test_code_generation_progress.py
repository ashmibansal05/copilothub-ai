"""Regression checks for incremental coding artifacts and faster small tasks."""
import asyncio

from app.services.coding_agent import file_plan, generate_files


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.calls.append((prompt, kwargs))
        if 'Return ONLY JSON' in prompt:
            return '{"files":["app.py", "README.md"]}'
        if 'CURRENT FILE: app.py' in prompt:
            return 'print("hello")'
        if 'CURRENT FILE: calculator.cpp' in prompt:
            return '#include <iostream>\nint main(){ std::cout << 42; }'
        return '# Project\n'


def test_single_language_calculator_skips_manifest_llm():
    async def run():
        provider = FakeProvider()
        paths = await file_plan(provider, 'Write a C++ calculator program', [])
        assert paths == ['calculator.cpp', 'README.md']
        assert provider.calls == []
    asyncio.run(run())


def test_saves_each_file_before_generating_next():
    async def run():
        provider = FakeProvider()
        sequence = []

        async def progress(stage, index, total, path):
            sequence.append(('progress', stage, path))

        async def save(path, content, index, total):
            sequence.append(('saved', path, index, total))

        result = await generate_files(provider, 'Write a C++ calculator program', [],
                                      on_progress=progress, on_file=save)
        assert list(result) == ['calculator.cpp', 'README.md']
        assert sequence == [
            ('progress', 'planning', ''),
            ('progress', 'generating', 'calculator.cpp'),
            ('saved', 'calculator.cpp', 1, 2),
            ('progress', 'generating', 'README.md'),
            ('saved', 'README.md', 2, 2),
        ]
        assert len(provider.calls) == 1
        assert 'g++' in result['README.md']
    asyncio.run(run())


def test_existing_multi_file_manifest_still_works():
    async def run():
        provider = FakeProvider()
        result = await generate_files(provider, 'Build an application using Python', [])
        assert 'app.py' in result
        assert len(provider.calls) == 3
    asyncio.run(run())
