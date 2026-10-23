"""Agent Research & Media — standalone, explicitly approved module actions."""
from __future__ import annotations

import hashlib
import os
import pandas as pd
import streamlit as st

from agent_hub import AgentContext
from agent_modules import build_registry
from ui_layout import apply_page_layout, render_page_header

st.set_page_config(page_title="Research & Media · AI Agent Hub", page_icon="🔎", layout="wide")
apply_page_layout()
render_page_header(title="🔎 網路研究與多媒體工具", category="RESEARCH / MEDIA",
                   description="自主搜尋公開索引、選擇來源、讀取 PDF／圖片／音訊／字幕以及影片公開資訊。")
st.info("各工具可獨立使用；搜尋需 Brave API Key，影像理解與音訊轉錄需 OpenAI API Key。"
        "不會自行外傳上傳檔案或訓練模型；公開網站仍須遵守擷取限制。")
registry = build_registry()
search_tab, media_tab, memory_tab = st.tabs(["網路搜尋與研究", "PDF／圖片／語音／影片", "本機記憶與排程"])

with search_tab:
    query = st.text_input("研究主題", placeholder="最近一年的 NVIDIA 顯示卡價格")
    brave_key = st.text_input("Brave Search API Key", type="password", key="research_brave")
    freshness = st.selectbox("搜尋範圍", ["不限時間", "過去一天", "過去一週", "過去一月", "過去一年"])
    freshness_code = {"不限時間": "", "過去一天": "pd", "過去一週": "pw",
                      "過去一月": "pm", "過去一年": "py"}[freshness]
    fingerprint = hashlib.sha256(repr((query, freshness_code)).encode()).hexdigest()
    if st.session_state.get("research_query_signature") != fingerprint:
        st.session_state["research_query_signature"] = fingerprint
        st.session_state.pop("research_search", None)
        st.session_state.pop("research_sources", None)
        st.session_state.pop("research_report", None)
    if st.button("核准查詢網路搜尋索引", type="primary"):
        try:
            with st.spinner("呼叫公開網路搜尋 API…"):
                answer = registry.run("web.search", AgentContext(), {
                    "query": query, "api_key": brave_key, "count": 8,
                    "freshness": freshness_code}, approved=True)
            st.session_state["research_search"] = answer
            st.session_state.pop("research_sources", None)
            st.session_state.pop("research_report", None)
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
    search_result = st.session_state.get("research_search")
    if search_result:
        st.caption(f"找到 {search_result['count']} 個搜尋結果。搜尋摘要尚未驗證。")
        rows = search_result["results"]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        choices = {f"{i+1}. {row['title'][:90]}": row["url"] for i, row in enumerate(rows)}
        selected = st.multiselect("選擇要實際擷取的網頁（最多三個）",
                                  list(choices), max_selections=3)
        if st.button("核准擷取選定的網址", disabled=not selected, type="primary"):
            try:
                actual_urls = [choices[x] for x in selected]
                # Never read an LLM-provided URL not already present in displayed results.
                with st.spinner("逐一擷取已核准的公開網址…"):
                    reviewed = registry.run("web.research_selected", AgentContext(),
                                            {"urls": actual_urls}, approved=True)
                st.session_state["research_sources"] = reviewed
                st.session_state.pop("research_report", None)
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
        if st.session_state.get("research_sources"):
            for item in st.session_state["research_sources"]["sources"]:
                with st.expander(item["url"], expanded=True):
                    if item["status"] != "completed":
                        st.warning("此來源無法讀取，未納入分析。")
                    else:
                        st.write(item["title"])
                        st.text(item["text_preview"])
                        if item["kind"] == "table":
                            st.caption(f"表格：{item['rows']} 列、{item['columns']} 欄")
            st.caption("來源已分別列出，內容不代表已查證。")
            api_key_report = st.text_input("OpenAI API Key（來源報告，選填）",
                                            type="password", key="research_synthesis_key")
            consent_report = st.checkbox("我同意將上方已擷取的來源文字片段傳給 OpenAI 整理研究報告",
                                         value=False, key="research_synthesis_consent")
            if st.button("核准產生有來源標記的研究報告", disabled=not consent_report):
                try:
                    with st.spinner("綜合已核准的網頁文字…"):
                        report = registry.run("web.synthesize", AgentContext(), {
                            "query": query, "sources": st.session_state["research_sources"]["sources"],
                            "api_key": api_key_report}, approved=True)
                    st.session_state["research_report"] = report
                except (ValueError, RuntimeError, OSError) as exc:
                    st.error(str(exc))
            if st.session_state.get("research_report"):
                summary = st.session_state["research_report"]
                st.markdown(summary["report"])
                for source in summary["sources"]:
                    st.markdown(f"[{source['index']}] {source['url']}")
                st.caption(summary["warning"])

