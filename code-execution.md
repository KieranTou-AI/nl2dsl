# 代码执行方案

## 当前方案（轻量版）：受限 `exec()`

### 不搞 AST + Docker 的原因

- AST 白名单写起来极其痛苦——`import pandas` 一行代码的 AST 节点就要递归十几层
- Docker 沙箱需要管理镜像、容器生命周期、超时、内存限制——对学习项目太重
- 真正安全地执行 LLM 生成的 Python 代码，业界也没几个完美方案

### 两层防护

**第一层 — Prompt 约束**

CodeAgent 的 System Prompt 明确限定可用 API：

```
你只能使用以下函数和库：
- data_query(sql_json)  — 查询数据，返回 DataFrame
- pd (pandas)           — 对 DataFrame 做计算、聚合、排序

不允许 import 任何其他模块。
不允许使用 open()、eval()、exec()、os、subprocess。
```

**第二层 — `data_query` 函数内置校验**

LLM 生成的代码不直接写 SQL 字符串，而是调用一个受控函数：

```python
def data_query(sql_json: dict) -> "pd.DataFrame":
    """
    受限查询函数。只接受结构化的 SQL 描述。

    示例:
    {
        "table": "ningchao_revenue",
        "select": ["year_month", "receivable", "store_name"],
        "where": [
            {"field": "year_month", "op": ">=", "value": "2026-01"},
            {"field": "store_name", "op": "=", "value": "宁巢·东城公寓"}
        ],
        "order_by": [{"field": "year_month", "direction": "asc"}]
    }
    """
    ALLOWED_TABLES = {"ningchao_revenue", "ningchao_rooms"}

    if sql_json["table"] not in ALLOWED_TABLES:
        raise ValueError(f"不允许访问表: {sql_json['table']}")

    # 内部用参数化查询拼接 SQL，杜绝注入
    query = build_sql(sql_json)       # 用 ? 占位符
    params = extract_params(sql_json)
    return pd.read_sql(query, conn, params=params)
```

安全靠两点：
- 表名白名单——LLM 生成了别的表名直接报错
- 参数化查询——即使 LLM 在 value 里塞了 `' OR 1=1 --`，也只是查一个字面值

### 执行层

```python
def execute_code(code: str, conn) -> dict:
    safe_globals = {
        "data_query": lambda sql_json: data_query(sql_json, conn),
        "pd": pd,
        "__builtins__": {
            "print": print, "len": len, "range": range,
            "str": str, "int": int, "float": float,
            "list": list, "dict": dict, "sum": sum,
            "sorted": sorted, "round": round, "abs": abs,
            "min": min, "max": max, "enumerate": enumerate,
            "zip": zip, "isinstance": isinstance, "bool": bool,
        },
    }
    local_vars = {}
    exec(code, safe_globals, local_vars)
    return {"result": local_vars.get("result"), "df": local_vars.get("df")}
```

注意 `__builtins__` 里**没有** `open`、`eval`、`exec`、`__import__`——LLM 即使生成了这些调用，运行时直接 `NameError`。

### 生成示例

LLM 看到槽位 `{"time_range": "2026-02", "metric": "receivable", "dimension": "宁巢·东城公寓"}` 后，生成：

```python
# 查询2026年2月宁巢·东城公寓应收金额及环比增长
# 注：环比增长不是表字段，由 CodeAgent 根据 intent=mom_growth 自己算
df_current = data_query({
    "table": "ningchao_revenue",
    "select": ["year_month", "receivable", "store_name"],
    "where": [
        {"field": "year_month", "op": "=", "value": "2026-02"},
        {"field": "store_name", "op": "=", "value": "宁巢·东城公寓"},
    ],
})
df_prev = data_query({
    "table": "ningchao_revenue",
    "select": ["year_month", "receivable", "store_name"],
    "where": [
        {"field": "year_month", "op": "=", "value": "2026-01"},
        {"field": "store_name", "op": "=", "value": "宁巢·东城公寓"},
    ],
})

current_amount = df_current["receivable"].iloc[0]
previous_amount = df_prev["receivable"].iloc[0]
mom_growth_rate = (current_amount - previous_amount) / previous_amount

print(f"2026年2月宁巢·东城公寓应收金额: {current_amount}")
print(f"2026年1月: {previous_amount}")
print(f"环比增长率: {mom_growth_rate}")
```

一段标准的 pandas 代码，不碰任何危险操作。

---

## 进阶方案：AST 白名单 + Docker 沙箱

### 什么时候升级

系统要开放给不可信用户，或者 `exec()` 被人多次绕过。

### AST 白名单校验

在执行前用 Python 的 `ast` 模块静态扫描代码，拦截危险调用。

```python
import ast

class CodeValidator(ast.NodeVisitor):
    ALLOWED_CALLS = {"data_query", "print", "len", "round", "pd.DataFrame", ...}
    FORBIDDEN_IMPORTS = {"os", "subprocess", "sys", "shutil", "socket", ...}

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in self.FORBIDDEN_IMPORTS:
                raise SecurityError(f"禁止 import {alias.name}")

    def visit_ImportFrom(self, node):
        if node.module in self.FORBIDDEN_IMPORTS:
            raise SecurityError(f"禁止 from {node.module} import ...")

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id not in self.ALLOWED_CALLS:
                raise SecurityError(f"禁止调用 {node.func.id}()")
        self.generic_visit(node)
```

### Docker 沙箱

把 LLM 生成的代码丢进一次性 Docker 容器执行——没网、限内存、限 CPU、超时强杀。

```python
import docker

def execute_in_sandbox(code: str, timeout: int = 10) -> str:
    container = docker.from_env().containers.run(
        "python:3.12-slim",
        command=["python", "-c", code],
        network_disabled=True,   # 断网
        mem_limit="128m",        # 限内存
        cpu_quota=50000,         # 限 CPU
        detach=True,
    )
    try:
        result = container.wait(timeout=timeout)
    except Exception:
        container.kill()
        raise TimeoutError("代码执行超时")
    finally:
        logs = container.logs().decode()
        container.remove()
    return logs
```

### 从轻量版迁移

升级时两层是独立演进的：
- 先加 AST 校验——在执行 `exec()` 之前多一步 `CodeValidator().visit(ast.parse(code))`
- 再加 Docker——把 `exec()` 替换成 `execute_in_sandbox()`

接口不变，上层 CodeAgent 无感知。