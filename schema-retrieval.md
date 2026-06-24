# Schema 检索方案

## 当前方案（轻量版）：Prompt 内嵌表结构

### 前提

模拟数仓 **5-10 张表，总字段不超过 50 个**。在这个量级下，完全不需要 BM25 + 向量检索。

### 做法

模拟数仓的完整表结构存为一个 JSON 文件，CodeAgent 的 Prompt 里直接塞进去——LLM 自己看到所有字段和别名，做选择题。

```python
TABLE_SCHEMA = {
    "tables": [
        {
            "name": "ningchao_revenue",
            "description": "宁巢公寓应收表",
            "fields": [
                {"name": "year_month",   "type": "date",    "aliases": ["年月", "月份", "时间"]},
                {"name": "store_name",   "type": "string",  "aliases": ["门店名称", "公寓", "门店"]},
                {"name": "receivable",   "type": "float",   "aliases": ["应收金额", "应收", "应收账款"]},
                {"name": "received",     "type": "float",   "aliases": ["实收金额", "实收"]},
            ],
            "sample_values": {
                "store_name": ["宁巢·东城公寓", "宁巢·明石公寓", "宁巢·钱塘公寓"],
                "year_month": ["2025-01", "2025-02", "2026-06"],
            }
        }
    ]
}
```

Prompt 模板：

```
你是一个代码生成助手。以下是可用的数据表结构：

{json.dumps(TABLE_SCHEMA, ensure_ascii=False)}

根据用户问题中的槽位，选择合适的表和字段，生成 data_query(...) 调用。
```

### 字段映射：一个 dict 搞定

```python
ALIAS_MAP = {}
for table in TABLE_SCHEMA["tables"]:
    for field in table["fields"]:
        for alias in field["aliases"]:
            ALIAS_MAP[alias] = (table["name"], field["name"])

# "应收金额" → ("ningchao_revenue", "receivable")
# "门店"     → ("ningchao_revenue", "store_name")
```

SlotAgent 的工具函数 `get_candidate_values` 就是这个 dict 的 O(1) 查询，实体映射从"检索 + LLM 精排"变成了一次字典查找。

### 这一版不引入

- `rank-bm25`
- `sentence-transformers`
- pgvector 扩展
- Embedding 编码代码

---

## 进阶方案：BM25 + pgvector 混合检索

### 什么时候升级

模拟数仓膨胀到 **50 张表以上**，表结构塞不进 Prompt 了（token 超限），或者字段别名覆盖不全导致 LLM 频繁选错。

### 三层架构

```
用户输入: "宁巢·东城公寓的应收金额"

Layer 1 — BM25 关键词召回 (rank-bm25)
  匹配字段别名、字段值 → Top-20

Layer 2 — pgvector 语义召回 (Supabase)
  embedding <=> query_vector → 余弦相似度 Top-10

合并去重 → Top-15 → Layer 3 — LLM 精排
  "应收金额" 最可能映射为 "宁巢应收金额" → 确定
```

### 各层详解

**Layer 1 — BM25 关键词召回**

经典的倒排索引检索，按词频和逆文档频率打分。对精确字段名匹配非常有效——"应收金额"直接命中 `aliases` 里的"应收金额"。

**Layer 2 — pgvector 语义召回**

在 Supabase PostgreSQL 里启用 pgvector 扩展，字段名和别名的 embedding 存在同一张表。用户输入也编码成向量，用余弦距离找语义最近邻。

```sql
SELECT field_name, 1 - (embedding <=> query_vec) AS similarity
FROM field_metadata
ORDER BY embedding <=> query_vec
LIMIT 10;
```

**Layer 3 — LLM 精排**

Top-15 候选字段丢给 LLM："用户的'应收金额'最可能是哪个字段？"——从检索变成选择题，准确率远高于纯 RAG。

### 需要新增

| 新增 | 说明 |
|---|---|
| `rank-bm25` | Python BM25 实现 |
| `sentence-transformers` | 中文 Embedding 模型，如 BAAI/bge-small-zh |
| Supabase pgvector 扩展 | `CREATE EXTENSION vector` |
| `field_metadata` 表 | 新增 `embedding VECTOR(768)` 列 |

### 从轻量版迁移

当前 `ALIAS_MAP` 字典已经是一个微型索引。迁移时：
- ALIAS_MAP → BM25 索引（Layer 1），接口不变，内部切换存储
- 字段别名 encode 成向量存 pgvector（Layer 2），新增一个 embedding 写入脚本
- CodeAgent 的 Prompt 从"内嵌完整 Schema"变成"接收 Top-15 候选字段"

轻量版和进阶版的接口是一致的——上层代码不需要改。

---

## 为什么不是纯 RAG

业界最好的纯 RAG 方法在 Text-to-SQL 场景也只能到 81% 左右，且查不了大连表。核心问题：

1. **字段名和用户说法差异大**："应收金额" vs 表里 `nested_receivable_amount` → 纯 Embedding 召不回
2. **值映射需要精确区分**："宁巢·东城公寓" vs "宁巢·明石公寓" → 纯 BM25 也分不清
3. **大连表 token 爆炸**：几百张表几千字段全塞 prompt → 超限

所以用 BM25（精确）+ pgvector（语义）+ LLM（推理）三层互补，而不是单一的 RAG pipeline。