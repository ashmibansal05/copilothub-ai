"""Small-model output must not corrupt a saved project file."""
import asyncio
import pytest
from app.services.coding_agent import clean_file_output, generate_files
from app.services.code_service import CodeError


def test_extracts_requested_language_from_multifile_fences():
    raw = '```cpp\nint main(){ return 0; }\n```\n```python\nprint(3)\n```'
    cpp = clean_file_output('calculator.cpp', raw)
    assert 'int main' in cpp
    assert 'print(3)' not in cpp
    assert '```' not in cpp
    py = clean_file_output('calculator.py', raw)
    assert py.strip() == 'print(3)'


def test_rejects_raw_cpp_with_fenced_python():
    with pytest.raises(CodeError):
        clean_file_output('calculator.cpp', 'int main() {}\n```\n```python\nprint(3)\n```')


def test_rejects_invalid_python_syntax():
    with pytest.raises(CodeError, match='Invalid generated file'):
        clean_file_output('calculator.py', 'def broken(:\n  pass')


def test_retries_invalid_file_once_and_saves_cleaned_code():
    class Provider:
        def __init__(self): self.calls = 0
        async def generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return 'int main() {}\n```python\nprint(3)\n```'
            return '```cpp\nint main(){ return 0; }\n```'
    async def run():
        provider = Provider()
        saved = {}
        async def save(path, content, index, total): saved[path] = content
        out = await generate_files(provider, 'Write a C++ calculator program', [], on_file=save)
        assert provider.calls == 2
        assert out['calculator.cpp'] == saved['calculator.cpp']
        assert 'print(3)' not in saved['calculator.cpp']
    asyncio.run(run())


def test_does_not_save_bad_file_after_retry_fails():
    class Provider:
        async def generate(self, messages, **kwargs):
            return '```python\nprint(3)\n```\nextra noncode'
    async def run():
        saved = []
        async def save(*args): saved.append(args)
        with pytest.raises(CodeError):
            await generate_files(Provider(), 'Write a C++ calculator program', [], on_file=save)
        assert saved == []
    asyncio.run(run())
