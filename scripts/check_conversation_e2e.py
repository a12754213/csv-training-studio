"""Real browser acceptance of multi-file collection, follow-up and CSV handoff.

Only synthetic repository samples are uploaded. No model key or paid API call.
APP_URL optionally targets the deployed website after merging to main.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_local_ui_browser import find_free_port, wait_healthy
from scripts.check_training_e2e import open_page, assert_clean
from ui_layout import HOME_HEADING
from playwright.sync_api import sync_playwright


def verify(base):
    from scripts.check_training_e2e import test_conversation
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':1280,'height':960},locale='zh-TW')
            test_conversation(page,base)
        finally:
            browser.close()


def main():
    remote=os.environ.get('APP_URL','').strip()
    if remote:
        verify(remote)
        return
    port=find_free_port();base=f'http://127.0.0.1:{port}'
    with tempfile.TemporaryFile(mode='w+') as log:
        proc=subprocess.Popen([sys.executable,'-m','streamlit','run','app.py','--server.headless=true',
                               '--server.address=127.0.0.1',f'--server.port={port}',
                               '--browser.gatherUsageStats=false'],cwd=ROOT,stdout=log,stderr=log)
        try:
            wait_healthy(base,proc)
            verify(base)
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()


if __name__=='__main__': main()
