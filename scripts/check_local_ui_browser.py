"""Actual Chromium regression test for heading clipping on desktop/mobile.

This tests a local Streamlit build, independently of a stale Cloud deployment.
The GitHub Cloud check runs this before checking the public URL.
"""
from pathlib import Path
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urljoin
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

# Import labels from the shared UI module for version-safe browser assertions.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui_layout import HOME_HEADING, AGENT_HEADING, CHAT_HEADING, CRAWLER_HEADING, ROUTER_HEADING


def find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_healthy(url, process, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Streamlit exited before HTTP readiness")
        try:
            with urlopen(url + "/_stcore/health", timeout=1.5) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.25)
    raise TimeoutError("Local Streamlit health check timed out")


def verify_heading(page, name, min_top=40):
    heading = page.get_by_role("heading", name=name).first
    heading.wait_for(state="visible", timeout=35000)
    box = heading.bounding_box()
    if box is None:
        raise AssertionError(f"{name}: heading has no bounding box")
    if box["y"] < min_top:
        raise AssertionError(f"{name}: heading starts at y={box['y']:.1f}; covered by top toolbar")
    if box["width"] < 100 or box["height"] < 20:
        raise AssertionError(f"{name}: heading appears collapsed or clipped ({box})")
    if box["y"] + box["height"] > page.viewport_size["height"]:
        raise AssertionError(f"{name}: heading isn't inside the initial viewport ({box})")
    if page.get_by_test_id("stException").count():
        raise AssertionError(f"{name}: Streamlit displayed an exception")


def run_browser(base):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for viewport in ({"width": 1280, "height": 900}, {"width": 390, "height": 844}):
                context = browser.new_context(viewport=viewport, locale="zh-TW")
                page = context.new_page()
                page.goto(base, wait_until="domcontentloaded", timeout=45000)
                verify_heading(page, HOME_HEADING)
                print(f"PASS: homepage heading visible at {viewport['width']}px", flush=True)
                if viewport["width"] == 1280:
                    # Streamlit's automatic multipage navigation must link both new pages.
                    nav = page.locator('[data-testid="stSidebarNav"]')
                    nav.wait_for(state="visible", timeout=15000)
                    for label, heading in (
                        ("AI Agent", AGENT_HEADING),
                        ("AI Chat", CHAT_HEADING),
                        ("Web Crawler", CRAWLER_HEADING),
                        ("Agent Router", ROUTER_HEADING),
                    ):
                        link = nav.get_by_role("link", name=re.compile(label)).first
                        link.wait_for(state="attached", timeout=10000)
                        href = link.get_attribute("href")
                        if not href:
                            raise AssertionError(f"Missing navigation URL for {label}")
                        page.goto(urljoin(base + "/", href), wait_until="domcontentloaded", timeout=45000)
                        verify_heading(page, heading)
                        print(f"PASS: {label} navigation and heading are visible", flush=True)
                context.close()
        finally:
            browser.close()


def main():
    port = find_free_port()
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as temp:
        log_path = Path(temp) / "streamlit.log"
        with log_path.open("w+", encoding="utf-8") as log:
            kwargs = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                      else {"start_new_session": True})
            proc = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
                 "--server.headless=true", "--server.address=127.0.0.1",
                 "--server.port", str(port), "--browser.gatherUsageStats=false"],
                cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, **kwargs,
            )
            try:
                wait_healthy(base, proc)
                run_browser(base)
            except Exception:
                log.flush()
                print(log_path.read_text(encoding="utf-8", errors="replace")[-9000:])
                raise
            finally:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   capture_output=True)
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    main()
