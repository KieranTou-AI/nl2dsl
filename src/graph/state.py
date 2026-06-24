"""LangGraph 全局 State 定义。"""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Supervisor 多 Agent 协作的全局状态。

    所有 Agent 共享这个 State，各自读写自己负责的字段。
    """

    # ── 用户输入 ──
    user_query: str                               # 当前轮用户输入
    messages: Annotated[list, add_messages]       # 对话历史（LangGraph 消息格式）

    # ── IntentAgent 产出 ──
    intent_labels: list[str]                      # 命中的意图标签
    intent_confidence: float                      # 意图置信度
    active_tools: list[str]                       # 后续需要的工具列表

    # ── SlotAgent 产出 ──
    slots: list[dict]                             # 当前轮抽取的槽位
    needs_clarification: bool                     # 是否需要反问
    clarification_question: str                   # 反问内容（如有）

    # ── CodeAgent 产出 ──
    generated_code: str                           # 生成的 Python 代码
    code_explanation: str                         # 代码说明

    # ── 执行结果 ──
    execution_result: str                         # exec() 执行输出
    execution_error: Optional[str]                # 执行错误（如有）

    # ── 路由控制 ──
    next_agent: str                               # Supervisor 路由目标
    final_answer: str                             # 最终返回给用户的文本
