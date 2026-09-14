# 便携数据包

本目录由 `scripts/build_portable_data.py` 从只读源数据生成，供 LangChain、Neo4j 导入器、全文检索器和竞赛演示统一读取。

```text
package/
├─ metadata/   数据集说明、构建报告和旧编号映射
├─ corpus/     文章清单、书目表和精简正文
├─ graph/      实体、关系、证据和语境命题
├─ analytics/  图指标、实体指标和专题视图指标
└─ quality/    精度、忠实率、召回与指代敏感性指标
```

运行表使用短文件名和稳定字段。旧阶段编号只保存在 `metadata/id_map_*.csv` 中，不允许进入 Agent 的业务状态或回答结构。

文章正文统一命名为 `doc_########.txt`，文件中只保留正文；标题、分类、书目、原始网页和层级路径由 `corpus/documents.jsonl` 管理。合并卷册不重复复制，避免数据包体积翻倍。

构建与验证：

```powershell
python scripts/build_portable_data.py
python scripts/build_portable_data.py --validate-only
```

字段、类型、主键和外键定义见 `config/data_schema.json`。