with media_tab:
    st.subheader("讀取本機檔案")
    uploaded = st.file_uploader("選擇 PDF、圖片、音訊或字幕",
                                type=["pdf", "png", "jpg", "jpeg", "webp", "gif",
                                      "wav", "mp3", "mp4", "m4a", "mpeg", "mpga", "webm", "srt", "vtt"],
                                key="agent_media_file")
    openai_key = st.text_input("OpenAI API Key（僅視覺辨識／音訊轉錄會使用）",
                               type="password", key="agent_media_api_key")
    if uploaded:
        ext = uploaded.name.lower().rsplit(".", 1)[-1]
        default_tool = {
            "pdf": "document.pdf",
            "png": "image.inspect", "jpg": "image.inspect", "jpeg": "image.inspect",
            "webp": "image.inspect", "gif": "image.inspect",
            "wav": "audio.inspect", "srt": "video.subtitles", "vtt": "video.subtitles",
        }.get(ext)
        tools = [default_tool] if default_tool else []
        if ext in {"png", "jpg", "jpeg", "webp"}:
            tools.append("image.describe")
        if ext in {"mp3", "mp4", "m4a", "mpeg", "mpga", "wav", "webm"}:
            tools.append("audio.transcribe")
        chosen = st.selectbox("處理方式", tools) if tools else None
        external = chosen in {"image.describe", "audio.transcribe"}
        if external:
            approved_upload = st.checkbox("我同意將這份檔案傳送至外部 OpenAI API 進行分析",
                                          value=False, key="media_approval")
        else:
            approved_upload = True
        if chosen and st.button("執行選定工具", disabled=not approved_upload, type="primary"):
            try:
                context = AgentContext(payload=uploaded.getvalue(), filename=uploaded.name)
                params = {"api_key": openai_key} if external else {}
                with st.spinner("讀取檔案與分析…"):
                    data = registry.run(chosen, context, params, approved=True)
                st.session_state["agent_media_result"] = {
                    "file_id": hashlib.sha256(uploaded.getvalue()).hexdigest(),
                    "tool": chosen, "data": data}
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
        previous = st.session_state.get("agent_media_result")
        if (previous and previous["file_id"] == hashlib.sha256(uploaded.getvalue()).hexdigest()
                and previous["tool"] == chosen):
            st.subheader("分析結果")
            st.json(previous["data"])
    st.divider()
    st.subheader("YouTube 公開影片")
    video_url = st.text_input("YouTube 影片網址", placeholder="https://www.youtube.com/watch?v=...")
    st.caption("影片資訊僅在本機管理員啟用 yt-dlp 的環境中可用；目前不會下載影片。")
    if st.button("核准查詢 YouTube 公開影片資訊", type="secondary"):
        try:
            info = registry.run("video.youtube_info", AgentContext(), {"url": video_url}, approved=True)
            st.json(info)
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
    if st.button("核准讀取 YouTube 公開字幕", type="secondary"):
        try:
            transcript = registry.run("video.youtube_transcript", AgentContext(),
                                      {"url": video_url}, approved=True)
            st.text_area("影片字幕", transcript["text"], height=180)
            st.caption(transcript["note"])
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
    st.divider()
    st.subheader("隔離瀏覽器：動態網頁")
    js_url = st.text_input("需 JavaScript 的公開網頁網址", key="js_url")
    if st.button("核准使用隔離 Playwright 擷取網頁", type="secondary"):
        try:
            result = registry.run("web.render", AgentContext(),
                                  {"url": js_url}, approved=True)
            st.json(result)
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))

with memory_tab:
    if os.environ.get("AI_AGENT_LOCAL_WORKSPACE") != "1":
        st.info("記憶與排程資料庫只提供單一使用者的本機工作區。"
                "公開 Streamlit Cloud 預設停用，避免不同訪客共享資料。")
    else:
        from pathlib import Path
        from agent_store import AgentStore
        store = AgentStore(Path("outputs/agent_hub.db"))
        note = st.text_area("明確記住這項工作偏好或筆記（儲存在本機 SQLite）")
        if st.button("同意儲存這則筆記", disabled=not bool(note.strip())):
            try:
                store.remember(note, consent=True)
                st.success("已加入本機工作筆記。")
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
        notes = store.recall()
        if notes:
            st.dataframe(pd.DataFrame(notes), hide_index=True, width="stretch")
            delete_id = st.selectbox("刪除本機筆記", [None] + [x["id"] for x in notes])
            if delete_id and st.button("確認刪除選定筆記"):
                store.forget(delete_id)
                st.rerun()
        st.divider()
        st.subheader("定期搜尋工作")
        period = st.selectbox("執行間隔", ["每小時", "每天", "每週"])
        period_value = {"每小時": 60, "每天": 1440, "每週": 10080}[period]
        recurring = st.text_input("未來定期查詢的公開搜尋詞")
        if st.button("核准建立本機排程", disabled=not bool(recurring.strip())):
            try:
                store.schedule_search(recurring, period_value, consent=True)
                st.success("已建立排程定義。另需啟動本機排程 Worker 才會定期執行。")
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
        schedules = store.list_schedules()
        if schedules:
            st.dataframe(pd.DataFrame([{k: v for k, v in rec.items() if k != "result_json"}
                                       for rec in schedules]), hide_index=True, width="stretch")
            picked = st.selectbox("停用排程", [None] + [x["id"] for x in schedules])
            if picked and st.button("確認停用選定排程"):
                store.stop_schedule(picked)
                st.rerun()
        st.caption("排程 Worker 必須由你的 Windows 工作排程器／cron 獨立啟動；不會在雲端背景自動執行。")
