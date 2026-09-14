# 便携数据包规范

## 目标

`data/package/`是项目打包、离线演示和部署时唯一需要携带的业务数据。它从研究源数据复制生成，不改动原文件，也不把实验阶段名称暴露给Agent运行层。

## 目录

```text
data/package/
├─ metadata/   数据集说明、构建报告、源编号映射
├─ corpus/     documents.jsonl、books.csv、articles/
├─ graph/      entities、aliases、relations、evidence、claims
├─ analytics/  graph_metrics、entity_metrics、view_metrics
└─ quality/    quality_metrics.json
```

## 编号

- 文章：`doc_########`，数字取自原网页文章号；
- 书目：`book_###`；
- 实体、关系和证据：语义前缀加原编号的12位SHA-256摘要；
- 段落：`par_文章号_段号`；
- 句子：`sent_文章号_段号_句号`。

摘要ID由源编号确定，新旧机器重复构建结果一致。源编号到运行编号的对应关系只存放在 `metadata/id_map_*.csv`。

## 字段

1. 字段统一使用英文 `lower_snake_case`。
2. 主键统一以 `_id` 结尾；多值字段使用分号分隔，JSONL数组除外。
3. 计数统一以 `_count` 结尾，比例和网络指标使用数值类型。
4. 布尔值在CSV中只使用小写 `true` 与 `false`。
5. 缺失值使用空字段，不使用 `-`、`?`、`N/A` 或临时实验符号。
6. 运行表不保留 `stage`、旧边编号、旧证据编号和构建过程字段。

机器可读的完整字段合同见 `config/data_schema.json`。

## 正文清洗

- 删除每篇文件开头重复的标题、URL、分类、书目和路径五个元数据字段；
- 元数据集中写入 `corpus/documents.jsonl`；
- 统一UTF-8和LF换行；
- 去除行尾空白，连续空行压缩为一个；
- 文件名只保留稳定文章编号。

不做繁简转换、标点改写、内容纠错或段落重排，避免损伤引文真实性。

## 构建纪律

`scripts/build_portable_data.py`是唯一构建入口。每次构建完成后必须通过主键、外键、行数、文件数、编号格式和正文头部检查。Agent只读运行表，新增切片和索引写入 `data/derived/` 或 `runtime/`。
