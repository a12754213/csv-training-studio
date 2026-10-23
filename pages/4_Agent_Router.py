"""Unified tool router: chooses CSV workflow or text workflow after fetching a URL."""
from __future__ import annotations

import io
import pandas as pd
import streamlit as st
from agent_hub import AgentContext
from agent_modules import build_registry
from agent_router import run_web_workflow
from ui_layout import apply_page_layout, render_page_header, ROUTER_HEADING

st.set_page_config(page_title="Agent 工具自動分流 · AI Agent Hub", page_icon="🧭", layout="wide")
apply_page_layout()
render_page_header(
    title=ROUTER_HEADING,
    category="TOOL ROUTER",
    description="從公開網址取得內容後，自動選擇文字分析或 CSV 資料分析工具；模型訓練仍須另外批准。",
)
st.info("目前的路由是可解釋的規則型 Agent，不需要 API Key；尚不是自由網路搜尋或 LLM 自主瀏覽。抓取與訓練分開確認。")

registry = build_registry()
url = st.text_input("請提供想分析的公開網址", placeholder="https://example.com/data.csv")
target_hint = st.text_input("想預測的欄位（選填，請輸入完整欄名）", help="留空只會分析；Agent 不會猜測你要預測什麼。")
# A changed source invalidates the old result, preventing stale/misattributed data.
if st.session_state.get("web_agent_requested_url") != url.strip():
    st.session_state.pop("web_agent_result", None)
    st.session_state.pop("web_agent_training", None)
if st.button("確認抓取並讓 Agent 自動分流", type="primary"):
    try:
        with st.spinner("抓取單頁資料，辨識是否適合交給 CSV 訓練或文字分析…"):
            result = run_web_workflow(registry, url, target=target_hint.strip())
        st.session_state["web_agent_result"] = result
        st.session_state["web_agent_requested_url"] = url.strip()
        st.session_state.pop("web_agent_training", None)
        st.success("Agent 已選擇合適的分析模組。")
    except (ValueError, OSError) as exc:
        st.session_state.pop("web_agent_result", None)
        st.session_state.pop("web_agent_training", None)
        st.error(str(exc))

state = st.session_state.get("web_agent_result")
if state:
    data = state["fetched"]
    st.subheader("Agent 的執行順序")
    st.write(" → ".join(state["steps"]))
    st.write(state["reason"])
    st.caption(f"資料來源：{data['url']}")
    if state["route"] == "text_analysis":
        info = state["text_info"]
        st.metric("擷取文字字數", info["characters"])
        st.text(info["preview"])
        st.info(info["note"])
    else:
        overview = state["overview"]
        st.write(f"偵測到 {overview['rows']} 筆、{len(overview['columns'])} 欄；選用 CSV 分析工具。")
        st.dataframe(pd.read_csv(io.BytesIO(data["csv_bytes"])).head(30), hide_index=True, width="stretch")
        st.download_button("下載爬蟲產生的 CSV", data["csv_bytes"], file_name="web_extract.csv",
                           mime="text/csv")
        selected = st.selectbox("確認預測目標欄位（不預測可不選）",
                                ["（只檢視資料）"] + overview["columns"],
                                index=(overview["columns"].index(target_hint.strip()) + 1
                                       if target_hint.strip() in overview["columns"] else 0))
        if selected != "（只檢視資料）":
            context = AgentContext(payload=data["csv_bytes"], filename="web_extract.csv")
            try:
                plan = registry.run("csv.plan", context, {"target": selected})
                state["plan"] = plan
                st.subheader("自動訓練建議（尚未執行）")
                for note in plan["notes"]:
                    st.caption("• " + note)
                if plan.get("suggested_options"):
                    options = dict(plan["suggested_options"])
                    st.json(options)
                    st.warning("請確認標籤、欄位資訊洩漏及訓練用途；按下方按鈕才會開始訓練。")
                    if st.button("核准並啟動 CSV 訓練", type="primary"):
                        with st.spinner("使用原有 CSV Training 引擎訓練中…"):
                            trained = registry.run("csv.train", context, options, approved=True)
                        st.session_state["web_agent_training"] = {
                            "source": data["url"], "target": selected, "options": options, "result": trained
                        }
                        st.success("訓練完成。")
            except (ValueError, RuntimeError, TypeError) as exc:
                st.error(f"訓練計畫或執行失敗：{exc}")

        trained = st.session_state.get("web_agent_training")
        if trained and trained["source"] == data["url"] and trained["target"] == selected:
            st.subheader("訓練結果")
            st.json(trained["result"]["summary"]["metrics"])
            st.download_button("下載模型與評估 ZIP", data=trained["result"]["bundle"],
                               file_name="training_data.zip", mime="application/zip")
        st.caption("這個流程不會自動搜尋整個網路，也不會把文章任意轉成分類訓練資料。")
