"""SupervisorAgent — 总管路由。

读 State，决定下一步找哪个 Agent：IntentAgent? SlotAgent? CodeAgent? 还是直接回复？
"""

from __future__ import annotations

SUPERVISOR_PROMPT = """你是一个多 Agent 系统的总管。根据当前对话状态，决定下一步应该调用哪个 Agent。

## 可调用的 Agent

| Agent | 职责 | 何时调用 |
|-------|------|----------|
| IntentAgent | 意图分类 | 用户刚刚发来新消息，还没有分类意图 |
| SlotAgent | 槽位抽取 | 意图已分类（非闲聊），但槽位未全部确定 |
| CodeAgent | 代码生成 | 所有槽位已确定，可以生成查询代码 |
| FINISH | 结束 | 代码已执行完毕，可以返回结果给用户 |

## 路由规则

1. 如果用户是闲聊（chitchat），直接 FINISH，不需要跑后续 Agent
2. 如果槽位有模糊/未知 → 反问用户（FINISH），等人回复后再跑 SlotAgent
3. 如果所有槽位确定但还没有代码 → CodeAgent
4. 如果代码已生成但尚未执行 → 执行后 FINISH

## 当前状态

- 用户输入: {user_query}
- 意图标签: {intent_labels}
- 槽位状态: {slots_summary}
- 是否已生成代码: {has_code}

请只输出下一个 Agent 的名字（IntentAgent / SlotAgent / CodeAgent / FINISH）。
"""


def decide_next(
    user_query: str,
    intent_labels: list[str] | None = None,
    slots: list[dict] | None = None,
    has_code: bool = False,
) -> str:
    """简单的规则路由，不调 LLM，省 token。

    复杂的歧义情况可以升级为 LLM 路由。
    """
    # 还没分类意图 → IntentAgent
    if not intent_labels:
        return "IntentAgent"

    # 闲聊 → 直接结束
    if "chitchat" in intent_labels and len(intent_labels) == 1:
        return "FINISH"

    # 有槽位但未全部确定 → 检查是否需要反问
    if slots:
        all_confirmed = all(
            s.get("status") == "确定" for s in slots
        )
        if not all_confirmed:
            return "FINISH"  # 反问用户，暂停等待回复

    # 槽位全确定但没代码 → CodeAgent
    if slots and all(s.get("status") == "确定" for s in slots) and not has_code:
        return "CodeAgent"

    # 代码已生成 → 执行后结束
    if has_code:
        return "FINISH"

    # 默认：先跑意图
    return "IntentAgent"
