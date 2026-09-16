# 工作日志

## 2026-09-04 基础架构冻结

### 已完成

- 确定项目总名称和独立工程根目录。
- 脱敏识别外部密钥文件中的Provider标签，未输出密钥值。
- 验证全文清单20,020行、20,020个唯一文章ID、20,020个正文文件、105个合并卷册，无缺失路径。
- 冻结Stage265图谱发布数据和Stage266 Neo4j实现为业务基线。
- 确定Stage278、Stage279、Stage289为质量与边界依据。
- 建立数据路径、模型角色、项目章程、编排蓝图、决策日志和工作日志。

### 已知问题

- 密钥附件有9行缺少标签，默认不使用。
- Groq与NVAPI的具体模型ID尚未做在线能力探测。
- Agnes缺少API地址、模型ID和协议说明，暂时禁用。
- 本地Neo4j日志显示数据库曾成功启动，但最近记录为停止状态；接入前需执行只读健康检查。
- 尚未生成全文切片和向量索引。

### 下一步

1. 实现安全秘密加载器与配置模型。
2. 实现Provider模型工厂和在线能力探测脚本。
3. 定义Pydantic版 `IntentResult`、`EvidenceItem`、`FinalResponse` 和 `AgentState`。
4. 实现意图识别节点及固定测试用例。
5. 实现Neo4j只读连接和实体解析工具。

## 2026-09-07 便携数据包建立

### 已完成

- 新增 `config/data_schema.json`，统一13张运行表的字段、类型、主键、外键和ID格式。
- 新增 `scripts/build_portable_data.py`，从只读构建源复制、重命名并清洗运行数据。
- 生成 `data/package/`：20,020篇正文、105条书目、25,560个实体、43,632条别名、153种关系类型、2,748条稳定关系、3,514条稳定证据、4,250个Claim、3,960条Claim关系和4,437条Claim证据。
- 生成图指标1行、实体指标1,784行、专题视图指标5行及统一质量指标。
- 正文文件改为 `doc_########.txt`，删除重复元数据头；特殊的多行标题头已纳入清洗规则。
- 旧阶段编号只保留在 `metadata/id_map_*.csv`，运行表与运行文件名未检出阶段标记。
- 不复制105个合并卷册文本，避免与单篇正文重复。

### 验证结果

- 构建内校验通过。
- 独立 `--validate-only` 冷读取校验通过。
- 13张运行表字段顺序、必填值、主键、外键和ID格式通过。
- 正文文件数与文章清单均为20,020，未发现残留元数据头。
- 数据包共20,043个文件，138,925,628字节。

### 下一步

1. 实现配置加载器，并规定Agent业务代码只读 `runtime_data` 配置。
2. 实现Provider模型工厂和在线能力探测脚本。
3. 定义Pydantic版 `IntentResult`、`EvidenceItem`、`FinalResponse` 和 `AgentState`。
4. 先实现意图识别、实体解析和全文检索三个基础节点。
5. 以规范化CSV重新生成Neo4j导入脚本，移除业务代码对旧编号的依赖。

## 2026-09-13 首个端到端可运行竖切

### 已完成

- 实现配置/密钥层：`Settings`（pydantic-settings）、`RuntimePaths`（只读 `data/package/`）、`SecretLoader`（只解析具名条目、groq 多 key 池、脱敏）。
- 实现模型工厂 `ModelFactory` 与角色装配 `ModelBundle`；结构化输出改为「提示词驱动 JSON + 稳健解析」（`agent/parsing.py`），不依赖 Provider 不一致的 `with_structured_output`。
- 定义 Pydantic 契约：`IntentResult`、`EvidenceItem`（四层 A/B/C/D）、`ResolvedEntity`、`FinalResponse`、`VerificationResult`、`AgentState`。
- 实现仓储：`GraphRepository`（实体/别名解析、稳定关系、BFS≤3 跳路径、邻域、证据回链、冻结指标）、`CorpusRepository`（元数据 + 正文扫描）、`Neo4jClient`（只读健康检查）。
- 实现 LangGraph 编排：意图识别（规则先验 + LLM + 合并）、实体解析（「大师」不自动等同「星云大师」）、7 条路由、证据融合、答案生成、逐句审校（最多修订 1 次）、格式化、脱敏审计日志。
- 接入智谱 GLM：`langchain-openai` 走 OpenAI 兼容端点 `open.bigmodel.cn/api/paas/v4/`；`.env` 三个角色统一 `glm-4-flash`。
- CLI：`python -m huidu_xingyun.cli ask/repl`，支持 `--no-llm` 离线规则模式。
- 探测脚本 `scripts/probe_models.py`；离线测试集 30 条全绿。

