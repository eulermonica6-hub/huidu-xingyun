# 部署运行手册（09）

本地与公开部署的操作步骤、数据重建与故障排查。

## 1. 环境与依赖

- Python 3.11 / 3.12（Windows / Linux / macOS）。
- 依赖（`pyproject.toml` 已声明）：

```powershell
pip install "langchain>=1.2,<2.0" "langgraph>=1.0,<2.0" langchain-openai langchain-deepseek \
    langchain-groq langchain-nvidia-ai-endpoints "numpy>=1.26" "sentence-transformers>=3.0" \
    neo4j "pydantic>=2.0,<3.0" pydantic-settings "pytest" "pytest-asyncio"
```

> 包为扁平布局，在项目根目录直接 `python -m huidu_xingyun.cli …` 或 `python scripts/…` 即可，无需安装、无需 `PYTHONPATH`。

## 2. 配置

### 2.1 模型角色（`.env`）

复制 `.env.example` 为 `.env`，按需覆盖：

| 变量 | 默认 | 说明 |
|---|---|---|
| `HUIDU_ROUTER_MODEL` | `qwen-flash` | 意图路由（快模型） |
| `HUIDU_REASONER_MODEL` | `qwen-plus` | 领域推理（强模型） |
| `HUIDU_VERIFIER_MODEL` | `qwen-flash` | 逐句审校（快模型） |
| `HUIDU_FALLBACK_PROVIDER` / `_MODEL` | `zhipu` / `glm-4-flash` | Provider 级兜底 |

Provider 分别对应：`ali`（DashScope，OpenAI 兼容端点）、`zhipu`（智谱）、`deepseek`、`groq`、`nvapi`。路由/审校确定性角色启用磁盘缓存 `runtime/cache/llm_cache.jsonl`。

### 2.2 密钥（工程外）

密钥文件位于工程**上一级**：`../LLM api key.txt`，每条一标签：

```text
ali: <dashscope-key>;
zhipu: <zhipu-key>;
```

- 只解析具名条目；多行 JSON 数组（多 key 池）亦支持。
- 密钥仅存内存，日志与导出均脱敏，绝不被提交。

### 2.3 数据路径

`config/data_paths.json` 读取 `runtime_data`（`data/package/`）与 `derived`（`data/derived/`）段。业务代码禁止触碰只读构建源路径。

## 3. 校验与探测

```powershell
python scripts/validate_foundation.py      # 路径/数量/字段/密钥标签
python scripts/probe_models.py --provider ali    # 锁定可用模型
python scripts/probe_models.py --provider zhipu  # 兜底能力
```

探测通过 chat / JSON 意图 / 工具调用三项才算可进正式路由；报告写 `data/derived/model_probe_report.json`。

## 4. 运行

```powershell
python -m huidu_xingyun.cli ask "星云大师在哪些文章中谈到共生？"
python -m huidu_xingyun.cli ask --no-llm "什么是人間佛教"   # 离线规则模式
python -m huidu_xingyun.cli ask --export "慈悲与教育是什么关系？"
python -m huidu_xingyun.cli repl                            # 多轮交互
```

`--export` 输出 Markdown 证据包到 `outputs/evidence_<trace>_<ts>.md`。审计日志在 `runtime/logs/audit.jsonl`（只记 provider/model/时延/重试/错误类型，无密钥）。

## 5. 数据重建

### 5.1 便携数据包（仅小数据入仓）

仓库提交了图谱/元数据/文章清单；190MB 的 20,020 篇正文默认不入仓。从冻结源重建（需本机存在原始 `../../数据` 与 `../../formal_experiment`）：

```powershell
python scripts/build_portable_data.py                 # 重建 data/package
python scripts/build_portable_data.py --validate-only # 冷读复核
```

产出：`data/package/corpus/articles/`（20,020 篇正文）及其余规范化表。

### 5.2 语义向量索引

```powershell
python scripts/build_vector_index.py                  # DashScope text-embedding-v3
python scripts/build_vector_index.py --local-bge      # 离线 BGE 兜底
python scripts/build_vector_index.py --validate-only
```

产物 `data/derived/vector_metadata/document_embeddings.npy`（20,020 × 1024，归一化）+ 构建报告。构建带断点续跑（`build_progress.json`），网络抖动可续。

## 6. 测试

```powershell
python -m pytest -q
```

`tests/` 覆盖：路由/实体解析/图谱/全文/语义向量/可靠层（重试缓存）/模型路由（主备回退）/多轮指代/密钥解析/证据导出，全程离线不调 API。

## 7. 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `deepseek` 402 | 账号余额不足，换 Provider |
| `groq` 401 | 密钥失效，换 key 或 Provider |
| 智谱 1301 内容过滤 | 间歇性内容安全拦截；已内置重试，命中则降级证据摘要 |
| 嵌入/LLM `SSLError` 瞬时失败 | 已内置重试 + 断点续跑 |
| 简化字「人间佛教」触发澄清 | 别名表歧义；用繁体「人間佛教」或补简体→繁体归一化 |
| 高连接度实体回答偏慢 | reasoner 大证据块耗时；调小 top-N 证据或换推理模型 |
| `pip install -e .` 报编码错 | 中文路径 editable 安装偶发；无需安装，直接 `python -m huidu_xingyun.cli …` |

## 8. API 服务与公开部署要点

- **API 层已实现**（`huidu_xingyun/server/`）：`python -m huidu_xingyun.server` 起服务，
  `POST /api/v1/ask`、`POST /api/v1/export`、`GET /api/v1/health`（AgentContext 单例复用）。
- 前端仍未接入；公开部署按 `docs/13_deployment_plan.md` 补三栏前端 → 反向代理/HTTPS → 合规备案。
- 上线前完成：等保/大模型备案（以实际为准）、密钥轮换、只读数据库与代理、`docs/10_competition_description.md` 中「测试链接/账号」填写。