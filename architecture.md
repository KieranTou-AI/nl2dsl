# 系统架构

## 数据库的角色

这个项目里 Supabase 干了**两件事**：

```
┌──────────────────────────────────────────────────┐
│                    Supabase                       │
│                                                  │
│  ┌────────────────────────────┐                  │
│  │  角色 1: 项目元数据库       │                  │
│  │  - 评测集 (eval_datasets)  │                  │
│  │  - 评测结果 (eval_results) │                  │
│  │  - 会话记录 (conversations)│                  │
│  │  - 意图标签 (intent_labels)│                  │
│  │  - 表结构元数据            │                  │
│  └────────────────────────────┘                  │
│                                                  │
│  ┌────────────────────────────┐                  │
│  │  角色 2: 模拟数仓           │                  │
│  │  - 宁巢营收表               │                  │
│  │  - 门店信息表               │                  │
│  │  - ...（模拟的业务数据表）   │                  │
│  └────────────────────────────┘                  │
│                                                  │
└──────────────────────────────────────────────────┘
```

- **角色 1**：存所有"项目自己的数据"，评测、会话、标签体系
- **角色 2**：存"模拟出来的业务数据"，就是你要查的那些表——宁巢营收、门店信息等。这些表是手工构造的模拟数据（CSV/JSON → 导入 Supabase），不是真实数仓

真实生产环境里，角色 2 会被替换成公司的真实数仓（Hive/ClickHouse/Doris），但角色 1 保持不变——Supabase 始终作为项目的元数据库。

---

## 模拟数仓的数据从哪来

学习阶段自己造数据，不接真实数仓：

```
data/schema/table_metadata.json    ← 定义有哪些表、字段、中文别名、示例值
           │
           ▼
src/db/seed.py                     ← 读取 JSON → 在 Supabase 建表 + 插入模拟数据
           │
           ▼
Supabase (模拟数仓)                 ← 几张表 + 几百行假数据，足够跑通完整链路
```

`table_metadata.json` 大概长这样：

```json
{
  "tables": [
    {
      "name": "ningchao_revenue",
      "description": "宁巢公寓营收月报",
      "fields": [
        {"name": "year_month", "type": "DATE",    "aliases": ["年月", "月份"]},
        {"name": "store_name", "type": "TEXT",    "aliases": ["门店", "公寓名称"]},
        {"name": "receivable", "type": "NUMERIC", "aliases": ["应收金额", "应收"]},
        {"name": "received",   "type": "NUMERIC", "aliases": ["实收金额", "实收"]}
      ],
      "sample_rows": [
        {"year_month": "2026-01", "store_name": "宁巢·东城公寓", "receivable": 580000, "received": 552000},
        {"year_month": "2026-02", "store_name": "宁巢·东城公寓", "receivable": 610000, "received": 585000}
      ]
    }
  ]
}
```

`seed.py` 做的事很简单：遍历 tables → `CREATE TABLE IF NOT EXISTS` → `INSERT` sample_rows。几百行假数据足够验证链路。

---

## AI 怎么知道是哪张表

### 答案：查表这件事在槽位抽取阶段就完成了，不是后面才决定

关键在于 `ALIAS_MAP` 的结构不是 `别名 → 字段名`，而是 `别名 → (表名, 字段名)`：

```python
# seed.py 读 table_metadata.json 时自动生成
ALIAS_MAP = {
    "应收金额":   ("ningchao_revenue", "receivable"),
    "实收金额":   ("ningchao_revenue", "received"),
    "门店名称":   ("ningchao_revenue", "store_name"),
    "房间数量":   ("ningchao_rooms",   "room_count"),
    "出租率":     ("ningchao_rooms",   "occupancy_rate"),
}
```

### 轻量版（5-10 张表）：别名不会跨表冲突

模拟数仓表少，每个别名天然只属于一张表。"应收金额"只可能出现在营收表，不可能在房间表。所以 SlotAgent 查一次字典就同时拿到了**表名 + 字段名**，一步到位：

