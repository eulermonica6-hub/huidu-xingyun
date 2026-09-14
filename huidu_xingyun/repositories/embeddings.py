"""嵌入后端：把文本转为向量。

插件式设计：首选 DashScope `text-embedding-v3`（复用 ali 密钥、无需下载模型），
回退本地 BGE（`sentence_transformers` 已随环境安装），便于离线部署。
"""

from __future__ import annotations

from typing import Sequence

from ..models.retry import retry_transient


class EmbeddingBackend:
    """嵌入后端接口。"""

    name: str = "base"
    model: str = ""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class DashScopeEmbeddings(EmbeddingBackend):
    """阿里百炼 text-embedding-v3，走 DashScope 原生嵌入端点。

    说明：OpenAI 兼容端点的 ``/embeddings`` 与 openai 3.x 客户端存在请求体格式
    不兼容（DashScope 原生校验拒绝），故这里直接调用原生 REST 端点，复用同一
    ``ali`` 密钥。批量上限按 10 条保守处理。
    """

    URL = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"

    def __init__(self, api_key: str, model: str = "text-embedding-v3") -> None:
        import requests

        self.name = "dashscope"
        self.model = model
        self._api_key = api_key
        self._requests = requests

    def _post(self, texts: list[str], text_type: str):
        return self._requests.post(
            self.URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": {"texts": texts},
                "parameters": {"text_type": text_type},
            },
            timeout=120,
        )

    def _call(self, texts: list[str], text_type: str) -> list[list[float]]:
        response = retry_transient(
            lambda: self._post(texts, text_type),
            retries=4,
            backoff=(1.0, 2.0, 4.0),
        )
        response.raise_for_status()
        payload = response.json()
        records = payload.get("output", {}).get("embeddings", [])
        records.sort(key=lambda item: item.get("text_index", 0))
        return [record["embedding"] for record in records]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        output: list[list[float]] = []
        for offset in range(0, len(texts), 10):
            batch = list(texts[offset : offset + 10])
            output.extend(self._call(batch, text_type="document"))
        return output

    def embed_query(self, text: str) -> list[float]:
        return self._call([text], text_type="query")[0]


class LocalBgeEmbeddings(EmbeddingBackend):
    """本地 BGE 中文模型，离线兜底（首次使用需下载模型权重）。"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        from sentence_transformers import SentenceTransformer

        self.name = "bge"
        self.model = model_name
        self._model = SentenceTransformer(model_name)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.encode([text], normalize_embeddings=True)[0]
        return vector.tolist()