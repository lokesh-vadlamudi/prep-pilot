"""Client for the DGX vLLM OpenAI-compatible API (qwen3.8-27b)."""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import settings


class LLMError(RuntimeError):
    pass


async def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    num_predict: int = 1200,
) -> str:
    payload = {
        "model": settings.model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": num_predict,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
            r = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions", json=payload
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise LLMError(f"DGX model unreachable: {e}") from e
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("DGX model returned no completion choices")
    content = (choices[0].get("message", {}) or {}).get("content")
    if not content:
        raise LLMError("DGX model returned an empty completion")
    return content.strip()


def _extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of a model response.

    Handles code-heavy payloads: braces/brackets inside string values are ignored
    (string-aware scan), and parsing is lenient (`strict=False`) so literal tabs /
    newlines inside strings — common when embedding source code — don't break it.
    """
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start == -1:
        raise LLMError("No JSON found in model output")
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob, strict=False)
                except json.JSONDecodeError as e:
                    raise LLMError(f"Malformed JSON in model output: {e}") from e
    raise LLMError("Unbalanced JSON in model output")


async def chat_json(
    messages: list[dict[str, str]], *, temperature: float = 0.3, num_predict: int = 1600
) -> Any:
    raw = await chat(messages, temperature=temperature, num_predict=num_predict)
    return _extract_json(raw)


async def health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.llm_base_url.rstrip('/')}/models")
            return r.status_code == 200
    except httpx.HTTPError:
        return False
