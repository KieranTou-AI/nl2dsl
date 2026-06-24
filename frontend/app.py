"""NL2DSL Streamlit 前端原型。

启动:
    streamlit run frontend/app.py
"""

from __future__ import annotations

import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.set_page_config(page_title="NL2DSL 查数助手", page_icon="📊")
st.title("📊 NL2DSL 自然语言查数助手")

st.markdown("""
用日常中文提问，我来帮你查数据。

**试试看:**
- "宁巢·东城公寓2月应收金额是多少"
- "各门店出租率排名"
- "明石公寓2月比1月环比增长多少"
""")

# ── 输入框 ──
question = st.text_input(
    "输入你的问题",
    placeholder="例如：宁巢·东城公寓2月应收环比增长多少",
)

if st.button("查询", type="primary") and question:
    with st.spinner("分析中..."):
        try:
            resp = requests.post(
                f"{API_URL}/ask",
                json={"question": question},
                timeout=30,
            )
            data = resp.json()
        except requests.ConnectionError:
            st.error(f"无法连接到后端 ({API_URL})，请先启动 FastAPI 服务")
            st.stop()
        except Exception as e:
            st.error(f"请求失败: {e}")
            st.stop()

    # ── 展示各 Agent 中间结果 ──
    if data.get("intent_labels"):
        with st.expander("🎯 意图识别 (IntentAgent)", expanded=False):
            st.json({"labels": data["intent_labels"]})

    if data.get("slots"):
        with st.expander("🔍 槽位抽取 (SlotAgent)", expanded=False):
            st.json(data["slots"])

    if data.get("code"):
        with st.expander("💻 代码生成 (CodeAgent)", expanded=False):
            st.code(data["code"], language="python")

    # ── 最终结果 ──
    if data.get("result"):
        st.success(data["result"])

    if data.get("error"):
        st.error(f"执行失败: {data['error']}")
