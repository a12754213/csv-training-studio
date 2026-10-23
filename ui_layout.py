"""Consistent safe-area aware spacing for Streamlit's multipage interface.

Streamlit's fixed toolbar can overlap the first heading on narrow/mobile screens
when page-level CSS reduces the default content padding too aggressively.
"""
import streamlit as st


PAGE_CSS = """
<style>
/* Keep the first content block below Streamlit's fixed header/toolbar. */
section.main .block-container,
[data-testid="stMainBlockContainer"] {
    max-width: 1280px;
    padding-top: 5.5rem !important;
    padding-bottom: 3rem !important;
    padding-left: max(1.25rem, env(safe-area-inset-left, 0px)) !important;
    padding-right: max(1.25rem, env(safe-area-inset-right, 0px)) !important;
}

/* Chinese headings need extra line-height; don't crop their glyph bounds. */
[data-testid="stMainBlockContainer"] h1,
section.main h1 {
    line-height: 1.25 !important;
    margin-top: 0.15rem !important;
    margin-bottom: 0.45rem !important;
    padding-top: 0.15rem !important;
    padding-bottom: 0.18rem !important;
    overflow-wrap: anywhere;
    overflow: visible !important;
}

/* Do not let wide tables/metrics force the mobile page to overflow sideways. */
[data-testid="stMainBlockContainer"] {
    min-width: 0;
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
    """Render a shared stylesheet on every Streamlit page after set_page_config."""
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
