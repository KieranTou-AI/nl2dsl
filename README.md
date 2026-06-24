# NL2DSL — 自然语言查数助手

让业务人员用日常中文（"宁巢·东城公寓2月应收环比增长多少"）直接问到数据库里的答案，背后是一个多 Agent 协作的 LLM 系统，生成 Python 代码而不是 SQL 来取数计算。

## 一句话说清楚

**输入**：自然语言问题 → **输出**：数据答案（数值 + 计算结果）

## 核心架构

4 个 Agent 协作，LangGraph Supervisor 模式编排：

```
用户输入 → Supervisor（路由）
              ├── IntentAgent（意图分类）
              ├── SlotAgent  （槽位抽取）
              └── CodeAgent  （代码生成 → exec() → 返回结果）
```

| Agent | 模型 | 职责 |
|---|---|---|
| Supervisor | DeepSeek-V3 | 路由决策 |
| IntentAgent | DeepSeek-V3 | 多标签意图分类（查数/环比/占比/归因/闲聊） |
| SlotAgent | DeepSeek-V3 | 实体抽取 → 表字段映射 → 状态判定 |
| CodeAgent | DeepSeek-R1 | 槽位 + 表结构 → Python 代码生成 |

## 项目结构

```
nl2dsl/
├── environment.yml              # Conda 环境配置（Python 3.12）
├── pyproject.toml              # 项目元信息
├── .env.example                # 环境变量模板
├── .gitignore
│
├── src/
│   ├── main.py                 # FastAPI 入口（POST /ask, GET /health）
│   ├── config.py               # 配置管理（读 .env 环境变量）
│   │
│   ├── agents/                 # 多 Agent 实现
│   │   ├── supervisor.py       #   Supervisor 总管路由
│   │   ├── intent.py           #   IntentAgent 意图分类
│   │   ├── slot.py             #   SlotAgent 槽位抽取
│   │   └── coder.py            #   CodeAgent 代码生成
│   │
│   ├── graph/                  # LangGraph 工作流编排
│   │   ├── state.py            #   全局 AgentState 定义
│   │   └── workflow.py         #   Supervisor 多 Agent 工作流
│   │
│   ├── models/                 # Pydantic 结构化输出模型
│   │   └── __init__.py         #   IntentOutput, SlotOutput, CodeOutput
│   │
│   ├── llm/                    # LLM 客户端
│   │   ├── client.py           #   DeepSeek API（OpenAI 兼容接口）
│   │   └── prompts/            #   Prompt 模板目录
│   │
│   ├── db/                     # 数据库
│   │   ├── client.py           #   Supabase 客户端
│   │   └── seed.py             #   模拟数据初始化（读 JSON → 建表 + 插入）
│   │
│   ├── sandbox/                # 代码执行沙箱
│   │   ├── dsl.py              #   data_query() 安全查询函数
│   │   └── executor.py         #   受限 exec() 执行器
│   │
│   ├── session/                # 会话管理（预留）
│   └── eval/                   # 评测模块（预留）
│
├── data/
│   ├── schema/
│   │   └── table_metadata.json # 模拟表结构定义（3 张表 + 别名 + 样例数据）
│   └── eval/                   # 评测集目录
│
├── frontend/
│   └── app.py                  # Streamlit 前端原型
│
├── tests/                      # 测试目录
│
└── docs/                       # 设计文档
    ├── PROJECT_OVERVIEW.md      #   项目全景
    ├── TECH_STACK.md            #   技术栈总览
    ├── architecture.md          #   系统架构
    ├── agents.md                #   多 Agent 设计
    ├── schema-retrieval.md      #   Schema 检索方案
    ├── code-execution.md        #   代码执行方案
    └── evaluation.md            #   评测体系 & 成本分析
```

## 快速开始

```bash
# 1. 创建 Conda 环境
conda env create -f environment.yml
conda activate nl2dsl

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY, SUPABASE_URL, SUPABASE_KEY

# 3. 导入模拟数据
python -m src.db.seed

# 4. 启动后端
uvicorn src.main:app --reload

# 5. 启动前端（新终端）
streamlit run frontend/app.py
```

## 技术栈

| 组件 | 选型 |
|---|---|
| 工作流编排 | LangGraph（Supervisor 多 Agent） |
| LLM | DeepSeek API（V3 + R1） |
| 结构化输出 | Instructor + Pydantic v2 |
| 数据库 | Supabase（PostgreSQL） |
| 后端 | FastAPI + Uvicorn |
| 前端 | Streamlit |
| 可观测性 | LangFuse |
| 环境管理 | Conda |

## 关键设计决策

1. **生成 Python 而不是 SQL** — 安全（参数化查询）、灵活（复杂计算用 pandas）
2. **受限 exec() 沙箱** — 白名单表名 + 参数化 SQL + 干净 `__builtins__`
3. **槽位抽取时确定表名** — `ALIAS_MAP` 是 `别名 → (表名, 字段名)`，不是后面才猜
4. **分 Agent 独立评测** — 改了谁的 Prompt 就看谁的分，问题定位精确到一个节点