```
用户说"宁巢·东城公寓的应收金额"

SlotAgent:
  提取实体 → "应收金额"
  查 ALIAS_MAP["应收金额"] → ("ningchao_revenue", "receivable")
                               ↑ 表名当场就拿到了

  输出槽位:
  {
    "metric": {
      "table": "ningchao_revenue",    ← 表已经确定了
      "field": "receivable",
      "status": "确定"
    },
    "dimension": {
      "table": "ningchao_revenue",
      "field": "store_name",
      "value": "宁巢·东城公寓",
      "status": "确定"
    }
  }

CodeAgent 拿到槽位 → "table"字段已经有了 → 直接填 data_query({"table": "ningchao_revenue", ...})
```

SlotAgent 的职责不仅是"抽实体"，还包括"把每个实体落到表+字段+值"——**表是槽位的一部分，不是到了代码生成阶段才推的**。

### 进阶版（50+ 张表）：别名出现歧义，LLM 消歧

表多了之后，"金额"这个别名可能跨多张表：

```
"金额" →
  ningchao_revenue.receivable      (营收表·应收金额)
  ningchao_cost.utility_cost       (成本表·水电费金额)
  ningchao_contract.contract_amt   (合同表·合同金额)
```

这时候 `ALIAS_MAP` 从一对一变一对多，SlotAgent 拿到的是一组候选。LLM 根据上下文消歧义：

```
用户说"应收金额的近三个月趋势"
               ↑
     有"应收"限定 → LLM 排除成本和合同，选营收表
```

这就是 Schema 检索进阶方案（[schema-retrieval.md](schema-retrieval.md)）里的 LLM 精排层——它的作用不只是"找最像的字段"，更是**根据对话上下文从一组候选里挑最合理的表**。

### 完整映射链路（一张图）

```
用户输入: "宁巢·东城公寓的应收金额"
        │
        ▼
┌───────────────────────────────────────────────┐
│              SlotAgent                        │
│                                               │
│  1. 提取实体: "宁巢·东城公寓", "应收金额"      │
│                                               │
│  2. 查 ALIAS_MAP（或 进阶版的混合检索）:       │
│     "应收金额" → ("ningchao_revenue",          │
│                    "receivable")              │
│     "宁巢·东城公寓" → store_name 的候选值       │
│                                               │
│  3. 输出槽位（表名已在其中）:                   │
│  {                                            │
│    "metric":    {"table": "ningchao_revenue", │
│                  "field": "receivable",       │
│                  "status": "确定"},            │
│    "dimension": {"table": "ningchao_revenue", │
│                  "field": "store_name",       │
│                  "value": "宁巢·东城公寓",     │
│                  "status": "确定"}             │
│  }                                            │
└───────────────────────┬───────────────────────┘
                        │ 槽位（含表名）传给 CodeAgent
                        ▼
┌───────────────────────────────────────────────┐
│              CodeAgent                        │
│                                               │
│  槽位里已经有 table → 直接填:                  │
│  data_query({                                 │
│      "table": "ningchao_revenue",  ← 这里     │
│      "select": ["receivable"],                │
│      "where": [                               │
│        {"field": "year_month", "op": "=",     │
│         "value": "2026-02"},                  │
│        {"field": "store_name", "op": "=",     │
│         "value": "宁巢·东城公寓"}             │
│      ]                                        │
│  })                                           │
└───────────────────────────────────────────────┘
```

---

## AI 到底生成了什么

### 不是 SQL

AI **不直接生成 SQL 字符串**。原因：

- 直接生成 SQL 不安全（注入风险）
- SQL 做环比、占比、排序等计算很绕，不如 pandas 直观
- 你无法在 SQL 里打断点看中间结果

### 生成的是 Python 代码

AI（CodeAgent）生成一段 **Python 程序**，在这段程序里调用一个受限函数 `data_query(sql_json)` 来获取数据，然后用 **pandas** 做计算。

