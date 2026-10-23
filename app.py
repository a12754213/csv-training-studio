"""Unified entrypoint; existing tools keep independent engines."""
import streamlit as st
st.set_page_config(page_title="AI Agent Hub", page_icon="🤖", layout="wide")
page = st.navigation({
    "開始工作": [
        st.Page("pages/0_AI_Workspace.py", title="AI 任務", icon="🤖", default=True),
        st.Page("pages/8_CSV_Workspace.py", title="CSV 訓練", icon="📊", url_path="CSV_Workspace"),
        st.Page("pages/7_Research_Media.py", title="網路與多媒體", icon="🔎", url_path="Research_Media"),
    ],
    "進階工具": [
        st.Page("pages/1_AI_Agent.py", title="資料分析 Agent", url_path="AI_Agent"),
        st.Page("pages/2_AI_Chat.py", title="CSV 自然語言規劃", url_path="AI_Chat"),
        st.Page("pages/3_Web_Crawler.py", title="單一網頁擷取", url_path="Web_Crawler"),
        st.Page("pages/4_Agent_Router.py", title="工具分流", url_path="Agent_Router"),
        st.Page("pages/5_Agent_Core.py", title="Core 2.0", url_path="Agent_Core"),
        st.Page("pages/6_Agent_Core_3.py", title="Core 3.0", url_path="Agent_Core_3"),
    ],
})
page.run()
