"""代码执行器 — 受限 exec() 沙箱。

两层防护：
  1. Prompt 约束 — CodeAgent 只能使用 data_query + pandas
  2. 受限 __builtins__ — 没有 open/eval/exec/__import__
"""

from __future__ import annotations

import sqlite3
from io import StringIO
from typing import Any

import pandas as pd

from src.sandbox.dsl import data_query


# 安全的内建函数白名单
SAFE_BUILTINS: dict[str, Any] = {
    "print": print,
    "len": len,
    "range": range,
    "str": str,
    "int": int,
    "float": float,
    "list": list,
    "dict": dict,
    "sum": sum,
    "sorted": sorted,
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
    "enumerate": enumerate,
    "zip": zip,
    "isinstance": isinstance,
    "bool": bool,
    "tuple": tuple,
    "set": set,
    "type": type,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
}


def execute_code(code: str, conn: sqlite3.Connection) -> dict:
    """在受限环境中执行 LLM 生成的代码。

    Args:
        code: CodeAgent 生成的 Python 代码字符串。
        conn: 数据库连接，传给 data_query。

    Returns:
        {"output": str, "error": str | None}
    """
    # 捕获 print 输出
    stdout = StringIO()

    safe_globals: dict[str, Any] = {
        "data_query": lambda sql_json: data_query(sql_json, conn),
        "pd": pd,
        "__builtins__": SAFE_BUILTINS,
    }

    try:
        exec(code, safe_globals, {})
        output = stdout.getvalue() or "(no output)"
        return {"output": output, "error": None}
    except Exception as e:
        return {"output": stdout.getvalue(), "error": f"{type(e).__name__}: {e}"}


def execute_code_with_capture(code: str, conn: sqlite3.Connection) -> dict:
    """执行代码并捕获 print 输出到 stdout。"""
    import sys

    stdout = StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout

    try:
        result = execute_code(code, conn)
        captured = stdout.getvalue()
        if captured:
            result["output"] = captured
        return result
    finally:
        sys.stdout = old_stdout
