"""Produce configuration using this installation's exact executable and absolute paths."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    output = ROOT / 'outputs' / 'chatgpt'
    inbox = ROOT / 'uploads'
    output.mkdir(parents=True, exist_ok=True)
    inbox.mkdir(exist_ok=True)
    args = [str(ROOT / 'chatgpt_server.py'), '--workspace', str(output), '--inbox', str(inbox)]
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    config = ('[mcp_servers.csv-training-studio]\ncommand = ' + quote(sys.executable)
              + '\nargs = ' + quote(args) + '\nstartup_timeout_sec = 30\ntool_timeout_sec = 60\n')
    path = output / 'mcp-config.toml'
    path.write_text(config, encoding='utf-8')
    (output / 'connection.json').write_text(json.dumps({'type': 'stdio', 'command': sys.executable,
                                                       'args': args}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('ChatGPT Settings > MCP servers > Add server > STDIO')
    print('Command:', sys.executable)
    print('Arguments:', quote(args))
    print('Configuration snippet:', path)
    print('Input folder:', inbox)
    print('This only prepared the connection; add the server in your local client and restart it.')


if __name__ == '__main__':
    main()
