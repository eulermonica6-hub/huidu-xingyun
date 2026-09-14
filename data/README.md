# 数据目录

这里不直接修改原始语料或图谱发布文件；源数据一律只读。

## 入仓与不入仓

| 路径 | 是否入仓 | 说明 |
|---|---|---|
| `package/corpus/documents.jsonl`、`books.csv` | ✅ 入仓 | 20,020 篇文章清单（标题/分类/书目/URL/字数） |
| `package/graph/*.csv` | ✅ 入仓 | 实体/别名/关系类型/稳定关系/证据/Claim（规范化运行表） |
| `package/analytics/*.csv` | ✅ 入仓 | 图/实体/专题指标 |
| `package/quality/quality_metrics.json` | ✅ 入仓 | 冻结质量指标 |
| `package/metadata/` | ✅ 入仓 | 构建报告与源编号→运行编号映射（支撑可回溯） |
| `package/corpus/articles/` | ❌ 不入仓 | 20,020 篇正文（约 149MB），另附压缩包/链接 |
| `derived/vector_metadata/`、`derived/model_probe_report.json` | ❌ 不入仓 | 向量索引（约 79MB）与探测报告，可重建 |

## 重建

```powershell
# 便携数据包（需本机存在冻结构建源 ../../数据 与 ../../formal_experiment）
python scripts/build_portable_data.py

# 语义向量索引
python scripts/build_vector_index.py            # DashScope 嵌入
python scripts/build_vector_index.py --local-bge  # 离线 BGE
```

`package/` 只能由构建脚本生成，Agent 业务代码不得改写；所有生成数据必须记录生成时间、源版本、构建脚本与校验结果。

## 说明

- 正文 190MB 不全量提交：可向项目负责人索取压缩包，或本地用 `build_portable_data.py` 从冻结源重建。
- 向量索引 79MB 为派生数据，随时可重建，不入仓。
- 字段契约见 `config/data_schema.json`；编号与清洗规则见 `docs/07_portable_data_spec.md`。