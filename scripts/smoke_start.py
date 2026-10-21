"""Start the real launcher from another directory; verify HTTP readiness."""
from pathlib import Path
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / 'server.log'
        with log_path.open('w+', encoding='utf-8') as log:
            flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
            process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/serve.py'), '--no-browser', '--port', str(port)],
                                       cwd=tmp, stdout=log, stderr=subprocess.STDOUT, **flags)
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Launcher exited before readiness')
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=2) as response:
                            if response.status == 200:
                                print('PASS: launcher served HTTP health from a different working directory')
                                return
                    except OSError:
                        pass
                    time.sleep(0.25)
                raise RuntimeError('Server readiness timed out')
            except Exception:
                log.flush()
                print(log_path.read_text(encoding='utf-8', errors='replace'))
                raise
            finally:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    try:
                        os.killpg(process.pid, signal.SIGINT)
                    except ProcessLookupError:
                        pass
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    if os.name != 'nt':
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()


if __name__ == '__main__':
    main()
