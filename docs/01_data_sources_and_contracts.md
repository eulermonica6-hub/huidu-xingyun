# 数据源与契约

## 只读构建源

所有路径相对于本项目根目录解析，机器配置见 `config/data_paths.json`。这些文件只由数据包构建脚本读取，不由Agent业务节点直接读取。

| 数据层 | 权威路径 | 用途 | 写入权限 |
|---|---|---|---|
| 文章清单 | `../../数据/hsingyun_texts/manifest.jsonl` | 全文检索的唯一文章入口 | 只读 |
| 文章正文 | `../../数据/hsingyun_texts/texts/` | 切片、向量化和证据展示 | 只读 |
| 合并卷册 | `../../数据/hsingyun_texts/books/` | 卷册级阅读和人工核验 | 只读 |
| 实体注册表 | Stage265 `stage265_entity_registry.csv` | 实体ID、类型和活动状态 | 只读 |
| 别名注册表 | Stage265 `stage265_entity_alias_registry.csv` | 实体链接和消歧 | 只读 |
| 关系本体 | Stage265 `stage265_relation_registry.csv` | 关系方向与类型契约 | 只读 |
| 稳定关系 | Stage265 `stage265_stable_relations.csv` | 图谱查询和专题结构 | 只读 |
| 稳定证据 | Stage265 `stage265_stable_relation_evidence.csv` | 原文回链 | 只读 |
| Claim层 | Stage265 Claim三表 | 语境解释与条件命题 | 只读 |
| Neo4j | Stage266 | 在线图查询 | 只读账号 |
| 评价数据 | Stage278、279、289 | 质量说明和系统边界 | 只读 |

## 已完成的数据核验

- `manifest.jsonl`：20,020行。
- 唯一 `article_id`：20,020个，无重复。
- 文章文本：20,020个，无缺失。
- 合并卷册：105个。
- 分类：13类。
- 书目ID：105个。

清单中的 `text_file` 以 `../../数据` 为路径基准，而不是以 `manifest.jsonl` 所在目录为基准。加载器必须把Windows反斜杠转换为当前系统可识别的路径分隔符。

## Agent运行入口

Agent、检索器、Neo4j导入器和评价脚本统一读取 `data/package/`：

- `corpus/documents.jsonl`：文章元数据唯一入口；
- `corpus/articles/doc_########.txt`：无冗余头部的正文；
- `graph/*.csv`：规范化实体、关系、证据和Claim数据；
- `analytics/*.csv`：网络与专题指标；
- `quality/quality_metrics.json`：对外指标及限制；
- `metadata/id_map_*.csv`：旧编号追溯，业务代码不得依赖。

字段、类型、主键和外键以 `config/data_schema.json` 为唯一合同。

## 图谱层使用合同

### 稳定关系层

- 可用于直接关系查询、路径搜索和专题分析。
- 只有 `centrality_eligible=true` 的关系可以进入中心性与网络计算。
- 每条对外展示的关系必须关联至少一条证据记录。

### Claim层

- 用于解释、条件、张力、修正、推理和语境变化。
- 不参与稳定实体中心性、PageRank或社团计算。
- 回答中必须使用“在该语境中”“原文将其解释为”等限定表达。

### 全文语料层

- 用于弥补图谱低召回、查询原文和发现新线索。
- 全文命中不等于图谱稳定关系。
- 未经馆员或研究者复核，不得自动写回正式图谱。

## 派生数据

所有后续计算数据写入：

- `data/derived/document_chunks/`：文章与段落切片；
- `data/derived/vector_metadata/`：向量索引元数据；
- `data/derived/demo_subgraph/`：公开演示子图；
- `data/derived/evaluation_sets/`：Agent固定测试集；
- `runtime/indexes/`：本地索引；
- `runtime/cache/`：可删除缓存；
- `runtime/logs/`：脱敏运行日志。

任何脚本不得原地改写 `../../数据`、Stage265或Stage266输入。`data/package/`只能由 `scripts/build_portable_data.py` 整体重建。

## 竞赛口径

项目对外不得继续使用旧材料中的候选关系总量作为正式图谱关系数。当前业务基线使用Stage265发布统计，质量与覆盖边界使用Stage278和Stage279结果。若后续发布新图谱版本，必须新增版本目录并更新本配置，不得静默替换。
