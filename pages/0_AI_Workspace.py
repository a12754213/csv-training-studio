"""Single task surface with readable results and handoff to existing tools."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from agent_modules import build_registry
from agent_modules.market_tools import backtest_prices
from agent_supervisor import plan_task, run_task
from ui_layout import apply_page_layout, render_page_header, HOME_HEADING
from version import __version__

st.set_page_config(page_title="AI 任務 · AI Agent Hub", page_icon="🤖", layout="wide")
apply_page_layout()
render_page_header(title=HOME_HEADING, category="AI WORKSPACE",
                   description="描述目標，讓 Agent 搜尋、讀取與分析資料；查看結果與來源，再接續模型訓練。")


def configured(name):
    # Shared server keys must not become anonymously spendable by default.
    if os.environ.get("AI_AGENT_PRIVATE_DEPLOYMENT") != "1":
        return ""
    value = os.environ.get(name, "")
    if not value:
        try:
            value = st.secrets.get(name, "")
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            pass
    return str(value)


with st.sidebar:
    with st.expander("連線設定"):
        brave = st.text_input("Brave Search API Key", type="password", key="workspace_brave") or configured("BRAVE_SEARCH_API_KEY")
        openai = st.text_input("OpenAI API Key", type="password", key="workspace_openai") or configured("OPENAI_API_KEY")
        st.caption("金鑰只用於本次工作階段，不寫入報告。請在這裡輸入，勿貼在聊天或指令欄。")
    st.caption("網路搜尋：" + ("已提供金鑰（尚未驗證）" if brave else "待設定 Brave Key"))
    st.caption("AI 報告：" + ("已提供金鑰（尚未驗證）" if openai else "選用 OpenAI Key"))
    st.caption("台股日成交分析與 CSV 訓練不需 API Key。")
    st.caption(f"AI Agent Hub · 程式版本 v{__version__}")

work_mode = st.radio("工作方式", ["快速分析", "對話與多來源 Agent"], horizontal=True, key="workspace_mode")
if work_mode == "對話與多來源 Agent":
    from conversation_ui import render_conversation
    render_conversation(openai_key=openai, brave_key=brave)
    st.stop()

st.subheader("今天想完成什麼？")
examples = ["分析台積電股價未來趨勢", "搜尋近期半導體新聞並整理來源", "分析我上傳的檔案"]
for col, example in zip(st.columns(3), examples):
    if col.button(example, width="stretch"):
        st.session_state["workspace_query"] = example
query = st.text_area("任務描述", key="workspace_query", height=100,
                     placeholder="例如：分析台積電股價未來趨勢，找出近期新聞與可能影響因素")
upload = st.file_uploader("附上檔案（選填）", type=["csv", "tsv", "pdf", "png", "jpg", "jpeg", "webp",
                                                       "gif", "wav", "mp3", "mp4", "m4a", "webm", "srt", "vtt"])
payload = upload.getvalue() if upload else None
filename = upload.name if upload else ""
with st.expander("分析選項"):
    months = st.select_slider("台股歷史月份", options=[3, 6, 9, 12], value=6)
    report_on = st.checkbox("使用 OpenAI 整理公開網頁來源（需金鑰，按用量計費）", value=False)
    upload_on = st.checkbox("允許將這次上傳的圖片／音訊傳給 OpenAI 理解或轉錄", value=False)
st.caption("按下開始會查詢外部資料，並自動讀取最多三個公開搜尋結果；無法讀取時會列出缺口。模型訓練另有按鈕。")
fingerprint = hashlib.sha256(json.dumps([query, filename, hashlib.sha256(payload or b"").hexdigest(),
                                       months, report_on, upload_on]).encode()).hexdigest()
if st.session_state.get("workspace_fp") != fingerprint:
    for key in ("workspace_result", "workspace_error", "workspace_backtest", "workspace_model_zip", "workspace_horizon"):
        st.session_state.pop(key, None)
    st.session_state["workspace_fp"] = fingerprint

if st.button("開始分析", type="primary", disabled=len(query.strip()) < 2, width="stretch"):
    for key in ("workspace_result", "workspace_error", "workspace_backtest", "workspace_model_zip"):
        st.session_state.pop(key, None)
    try:
        plan = plan_task(query, filename=filename, upload_present=upload is not None)
        if report_on and not openai:
            raise ValueError("請在左側「連線設定」填入 OpenAI API Key，或關閉 AI 報告。")
        if plan.kind == "search" and not brave:
            raise ValueError("全網搜尋需要 Brave Search API Key。請在左側連線設定補上；也可貼公開網址或使用台股分析。")
        if plan.requires_external and (not openai or not upload_on):
            raise ValueError("此檔案任務需要 OpenAI 金鑰，以及分析選項中的圖片／音訊傳送授權。")
        labels = {"market.twse": "取得證交所日成交資料與計算趨勢", "web.search": "搜尋相關公開來源",
                  "web.research_selected": "讀取來源並分析表格", "web.synthesize": "整理有來源標記的研究報告"}
        with st.status("正在執行任務…", expanded=True) as status:
            result = run_task(plan, build_registry(), upload=payload, filename=filename,
                              brave_key=brave, openai_key=openai, months=months,
                              approved_read=True, approved_follow=True,
                              approved_external_upload=upload_on, approved_report=report_on,
                              progress=lambda tool: st.write(labels.get(tool, "處理檔案：" + tool)))
            result["query"] = query
            result["created_at"] = datetime.now(timezone.utc).isoformat()
            st.session_state["workspace_result"] = result
            history = st.session_state.get("workspace_history", [])
            st.session_state["workspace_history"] = ([{"任務": query[:150], "時間": result["created_at"],
                                                     "狀態": result["status"]}] + history)[:10]
            status.update(label="分析已完成" if result["status"] == "completed" else "已完成可取得的部分，請查看缺口",
                          state="complete", expanded=False)
    except (ValueError, RuntimeError, OSError, PermissionError) as exc:
        st.session_state["workspace_error"] = str(exc)

if st.session_state.get("workspace_error"):
    st.error(st.session_state["workspace_error"])
result = st.session_state.get("workspace_result")
if result:
    outer = result["result"]
    data = outer.get("data", outer)
    sources = (data.get("research") or data).get("sources", [])
    summary_tab, data_tab, source_tab, trace_tab = st.tabs(["分析結論", "資料與圖表", "來源與缺口", "執行紀錄"])
    with summary_tab:
        if result["status"] == "no_sources":
            st.warning("尚未讀到可供分析的來源。搜尋索引摘要不能代替原文；請更換關鍵字或提供可讀網址。")
        if data.get("analysis"):
            prices, analysis = data["prices"], data["analysis"]
            stats = analysis["statistics"]
            st.subheader(f"{prices['symbol']} · 台股趨勢")
            st.caption(f"資料截至 {prices['as_of']} · TWD · 證交所未還原日成交價 · 非即時報價")
            a, b, c = st.columns(3)
            a.metric("最近收盤", f"{stats['latest_close']:,.2f}", f"{stats['change_1d_pct']:+.2f}%")
            b.metric("20 筆成交價格變動", f"{stats['change_20_sessions_pct']:+.2f}%")
            c.metric("本期最大回撤", f"{stats['max_drawdown_pct']:.2f}%")
            st.write(analysis["interpretation"])
            st.caption(analysis["method"])
            st.subheader("接著驗證：模型真的比簡單基準好嗎？")
            horizon = st.selectbox("預測未來第幾筆成交資料", [1, 5, 20], index=1)
            if st.session_state.get("workspace_horizon") != horizon:
                st.session_state.pop("workspace_backtest", None)
                st.session_state.pop("workspace_model_zip", None)
                st.session_state["workspace_horizon"] = horizon
            st.caption("在前 80% 時間區間內選模型，後 20% 留作測試；此按鈕會實際訓練。")
            if st.button("訓練並回測股價模型", type="primary"):
                try:
                    with st.spinner("依時間切分、比較模型及 Naive 基準…"):
                        tested, bundle = backtest_prices(prices, horizon)
                        st.session_state["workspace_backtest"] = tested
                        st.session_state["workspace_model_zip"] = bundle
                except (ValueError, RuntimeError, OSError) as exc:
                    st.error(str(exc))
            tested = st.session_state.get("workspace_backtest")
            if tested:
                metrics, future = tested["metrics"], tested["future"]
                if not metrics["beats_naive_mae"]:
                    st.warning("模型在保留測試集沒有勝過 Naive（沿用最近價格）。目前沒有證據支持採用這個模型做投資判斷。")
                else:
                    st.info("模型在本次測試集 MAE 低於 Naive；一次回測不代表未來也有效。")
                st.dataframe(pd.DataFrame([{"模型": metrics["selected_model"], **metrics["test_scores"]},
                                           {"模型": "Naive", **metrics["naive_scores"]}]), hide_index=True)
                st.write(f"第 {horizon} 筆成交資料的模型估計：{future['prediction']:,.2f} TWD；"
                         f"Naive：{future['naive_prediction']:,.2f} TWD。")
                st.caption(tested["note"] + " 此為單點估計，尚未校準機率區間，也不是未來每日路徑。")
                predictions = pd.DataFrame(tested["predictions"])
                st.line_chart(predictions.set_index("target_time")[["actual", "prediction", "naive_prediction"]])
                st.download_button("下載模型與完整回測 ZIP", st.session_state["workspace_model_zip"],
                                   f"{prices['symbol']}_backtest.zip", "application/zip")
        if outer.get("report"):
            st.subheader("公開來源研究報告")
            st.markdown(outer["report"]["report"])
            for source in outer["report"]["sources"]:
                st.write(f"[{source['index']}] {source['url']}")
            st.caption(outer["report"]["warning"])
        elif sources:
            st.info("已整理來源摘錄與表格。若需要 AI 綜合解讀，填入 OpenAI Key 並開啟 AI 報告後重新分析。")
            for source in sources:
                if source.get("status") == "completed":
                    st.write(source.get("title") or source["url"])
                    st.text(source.get("text_preview", ""))
        if result["kind"] == "csv":
            st.write(f"已讀取 {data['rows']:,} 列、{len(data['columns'])} 欄。")
            st.write("建議排除的識別欄位：", data.get("suggested_excluded_columns", []))
            st.caption("下一步：到資料與圖表確認內容，再接續 CSV 訓練選擇目標欄位。")
        if result["kind"] not in ("market", "search", "web", "csv"):
            for field in ("description", "text", "preview", "title", "note"):
                if data.get(field):
                    st.text(str(data[field]))
            with st.expander("完整檔案分析"):
                st.json(data)
    with data_tab:
        datasets = []
        if data.get("analysis"):
            chart = pd.DataFrame(data["analysis"]["chart"])
            st.line_chart(chart.set_index("Date")[["Close", "MA5", "MA20", "MA60"]])
            frame = pd.DataFrame(data["prices"]["rows"])
            datasets.append((data["prices"]["symbol"] + ".csv", frame.to_csv(index=False).encode("utf-8-sig")))
            st.dataframe(frame, hide_index=True)
        if result["kind"] == "csv" and payload:
            datasets.append((filename, payload))
            st.dataframe(pd.DataFrame(data["profile"]), hide_index=True)
        for i, source in enumerate(sources):
            if source.get("table_csv"):
                st.write(source["url"])
                if source.get("numeric_summary"):
                    st.dataframe(pd.DataFrame(source["numeric_summary"]), hide_index=True)
                datasets.append((f"web_table_{i+1}.csv", source["table_csv"].encode("utf-8-sig")))
        for i, (name, content) in enumerate(datasets):
            left, right = st.columns(2)
            left.download_button("下載 " + name, content, name, "text/csv", key=f"dataset_download_{i}")
            if right.button("用這份資料接續 CSV 訓練", key=f"dataset_train_{i}"):
                st.session_state["workspace_dataset"] = {"name": name, "payload": content}
                st.switch_page("pages/8_CSV_Workspace.py")
        if not datasets:
            st.caption("此任務未產生可用表格；文字內容請見分析結論與來源。")
    with source_tab:
        for warning in result.get("warnings", []):
            st.warning(warning)
        for source in sources:
            st.write(source["url"])
            st.caption("已讀取原文" if source.get("status") == "completed" else "無法讀取，未納入分析")
        for source in data.get("prices", {}).get("sources", []):
            st.write(source["month"], source["url"])
        if data.get("search", {}).get("results"):
            st.caption("搜尋索引結果（不代表已閱讀全文）")
            st.dataframe(pd.DataFrame(data["search"]["results"]), hide_index=True)
        st.caption("新聞僅依讀到的片段分析；尚未包含完整財報估值或事件因果驗證。")
    with trace_tab:
        st.write("任務狀態：", result["status"])
        st.write("取得時間：", result["created_at"])
        st.write(" → ".join(result["trace"]))
        st.download_button("下載分析紀錄 JSON", json.dumps(result, ensure_ascii=False, indent=2),
                           "agent_analysis.json", "application/json")
        with st.expander("檢視原始結果"):
            st.json(result)

with st.expander("本次工作階段的任務紀錄"):
    history = st.session_state.get("workspace_history", [])
    if history:
        st.dataframe(pd.DataFrame(history), hide_index=True)
    st.caption("最多保留 10 筆任務摘要；重新整理可能清除。需要保存的結果請下載。")
with st.expander("功能與設定檢查"):
    st.markdown("- **可直接用**：CSV 訓練、公開網址爬蟲、文字 PDF、字幕檔、台股日成交趨勢。\n"
                "- **Brave Key**：自動上網搜尋；**OpenAI Key**：來源研究報告、圖片理解、音訊轉錄。\n"
                "- **本機額外設定**：動態網頁需隔離瀏覽器；YouTube 需選用套件及啟用設定。\n"
                "- **需另部署**：ChatGPT 遠端連接、持久排程／通知、跨裝置記憶。")
    st.caption("目前是可擴充的受控工具流程，不能自行登入任意網站、繞過驗證或保證未來股價。")
