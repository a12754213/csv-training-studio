"""Confirm that the publicly visible Streamlit UI renders in a real browser.

A plain HTTP probe is not reliable on Streamlit Community Cloud:
public apps may use JS and cookies to establish a session.
"""

import os
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


APP_URL = os.environ.get("APP_URL", "").strip()
EXPECTED_HEADING = "把 CSV，整理成能訓練的資料。"
ATTEMPTS = 5


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
                page.get_by_role("heading", name=EXPECTED_HEADING).wait_for(
                    state="visible", timeout=55000
                )
            except Exception as exc:
                # Avoid logging auth payloads or session tokens.
                try:
                    title = page.title()[:90]
                except Exception:
                    title = "(unavailable)"
                print(
                    f"Not ready: {type(exc).__name__}; "
                    f"page={safe_location(page.url)}; title={title!r}",
                    flush=True,
                )
                if attempt < ATTEMPTS:
                    time.sleep(12)
            else:
                print(
                    "PASS: CSV Training Studio heading is visible in a real "
                    f"browser at {safe_location(page.url)}",
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
