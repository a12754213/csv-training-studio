"""Agent Core 2.0: conversational intent -> approved source -> auditable tools."""
from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from agent_core import (
    AgentCoreError, DEFAULT_MODEL, execute_approved_training,
    execute_read_plan, prepare_training, propose_with_openai, suggest_without_api,
)
from agent_hub import AgentContext
from agent_modules import build_registry
from ui_layout import apply_page_layout, render_page_header

st.set_page_config(page_title="Agent Core 2.0 · AI Agent Hub", page_icon="🧠", layout="wide")
apply_page_layout()
render_page_header(
    title="🧠 Agent Core 2.0",
    category="MULTI-TOOL AGENT",
    description="用中文描述工作，先確認 AI 的工具計畫，再執行爬蟲、文字或 CSV 分析；模型訓練需另行核准。",
)
st.info("目前支援公開單頁網頁／HTML 表格／CSV 上傳及分析。這是受控的多工具工作流，"
        "尚不支援搜尋全網、JavaScript 動態頁面、影片或完全自主長時間任務。")

registry = build_registry()
upload_file = st.file_uploader("上傳 CSV（選填，可不透過網頁爬蟲）", type=["csv", "tsv", "txt"], key="core_upload")
uploaded = upload_file.getvalue() if upload_file else None
filename = upload_file.name if upload_file else "upload.csv"
columns = []
if uploaded is not None:
    try:
        overview_upload = registry.run("csv.inspect", AgentContext(payload=uploaded, filename=filename))
        columns = overview_upload["columns"]
        st.caption(f"已辨識 {overview_upload['rows']:,} 筆資料、{len(columns)} 個欄位；不會把 CSV 內容傳給語言模型。")
    except (ValueError, TypeError, UnicodeError) as exc:
        st.error(f"CSV 無法讀取：{exc}")
        st.stop()

instruction = st.text_area("你希望 Agent 完成什麼？", height=98,
                           placeholder="例如：讀取 https://example.com/data.csv，整理欄位並準備訓練計畫")
url_hint = st.text_input("公開網址（選填，也可以直接放在上方指令）", placeholder="https://example.com/data.csv")
target_hint = st.selectbox("上傳檔案的預測目標（選填）", ["（只分析）"] + columns,
                           help="若讀取的是網頁表格，取得欄位後再選目標。") if columns else "（只分析）"

with st.expander("語言模型連接與資料隱私"):
    use_model = st.checkbox("使用 OpenAI 解析自然語言（需自己的 API Key）", value=False)
    key = st.text_input("OpenAI API Key", type="password") if use_model else ""
    st.caption(f"使用 {DEFAULT_MODEL} 進行意圖解析。只傳送你的指令、公開網址和有限的 CSV 欄名，"
               "不傳送 CSV 儲存格資料。API 獨立計費；不用 API 仍可透過規則分流。")

signature = hashlib.sha256(repr((
    instruction, url_hint, target_hint, hashlib.sha256(uploaded or b"").hexdigest(),
    filename, use_model,
)).encode("utf-8")).hexdigest()
if st.session_state.get("core_signature") != signature:
    for name in ("core_intent", "core_read", "core_training"):
        st.session_state.pop(name, None)
    st.session_state["core_signature"] = signature

if st.button("1 · 解析需求並預覽工具計畫", type="primary"):
    try:
        if use_model:
            intent = propose_with_openai(instruction, key, has_upload=uploaded is not None,
                                         upload_columns=columns, url_hint=url_hint)
        else:
            intent = suggest_without_api(instruction, has_upload=uploaded is not None,
                                         upload_columns=columns, url_hint=url_hint,
                                         target_hint="" if target_hint == "（只分析）" else target_hint)
        st.session_state["core_intent"] = intent
        st.session_state.pop("core_read", None)
        st.session_state.pop("core_training", None)
    except AgentCoreError as exc:
        st.error(str(exc))

