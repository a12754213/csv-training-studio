"""Independent public-web crawler page. Does not train any model."""
from __future__ import annotations

import io
import pandas as pd
import streamlit as st
from agent_hub import AgentContext
from agent_modules import build_registry
from ui_layout import apply_page_layout

st.set_page_config(page_title="網路爬蟲 · CSV Training Studio", page_icon="🌐", layout="wide")
apply_page_layout()
st.title("🌐 網路爬蟲 · 獨立工具")
st.caption("單一公開網址 → 網頁文字或 HTML 表格 → 預覽／下載 CSV；不會自動啟動模型訓練。")
st.info("首版支援公開、靜態 HTML／CSV，最多 1.5 MB、1,000 列。會尊重 robots.txt；不支援登入、JavaScript 動態資料或反爬限制。")

url = st.text_input("公開網頁網址", placeholder="https://example.com/articles")
# Display only the fetched result matching the current URL input.
if st.session_state.get("crawler_requested_url") != url.strip():
    st.session_state.pop("crawler_result", None)
if st.button("確認網址並抓取", type="primary"):
    try:
        result = build_registry().run("web.crawl", AgentContext(), {"url": url}, approved=True)
        st.session_state["crawler_result"] = result
        st.session_state["crawler_requested_url"] = url.strip()
        st.success("資料擷取完成。")
    except (ValueError, OSError) as exc:
        st.session_state.pop("crawler_result", None)
        st.error(str(exc))

result = st.session_state.get("crawler_result")
if result:
    st.caption(f"已抓取：{result['url']}")
    if result["title"]:
        st.subheader(result["title"])
    if result["csv_bytes"]:
        st.metric("表格資料列數", result["rows"])
        st.dataframe(pd.read_csv(io.BytesIO(result["csv_bytes"])).head(50), width="stretch", hide_index=True)
        st.download_button("下載網頁擷取資料 CSV", data=result["csv_bytes"],
                           file_name="web_extract.csv", mime="text/csv")
    if result["text"]:
        st.subheader("網頁文字預覽")
        st.text(result["text"][:6000])
    st.caption("表格或文章是否能直接用於機器學習，仍取決於欄位、標籤與資料品質。")
