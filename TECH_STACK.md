# 技术栈总览

## 选型一览

| 层 | 选型 |
|---|---|
| 环境管理 | **Conda** (`environment.yml`) |
| 版本控制 | **Git + GitHub** |
| 工作流编排 | **LangGraph**（Supervisor 多 Agent 模式） |
| LLM | **DeepSeek API** |
| 结构化输出 | **Instructor** + Pydantic v2 |
| 关系数据库 | **Supabase**（PostgreSQL） |
| Schema 检索 | **Prompt 内嵌表结构**（详见 [schema-retrieval.md](schema-retrieval.md)） |
| 会话存储 | Supabase PostgreSQL（JSONB） |
| 代码执行 | **受限 `exec()`**（详见 [code-execution.md](code-execution.md)） |
| 网络框架 | **FastAPI + Uvicorn**（前后端分离，SSE 流式输出） |
| 前端原型 | **Streamlit** |
| 可观测性 | **LangFuse**（Tracing + Prompt 版本管理 + 实验对比） |
| API 测试 | **Postman**（开发期独立调 API 验证 Agent 效果） |
| 评测框架 | 分节点 PRF1 + 4 桶评测集，详见 [evaluation.md](evaluation.md) |

---

## 环境管理 — Conda

- 隔离干净，`environment.yml` 一个文件复现整个环境，包括 Python 版本本身
- Conda 能同时管理 Python + 非 Python 依赖，学习阶段环境问题最少

### environment.yml

```yaml
name: nl2dsl
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.12
  - pip
  - pip:
      - langgraph>=0.2
      - langgraph-supervisor
      - langfuse         # 可观测性：Tracing + Prompt 管理
      - fastapi
      - uvicorn[standard]
      - supabase
      - instructor
      - openai          # DeepSeek API 兼容 OpenAI 接口
      - pydantic>=2
      - pandas
      - streamlit
      - pytest
      - pytest-asyncio
      - python-dotenv
```

### 常用命令

```bash
conda env create -f environment.yml   # 创建环境
conda activate nl2dsl                 # 激活
conda env update -f environment.yml --prune  # 更新
```

---

## 版本控制 — Git + GitHub

学习过程全记录，commit history 就是学习日记。分支策略：

```
main          ← 稳定可跑的版本
├── feat/setup      ← 搭环境
├── feat/agents     ← 实现各个 Agent
├── feat/eval       ← 评测体系
└── feat/frontend   ← Streamlit 前端
```

---

## LLM — DeepSeek API

全部走 DeepSeek，OpenAI 兼容接口，Instructor `from_openai` 模式 patch。

| Agent | 模型 | 理由 |
|---|---|---|
| Supervisor | DeepSeek-V3 | 路由决策，不需要强推理 |
| IntentAgent | DeepSeek-V3 | 分类任务 |
| SlotAgent | DeepSeek-V3 | 指令遵循 + 结构化输出 |
| CodeAgent | DeepSeek-**R1** | 代码生成需要强推理 |

学习期 CodeAgent 也可先用 V3 省钱，评测时切 R1。

---

## 关系数据库 — Supabase（PostgreSQL）

| 数据 | 存储表 |
|---|---|
| 表元数据 | `table_metadata` |
| 评测集 | `eval_datasets` |
| 评测结果 | `eval_results` |
| 会话记录 | `conversations`（JSONB 存 state） |
| 意图标签体系 | `intent_labels` |

会话存储不用 Redis——Supabase PostgreSQL JSONB 足够。代码用接口抽象（`SessionStore` 基类），将来切 Redis 只改一行。

---

## 结构化输出 — Instructor + Pydantic v2

每个 Agent 的输出都有明确的 Pydantic 模型约束，Instructor 自动处理 retry + validation。

| Agent | 输出模型 |
|---|---|
| IntentAgent | `IntentOutput(labels, tools, confidence)` |
| SlotAgent | `SlotOutput(slots: list[SlotItem])` |
| CodeAgent | `CodeOutput(code, explanation)` |

---

## 前端原型 — Streamlit

| 页面 | 功能 |
|---|---|
| 问答页 | 输入自然语言 → 看各 Agent 中间结果 → 最终代码 |
| 评测页 | 选择评测桶 → 跑评测 → 看指标趋势 |

---

## 网络框架 — FastAPI + Uvicorn

### 为什么需要

Streamlit 是界面，LangGraph 是引擎——中间需要一层"桥梁"把两者连起来。FastAPI 就是这个桥梁。

```
用户浏览器
    │
    ▼
┌──────────────┐
│  Streamlit   │  展示界面（输入框、按钮、结果渲染）
│  前端页面     │
└──────┬───────┘
       │  HTTP POST /ask
       │  {"question": "2月应收环比多少"}
       ▼
┌──────────────┐
│  FastAPI     │  网络框架（就是这一层）
│  API 服务     │  接收请求 → 调 LangGraph → 返回结果
└──────┬───────┘
       │  app.invoke(state)
       ▼
┌──────────────┐
│  LangGraph   │  Supervisor → IntentAgent → SlotAgent → CodeAgent
│  工作流引擎   │
└──────────────┘
```

### 三个核心价值

| 价值 | 说明 |
|---|---|
| **前后端分离** | Streamlit 只做界面，FastAPI 负责所有业务逻辑。以后想把 Streamlit 换成网页或飞书机器人，API 不用改 |
| **独立测试** | 不开前端，用 curl 或 Postman 直接调 API → 快速验证 Agent 效果，不用每次点浏览器 |
| **SSE 流式输出** | LLM 生成代码是逐字出的，FastAPI 原生支持 StreamingResponse，前端能实时看到 CodeAgent 正在写的代码 |

