"""Agent Core 3.0 — stateful, bounded tool execution, separate from legacy 2.0."""
from __future__ import annotations

import hashlib
import pandas as pd
import streamlit as st

from agent_engine import (AgentEngineError, TaskJournal, make_task,
                          openai_adviser, run_until_gate)
from agent_modules import build_registry
from ui_layout import apply_page_layout, render_page_header

st.set_page_config(page_title="Agent Core 3.0 · AI Agent Hub", page_icon="🧠", layout="wide")
apply_page_layout()
render_page_header(
    title="🧠 Agent Core 3.0",
    category="ADAPTIVE WORKFLOWS",
    description="根據工具的實際結果逐步選擇下一個工具，顯示紀錄與失敗重試；公開網頁存取先由你核准。",
)
st.info("首版支援上傳 CSV 與最多三個公開靜態網址。可自動串接 web.crawl、text.inspect、csv.inspect、csv.plan。"
        "目前尚無全網搜尋、影片處理、持續背景任務或任意 Python 執行；訓練仍須使用原有 Agent Core／AutoML 頁面核准。")

registry = build_registry()
upload = st.file_uploader("CSV 檔案（可選）", type=["csv", "tsv", "txt"], key="v3_upload")
payload = upload.getvalue() if upload else None
filename = upload.name if upload else "uploaded.csv"
request_text = st.text_area("描述工作目標（可包含網址）", height=100,
                            placeholder="幫我分析 https://example.org/table.csv 的資料類型並規劃模型")
urls_text = st.text_area("其他公開網址（選填，一行一個；包含 CSV 最多三個來源）",
                         height=85, placeholder="https://example.org/news\nhttps://example.org/data.csv")
target = st.text_input("想預測的目標欄位（選填、完整欄名）",
                       help="如不存在於實際 CSV，Agent 不會猜測或訓練。")
with st.expander("可選：AI 逐步選擇工具"):
    use_llm = st.checkbox("讓 OpenAI 決定允許的下一個步驟", value=False, key="v3_use_llm")
    api_key = st.text_input("OpenAI API Key", type="password", key="v3_api_key") if use_llm else ""
    st.caption("沒有 API Key 時使用可驗證規則。使用模型時僅傳遞各工具的欄位、筆數與執行狀態摘要，"
               "不傳 CSV 原始列資料；API 用量另外計費。")

combined = request_text.strip() + "\n" + urls_text.strip()
signature = hashlib.sha256(repr((
    combined, target, filename, hashlib.sha256(payload or b"").hexdigest(), use_llm
)).encode("utf-8")).hexdigest()
if st.session_state.get("v3_signature") != signature:
    st.session_state["v3_signature"] = signature
    st.session_state.pop("v3_task", None)
    st.session_state.pop("v3_approved", None)

if st.button("1 · 建立與預覽任務", type="primary"):
    try:
        task = make_task(combined, upload=payload, filename=filename, target=target)
        st.session_state["v3_task"] = task
        st.session_state["v3_approved"] = set()
    except AgentEngineError as exc:
        st.error(str(exc))

task = st.session_state.get("v3_task")
if task is not None:
    st.subheader("任務執行")
    st.write("目前狀態：", task.status, "｜已執行步驟：", task.steps)
    st.caption("工作代碼：" + task.id)
    st.dataframe(pd.DataFrame([
        {"順序": i + 1, "來源": item["kind"],
         "站點": item["url"].split("/")[2] if item["kind"] == "web" else item["filename"]}
        for i, item in enumerate(task.sources)
    ]), hide_index=True, width="stretch")
    required_urls = {s["url"] for s in task.sources if s["kind"] == "web"}
    authorized = st.session_state.get("v3_approved", set())
    if required_urls and not required_urls.issubset(authorized):
        st.warning("下一步可能實際連線到以上公開網址。授權僅限本任務中明列的網址；不授權未知網址。")
        if st.button("2 · 核准讀取列出的公開網址", type="primary"):
            st.session_state["v3_approved"] = required_urls
            st.rerun()

    if task.status not in ("completed", "failed"):
        run_label = "3 · 開始／繼續執行工具" if task.status != "retryable" else "3 · 重試失敗步驟"
        if st.button(run_label, type="primary"):
            try:
                adviser = openai_adviser(api_key) if use_llm else None
                with st.spinner("依實際結果選擇並執行已註冊工具…"):
                    result = run_until_gate(task, registry,
                                            approved_urls=st.session_state.get("v3_approved", set()),
                                            adviser=adviser)
                if result == "needs_approval":
                    st.warning("尚未核准此網址的讀取。")
                elif result == "retryable":
                    st.warning("單一步驟失敗；你可以重試一次。")
                elif result == "failed":
                    st.error("連續失敗已達上限，工作停止。")
                elif task.status == "completed":
                    st.success("任務分析完成。")
            except (AgentEngineError, PermissionError, ValueError, RuntimeError) as exc:
                st.error(f"未執行新工具：{exc}")

    if task.events:
        st.subheader("逐步執行紀錄")
        st.dataframe(pd.DataFrame(task.events), hide_index=True, width="stretch")
    for n, outcome in enumerate(task.results, 1):
        with st.expander(f"來源 {n}：{outcome['kind']} ｜ 執行 {', '.join(outcome['steps'])}", expanded=True):
            if outcome.get("overview"):
                x = outcome["overview"]
                st.write(f"**{x['rows']:,} 筆資料；{len(x['columns'])} 個欄位**")
                st.dataframe(pd.DataFrame(x["profile"]), hide_index=True, width="stretch")
                if outcome.get("plan"):
                    st.write("建議訓練計畫（尚未訓練）")
                    st.json(outcome["plan"].get("suggested_options", {}))
                    for note in outcome["plan"].get("notes", []):
                        st.caption(note)
            if outcome.get("text_info"):
                info = outcome["text_info"]
                st.metric("字數", info["characters"])
                st.text(info["preview"])
                st.caption("僅擷取文字與概況；尚未做內容查核。")
    if task.status == "completed":
        st.success("全部來源已處理。若要模型訓練，請在原有 CSV／AutoML 工作台確認目標、排除欄與核准。")