intent = st.session_state.get("core_intent")
if intent:
    st.subheader("工作計畫（尚未存取網路、尚未訓練）")
    st.write(intent["message"])
    st.write("來源：", {"web": "公開網頁", "upload": "上傳 CSV", "none": "未指定"}[intent["source"]])
    if intent["url"]:
        st.caption("選定來源：" + intent["url"])
    if intent["tools_preview"]:
        st.write("預計工具：", " → ".join(intent["tools_preview"]))
    else:
        st.warning("請先上傳 CSV 或提供公開網址。")
    if intent["goal"] == "prepare_training" and not intent["target"]:
        st.warning("尚未指定有效的目標欄位；讀取後可以從實際欄位中選擇。")
    if intent["source"] != "none":
        st.warning("第二步會實際讀取來源；若是網址，將由伺服器連線公開網站。")
        if st.button("2 · 核准讀取來源並執行分析", type="primary"):
            try:
                with st.spinner("受控執行工具中…"):
                    read = execute_read_plan(intent, registry, upload=uploaded, filename=filename, user_approved=True)
                st.session_state["core_read"] = read
                st.session_state.pop("core_training", None)
            except (AgentCoreError, ValueError, RuntimeError, OSError, TypeError) as exc:
                st.session_state.pop("core_read", None)
                st.error(f"工具執行失敗：{exc}")

read = st.session_state.get("core_read")
if read:
    st.divider()
    st.subheader("實際工具執行紀錄")
    st.dataframe(pd.DataFrame(read["trace"]), hide_index=True, width="stretch")
    if read["fetched"]:
        st.caption("實際來源：" + read["fetched"]["url"])
    if read["kind"] == "text":
        info = read["text_info"]
        st.metric("擷取字數", info["characters"])
        st.text(info["preview"])
        st.caption(info["note"])
        st.info("這是文字概況，不是經過 LLM 的全文摘要或查證。")
    else:
        overview = read["overview"]
        st.write(f"已分析 **{overview['rows']:,} 筆資料**、**{len(overview['columns'])} 個欄位**。")
        with st.expander("資料欄位檢查", expanded=True):
            st.dataframe(pd.DataFrame(overview["profile"]), hide_index=True, width="stretch")
        if read["fetched"] and read["fetched"]["csv_bytes"]:
            st.download_button("下載擷取的表格 CSV", read["fetched"]["csv_bytes"],
                               "web_extract.csv", mime="text/csv")
        actual = overview["columns"]
        preselected = intent.get("target") if intent else None
        options = ["（只分析，不訓練）"] + actual
        selected = st.selectbox("3 · 確認預測目標", options,
                                index=options.index(preselected) if preselected in options else 0)
        if selected != options[0]:
            task = st.selectbox("任務類型", ["auto", "classification", "regression", "time_series"],
                                format_func=lambda v: {
                                    "auto": "依資料建議", "classification": "分類",
                                    "regression": "回歸", "time_series": "時間序列"}[v])
            time_column = None
            if task == "time_series":
                choices = [c for c in actual if c != selected]
                time_column = st.selectbox("時間欄位", choices) if choices else None
            try:
                if task == "time_series":
                    plan = registry.run("csv.plan", read["context"],
                                        {"target": selected, "time_column": time_column,
                                         "forecast_intent": True})
                else:
                    plan = prepare_training(registry, read, selected)
                for note in plan.get("notes", []):
                    st.caption("• " + note)
                if plan.get("suggested_options"):
                    options_train = dict(plan["suggested_options"])
                    if task in ("classification", "regression"):
                        options_train["task"] = task
                    exclusions = [c for c in actual if c not in {selected, time_column}]
                    defaults = [c for c in options_train.get("excluded_columns", []) if c in exclusions]
                    options_train["excluded_columns"] = st.multiselect(
                        "排除欄位（確認預測當下是否能取得）", exclusions, default=defaults)
                    options_train["model"] = "auto"
                    st.json(options_train)
                    st.warning("請確認目標的業務意義、時間／群組洩漏風險；只有按下按鈕才會開始訓練。")
                    if st.button("4 · 核准並開始模型訓練", type="primary"):
                        try:
                            with st.spinner("使用現有 AutoML 引擎訓練中…"):
                                trained = execute_approved_training(
                                    registry, read, options_train, user_approved=True)
                            st.session_state["core_training"] = {
                                "target": selected, "options": options_train, "result": trained}
                        except (AgentCoreError, ValueError, RuntimeError, TypeError, OverflowError) as exc:
                            st.error(f"訓練失敗：{exc}")
            except (AgentCoreError, ValueError, RuntimeError, TypeError) as exc:
                st.error(f"無法建立訓練計畫：{exc}")

        trained = st.session_state.get("core_training")
        if trained and trained["target"] == selected:
            st.subheader("模型訓練結果")
            st.json(trained["result"]["summary"]["metrics"])
            st.download_button("下載訓練成果 ZIP", trained["result"]["bundle"],
                               "training_data.zip", mime="application/zip", type="primary")
