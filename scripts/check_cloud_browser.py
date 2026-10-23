"""Confirm that the publicly visible Streamlit UI renders in a real browser.

A plain HTTP probe is not reliable on Streamlit Community Cloud:
public apps may use JS and cookies to establish a session.
"""

import os
import re
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
                # Detect an old deployed build explicitly instead of reporting
                # that the UI itself is missing (the v2.2.0 page was visible).
                visible_version = re.search(
                    r"程式版本 v([0-9]+\\.[0-9]+\\.[0-9]+)",
                    app.locator("body").inner_text(timeout=15000))
                if visible_version and visible_version.group(1) != __version__:
                    raise RuntimeError(
                        f"STALE DEPLOYMENT: Cloud serves v{visible_version.group(1)} "
                        f"but GitHub source expects v{__version__}; check main/app.py "
                        "and reboot/redeploy in Streamlit Cloud dashboard.")
                app.get_by_text(f"程式版本 v{__version__}", exact=True).wait_for(
                    state="visible", timeout=15000)
                for section in ("AI Agent", "AI Chat"):
                    # Multipage navigation may be collapsed on narrow screens.
                    # Check the sidebar link text on the desktop smoke viewport.
                    if app.get_by_text(section, exact=True).count() == 0:
                        raise RuntimeError(f"Missing deployed Agent navigation: {section}")
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
                message = str(exc)
                # Only expose our own stale-deployment diagnostic; never print
                # arbitrary exception bodies containing URLs/tokens.
                reason = message if message.startswith(("STALE DEPLOYMENT:", "Missing deployed Agent")) else type(exc).__name__
                print(
                    f"Not ready: {reason}; "
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
        "FAIL: Cloud deployment did not match the expected app release. "
        "Check Streamlit Cloud deployment branch (main), entrypoint (app.py), "
        "version, and Manage app > Logs / Reboot. "
        "This does not imply that GitHub Python unit tests failed."
    )


if __name__ == "__main__":
    main()
