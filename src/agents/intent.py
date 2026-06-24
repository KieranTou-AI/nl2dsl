"""IntentAgent — 意图识别。

多标签分类：用户想查数？看环比？做归因？还是纯闲聊？
"""

from __future__ import annotations

from src.llm.client import v3
from src.models import IntentOutput

INTENT_PROMPT = """你是一个意图分类助手。根据用户输入，判断用户的意图类别。

## 可选意图标签

| 标签 | 说明 | 示例 |
|------|------|------|
| data_query | 简单查数 | "昨天营收多少" |
| mom_growth | 环比增长 | "2月比1月增长多少" |
| yoy_growth | 同比增长 | "今年比去年同期" |
| proportion | 占比 | "各门店营收占比" |
| ranking | 排序/排名 | "营收最高的门店" |
| keydriver | 归因分析 | "为什么营收下降了" |
| chart | 作图 | "画个趋势图" |
| chitchat | 闲聊 | "你好"、"今天天气" |

## 规则

1. 可以同时命中多个标签（多标签分类）
2. 如果用户只是闲聊（问候、感谢、无关问题），只标 chitchat
3. "环比"相关提问同时标 data_query + mom_growth
4. 置信度反映你对分类的把握

## 用户输入

{user_query}

## 对话历史（最近3轮）

{history}

请输出 JSON 格式的意图分类结果。
"""


def classify_intent(user_query: str, history: str = "") -> IntentOutput:
    """调用 V3 做意图分类。"""
    prompt = INTENT_PROMPT.format(user_query=user_query, history=history or "(无历史)")

    response = v3.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    # 用 Instructor 做结构化提取
    import instructor
    client = instructor.from_openai(v3)
    return client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        response_model=IntentOutput,
        temperature=0.0,
    )
