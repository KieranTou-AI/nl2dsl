"""Pydantic 模型 — 所有 Agent 的结构化输出定义。"""

from __future__ import annotations

from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field


# ── IntentAgent ──────────────────────────────────────────────

class IntentLabel(str, Enum):
    """意图标签枚举。"""
    DATA_QUERY = "data_query"
    MOM_GROWTH = "mom_growth"        # 环比
    YOY_GROWTH = "yoy_growth"        # 同比
    PROPORTION = "proportion"        # 占比
    RANKING = "ranking"              # 排序/排名
    KEYDRIVER = "keydriver"          # 归因分析
    CHART = "chart"                  # 作图
    CHITCHAT = "chitchat"            # 闲聊


class IntentOutput(BaseModel):
    """IntentAgent 输出。"""
    labels: list[IntentLabel] = Field(description="命中的意图标签列表")
    tools: list[str] = Field(default_factory=list, description="后续需要的工具")
    confidence: float = Field(ge=0, le=1, description="置信度 0-1")


# ── SlotAgent ────────────────────────────────────────────────

class SlotStatus(str, Enum):
    CONFIRMED = "确定"
    FUZZY = "模糊"
    UNKNOWN = "未知"


class SlotItem(BaseModel):
    """单个槽位。"""
    entity: str = Field(description="用户原文中的实体文本")
    category: str = Field(description="槽位类别: metric / dimension / time / filter")
    table: Optional[str] = Field(default=None, description="映射到的表名")
    field: Optional[str] = Field(default=None, description="映射到的字段名")
    value: Optional[str] = Field(default=None, description="字段值（维度时使用）")
    status: SlotStatus = Field(description="确定 / 模糊 / 未知")
    clarification: Optional[str] = Field(default=None, description="状态为模糊/未知时的反问内容")


class SlotOutput(BaseModel):
    """SlotAgent 输出。"""
    slots: list[SlotItem] = Field(description="抽取的槽位列表")
    needs_clarification: bool = Field(default=False, description="是否需要反问用户")


# ── CodeAgent ────────────────────────────────────────────────

class CodeOutput(BaseModel):
    """CodeAgent 输出。"""
    code: str = Field(description="生成的 Python 代码")
    explanation: str = Field(default="", description="代码逻辑说明")
