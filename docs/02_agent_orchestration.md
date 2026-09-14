# Agent编排蓝图

## 技术选择

第一版采用显式状态图，而不是让单个ReAct Agent自由决定全部流程：

- LangChain负责模型适配、结构化输出、工具接口和消息对象；
- LangGraph负责意图分类后的条件路由、并行检索、重试和答案审校；
- Neo4j工具只开放参数化只读查询；
- LLM负责分类、证据内归纳和语言表达，不负责生成数据库事实。

## 状态图

```text
START
  -> normalize_input
  -> resolve_conversation_context
  -> classify_intent
  -> resolve_entities
  -> plan_route
       -> llm_direct
       -> graph_direct
       -> graph_retrieve -----+
       -> corpus_retrieve ----+-> fuse_evidence
       -> graph_analytics ----+
       -> clarify_or_refuse
  -> generate_answer
  -> verify_answer
       -> revise_once -> verify_answer
  -> format_response
  -> write_audit_log
  -> END
```

图谱和全文检索在混合问题中并行执行，证据融合完成后才调用领域推理模型。审校失败最多自动修订一次。

## 第一版路由

| 路由 | 适用意图 | 工具 | LLM角色 |
|---|---|---|---|
| `LLM_DIRECT` | 系统帮助、一般表达、问题改写 | 无领域工具 | 直接回答，不声称来自全集 |
| `KG_DIRECT` | 直接关系、邻居、固定统计 | Neo4j与证据工具 | 只做自然语言整理 |
| `KG_LLM_HYBRID` | 为什么、如何、关系路径、比较 | 图谱＋Claim＋证据＋全文 | 在证据包内综合解释 |
| `CORPUS_RAG` | 原文、出处、图谱未覆盖问题 | 全文/向量混合检索 | 摘要与引用组织 |
| `GRAPH_ANALYTICS` | 中心性、社团、专题指标 | 冻结指标或白名单计算 | 解释结构意义，不推断历史因果 |
| `RESEARCH_WORKFLOW` | 阅读路线、专题证据包 | 多工具组合 | 规划和生成可导出结果 |
| `CLARIFY_OR_REFUSE` | 实体歧义、证据不足、越界请求 | 消歧或安全节点 | 追问或说明边界 |

## 核心状态

正式实现时，`AgentState`至少包含：

- `messages`；
- `normalized_query`；
- `intent`；
- `resolved_entities`；
- `execution_plan`；
- `graph_results`；
- `claim_results`；
- `corpus_results`；
- `evidence_items`；
- `draft_answer`；
- `verification_result`；
- `final_response`；
- `errors`和`trace_id`。

## 工具分组

### 实体工具

- `resolve_entities`
- `disambiguate_entity`
- `expand_aliases`

### 图谱工具

- `search_relations`
- `find_graph_paths`
- `get_entity_neighborhood`
- `get_graph_metrics`

### 证据与全文工具

- `get_relation_evidence`
- `search_corpus`
- `get_article_metadata`
- `get_source_passage`

### 治理工具

- `verify_answer_claims`
- `submit_relation_feedback`
- `export_evidence_package`

路由后只向模型暴露当前流程需要的少量工具，避免一次注册过多工具导致误选。

## 输出合同

最终响应不是一个纯字符串，而是结构化对象：

- `answer`：直接结论；
- `evidence_cards`：篇名、卷册、原文片段和URL；
- `graph_paths`：稳定关系路径；
- `contextual_claims`：Claim语境解释；
- `coverage_notice`：覆盖与不确定性说明；
- `follow_up_actions`：展开子图、查看原文、导出或反馈。

前端据此分别渲染文字、关系图和证据卡。
