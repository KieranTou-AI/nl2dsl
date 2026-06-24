"""数据初始化 — 读取 table_metadata.json → 建表 + 插模拟数据。

用法:
    python -m src.db.seed
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.db.client import get_client

# 项目根目录
ROOT = Path(__file__).parent.parent.parent

# 表结构定义路径
SCHEMA_PATH = ROOT / "data" / "schema" / "table_metadata.json"


def load_table_metadata() -> dict:
    """加载表结构 JSON。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_alias_map(metadata: dict) -> dict[str, tuple[str, str]]:
    """从表结构构建别名映射。

    Returns:
        {"应收金额": ("ningchao_revenue", "receivable"), ...}
    """
    alias_map: dict[str, tuple[str, str]] = {}
    for table in metadata["tables"]:
        for field in table["fields"]:
            for alias in field.get("aliases", []):
                alias_map[alias] = (table["name"], field["name"])
    return alias_map


def seed_tables(metadata: dict) -> None:
    """在 Supabase 中建表并插入模拟数据。"""
    client = get_client()

    for table in metadata["tables"]:
        table_name = table["name"]
        print(f"[seed] 处理表: {table_name}")

        # 根据字段定义建表（简化版：用 TEXT 类型，生产环境按 type 映射）
        columns: list[str] = []
        for field in table["fields"]:
            col_type = _map_type(field.get("type", "TEXT"))
            columns.append(f"{field['name']} {col_type}")

        create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)});"
        print(f"[seed]   {create_sql}")

        # Supabase REST API 不支持直接跑 SQL，需要用 supabase.sql()
        # 或者通过 Supabase Dashboard 的 SQL Editor 手动执行
        # 这里用 Python SQLite 做本地模拟，生产环境改为 Supabase SQL
        try:
            client.rpc("exec_sql", {"query": create_sql}).execute()
        except Exception:
            print(f"[seed]   (跳过建表 — 请在 Supabase SQL Editor 中手动执行 DDL)")

        # 插入 sample_rows
        for row in table.get("sample_rows", []):
            try:
                client.table(table_name).insert(row).execute()
                print(f"[seed]   INSERT: {row}")
            except Exception as e:
                print(f"[seed]   插入失败: {e}")


def _map_type(field_type: str) -> str:
    """字段类型映射：JSON schema type → PostgreSQL type。"""
    mapping = {
        "DATE": "DATE",
        "TEXT": "TEXT",
        "NUMERIC": "NUMERIC",
        "INTEGER": "INTEGER",
        "FLOAT": "FLOAT",
        "BOOLEAN": "BOOLEAN",
    }
    return mapping.get(field_type.upper(), "TEXT")


def main():
    """主入口。"""
    metadata = load_table_metadata()
    alias_map = build_alias_map(metadata)

    print(f"[seed] 加载 {len(metadata['tables'])} 张表")
    print(f"[seed] 别名映射: {len(alias_map)} 条")
    print()

    seed_tables(metadata)
    print()
    print("[seed] 完成！")


if __name__ == "__main__":
    main()
