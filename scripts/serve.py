"""Start a loopback-only Streamlit server and open the browser after readiness."""
from __future__ import annotations
import argparse
from pathlib import Path
import socket
import subprocess
import sys
import threading
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def select_port(requested: int | None = None) -> int:
    for port in ([requested] if requested else range(8501, 8521)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Port is in use. Close the other app or choose --port 8601.")


def open_when_ready(process: subprocess.Popen, url: str, stop: threading.Event):
    for _ in range(120):
        if stop.is_set() or process.poll() is not None:
            return
        try:
            with urlopen(url + "/_stcore/health", timeout=1) as response:
                ready = response.status == 200
            if ready:
                webbrowser.open(url)
                return
        except (OSError, ValueError):
            pass
        stop.wait(0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        port = select_port(args.port)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{port}"
    print(f"CSV Training Studio: {url}\nKeep this terminal open. Press Ctrl+C to stop.", flush=True)
    process = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
        "--server.address=127.0.0.1", f"--server.port={port}",
        "--server.headless=true", "--browser.gatherUsageStats=false",
    ], cwd=ROOT)
    stop = threading.Event()
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(process, url, stop), daemon=True).start()
    try:
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    sys.exit(main())
