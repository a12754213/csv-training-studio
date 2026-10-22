"""Confirm that the publicly visible Streamlit UI renders in a real browser.

A plain HTTP probe is not reliable on Streamlit Community Cloud:
public apps may use JS and cookies to establish a session.
"""

import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from version import __version__

APP_URL = os.environ.get("APP_URL", "").strip()
EXPECTED_HEADING = "把 CSV，整理成能訓練的資料。"
ATTEMPTS = 3


def wait_for_app_frame(page, timeout=40):
    """Community Cloud may wrap the app in a child iframe."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if frame.get_by_role("heading", name=EXPECTED_HEADING).is_visible():
                    return frame
            except Exception:
                # A deployment/navigation may replace the iframe during this check.
                continue
        time.sleep(0.5)
    raise TimeoutError("App heading was not visible in any page frame")


def safe_location(url):
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def main():
    if not APP_URL.startswith("https://"):
        raise SystemExit("APP_URL must be an HTTPS URL")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(locale="zh-TW")
        page = context.new_page()
        for attempt in range(1, ATTEMPTS + 1):
            print(f"Browser check attempt {attempt}/{ATTEMPTS}", flush=True)
            try:
                page.goto(APP_URL, wait_until="domcontentloaded", timeout=45000)
                app = wait_for_app_frame(page)
                app.get_by_text(f"程式版本 v{__version__}", exact=True).wait_for(
                    state="visible", timeout=30000)
                app.get_by_role("tab", name="2 · 整理與切分").click(timeout=10000)
                app.get_by_text("不參與訓練的欄位", exact=True).wait_for(
                    state="visible", timeout=10000)
                # This control is rendered after constructing PrepConfig. A heading
                # alone previously passed even with stale imported Python modules.
                app.get_by_role("button", name="整理成訓練資料", exact=True).wait_for(
                    state="visible", timeout=10000)
                if app.get_by_test_id("stException").count():
                    raise RuntimeError("Streamlit displayed an application exception")
            except Exception as exc:
                # Avoid logging auth payloads or session tokens.
                try:
                    title = page.title()[:90]
                except Exception:
                    title = "(unavailable)"
                try:
                    # Visible content, not page source/cookies/secret query strings.
                    visible_text = " ".join(
                        frame.locator("body").inner_text(timeout=5000)
                        for frame in page.frames
                    )
                    visible_text = " ".join(visible_text.split())[:600]
                except Exception:
                    visible_text = "(body text unavailable)"
                print(f"VISIBLE PAGE TEXT: {visible_text!r}", flush=True)
                print(
                    f"Not ready: {type(exc).__name__}; "
                    f"page={safe_location(page.url)}; title={title!r}",
                    flush=True,
                )
                if attempt < ATTEMPTS:
                    time.sleep(6)
            else:
                print(
                    f"PASS: CSV Training Studio v{__version__}, feature exclusions "
                    "and preparation control are visible without app exceptions "
                    f"at {safe_location(page.url)}",
                    flush=True,
                )
                browser.close()
                return
        browser.close()
    raise SystemExit(
        "FAIL: CSV Training Studio UI was not visible in Chromium. "
        "Inspect Streamlit Community Cloud deployment logs; "
        "this does not imply that GitHub Python unit tests failed."
    )


if __name__ == "__main__":
    main()
