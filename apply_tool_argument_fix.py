"""CoPilotHub AI: targeted Phase 11 tool-argument fixes.
Run from the repository root: python apply_tool_argument_fix.py
Creates .bak backups and a focused regression-test file. Does not change DB or Docker volumes.
"""
from __future__ import annotations
import ast
from pathlib import Path
import shutil

ROOT = Path.cwd()
PROMPTS = ROOT / 'backend/app/agents/prompts.py'
BASE = ROOT / 'backend/app/tools/base.py'
REGISTRY = ROOT / 'backend/app/tools/registry.py'
TEST = ROOT / 'backend/tests/test_tool_argument_repair.py'


def replace_once(source: str, old: str, new: str, title: str) -> str:
    occurrences = source.count(old)
    if occurrences != 1:
        raise RuntimeError(f'{title}: expected exactly one matching code block, got {occurrences}. No files changed.')
    return source.replace(old, new, 1)


prompt_old = '- Call at most one tool per reply. Arguments must match the listed parameters exactly.'
prompt_new = '''- Call at most one tool per reply. Arguments must match the listed parameters exactly.
- Use real JSON arrays for array parameters; NEVER encode an array as a quoted string.
- search_web max_results must be an integer from 1 through 8 (prefer 5).
- retrieve_documents k must be an integer from 1 through 8 (prefer 4).
- compare_sources topics must be an array of 2 to 5 strings and criteria an array of 1 to 6 strings; at most 12 topic-criterion pairs.
- calculate supports arithmetic only, not comparisons (such as 8 < 10), Python statements, or arbitrary code.
- Example tool call: {"action":"tool","tool":"compare_sources","arguments":{"topics":["AWS","Azure"],"criteria":["cost","security"]}}.
- On a validation error, do not repeat the same invalid call; use the error to correct the arguments.'''

base_old = '''            optional = "" if name in required else f" (optional, default {prop.get('default')!r})"
            parts.append(f"{name}: {kind}{optional}")'''
base_new = '''            limits = []
            if "minimum" in prop:
                limits.append(f"min {prop['minimum']}")
            if "maximum" in prop:
                limits.append(f"max {prop['maximum']}")
            if "minItems" in prop:
                limits.append(f"min items {prop['minItems']}")
            if "maxItems" in prop:
                limits.append(f"max items {prop['maxItems']}")
            if "minLength" in prop:
                limits.append(f"min chars {prop['minLength']}")
            if "maxLength" in prop:
                limits.append(f"max chars {prop['maxLength']}")
            constraints = f" ({', '.join(limits)})" if limits else ""
            optional = "" if name in required else f" (optional, default {prop.get('default')!r})"
            parts.append(f"{name}: {kind}{constraints}{optional}")'''

registry_import_old = '''import asyncio
import json'''
registry_import_new = '''import asyncio
import ast
import json'''

registry_helper_anchor = '''class ToolRegistry:
'''
registry_helper = '''def normalize_known_llm_mistakes(name: str, raw: dict) -> tuple[dict, list[str]]:
    """Repair only known, low-risk model formatting errors.

    This is NOT a validation bypass; the result must still pass the original
    Pydantic schema. Do not correct unknown tools or unknown parameters.
    """
    args = dict(raw)
    repairs: list[str] = []

    bounds = {"search_web": "max_results", "retrieve_documents": "k"}
    bound_name = bounds.get(name)
    if bound_name and type(args.get(bound_name)) is int and args[bound_name] > 8:
        repairs.append(f"{bound_name}: {args[bound_name]} -> 8")
        args[bound_name] = 8

    if name == "compare_sources":
        for key in ("topics", "criteria"):
            value = args.get(key)
            if not isinstance(value, str) or len(value) > 1000:
                continue
            stripped = value.strip()
            if not (stripped.startswith("[") and stripped.endswith("]")):
                continue
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                try:
                    parsed = ast.literal_eval(stripped)
                except (ValueError, SyntaxError, TypeError, RecursionError):
                    continue
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                args[key] = parsed
                repairs.append(f"{key}: encoded string -> JSON array")

    return args, repairs


class ToolRegistry:
'''
registry_validate_old = '''        try:
            args = tool.args_model.model_validate(raw_arguments)
        except ValidationError as exc:
            return done("REJECTED", error=f"Invalid arguments: {_format_validation_error(exc)}")'''
