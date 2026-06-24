"""LangGraph Workflow — Supervisor 多 Agent 编排。

核心流程：
  Supervisor → IntentAgent（分类意图）
       │
       ├── chitchat → 直接回复
       │
       └── data_query / ... → SlotAgent（抽槽位）
             │
             ├── 模糊/未知 → 反问用户 → 等人回复 → SlotAgent 补全
             │
             └── 全确定 → CodeAgent（生成代码）→ exec() → 返回结果
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.graph.state import AgentState
from src.agents.supervisor import decide_next
from src.agents.intent import classify_intent, INTENT_PROMPT
from src.agents.slot import extract_slots, SLOT_PROMPT
from src.agents.coder import generate_code, CODE_PROMPT


# ── 节点函数 ────────────────────────────────────────────────

def node_supervisor(state: AgentState) -> dict:
    """Supervisor 路由节点。"""
    next_agent = decide_next(
        user_query=state.get("user_query", ""),
        intent_labels=state.get("intent_labels"),
        slots=state.get("slots"),
        has_code=bool(state.get("generated_code")),
    )
    return {"next_agent": next_agent}


def node_intent(state: AgentState) -> dict:
    """意图识别节点。"""
    result = classify_intent(
        user_query=state["user_query"],
        history=str(state.get("messages", [])[-6:]),  # 最近3轮
    )
    return {
        "intent_labels": [label.value for label in result.labels],
        "intent_confidence": result.confidence,
        "active_tools": result.tools,
    }


def node_slot(state: AgentState) -> dict:
    """槽位抽取节点。"""
    result = extract_slots(
        user_query=state["user_query"],
        intent_labels=state.get("intent_labels", []),
        inherited_slots=str(state.get("slots", [])),
    )
    return {
        "slots": [s.model_dump() for s in result.slots],
        "needs_clarification": result.needs_clarification,
    }


def node_code(state: AgentState) -> dict:
    """代码生成节点。"""
    result = generate_code(
        user_query=state["user_query"],
        slots=state.get("slots", []),
        intent_labels=state.get("intent_labels", []),
        use_r1=False,  # 开发期用 V3
    )
    return {
        "generated_code": result.code,
        "code_explanation": result.explanation,
    }


def node_finish(state: AgentState) -> dict:
    """终止节点 — 构建最终回复。"""
    if "chitchat" in state.get("intent_labels", []):
        return {"final_answer": "你好！有什么数据问题可以帮你查？"}

    if state.get("execution_result"):
        return {"final_answer": state["execution_result"]}

    if state.get("generated_code"):
        return {"final_answer": f"生成的代码:\n```python\n{state['generated_code']}\n```"}

    return {"final_answer": "抱歉，无法处理你的请求。"}


# ── 路由函数 ────────────────────────────────────────────────

def route_after_supervisor(state: AgentState) -> Literal["intent", "slot", "code", "finish"]:
    """Supervisor 之后的分发。"""
    next_agent = state.get("next_agent", "IntentAgent")
    routing = {
        "IntentAgent": "intent",
        "SlotAgent": "slot",
        "CodeAgent": "code",
        "FINISH": "finish",
    }
    return routing.get(next_agent, "finish")


def route_after_intent(state: AgentState) -> Literal["supervisor", "finish"]:
    """意图分类后：如果是闲聊直接结束，否则回到 Supervisor 继续路由。"""
    labels = state.get("intent_labels", [])
    if labels == ["chitchat"]:
        return "finish"
    return "supervisor"


def route_after_slot(state: AgentState) -> Literal["supervisor", "finish"]:
    """槽位抽取后：如果需要反问则暂停，否则继续。"""
    if state.get("needs_clarification"):
        return "finish"
    return "supervisor"


def route_after_code(state: AgentState) -> Literal["supervisor"]:
    """代码生成后回到 Supervisor。"""
    return "supervisor"


# ── 构建 Workflow ───────────────────────────────────────────

def build_workflow() -> StateGraph:
    """构建并编译 LangGraph 工作流。"""
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("supervisor", node_supervisor)
    workflow.add_node("intent", node_intent)
    workflow.add_node("slot", node_slot)
    workflow.add_node("code", node_code)
    workflow.add_node("finish", node_finish)

    # 入口
    workflow.set_entry_point("supervisor")

    # Supervisor → 分发到具体 Agent
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"intent": "intent", "slot": "slot", "code": "code", "finish": "finish"},
    )

    # 各 Agent → 回 Supervisor 或结束
    workflow.add_conditional_edges(
        "intent",
        route_after_intent,
        {"supervisor": "supervisor", "finish": "finish"},
    )
    workflow.add_conditional_edges(
        "slot",
        route_after_slot,
        {"supervisor": "supervisor", "finish": "finish"},
    )
    workflow.add_edge("code", "supervisor")
    workflow.add_edge("finish", END)

    # 编译（带内存 checkpointer 支持多轮对话）
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