### 验证结果

- 离线端到端（`--no-llm`）四类路由正确：实体歧义→澄清、直接关系→`graph_direct`、路径→`graph_retrieve`、指标→`graph_analytics`。
- 在线（glm-4-flash）实测「星云大师连接了哪些机构」正确路由 `graph_direct` 并返回机构列表与 A 层证据。
- `pytest -q` 30 passed。

### 已知问题

- 智谱内容安全过滤器会**间歇性**拦截佛教内容（错误码 1301），重试可通过；已在 `generate_answer` 加兜底，命中过滤时退回结构化证据摘要。
- `glm-4-flash` 单次调用约 8–20 秒，完整问答（意图+回答+审校，可能含一次修订）约 20–120 秒，演示偏慢；可考虑换 `glm-4-plus` 或加缓存。
- 简化字「人间佛教」在别名表中是歧义别名，会触发澄清（繁体「人間佛教」唯一）。
- 智谱 `with_structured_output` 不可用（JSON 模式被忽略、function-calling 参数解析异常），故全部结构化输出走 JSON 提示词解析。

### 下一步

1. 缓解智谱内容过滤与延迟（换模型/重试/缓存）。
2. 向量索引与 `search_corpus` 语义检索。
3. 以规范化 CSV 重新生成 Neo4j 导入脚本。
4. 补 `08_evaluation_plan.md` 固定测试集与路由准确率。

## 2026-09-11 首个端到端可运行竖切

### 已完成

- 新增 `src/huidu_xingyun/` 业务包，按蓝图落地 LangChain/LangGraph 编排：
  - `config/`：`Settings`（pydantic-settings，只读 env/`.env`）、`RuntimePaths`（只读 `runtime_data`）、`SecretLoader`（仅解析具名密钥、Groq 多 key 池、脱敏）。
  - `schemas/`：`IntentResult`、`EvidenceItem`（A/B/C/D 四层）、`ResolvedEntity`、`FinalResponse`、`VerificationResult`、`AgentState`。
  - `repositories/`：`GraphRepository`（实体/别名解析、关系/路径/邻域/证据/冻结指标，稳定层与 Claim 层分离）、`CorpusRepository`（元数据 + 正文关键词检索）、`Neo4jClient`（只读健康检查）。
  - `models/`：`ModelFactory`（角色→Provider→ChatModel + 结构化输出 + `ModelBundle`）、`probe.py` 在线能力探测。
  - `tools/`：实体、图谱、证据、全文四组受控 `@tool` 包装。
  - `agent/`：`nodes`（14 个节点）、`routing`（规则先验 + 意图→路由 + 歧义消歧）、`prompts`、`graph`（StateGraph 装配）、`pipeline`（`run_agent`）。
  - `cli.py`：`ask` / `repl`，支持 `--no-llm` 离线规则模式。
  - `scripts/probe_models.py`：探测并回写 `.env` 的模型 ID。
  - `tests/`：31 个离线测试。

### 验证结果

- `python scripts/validate_foundation.py` 通过，源数据与密钥未变动。
- `python -m pytest -q` 31 passed。
- 离线 CLI 三条核心路线跑通：`graph_direct`（星雲大師→机构，按类型过滤）、`graph_analytics`（桥梁指标）、`corpus_retrieve`（共生出处）。
- 实体解析确认「大师」≠「星雲大師」（RoleTitle 与 Person 分离），呼应 Stage289。

### 已知问题

