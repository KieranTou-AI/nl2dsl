"""DSL 层 — data_query 安全查询函数 + SQL 构建。

这是整个系统安全模型的核心：LLM 生成的代码不直接写 SQL 字符串，
而是调用 data_query() 传入结构化的 JSON 描述，由本模块内部完成：
  1. 表名白名单校验
  2. 参数化 SQL 拼接
  3. 查询执行
"""

from __future__ import annotations

from typing import Any
import sqlite3

import pandas as pd

# ── 表名白名单（seed.py 建表后自动同步） ──
ALLOWED_TABLES: set[str] = {
    "ningchao_revenue",
    "ningchao_rooms",
    "ningchao_stores",
}


def build_sql(sql_json: dict) -> tuple[str, list[Any]]:
    """把结构化的 SQL 描述转为参数化 SQL。

    Args:
        sql_json: {"table": "...", "select": [...], "where": [...], "order_by": [...]}

    Returns:
        (sql_string, params_list) — 参数化查询，杜绝 SQL 注入。
    """
    table = sql_json["table"]
    select_cols = ", ".join(sql_json.get("select", ["*"]))
    query = f"SELECT {select_cols} FROM {table}"
    params: list[Any] = []

    where_clauses = sql_json.get("where", [])
    if where_clauses:
        conditions: list[str] = []
        for w in where_clauses:
            conditions.append(f"{w['field']} {w['op']} ?")
            params.append(w["value"])
        query += " WHERE " + " AND ".join(conditions)

    order_by = sql_json.get("order_by", [])
    if order_by:
        orders = [f"{o['field']} {o.get('direction', 'asc')}" for o in order_by]
        query += " ORDER BY " + ", ".join(orders)

    limit = sql_json.get("limit")
    if limit:
        query += f" LIMIT {int(limit)}"

    return query, params


def data_query(sql_json: dict, conn: sqlite3.Connection) -> pd.DataFrame:
    """受限查询函数 — LLM 生成的代码只能通过它访问数据库。

    Args:
        sql_json: 结构化的查询描述，见 build_sql 文档。
        conn: 数据库连接。

    Returns:
        pandas DataFrame。

    Raises:
        ValueError: 表名不在白名单中。
    """
    table = sql_json.get("table", "")
    if table not in ALLOWED_TABLES:
        raise ValueError(
            f"不允许访问表: {table}，可用表: {ALLOWED_TABLES}"
        )

    query, params = build_sql(sql_json)
    return pd.read_sql(query, conn, params=params)
