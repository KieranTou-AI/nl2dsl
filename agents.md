# 多 Agent 设计

## 为什么拆 Agent

单 Agent 把所有事塞进一个巨型 Prompt，意图识别、槽位抽取、反问、Schema 链接、代码生成全耦合在一起——评测拆不开、模型没法按需分配、一个环节改 Prompt 影响全局。拆成多 Agent 后，每个 Agent 只做一件事，独立 Prompt、独立工具、独立评测。

以学习为目的，拆 **4 个 Agent** 刚好体验协作，又不至于过度工程化。

## Agent 拆解

```
用户: "查看26年2月宁巢·东城公寓应收金额相较于1月环比增长多少"
                         │
                         ▼
              ┌─────────────────────┐
              │   SupervisorAgent   │  "当前该走哪个 Agent？"
              │   模型: DeepSeek-V3 │  读 State，做路由决策
              └──────────┬──────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
┌─────────────────┐ ┌───────────────┐ ┌─────────────────┐
│  IntentAgent    │ │  SlotAgent    │ │   CodeAgent     │
│  识别意图       │ │  抽取槽位     │ │  链接 + 生成    │
│  模型: V3       │ │  模型: V3     │ │  模型: R1       │
├─────────────────┤ ├───────────────┤ ├─────────────────┤
│ 输入:           │ │ 输入:         │ │ 输入:           │
│  user_query     │ │  user_query   │ │  confirmed_slots│
│  history(最近3轮)│ │  intent_label │ │  表结构(Prompt)  │
│                 │ │  inherited_   │ │                 │
│ 输出:           │ │  slots(多轮)  │ │ 输出:           │
│  intent_labels  │ │               │ │  generated_code │
│  active_tools   │ │ 输出:         │ │  query_plan     │
│                 │ │  slots[]      │ │                 │
│ 工具:           │ │  needs_       │ │ 工具: 无        │
│  get_intent_    │ │  clarification│ │ (表结构已在      │
│  labels         │ │               │ │  Prompt 里)     │
│                 │ │ 工具:          │ │                 │
│                 │ │  get_candidate │ │                 │
│                 │ │  _values       │ │                 │
└─────────────────┘ └───────────────┘ └─────────────────┘
```

## 各 Agent 职责

| Agent | 一句话 | 独占工具 |
|---|---|---|
| **SupervisorAgent** | 总管，读 State 决定下一步找谁，处理闲聊直返 | 无（纯路由推理） |
| **IntentAgent** | 多标签分类（查数/环比/占比/归因/闲聊），支持多轮承接 | `get_intent_labels` |
| **SlotAgent** | 抽实体 → 打状态（确定/模糊/未知）→ 模糊了反问 → 澄清后更新 | `get_candidate_values`（查 ALIAS_MAP 字典） |
| **CodeAgent** | 把确认的槽位 + 表结构 Prompt → 生成 Python + DSL 代码 | 无（表结构已在 Prompt 里） |

## 协作流程（按意图分支）

```
Supervisor → IntentAgent（分类）
     │
     ├── chitchat → Supervisor 直接回复
     │
     └── data_query / mom_growth / ... → SlotAgent（抽槽位）
           │
           ├── needs_clarification=true → 反问用户 → 等回复 → SlotAgent 再跑一次
           │
           └── 全部确定 → CodeAgent（生成代码）
```

### 关键细节

- **闲聊直返**：Supervisor 看到 chitchat 直接回，后面的 Agent 完全不跑，省一次 LLM 调用
- **反问是 human-in-the-loop**：LangGraph `interrupt()` 暂停，用户回复后 resume，SlotAgent 只更新对应槽位，不会重新跑意图识别
- **多轮槽位继承**：LangGraph checkpointer 恢复上一轮 slots，当前轮明确提到的覆盖，未提及的保留
- **每条意图独立路由**：data_query 走 SlotAgent，keydriver 也可以走 SlotAgent（归因分析的入参也是槽位），chart 同理

## 为什么拆 4 个而不是 5 个

学术上可以把 Schema 链接单独拆成 LinkerAgent。但：
- Schema 链接本质是"检索 + 映射"，和代码生成输入强耦合
- 多维护一个 Agent 的 Prompt 和评测
- 4 个已经能体验 Supervisor 路由 + 3 个 Worker 的完整协作

后续要拆，LangGraph 里加一个节点即可，不改架构。

## 模型分配

| Agent | 模型 | 理由 |
|---|---|---|
| Supervisor | DeepSeek-V3 | 路由逻辑简单 |
| IntentAgent | DeepSeek-V3 | 分类任务 |
| SlotAgent | DeepSeek-V3 | 指令遵循 + 结构化输出 |
| CodeAgent | DeepSeek-**R1** | 代码生成需要强推理 |

省钱模式：开发调试时 CodeAgent 也用 V3，评测跑分时切 R1。

## LangGraph Supervisor 模式要点

用 `langgraph-supervisor` 库，每个 Agent 是独立的 ReAct Agent（有自己的 tools + prompt），Supervisor 在它们之间路由。

```python
from langgraph_supervisor import create_supervisor
from langgraph.prebuilt import create_react_agent

intent_agent = create_react_agent(
    model=v3, tools=[get_intent_labels], prompt=INTENT_PROMPT
)
slot_agent = create_react_agent(
    model=v3, tools=[get_candidate_values], prompt=SLOT_PROMPT
)
code_agent = create_react_agent(
    model=r1, tools=[], prompt=CODE_PROMPT
)

supervisor = create_supervisor(
    agents=[intent_agent, slot_agent, code_agent],
    model=v3,
    prompt=SUPERVISOR_PROMPT,
)
```

## 为什么不选其他多 Agent 框架

| 框架 | 不选原因 |
|---|---|
| **CrewAI** | 太高层抽象，黑盒太多，学习价值低 |
| **AutoGen** | 微软生态，文档偏向 Azure |
| **LangGraph** | 可控、透明，能深入到每个 Agent 的 state 和 prompt，学习价值最高 |