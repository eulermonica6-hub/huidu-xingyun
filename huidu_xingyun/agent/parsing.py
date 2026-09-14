"""把 LLM 文本响应稳健解析为 Pydantic 对象。

各 Provider 的 JSON 模式能力不一致（智谱 GLM 忽略 JSON 模式），因此路由/审校
统一采用「提示词要求 JSON + 文本解析」的路径；解析失败时由调用方规则兜底。
"""

from __future__ import annotations

import json
import re
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def parse_json_object(text: str, model_cls: Type[T]) -> T | None:
    if not text:
        return None
    for candidate in _json_candidates(text):
        try:
            return model_cls.model_validate(json.loads(candidate))
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _json_candidates(text: str) -> list[str]:
    stripped = text.strip()
    candidates: list[str] = []

    balanced = _extract_balanced(stripped, "{", "}")
    if balanced:
        candidates.append(balanced)

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))

    if stripped:
        candidates.append(stripped)

    unique: list[str] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _extract_balanced(text: str, open_char: str, close_char: str) -> str | None:
    start = text.find(open_char)
    if start < 0:
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == open_char:
            depth += 1
        elif text[index] == close_char:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
