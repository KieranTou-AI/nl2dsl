"""SlotAgent — 槽位抽取。

从用户输入中抽取实体，映射到数据库表和字段，标记确定/模糊/未知状态。
"""

from __future__ import annotations

from src.llm.client import v3
from src.models import SlotOutput

SLOT_PROMPT = """你是一个槽位抽取助手。根据用户输入和意图标签，抽取查询所需的槽位。

## 可用数据表

{table_schema}

## 槽位类别

- **metric**: 指标（查什么数值），如"应收金额"
- **dimension**: 维度（按什么分组/筛选），如"宁巢·东城公寓"
- **time**: 时间范围，如"2026年2月"
- **filter**: 其他过滤条件，如"金额>1000"

## 状态标记

- **确定**: 槽位完全明确，可以直接查询
- **模糊**: 槽位部分明确但需要确认（如"上个月"——需要确认具体月份）
- **未知**: 槽位缺失且无法推断（如"那个门店"——不知道具体哪个）

## 规则

1. 每个实体必须映射到具体的表名和字段名
2. 时间表达要解析为具体日期（"2月"→"2026-02"）
3. 能从 ALIAS_MAP 找到的字段标记为确定
4. 模糊的槽位需要生成一句反问，帮用户澄清

## 意图标签

{intent_labels}

## 用户输入

{user_query}

## 已继承的槽位（多轮对话）

{inherited_slots}

请输出 JSON 格式的槽位列表。
"""


def extract_slots(
    user_query: str,
    intent_labels: list[str],
    table_schema: str = "",
    inherited_slots: str = "",
) -> SlotOutput:
    """调用 V3 做槽位抽取。"""
    prompt = SLOT_PROMPT.format(
        user_query=user_query,
        intent_labels=", ".join(intent_labels),
        table_schema=table_schema or "(表结构暂未加载)",
        inherited_slots=inherited_slots or "(无)",
    )

    import instructor
    client = instructor.from_openai(v3)
    return client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        response_model=SlotOutput,
        temperature=0.0,
    )
