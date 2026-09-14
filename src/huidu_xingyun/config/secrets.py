"""外部秘密文件加载器。

只解析带明确 ``label:value`` / ``label=value``（含全角冒号）的行；无标签行默认忽略。
密钥值仅存活于当前进程内存，任何日志、异常或文件写入都不得包含明文。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ACCEPTED_LABELS = {"deepseek", "groq", "nvapi", "agnes", "zhipu", "ali"}
_LABEL_PATTERN = re.compile(r"^([^:=：]+)\s*[:=：]\s*(.+)$")
_SECRET_PATTERN = re.compile(
    r"(?i)(sk-[A-Za-z0-9_.\-]+|nvapi-[A-Za-z0-9_\-]+|gsk_[A-Za-z0-9_\-]+)"
)


def redact(text: str) -> str:
    """把常见密钥/令牌替换为占位符，供日志与异常信息使用。"""
    if not text:
        return text
    return _SECRET_PATTERN.sub("***", text)


def _brackets_balanced(text: str) -> bool:
    return text.count("[") == text.count("]")


class SecretLoader:
    """解析外部密钥文件，只接受已登记 Provider 的具名条目。"""

    def __init__(self, path: Path, allowed_labels: set[str] | None = None) -> None:
        self.path = path
        self.allowed_labels = allowed_labels or ACCEPTED_LABELS
        self._values: dict[str, str | list[str]] = {}

    def load(self) -> dict[str, str | list[str]]:
        self._values.clear()
        if not self.path.exists():
            return self._values
        text = self.path.read_text(encoding="utf-8-sig", errors="replace")
        lines = [line.rstrip() for line in text.splitlines()]

        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if not line:
                index += 1
                continue
            match = _LABEL_PATTERN.match(line)
            if not match:
                index += 1
                continue
            label = match.group(1).strip().lower()
            value = match.group(2).strip()

            # 多行 JSON 数组：续读后续行直到方括号平衡（如 groq 的多 key 池）。
            if value.startswith("[") and not _brackets_balanced(value):
                cursor = index + 1
                while cursor < len(lines) and not _brackets_balanced(value):
                    value += " " + lines[cursor].strip()
                    cursor += 1
                index = cursor
            else:
                index += 1

            if label not in self.allowed_labels:
                continue
            self._values[label] = self._parse_value(value)
        return self._values

    @staticmethod
    def _parse_value(value: str) -> str | list[str]:
        value = value.rstrip(";").strip()
        if value.startswith("[") and value.endswith("]"):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return value
            if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                return parsed
        return value

    def keys_for(self, label: str) -> list[str]:
        value = self._values.get(label.lower())
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def first_key(self, label: str) -> str | None:
        keys = self.keys_for(label)
        return keys[0] if keys else None

    @property
    def labels(self) -> set[str]:
        return set(self._values)
