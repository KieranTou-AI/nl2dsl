"""CodeAgent — 代码生成。

把确认好的槽位 + 表结构 → 生成 Python 代码（调用 data_query + pandas）。
"""

from __future__ import annotations

from src.llm.client import r1, v3
from src.models import CodeOutput

CODE_PROMPT = """你是一个 Python 代码生成助手。根据用户的查询意图和已确认的槽位，生成一段 Python 代码来回答问题。

## 可用函数

你只能使用以下函数和库：

- `data_query(sql_json)` — 查询数据，返回 pandas DataFrame
  ```python
  df = data_query({
      "table": "ningchao_revenue",
      "select": ["year_month", "receivable", "store_name"],
      "where": [
          {"field": "year_month", "op": "=", "value": "2026-02"},
          {"field": "store_name", "op": "=", "value": "宁巢·东城公寓"},
      ],
  })
  ```

- `pd` (pandas) — 对 DataFrame 做计算、聚合、排序

## 强制规则

1. **不允许** import 任何其他模块
2. **不允许** 使用 open()、eval()、exec()、os、subprocess
3. 环比、同比等计算用 pandas 完成，不是表里查出来的
4. 最后用 print() 输出结果

## 可用数据表

{table_schema}

## 意图标签

{intent_labels}

## 已确认的槽位

{slots}

## 用户原始问题

{user_query}

请只输出 Python 代码，不要解释（代码注释可以保留）。
"""


def generate_code(
    user_query: str,
    slots: list[dict],
    intent_labels: list[str],
    table_schema: str = "",
    use_r1: bool = False,
) -> CodeOutput:
    """调用 LLM 生成 Python 代码。

    Args:
        user_query: 用户原始问题。
        slots: 已确认的槽位列表。
        intent_labels: 意图标签列表。
        table_schema: 可用表结构 JSON。
        use_r1: 是否用 R1（强推理），默认 V3。

    Returns:
        CodeOutput(code=生成的代码, explanation=说明)。
    """
    prompt = CODE_PROMPT.format(
        user_query=user_query,
        slots=_format_slots(slots),
        intent_labels=", ".join(intent_labels),
        table_schema=table_schema or "(表结构暂未加载)",
    )

    model = r1 if use_r1 else v3

    import instructor
    client = instructor.from_openai(model)
    return client.chat.completions.create(
        model="deepseek-reasoner" if use_r1 else "deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        response_model=CodeOutput,
        temperature=0.0,
    )


def _format_slots(slots: list[dict]) -> str:
    """格式化槽位列表为可读字符串。"""
    if not slots:
        return "(无槽位)"
    lines = []
    for s in slots:
        lines.append(
            f"  - {s.get('entity', '?')}: "
            f"table={s.get('table', '?')}, "
            f"field={s.get('field', '?')}, "
            f"value={s.get('value', '?')}, "
            f"status={s.get('status', '?')}"
        )
    return "\n".join(lines)