- 本机网络不可达（PyPI 与三家 API 均 ConnectionReset / ConnectionError），在线能力探测未能锁定 Groq/NVAPI 模型 ID；待网络恢复后运行 `python scripts/probe_models.py`。
- `neo4j-graphrag` 与 `hatchling` 因网络未安装，`pip install -e .` 暂不可用；当前以 `PYTHONPATH=src` 运行，依赖已单独装齐（langchain、langchain-deepseek、langchain-groq、langchain-nvidia-ai-endpoints、neo4j）。
- Groq 探测中 `llama-3.1-8b-instant` 返回 AuthenticationError，需在联网后确认是否因该模型已下线或首把 key 失效。

### 下一步

1. 网络恢复后跑探测、锁定模型 ID，验证真实 LLM 的三条闭环路线。
2. 建立全文切片与向量索引（`data/derived/`），替换第一版逐篇扫描。
3. 实现多轮会话状态与「大师/他」指代解析。
4. 以规范化 CSV 重新生成 Neo4j 导入脚本并接通只读在线查询。
5. 补 `08_evaluation_plan.md` 固定测试集与指标。

## 2026-09-13 第二阶段：Qwen 接入 + 可靠性 + 向量语义检索 + 竞赛说明书

### 已完成

- 接入阿里百炼（`ali` / DashScope）作为默认 Provider：`ModelFactory`/`probe` 通过
  `langchain_openai.ChatOpenAI` 走 OpenAI 兼容端点
  `https://dashscope.aliyuncs.com/compatible-mode/v1`；三个角色默认 `qwen-plus`。
  `deepseek/groq/nvapi/zhipu` 保留可回退。
- 在线探测：`qwen-plus` / `qwen-flash` / `qwen-turbo` 均通过 chat / JSON 意图 / 工具调用，
  佛教内容不被内容过滤（替换掉了智谱的 1301 隐患）。
- 可靠层：`models/retry.py`（限流/5xx/网络/内容过滤短退避重试）、`models/cache.py`
  （路由/审校两确定性角色的 JSONL 磁盘缓存，键=sha256，写 `runtime/cache/`）。
- 向量语义检索：`repositories/embeddings.py`（DashScope 原生嵌入端点 `text-embedding-v3`，
  1024 维；`LocalBgeEmbeddings` 离线兜底）、`repositories/vector_store.py`（numpy mmap
  余弦 top-k）、`scripts/build_vector_index.py`（20,020 篇文章级向量 + 归一化 + 构建报告）。
- `CorpusRepository.search_semantic`（语义召回 + 篇内关键词精排，失败回退关键词）；
  `corpus_retrieve`/`graph_retrieve` 优先语义、无缝回退。
- 竞赛建设说明书草稿 `docs/10_competition_description.md`（作品简介 + 实施成效，对齐附件3）。
- 多轮指代解析（roadmap 第十节）：`resolve_conversation_context`/`resolve_entities` 用回指
  （它/他/该/此…）把上一轮实体带入；`run_agent_verbose` + `history_entry` 支撑 REPL 历史；
  CLI `ask --export` 导出 Markdown 证据包（`agent/pipeline.export_evidence_package`）。
- 向量构建健壮性：`models/retry.py` 瞬时错误识别扩展到 SSL/EOF/ConnectionReset 等；
  `embeddings._call` 走重试；`build_vector_index.py` 用内存映射增量写入 + 进度文件断点续跑。

### 验证结果

- `pytest -q` 42 passed（新增可靠性/向量/多轮/导出离线测试）。
- OpenAI 兼容端点的 `/embeddings` 与 openai 3.x 客户端不兼容（DashScope 原生校验拒绝），
  已改为 DashScope **原生** 嵌入 REST 端点，复用同一 `ali` 密钥；首轮构建途中遇 SSL 瞬时错误，
  重试 + 断点续跑后继续推进；最终 20,020 × 1024 向量全部建成并通过 `--validate-only` 冷读校验。
- 语义检索实测命中精准：「星云大师谈共生」→ 同體共生/共生共榮；「慈悲是什么」→ 慈悲专文。
- 端到端在线（qwen-plus）：`星云大师在哪些文章中谈到共生？` 正确路由 `corpus_retrieve`，
  语义召回 8 条 C 层证据，答案与覆盖说明一致。

### 已知问题

