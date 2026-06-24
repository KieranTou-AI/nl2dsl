"""NL2DSL FastAPI 入口。

启动:
    uvicorn src.main:app --reload

API:
    POST /ask  — 自然语言查数
    GET  /health — 健康检查
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.graph.workflow import build_workflow

app = FastAPI(
    title="NL2DSL",
    description="自然语言查数助手 — 多 Agent 协作的 NL2DSL 系统",
    version="0.1.0",
)

# 全局 workflow 实例
workflow = build_workflow()


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    intent_labels: list[str] | None = None
    slots: list[dict] | None = None
    code: str | None = None
    result: str | None = None
    error: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest) -> AskResponse:
    """接收自然语言问题，返回查询结果。"""
    config = {"configurable": {"thread_id": "default"}}

    state = {
        "user_query": req.question,
        "messages": [],
    }

    try:
        result = workflow.invoke(state, config)
        return AskResponse(
            intent_labels=result.get("intent_labels"),
            slots=result.get("slots"),
            code=result.get("generated_code"),
            result=result.get("final_answer"),
            error=result.get("execution_error"),
        )
    except Exception as e:
        return AskResponse(error=str(e))
