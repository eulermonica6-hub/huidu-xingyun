"""运行时配置与路径解析。

约定：Agent 业务代码只读取 :class:`RuntimePaths` 指向的 ``data/package/``
规范化数据，绝不读取 ``config/data_paths.json`` 中 ``corpus`` /
``knowledge_graph`` / ``analysis`` / ``evaluation`` 等只读构建源路径。

API Key 不进入本模型：密钥由 :class:`~huidu_xingyun.config.secrets.SecretLoader`
从外部秘密文件解析，只在当前进程内存中存在。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录为 src/huidu_xingyun/config 向上三级。
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"

# 无 .env 时不报错；密钥一律来自外部秘密文件，不由 .env 承载。
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings(BaseSettings):
    """从环境变量（含可选 .env）读取的运行配置。"""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    project_name: str = Field(default="慧读星云", validation_alias="HUIDU_PROJECT_NAME")
    data_config: str = Field(default="config/data_paths.json", validation_alias="HUIDU_DATA_CONFIG")
    models_config: str = Field(
        default="config/models.example.json", validation_alias="HUIDU_MODEL_CONFIG"
    )
    secret_file: str = Field(default="../LLM api key.txt", validation_alias="HUIDU_SECRET_FILE")
    allow_unlabeled_keys: bool = Field(
        default=False, validation_alias="HUIDU_ALLOW_UNLABELED_KEYS"
    )

    router_provider: str = Field(default="ali", validation_alias="HUIDU_ROUTER_PROVIDER")
    router_model: str = Field(default="qwen-flash", validation_alias="HUIDU_ROUTER_MODEL")
    reasoner_provider: str = Field(default="ali", validation_alias="HUIDU_REASONER_PROVIDER")
    reasoner_model: str = Field(default="qwen-plus", validation_alias="HUIDU_REASONER_MODEL")
    verifier_provider: str = Field(default="ali", validation_alias="HUIDU_VERIFIER_PROVIDER")
    verifier_model: str = Field(default="qwen-flash", validation_alias="HUIDU_VERIFIER_MODEL")
    fallback_provider: str = Field(default="zhipu", validation_alias="HUIDU_FALLBACK_PROVIDER")
    fallback_model: str = Field(
        default="glm-4-flash", validation_alias="HUIDU_FALLBACK_MODEL"
    )

    neo4j_uri: str = Field(default="bolt://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_username: str = Field(default="neo4j", validation_alias="NEO4J_USERNAME")
    neo4j_password: str = Field(default="", validation_alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", validation_alias="NEO4J_DATABASE")

    log_level: str = Field(default="INFO", validation_alias="HUIDU_LOG_LEVEL")
    enable_llm_tracing: bool = Field(default=False, validation_alias="HUIDU_ENABLE_LLM_TRACING")

    @property
    def secret_path(self) -> Path:
        return (PROJECT_ROOT / self.secret_file).resolve()

    @property
    def data_config_path(self) -> Path:
        return (PROJECT_ROOT / self.data_config).resolve()

    @property
    def model_config_path(self) -> Path:
        return (PROJECT_ROOT / self.models_config).resolve()


class RuntimePaths:
    """解析 ``config/data_paths.json`` 的 ``runtime_data`` 与 ``derived`` 段。

    业务节点只通过本类拿路径，保证不接触只读构建源。
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        with config_path.open("r", encoding="utf-8") as stream:
            self._config: dict[str, Any] = json.load(stream)
        self._runtime: dict[str, str] = self._config["runtime_data"]
        self._derived: dict[str, str] = self._config["derived"]

    def resolve(self, value: str) -> Path:
        return (PROJECT_ROOT / value).resolve()

    def table(self, key: str) -> Path:
        return self.resolve(self._runtime[key])

    # 常用运行表路径。
    @property
    def documents(self) -> Path:
        return self.table("documents")

    @property
    def books(self) -> Path:
        return self.table("books")

    @property
    def article_text_root(self) -> Path:
        return self.table("article_text_root")

    @property
    def entities(self) -> Path:
        return self.table("entities")

    @property
    def aliases(self) -> Path:
        return self.table("aliases")

    @property
    def relation_types(self) -> Path:
        return self.table("relation_types")

    @property
    def relations(self) -> Path:
        return self.table("relations")

    @property
    def relation_evidence(self) -> Path:
        return self.table("relation_evidence")

    @property
    def claims(self) -> Path:
        return self.table("claims")

    @property
    def claim_relations(self) -> Path:
        return self.table("claim_relations")

    @property
    def claim_evidence(self) -> Path:
        return self.table("claim_evidence")

    @property
    def graph_metrics(self) -> Path:
        return self.table("graph_metrics")

    @property
    def entity_metrics(self) -> Path:
        return self.table("entity_metrics")

    @property
    def view_metrics(self) -> Path:
        return self.table("view_metrics")

    @property
    def quality_metrics(self) -> Path:
        return self.table("quality_metrics")

    # 派生目录（切片、向量、缓存、日志、导出）。
    @property
    def derived_root(self) -> Path:
        return self.resolve(self._derived["root"])

    @property
    def document_chunks(self) -> Path:
        return self.resolve(self._derived["document_chunks"])

    @property
    def vector_metadata(self) -> Path:
        return self.resolve(self._derived["vector_metadata"])

    @property
    def evaluation_sets(self) -> Path:
        return self.resolve(self._derived["evaluation_sets"])

    @property
    def cache(self) -> Path:
        return self.resolve(self._derived["cache"])

    @property
    def indexes(self) -> Path:
        return self.resolve(self._derived["indexes"])

    @property
    def logs(self) -> Path:
        return self.resolve(self._derived["logs"])

    @property
    def outputs(self) -> Path:
        return self.resolve(self._derived["outputs"])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_runtime_paths() -> RuntimePaths:
    return RuntimePaths(get_settings().data_config_path)
