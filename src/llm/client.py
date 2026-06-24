"""LLM 客户端 — DeepSeek API（OpenAI 兼容接口）。"""

from openai import OpenAI

from src.config import config


def create_v3_client() -> OpenAI:
    """创建 DeepSeek-V3 客户端。路由、分类、槽位抽取用。"""
    return OpenAI(
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
    )


def create_r1_client() -> OpenAI:
    """创建 DeepSeek-R1 客户端。代码生成需要强推理时用。"""
    return OpenAI(
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
    )


# 模块级默认客户端
v3 = create_v3_client()
r1 = create_r1_client()
