"""Browser end-to-end acceptance for the actual CSV training and Agent UI.

Default: local Streamlit server, used for pull requests. Set APP_URL to verify
the published Streamlit Cloud server after deploying to main. Uses only the
project's synthetic demonstration CSV: no private user data or API key.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urljoin
from urllib.request import urlopen
from zipfile import ZipFile, is_zipfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "demo_churn.csv"
APP_URL = os.environ.get("APP_URL", "").strip()
MAX_WAIT = 120000
sys.path.insert(0, str(ROOT))
from version import __version__
from ui_layout import HOME_HEADING, AGENT_HEADING, CHAT_HEADING
HEADING = HOME_HEADING


def app_frame(page, heading, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if frame.get_by_role("heading", name=heading).first.is_visible():
                    return frame
            except Exception:
                pass
        time.sleep(0.4)
    raise AssertionError(f"Missing visible page heading: {heading}")


def assert_clean(frame, name):
    exceptions = frame.get_by_test_id("stException")
    if exceptions.count():
        raise AssertionError(f"{name}: Streamlit exception visible")


def open_page(page, url, heading):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    frame = app_frame(page, heading)
    assert_clean(frame, heading)
    return frame


def download_zip(page, frame, label, directory):
    button = frame.get_by_role("button", name=label, exact=True)
    button.wait_for(state="visible", timeout=MAX_WAIT)
    with page.expect_download(timeout=MAX_WAIT) as pending:
        button.click()
    result = pending.value
    if result.failure():
        raise AssertionError(f"Browser download failed: {result.failure()}")
    destination = Path(directory) / "downloaded_training.zip"
    result.save_as(destination)
    if not is_zipfile(destination):
        raise AssertionError("Browser did not download a valid ZIP")
    with ZipFile(destination) as archive:
        names = archive.namelist()
        if "model.joblib" not in names:
            raise AssertionError("Downloaded ZIP has no trained model.joblib")
        if len(names) < 6:
            raise AssertionError(f"Training ZIP looks incomplete ({len(names)} files)")
        print(f"PASS: {label} -> ZIP with model.joblib and {len(names)} files", flush=True)


def click_selectbox_option(frame, label, option):
    control = frame.get_by_role("combobox", name=label)
    # Streamlit 1.66 uses a React-Aria searchable combobox, not BaseWeb.
    # Enter alone does not commit the filtered option; ArrowDown then Enter does.
    control.click(timeout=20000)
    control.fill(option, timeout=20000)
    control.press("ArrowDown", timeout=20000)
    control.press("Enter", timeout=20000)
    if control.input_value() != option:
        raise AssertionError(f"Could not select target option in {label}")


def test_home_training(page, url, directory):
    frame = open_page(page, url, HEADING)
    frame = open_page(page, get_nav_url(frame, "CSV 訓練"), "📊 CSV / AutoML 訓練工作區")
    version = frame.get_by_text(f"AI Agent Hub · 程式版本 v{__version__}", exact=True)
    version.wait_for(state="visible", timeout=20000)
    frame.get_by_role("tab", name="2 · 整理與切分").click()
    frame.get_by_role("button", name="整理成訓練資料", exact=True).click()
    frame.get_by_role("tab", name="3 · 訓練與下載").click()
    frame.get_by_role("button", name="訓練並查看測試結果", exact=True).click(timeout=MAX_WAIT)
    # Wait for the asynchronous Streamlit rerun to commit the trained model.
    # Otherwise the packaging button may still see an older session_state.
    frame.get_by_text("這次模型：", exact=False).first.wait_for(state="visible", timeout=MAX_WAIT)
    frame.get_by_role("button", name="產生可下載資料包", exact=True).click(timeout=MAX_WAIT)
    download_zip(page, frame, "下載 training_data.zip", directory)
    assert_clean(frame, "home training")
    print("PASS: published homepage demo CSV -> prepare -> train -> export", flush=True)
    return frame


def test_uploaded_csv(page, url):
    frame = open_page(page, url, HEADING)
    frame = open_page(page, get_nav_url(frame, "CSV 訓練"), "📊 CSV / AutoML 訓練工作區")
    # In Streamlit 1.66 radio options are labeled; switching sources shows input.
    frame.get_by_text("上傳我的 CSV", exact=True).first.click(timeout=20000)
    frame.locator('[data-testid="stFileUploader"] input[type="file"]').set_input_files(str(SAMPLE))
    frame.get_by_text("demo_churn.csv", exact=False).first.wait_for(state="visible", timeout=MAX_WAIT)
    frame.get_by_role("heading", name="📊 CSV / AutoML 訓練工作區").wait_for(state="visible")
    assert_clean(frame, "CSV upload")
    print("PASS: public CSV file upload parsed without error", flush=True)


def get_nav_url(frame, label):
    nav = frame.locator('[data-testid="stSidebarNav"]')
    nav.wait_for(state="visible", timeout=15000)
    link = nav.get_by_role("link", name=re.compile(label)).first
    link.wait_for(state="attached", timeout=10000)
    path = link.get_attribute("href")
    if not path:
        raise AssertionError(f"Missing navigation URL for {label}")
    return urljoin(frame.url, path)


def test_agent(page, url, directory):
    frame = open_page(page, url, HEADING)
    agent_url = get_nav_url(frame, "資料分析 Agent")
    frame = open_page(page, agent_url, AGENT_HEADING)
    frame.locator('[data-testid="stFileUploader"] input[type="file"]').set_input_files(str(SAMPLE))
    frame.get_by_text("資料品質與欄位分析").wait_for(state="visible", timeout=MAX_WAIT)
    click_selectbox_option(frame, "你想預測哪一欄？（必須由你確認）", "是否流失")
    frame.get_by_text("Agent 分析建議").wait_for(state="visible", timeout=15000)
    # Training must be approved through the form, not by the LLM.
    frame.get_by_role("button", name="確認設定並執行訓練", exact=True).click(timeout=MAX_WAIT)
    download_zip(page, frame, "下載 training_data.zip（含模型及評估）", directory)
    assert_clean(frame, "AI Agent training")
    print("PASS: public AI Agent CSV upload -> recommendations -> approval -> train -> ZIP", flush=True)


def test_chat_without_api(page, url):
    frame = open_page(page, url, HEADING)
    chat_url = get_nav_url(frame, "CSV 自然語言規劃")
    frame = open_page(page, chat_url, CHAT_HEADING)
    frame.locator('[data-testid="stFileUploader"] input[type="file"]').set_input_files(str(SAMPLE))
    chat = frame.get_by_test_id("stChatInput").locator("textarea")
    chat.wait_for(state="visible", timeout=MAX_WAIT)
    chat.fill("請分析這份示範資料")
    chat.press("Enter")
    frame.get_by_text("要使用網站內的自然語言 AI", exact=False).first.wait_for(
        state="visible", timeout=MAX_WAIT)
    assert_clean(frame, "AI Chat no-key safe fallback")
    print("PASS: AI Chat displays safe API-key requirement, no billing or training", flush=True)


def test_conversation(page, base):
    app = open_page(page, base, HEADING)
    app.get_by_text('對話與多來源 Agent', exact=True).click()
    app.get_by_role('heading', name='對話與多來源工作區', exact=True).wait_for(timeout=30000)
    app.locator('[data-testid="stFileUploader"] input[type="file"]').set_input_files([
        str(ROOT / 'samples/demo_churn.csv'), str(ROOT / 'samples/demo_housing.csv')])
    app.get_by_role('textbox', name='這次要完成的目標', exact=True).fill('整理兩份資料的概況')
    app.get_by_role('button', name='開始任務', exact=True).click()
    app.get_by_text('目前工作區共有 2 個可用來源', exact=False).first.wait_for(timeout=30000)
    assert_clean(app, 'conversation initial collection')
    print('PASS: two CSV files collected into one workspace', flush=True)
    chat = app.get_by_test_id('stChatInput').locator('textarea')
    chat.fill('接著查看兩份資料的欄位')
    chat.press('Enter')
    app.get_by_text('接著查看兩份資料的欄位', exact=True).wait_for(timeout=30000)
    app.get_by_text('目前工作區共有 2 個可用來源', exact=False).last.wait_for(timeout=30000)
    assert_clean(app, 'conversation follow-up')
    print('PASS: follow-up preserves two existing sources', flush=True)
    app.get_by_role('tab', name='資料與訓練', exact=True).click()
    app.get_by_role('button', name='接續 CSV 訓練', exact=True).click()
    app = app_frame(page, '📊 CSV / AutoML 訓練工作區')
    app.get_by_text('使用 AI 任務資料', exact=True).wait_for(timeout=30000)
    assert_clean(app, 'conversation dataset handoff')
    print('PASS: chosen conversation dataset handed to CSV training', flush=True)


def run_suite(base):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="zh-TW", accept_downloads=True)
        try:
            page = context.new_page()
            with tempfile.TemporaryDirectory() as artifacts:
                test_home_training(page, base, artifacts)
                test_uploaded_csv(page, base)
                test_agent(page, base, artifacts)
                test_chat_without_api(page, base)
                test_conversation(page, base)
            print(f"PASS: Full end-to-end browser acceptance v{__version__} at {base}", flush=True)
        finally:
            context.close()
            browser.close()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_local():
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as directory:
        log_path = Path(directory) / "server.log"
        with log_path.open("w+", encoding="utf-8") as log:
            flags = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                     else {"start_new_session": True})
            process = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
                 "--server.headless=true", "--server.address=127.0.0.1",
                 "--server.port", str(port), "--browser.gatherUsageStats=false"],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, **flags)
            try:
                for _ in range(240):
                    if process.poll() is not None:
                        raise RuntimeError("Streamlit quit before readiness")
                    try:
                        with urlopen(base + "/_stcore/health", timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        pass
                    time.sleep(0.25)
                else:
                    raise TimeoutError("Local Streamlit did not become ready")
                run_suite(base)
            except Exception:
                log.flush()
                # Only synthetic sample data is used. Never log session tokens.
                print(log_path.read_text(encoding="utf-8", errors="replace")[-5000:])
                raise
            finally:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True)
                else:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    if not SAMPLE.is_file():
        raise SystemExit("Missing synthetic sample CSV")
    if APP_URL:
        if not APP_URL.startswith("https://"):
            raise SystemExit("APP_URL must use HTTPS")
        run_suite(APP_URL)
    else:
        run_local()
