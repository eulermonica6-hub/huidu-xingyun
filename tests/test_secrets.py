"""密钥加载器测试：只解析具名条目，忽略无标签行，脱敏可用。"""

from __future__ import annotations

from pathlib import Path

from huidu_xingyun.config.secrets import SecretLoader, redact


def test_secret_loader_parses_labeled_only(tmp_path: Path) -> None:
    secret_file = tmp_path / "keys.txt"
    secret_file.write_text(
        'deepseek: sk-abc123;\n'
        'groq: ["gsk_111", "gsk_222"];\n'
        "nvapi=nvapi-xyz;\n"
        "agnes: sk-agnes;\n"
        "unlabeled sk-ghost\n",
        encoding="utf-8",
    )
    loader = SecretLoader(secret_file)
    loader.load()
    assert loader.first_key("deepseek") == "sk-abc123"
    assert loader.keys_for("groq") == ["gsk_111", "gsk_222"]
    assert loader.first_key("nvapi") == "nvapi-xyz"
    # 无标签行不得被解析
    assert not any("sk-ghost" in key for label in loader.labels for key in loader.keys_for(label))


def test_secret_loader_missing_file_returns_empty(tmp_path: Path) -> None:
    loader = SecretLoader(tmp_path / "nope.txt")
    assert loader.load() == {}


def test_secret_loader_multiline_json_array(tmp_path: Path) -> None:
    # 真实密钥文件中 groq 的 key 池跨多行，需正确合并解析为列表。
    secret_file = tmp_path / "keys.txt"
    secret_file.write_text(
        'groq: ["gsk_111",\n'
        '    "gsk_222",\n'
        '    "gsk_333"];\n'
        "ali: sk-ws-abc.def;\n",
        encoding="utf-8",
    )
    loader = SecretLoader(secret_file)
    loader.load()
    assert loader.keys_for("groq") == ["gsk_111", "gsk_222", "gsk_333"]
    assert loader.first_key("ali") == "sk-ws-abc.def"


def test_redact_masks_tokens() -> None:
    redacted = redact("使用 sk-abc123 和 nvapi-xyz 以及 gsk_aaa")
    assert "sk-abc123" not in redacted
    assert "nvapi-xyz" not in redacted
    assert "***" in redacted