registry_validate_new = '''        effective, repairs = normalize_known_llm_mistakes(name, raw_arguments)
        if repairs:
            logger.info("Normalized tool %s arguments: %s", label, "; ".join(repairs))
            preview = preview_arguments(effective)
        try:
            args = tool.args_model.model_validate(effective)
        except ValidationError as exc:
            return done("REJECTED", error=f"Invalid arguments: {_format_validation_error(exc)}")'''

test_code = '''"""Regression checks for real Llama tool argument errors in Sessions 1 and 2."""
from app.tools.base import describe_tools
from app.tools.builtin import CompareSourcesTool, RetrieveDocumentsTool, SearchWebTool
from app.tools.registry import normalize_known_llm_mistakes
import pytest
from pydantic import ValidationError


def test_clamp_known_web_and_retrieval_limits():
    web, repairs = normalize_known_llm_mistakes("search_web", {"query": "cloud platforms", "max_results": 10})
    assert web["max_results"] == 8 and repairs
    SearchWebTool.args_model.model_validate(web)
    docs, repairs = normalize_known_llm_mistakes("retrieve_documents", {"query": "cloud storage", "k": 10})
    assert docs["k"] == 8 and repairs
    RetrieveDocumentsTool.args_model.model_validate(docs)


def test_decode_only_stringified_lists():
    original = {"topics": '["AWS", "Azure"]', "criteria": "['cost', 'security']"}
    fixed, repairs = normalize_known_llm_mistakes("compare_sources", original)
    assert fixed == {"topics": ["AWS", "Azure"], "criteria": ["cost", "security"]}
    assert len(repairs) == 2
    assert isinstance(original["topics"], str)  # no mutation
    CompareSourcesTool.args_model.model_validate(fixed)


def test_still_rejects_invalid_arrays_and_unknown_tools():
    invalid, _ = normalize_known_llm_mistakes("compare_sources", {"topics": '["AWS"]'})
    with pytest.raises(ValidationError):
        CompareSourcesTool.args_model.model_validate(invalid)  # min 2 topics
    unknown, repairs = normalize_known_llm_mistakes("unknown", {"max_results": 10})
    assert unknown == {"max_results": 10} and not repairs
    boolean_value, repairs = normalize_known_llm_mistakes("search_web", {"max_results": True})
    assert boolean_value["max_results"] is True and not repairs


def test_tool_description_includes_real_bounds():
    descriptions = describe_tools([SearchWebTool().spec(), RetrieveDocumentsTool().spec(), CompareSourcesTool().spec()])
    assert "max 8" in descriptions
    assert "min items 2" in descriptions
    assert "array of string" in descriptions
'''


def main():
    for path in (PROMPTS, BASE, REGISTRY):
        if not path.is_file():
            raise RuntimeError(f'Missing {path}; run from CoPilotHub AI project root.')
    original = {p: p.read_text(encoding='utf-8-sig') for p in (PROMPTS, BASE, REGISTRY)}
    patched = dict(original)
    patched[PROMPTS] = replace_once(patched[PROMPTS], prompt_old, prompt_new, 'prompts.py')
    patched[BASE] = replace_once(patched[BASE], base_old, base_new, 'base.py')
    patched[REGISTRY] = replace_once(patched[REGISTRY], registry_import_old, registry_import_new, 'registry.py import')
    patched[REGISTRY] = replace_once(patched[REGISTRY], registry_helper_anchor, registry_helper, 'registry.py helper')
    patched[REGISTRY] = replace_once(patched[REGISTRY], registry_validate_old, registry_validate_new, 'registry.py validation')
    if TEST.exists():
        raise RuntimeError(f'{TEST} already exists. Nothing changed to avoid overwriting it.')
    for path, contents in patched.items():
        ast.parse(contents, filename=str(path))
    ast.parse(test_code, filename=str(TEST))
    for path in patched:
        backup = path.with_suffix(path.suffix + '.bak')
        if backup.exists():
            raise RuntimeError(f'Backup {backup} already exists; refusing to overwrite. Nothing changed.')
    for path in patched:
        shutil.copy2(path, path.with_suffix(path.suffix + '.bak'))
    for path, contents in patched.items():
        path.write_text(contents, encoding='utf-8')
        print(f'Patched {path.relative_to(ROOT)}')
    TEST.parent.mkdir(parents=True, exist_ok=True)
    TEST.write_text(test_code, encoding='utf-8')
    print(f'Created {TEST.relative_to(ROOT)}')
    print('Backups saved as *.py.bak; check git diff and run tests before restarting.')


if __name__ == '__main__':
    main()
