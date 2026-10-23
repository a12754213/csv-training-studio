"""Shared visual language for the modular AI Agent Hub Streamlit application.

Keeps Streamlit controls native and accessible; visual CSS only. All modules
render the same product identity and explain the scope of the tool clearly.
"""
from __future__ import annotations

import streamlit as st
from version import __version__


PRODUCT_NAME = "AI Agent Hub"
HOME_HEADING = "AI Agent Hub｜多功能智慧工作台"
AGENT_HEADING = "🤖 資料分析 Agent"
CHAT_HEADING = "💬 自然語言工作台"
CRAWLER_HEADING = "🌐 網頁資料擷取"
ROUTER_HEADING = "🧭 Agent 工具自動分流"

PAGE_CSS = """
<style>
/* Shared safe area: fixed Streamlit toolbars must not cover first heading. */
section.main .block-container,
[data-testid="stMainBlockContainer"] {
    max-width: 1260px;
    padding-top: 5.5rem !important;
    padding-bottom: 3.25rem !important;
    padding-left: max(1.4rem, env(safe-area-inset-left, 0px)) !important;
    padding-right: max(1.4rem, env(safe-area-inset-right, 0px)) !important;
    min-width: 0;
}
[data-testid="stMainBlockContainer"] h1,
section.main h1 {
    font-size: clamp(2rem, 3.5vw, 3.1rem) !important;
    letter-spacing: -.035em;
    line-height: 1.25 !important;
    margin-top: 0.12rem !important;
    margin-bottom: 0.4rem !important;
    padding: 0.12rem 0 0.2rem !important;
    overflow-wrap: anywhere;
    overflow: visible !important;
}
[data-testid="stMainBlockContainer"] h2 {
    letter-spacing: -.02em;
    line-height: 1.3;
}
.workspace-eyebrow {
    color: #13846f;
    font-size: .78rem;
    font-weight: 750;
    letter-spacing: .14em;
    line-height: 1.7;
    margin-bottom: .35rem;
    text-transform: uppercase;
}
.workspace-subtitle {
    color: #788980;
    font-size: clamp(.99rem, 1.4vw, 1.09rem);
    line-height: 1.75;
    max-width: 880px;
    margin: 0 0 1.05rem 0;
}
.workspace-feature-label {
    color: #14816d;
    font-weight: 700;
    font-size: .78rem;
    letter-spacing: .06em;
}
[data-testid="stMainBlockContainer"] [data-testid="stMetric"] {
    border: 1px solid rgba(70,130,113,.22);
    border-radius: 14px;
    padding: 14px 18px;
    background: rgba(84,159,130,.045);
}
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
    min-width: 0;
}
[data-testid="stSidebar"] {
    border-right: 1px solid rgba(106,139,125,.14);
}
[data-testid="stSidebarNav"] {
    margin-bottom: .65rem;
}
[data-testid="stMainBlockContainer"] [data-testid="stTabs"] {
    margin-top: .65rem;
}
[data-testid="stMainBlockContainer"] .stAlert {
    border-radius: 12px;
}
@media (max-width: 768px) {
    section.main .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: calc(5.75rem + env(safe-area-inset-top, 0px)) !important;
        padding-bottom: 2.75rem !important;
        padding-left: max(1rem, env(safe-area-inset-left, 0px)) !important;
        padding-right: max(1rem, env(safe-area-inset-right, 0px)) !important;
    }
    [data-testid="stMainBlockContainer"] h1,
    section.main h1 {
        font-size: clamp(1.8rem, 7.2vw, 2.6rem) !important;
        line-height: 1.3 !important;
    }
}
</style>
"""


def apply_page_layout() -> None:
    """Render shared responsive CSS on every Streamlit page."""
    st.markdown(PAGE_CSS, unsafe_allow_html=True)


def render_page_header(*, title: str, category: str, description: str) -> None:
    """Consistent product identity + descriptive module title without HTML titles."""
    st.markdown(
        f'<p class="workspace-eyebrow">AI AGENT HUB · V{__version__} / {category}</p>',
        unsafe_allow_html=True,
    )
    st.title(title)
    st.markdown(f'<p class="workspace-subtitle">{description}</p>', unsafe_allow_html=True)


def render_hub_directory() -> None:
    """Discovery cards for independent tools; existing CSV workflow stays below."""
    st.subheader("選擇工作模組")
    st.caption("每個模組可以單獨使用，也能在 Agent 流程中組合。")
    modules = [
        (
            "🤖 規則型資料 Agent", "pages/1_AI_Agent.py",
            "上傳 CSV → 分析欄位 → 建議模型 → 確認後訓練；不需要 API Key。",
        ),
        (
            "💬 自然語言規劃", "pages/2_AI_Chat.py",
            "以中文提出 CSV 分析需求；需要自己的 OpenAI API Key，訓練前仍會審核。",
        ),
        (
            "🌐 網頁擷取", "pages/3_Web_Crawler.py",
            "擷取單一公開靜態網頁的文字與表格；可預覽並下載 CSV。",
        ),
        (
            "🧭 Agent 工具分流", "pages/4_Agent_Router.py",
            "網址資料自動分流到表格或文字模組；不是全網搜尋。",
        ),
    ]
    for start in range(0, len(modules), 2):
        left, right = st.columns(2, gap="medium")
        for col, (label, path, description) in zip((left, right), modules[start:start + 2]):
            with col:
                with st.container(border=True):
                    st.page_link(path, label=label, use_container_width=True)
                    st.caption(description)
    st.divider()
