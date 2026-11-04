import json
import re
from typing import Any

from app.llm.base import LLMResponseError

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Qwen3 can emit <think>...</think> reasoning. We never show or parse it."""
    text = _THINK_RE.sub("", text)
    idx = text.lower().find("<think>")  # unterminated block (truncated output)
    if idx != -1:
        text = text[:idx]
    return text.strip()


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences and extra prose."""
    text = strip_thinking(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMResponseError("Model did not return valid JSON")