- 答案生成曾把 [C] 全文线索自行改判为 [A]/[B]，与覆盖说明冲突；已在 `ANSWER_SYSTEM`/`VERIFY_SYSTEM`
  中加入「层级标签照抄、不得升降级」的硬约束，复测已改正。
- `qwen-plus` 在证据块较大时（高连接度实体如「星雲大師」）端到端耗时偏高（>3 分钟可能超时），
  属已知延迟问题；可考虑证据截断、换更快的 qwen-flash 作路由、或对生成结果做流式。

### 已知问题

- 构建向量索引约 20,020 篇 × 10 条/批 ≈ 2000 次请求，需时较长（后台运行）。
- `neo4j-graphrag` 未安装（`pyproject.toml` 声明了但本机未装），仍以 `PYTHONPATH=src` 运行。

### 下一步

1. 向量索引构建完成后做冷读校验 + 端到端语义检索验证。
2. 多轮会话状态与「它/大师」指代解析（roadmap 第十节）。
3. 以规范化 CSV 重新生成 Neo4j 导入脚本并接通只读在线查询。
4. 补 `08_evaluation_plan.md`；测试链接与部署（`09_deployment_runbook.md`）。

## 2026-09-14 模型路由设计：角色分级 + Provider 级回退

### 已完成

- 新增 `models/router.py`：`RoleSpec`/`ROLE_SPECS`（角色→温度/缓存/用途的单一事实来源）与
  `invoke_with_fallback`（主模型瞬时错误重试、硬错误/穷尽切兜底、结果回填缓存）。
- 重构 `models/factory.py`：抽取 Provider 中性构建器 `build_chat_model`；`chat_fallback`
  构建全局兜底；`ModelBundle` 带 `fallback` 并委托 `invoke_with_fallback` 执行。
- 角色分级（延迟优先）：router/verifier → `ali/qwen-flash`，reasoner → `ali/qwen-plus`；
  兜底 → `zhipu/glm-4-flash`。配置已同步 `.env`/`.env.example`/`settings.py`/`models.example.json`。
- 修复 `SecretLoader` 多行 JSON 数组解析（groq 的 10 key 池此前因跨行被当成单 key 且截断）。
- 更新 `docs/03_model_and_secret_policy.md`：角色表 + 路由/回退语义 + 各 Provider 实测状态。

### 验证结果

- `pytest -q` 48 passed（新增 test_router、多行密钥数组测试）。
- 回退演练通过：把主模型设为不存在的 model ID，`invoke_with_fallback` 自动切 zhipu glm-4-flash 正常出答案。
- 在线探测结论：ali（qwen-plus/flash/turbo）、zhipu（glm-4-flash/4.6/4.5/plus）可调通；
  deepseek 返回 402（余额不足）、groq 返回 401（密钥失效），当前不可用。

### 已知问题

- deepseek 余额不足、groq 密钥失效，跨 Provider 兜底目前只有 zhipu 一个可用（zhipu 对佛教内容
  有间歇性 1301 内容过滤，作兜底可接受但非理想）。
- `qwen-flash` 作路由后延迟应显著下降，但 reasoner 仍为 qwen-plus，大证据块场景仍可能偏慢。

### 下一步

1. 端到端复测：路由 qwen-flash 后的延迟下降幅度与主备切换稳定性。
2. 证据块截断（只喂 top-N 证据）进一步压低 reasoner 大证据场景延迟。
3. 补充余额/密钥后再纳入 deepseek 或 groq 作为第二兜底。

## 2026-09-14 仓库发布 + 扁平布局 + 操作指南

### 已完成

- 发布准备：私有 GitHub 仓库，`.gitignore` 排除 `.env`/正文 149MB/向量索引 79MB/运行产物；
  仅小数据入仓（图谱 CSV + documents.jsonl + 元数据 ≈29MB）；密钥零泄露（三重扫描确认）。
- 重写 README（含 Mermaid 架构图/状态流/模型路由）、新增 `docs/09_deployment_runbook.md`、
  `docs/11_operation_guide.md`。
