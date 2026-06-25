"""NL2DSL 配置管理 — 从环境变量加载所有配置项。"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """集中管理所有配置，从 .env 文件和环境变量加载。"""

    # DeepSeek API
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")

    # 模型选择
    V3_MODEL: str = "deepseek-chat"       # DeepSeek-V3（OpenAI 兼容名）
    R1_MODEL: str = "deepseek-reasoner"    # DeepSeek-R1

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")             # anon key（普通查询）
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")  # service_role（建表等管理操作）

    # LangFuse
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")


config = Config()
