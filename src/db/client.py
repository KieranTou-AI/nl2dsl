"""Supabase 客户端。"""

from supabase import create_client, Client

from src.config import config


def get_supabase() -> Client:
    """获取 Supabase 客户端实例。"""
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL 和 SUPABASE_KEY 未配置，请检查 .env 文件")
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


# 模块级客户端（惰性初始化）
_client: Client | None = None


def get_client() -> Client:
    """获取全局单例 Supabase 客户端。"""
    global _client
    if _client is None:
        _client = get_supabase()
    return _client
