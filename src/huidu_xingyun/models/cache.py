"""确定性 LLM 角色的轻量磁盘缓存。

只对 temperature=0 确定性角色（路由、审校）启用，回答模型（temperature=0.1）
不缓存以保留表达多样性。键为 ``sha256(role + 归一化提示)``；值写入 JSONL，
只追加不覆盖。进程内用字典加速，磁盘仅作跨进程持久化。
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any


def cache_key(role: str, prompt: str) -> str:
    digest = hashlib.sha256(f"{role}\n{prompt}".encode("utf-8")).hexdigest()
    return digest


class LLMCache:
    def __init__(self, path: Path | None = None, ttl_seconds: float = 3600.0) -> None:
        self.path = path
        self.ttl = ttl_seconds
        self._memory: dict[str, str] = {}
        self._lock = threading.Lock()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = row.get("key")
                    output = row.get("output")
                    if key and output is not None:
                        self._memory[key] = output
        except OSError:
            pass

    def get(self, key: str) -> str | None:
        with self._lock:
            if not self._memory and self.path and self.path.exists():
                self._load()
        return self._memory.get(key)

    def set(self, key: str, output: str) -> None:
        with self._lock:
            self._memory[key] = output
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"key": key, "output": output}, ensure_ascii=False) + "\n")
        except OSError:
            pass


def _prompt_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for message in messages:
        role = getattr(message, "type", None) or message.__class__.__name__
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        parts.append(f"{role}:{content}")
    return "\n".join(parts)