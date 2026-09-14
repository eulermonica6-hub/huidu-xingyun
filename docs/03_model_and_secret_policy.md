# 模型与密钥策略

## 外部秘密源

真实密钥保留在：

`../LLM api key.txt`

该文件位于代码目录外，视为外部只读秘密源。工程不得复制、提交、打印或写入日志。

脱敏检查识别到以下具名标签：

- `deepseek`
- `groq`
- `nvapi`
- `zhipu`
- `ali`
- `agnes`

文件中另有9行没有显式标签。第一版加载器默认忽略这些行，不能依据位置猜测其所属平台。只有补充明确标签后才可启用。

> 实测状态（2026-09-14）：`ali`（qwen-plus/flash/turbo）与 `zhipu`（glm-4-flash）在线可调通；
> `deepseek` 返回 402（余额不足）、`groq` 返回 401（密钥失效），当前不可用；
> `nvapi` 模型 ID 未探测、`agnes` 缺协议，禁用。

## 模型角色

| 角色 | Provider | 模型 | 原因 |
|---|---|---|---|
| 意图路由 | ali | `qwen-flash` | JSON 意图 ~1s，延迟优先 |
| 领域推理 | ali | `qwen-plus` | 长文中文归纳，质量优先 |
| 答案审校 | ali | `qwen-flash` | 低温度逐句核验，快且确定性 |
| 故障回退 | zhipu | `glm-4-flash` | 跨 Provider 兜底，实测可调通 |
| Agnes | 禁用 | — | 缺 API 地址、模型清单和兼容协议 |

## 模型路由

1. **角色分级**：路由与审校用快模型（`qwen-flash`），推理用强模型（`qwen-plus`），
   由 `models/router.ROLE_SPECS` 声明温度与缓存策略。
2. **Provider 级回退**：主模型瞬时错误由 `retry_transient` 原地重试；
   遇到硬错误或重试穷尽，`invoke_with_fallback` 切换到 `fallback` 兜底模型；
   兜底也失败则向上抛错，编排节点降级为离线/规则，不崩溃。
3. **缓存**：路由/审校两个确定性角色（temperature 0）写磁盘缓存
   `runtime/cache/llm_cache.jsonl`，键=sha256(role+prompt)；回答模型不缓存。

DeepSeek 的推理模型与对话模型能力不同。涉及 LangChain 工具调用和结构化输出的
节点先使用 `deepseek-chat`，不把 `deepseek-reasoner` 作为路由器。

## 加载规则

1. 只解析带明确 `label=value` 或 `label:value` 的行。
2. 标签映射到标准环境变量后，只在当前进程内存中存在。
3. 日志只能记录Provider、模型ID、耗时、Token量和错误类型。
4. 异常对象、HTTP头、完整请求体和环境变量不得直接打印。
5. 前端和浏览器永远不能收到Provider API Key。
6. Neo4j密码与模型密钥使用同一脱敏等级。

## 上线前能力探测

每个候选模型必须通过：

- 基础对话；
- Pydantic结构化输出；
- 工具调用；
- 中文实体与意图分类；
- 流式输出；
- 超时和重试；
- 证据约束提示遵从；
- 费用与速率限制记录。

没有通过能力探测的模型不能进入正式路由。