- **包改为扁平布局**：`src/huidu_xingyun/` → `huidu_xingyun/`，`python -m huidu_xingyun.cli`
  在项目根目录直接可用，不再需要 `PYTHONPATH=src` 或 `pip install`；同步修正
  `settings.PROJECT_ROOT`（parents[3]→[2]）、`pyproject.toml`（hatch packages / pytest pythonpath）、
  `scripts/*` 的 `sys.path`。
- 修 CLI 参数位置：`--no-llm` 现可放在 `ask`/`repl` 子命令之后。
- 证据块截断：`_format_evidence(items, limit=20)`，LLM 提示只喂前 20 条（A→B→C 优先），
  完整证据仍进证据卡，缓解高连接度实体的生成延迟。

### 验证结果

- `python -m huidu_xingyun.cli ask "星云大师在哪些文章中谈到共生？"`（无任何环境变量）直接跑通。
- `python -m pytest -q` 48 passed。

## 2026-09-15 功能实测 + 展示文档 + 部署计划

### 已完成

- 示例问答实测：六条路由全部跑通（graph_retrieve/graph_direct/corpus_retrieve/graph_analytics/llm_direct/clarify_or_refuse）。
- 实测发现并修复两个问题：
  - graph_analytics 覆盖说明误报「无证据」→ 改为「冻结网络指标/结构统计」。
  - LLM 把繁体「人間佛教」简化改写导致误判歧义 → 实体解析原文提及优先 + 去重，
    并在 INTENT_SYSTEM 加「mention 逐字照抄、不繁简转换」。
- 证据块截断 `_format_evidence(limit=20)`（LLM 提示只喂前 20 条）。
- 产出证据包 3 份（`outputs/evidence_*.md`）。
- 新增 `docs/12_agent_showcase.md`（Agent 功能展示）、`docs/13_deployment_plan.md`（公开部署计划）。
- 验证：`python -m pytest -q` 48 passed；在线示例均产出结构化答案 + 证据。

### 已知问题

- 推送到 GitHub 受本机网络限制（github.com 无法连接，git push 失败），本地已 commit 待推。
- 端到端延迟 30–90s（无缓存时），属演示体验待优化项。

### 下一步

1. 网络恢复后 `git push origin main`。
2. 按 `docs/13_deployment_plan.md` 先补 FastAPI API 层，再搭最小三栏前端。

## 2026-09-15 D 层开放回答 + 防御说明

### 已完成

- 新增 D 层一般知识回答路径：开放型问题（llm_direct）或图谱/全文证据为空时，
  不再硬答「无证据」，而是调用 LLM 作一般解释，并附「防御说明」（不来自全集语料、
  未经证据核验、请读者自行查阅原文与相关文献验证）。
- 新增 `FinalResponse.defense_notice` / `AgentState.d_layer`；`D_SYSTEM` 提示词与
  `DEFENSE_NOTICE` 常量；`verify_answer` 对 D 层回答跳过逐句审校。
- CLI 与证据包导出同步展示「防御说明」。
- 测试：`python -m pytest -q` 49 passed（新增 D 层离线用例）。

## 2026-09-15 公开部署阶段 1：FastAPI API 层

### 已完成

- 抽取 `huidu_xingyun/bootstrap.py`：把 CLI 的密钥/数据/语义/模型装配收敛为 `build_context`，
  CLI 与 API 服务共用。
- 新增 `huidu_xingyun/server/`：FastAPI 应用，`AgentContext` 经 lifespan 启动期构建一次、
  单例复用（实测 ~14s 一次性构建），`POST /api/v1/ask`、`POST /api/v1/export`、
  `GET /api/v1/health`、`GET /api/v1/exports/{filename}`。
- 版本化前缀 `/api/v1` + 模块化路由，预留后续扩展入口（前端子图/馆员反馈/流式回答）。
- 安装 fastapi/uvicorn；`python -m huidu_xingyun.server` 为启动入口。
- 更新 `docs/13_deployment_plan.md`（阶段 1 标记已实现）、runbook、README。

### 验证结果

- `python -m pytest -q` 52 passed（新增 API 层测试，复用离线 ctx）。
- 真机 smoke：`TestClient` 触发 lifespan 构建上下文后 `/api/v1/health` 返回
  status=ok、llm_ready=True、corpus=20020、vector=True、模型路由配置正确。