### 关键依赖

`fastapi` 和 `uvicorn[standard]` 已在 [environment.yml](#environmentyml) 中声明。Uvicorn 是 ASGI 服务器，负责跑 FastAPI 应用。

### 启动命令

```bash
uvicorn src.main:app --reload   # 开发模式，代码改动自动重载
```

---

## 评测框架

评测集分 4 桶（single_intent / compound_intent / multi_turn / boundary），JSONL 本地备份 + Supabase 集中存储。指标包括：

| 指标 | 评估对象 |
|---|---|
| 主意图正确率 | IntentAgent |
| 意图 PRF1（每个 label） | IntentAgent |
| 实体识别 PRF1 | SlotAgent |
| 字段映射准确率 | SlotAgent + CodeAgent |
| 状态判定准确率 | SlotAgent |
| 完整槽位 Exact Match | 全链路 |

---

## 可观测性 — LangFuse

开源 LLM 可观测性平台。**学习期用 Cloud（cloud.langfuse.com）**，注册即用，免费层每月 5 万条 trace。生产环境数据敏感可切 Docker 自部署。

### 两种部署方式

| | LangFuse Cloud | Docker 自部署 |
|---|---|---|
| **安装** | 注册即用，零安装 | 需要 Docker，`docker compose up` |
| **数据** | LangFuse 服务器（德国，GDPR 合规） | 完全本地 |
| **免费额度** | 每月 5 万条 trace | 无限制（取决于硬盘） |
| **维护** | 零维护 | 管理容器、升级版本、磁盘空间 |
| **适用** | 学习项目、小团队 | 生产环境、敏感数据 |

### 两个核心能力

| 场景 | 功能 |
|---|---|
| Badcase 定位到哪个 Agent | **Tracing** — 每条请求自动录下 Supervisor → Intent → Slot → Code 的输入输出，浏览器里沿节点看 |
| 改 Prompt 后效果对比 | **Prompt Management** — Prompt 版本化（v1/v2/v3）+ Experiments 跑分对比 |

LangGraph 原生支持，两行代码接入：

```python
from langfuse.callback import CallbackHandler

# LangFuse Cloud
handler = CallbackHandler(
    public_key="pk-lf-...",
    secret_key="sk-lf-...",
    host="https://cloud.langfuse.com"
)

# Docker 自部署
# handler = CallbackHandler(host="http://localhost:3000")

app.invoke(input, config={"callbacks": [handler]})
```

PM 不需要部署，研发接入后给一个浏览器地址，打开就能看全链路 Trace 和评测趋势。

---

## API 测试 — Postman

### 为什么需要

开发期不想每次测 Agent 都开 Streamlit 页面——太慢了。用 API 测试工具直接发 HTTP 请求验证。

### 两种方式

| 工具 | 适用场景 | 费用 |
|---|---|---|
| **Postman** | 图形界面，保存请求、建集合、团队分享 | 免费版够用 |
| **curl** | 终端一行命令搞定，不需要装任何东西 | 系统自带 |

### 开发期怎么用

```bash
# 不开前端，直接在终端测 API
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "2月应收环比多少"}'

# 返回:
# {
#   "intent": {"labels": ["data_query", "mom_growth"]},
#   "slots": [{"metric": "应收金额", "status": "确定", ...}],
#   "code": "df = data_query({...})",
#   "result": "2月应收: 610000, 环比增长: 5.2%"
# }
```

### PM 视角

不需要装 Postman——让研发给你一个 curl 命令模板，改 `question` 字段就能自己测。每个 Agent 的中间结果（intent、slots、code）都在返回的 JSON 里，能直观看到每一步对不对。

Postman 不是项目依赖（独立桌面应用或网页版），不写入 `environment.yml`。

---

## 项目目录结构

```
nl2dsl/
├── environment.yml
├── pyproject.toml
├── .gitignore
├── .env.example
├── README.md
├── docs/                        # 技术文档
│   ├── TECH_STACK.md            # 本文件
│   ├── architecture.md          # 系统架构
│   ├── agents.md                # 多 Agent 设计
│   ├── schema-retrieval.md      # Schema 检索方案
│   ├── code-execution.md        # 代码执行方案
│   └── evaluation.md            # 评测体系 & 成本分析
├── src/
│   ├── main.py
│   ├── config.py
│   ├── agents/
│   │   ├── supervisor.py
│   │   ├── intent.py
│   │   ├── slot.py
│   │   └── coder.py
│   ├── graph/
│   │   ├── state.py
│   │   └── workflow.py
│   ├── llm/
│   │   ├── client.py
│   │   └── prompts/
│   ├── models/
│   ├── db/
│   │   ├── client.py
│   │   ├── migrations/
│   │   └── seed.py
│   ├── sandbox/
│   │   ├── executor.py
│   │   └── dsl.py
│   ├── session/
│   └── eval/
├── data/
│   ├── eval/
│   └── schema/
├── frontend/
│   └── app.py
└── tests/
```

---

## 首次搭建步骤

```bash
# 1. Conda 环境
conda env create -f environment.yml
conda activate nl2dsl

# 2. Git 初始化
git init && git add . && git commit -m "init"

# 3. Supabase 创建项目 → 获取 URL + anon_key

# 4. 配置
cp .env.example .env   # 填 LLM_API_KEY + SUPABASE_URL + SUPABASE_KEY

# 5. 导入模拟数据
python src/db/seed.py

# 6. 启动
uvicorn src.main:app --reload
streamlit run frontend/app.py
```