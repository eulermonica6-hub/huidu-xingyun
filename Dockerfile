# Dockerfile —— 面向 Hugging Face Spaces（Docker SDK）。
# 应用监听 HF 默认端口 7860；免费档为 CPU，本 agent 的重计算在云端 LLM/嵌入 API，
# 本地仅加载小数据（图谱/元数据，约 29MB）与内存索引。

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 HUIDU_PORT=7860

# 只装运行所需依赖（不含 torch / sentence-transformers / neo4j —— 本地 BGE 与 Neo4j 为可选路径）
RUN pip install --no-cache-dir \
    "langchain>=1.2,<2.0" "langgraph>=1.0,<2.0" \
    langchain-openai langchain-deepseek langchain-groq langchain-nvidia-ai-endpoints \
    "pydantic>=2.0,<3.0" "pydantic-settings>=2.0,<3.0" "python-dotenv>=1.0" \
    "numpy>=1.26" \
    "fastapi>=0.110" "uvicorn[standard]>=0.29"

COPY huidu_xingyun/ ./huidu_xingyun/
COPY config/ ./config/
COPY data/package/ ./data/package/
COPY pyproject.toml ./

EXPOSE 7860
CMD ["uvicorn", "huidu_xingyun.server.app:app", "--host", "0.0.0.0", "--port", "7860"]