```
用户输入:
  "查看26年2月宁巢·东城公寓应收金额相较于1月环比增长多少"

槽位 (SlotAgent 产出):
  {
    "26年2月":        ["确定", "年月->2026-02"],
    "宁巢·东城公寓":    ["确定", "门店名称->宁巢·东城公寓"],
    "应收金额":        ["确定", "宁巢应收金额"],
    "1月":            ["确定", "年月->2026-01"]
  }

  注意："环比增长"没有出现在槽位里。它不是表字段，
  而是 IntentAgent 输出的意图标签（mom_growth）。
  CodeAgent 拿到 intent=mom_growth + 两个时间槽位 → 自己算环比。

            │
            ▼  CodeAgent
            │
            ▼

CodeAgent 生成的 Python 代码:
┌─────────────────────────────────────────────────┐
│                                                 │
│  # 查询2月数据                                  │
│  df_current = data_query({                      │
│      "table": "ningchao_revenue",               │
│      "select": ["year_month", "receivable",     │
│                 "store_name"],                  │
│      "where": [                                 │
│          {"field": "year_month", "op": "=",     │
│           "value": "2026-02"},                  │
│          {"field": "store_name", "op": "=",     │
│           "value": "宁巢·东城公寓"},             │
│      ],                                         │
│  })                                             │
│                                                 │
│  # 查询1月数据                                  │
│  df_prev = data_query({                         │
│      "table": "ningchao_revenue",               │
│      "select": ["receivable"],                  │
│      "where": [                                 │
│          {"field": "year_month", "op": "=",     │
│           "value": "2026-01"},                  │
│          {"field": "store_name", "op": "=",     │
│           "value": "宁巢·东城公寓"},             │
│      ],                                         │
│  })                                             │
│                                                 │
│  current = df_current["receivable"].iloc[0]     │
│  previous = df_prev["receivable"].iloc[0]       │
│  mom = (current - previous) / previous          │
│                                                 │
│  print(f"2月应收: {current}")                   │
│  print(f"1月应收: {previous}")                  │
│  print(f"环比增长: {mom*100:.1f}%")             │
│                                                 │
└─────────────────────────────────────────────────┘

关键点：环比是 CodeAgent 算出来的 `(current - previous) / previous`，
不是表里查出来的。IntentAgent 的 mom_growth 标签告诉 CodeAgent
"这段查询需要包含环比计算"，SlotAgent 提供两个时间点 → CodeAgent 自己写公式。
```

### 数据流向

```
CodeAgent 生成的 Python 代码
        │
        │  exec() 执行
        ▼
┌──────────────────────────────────────┐
│  data_query(sql_json)                │
│    │                                 │
│    │  build_sql(sql_json)            │
│    │  把 JSON 描述  →  参数化 SQL    │
│    │                                 │
│    │  SELECT year_month, receivable, │
│    │         store_name              │
│    │  FROM ningchao_revenue          │
│    │  WHERE year_month = ?           │
│    │    AND store_name = ?           │
│    │                                 │
│    ▼                                 │
│  pd.read_sql(query, conn)            │
│    │                                 │
│    ▼                                 │
│  返回 DataFrame 给 Python 代码       │
└──────────────────────────────────────┘
        │
        ▼
  pandas 计算 → print 输出结果
```

### 为什么不直接生成 SQL

| 生成 SQL | 生成 Python + data_query |
|---|---|
| SQL 注入风险 | `data_query` 内部参数化查询，注入不可能 |
| 复杂计算（环比/占比/排序/分组）写 SQL 很绕 | pandas 几行搞定 |
| 中间结果看不到 | DataFrame 可以 print 出来调试 |
| 数仓方言不统一（Hive/ClickHouse/MySQL SQL 不一样） | `data_query` 内部适配方言，AI 不需要知道 |

---

## 总结

| 问题 | 答案 |
|---|---|
| Supabase 是目标数据库吗？ | 是，也不是。它同时是**项目元数据库**（存评测、会话）和**模拟数仓**（存业务表），生产环境会换成真实数仓 |
| 用什么模拟数仓？ | 手写 `table_metadata.json` → `seed.py` 在 Supabase 建表插数据，几百行模拟数据 |
| AI 到底生成什么？ | **Python 代码**，调用 `data_query(sql_json)` 获取 DataFrame，再用 pandas 做计算。不直接生成 SQL |