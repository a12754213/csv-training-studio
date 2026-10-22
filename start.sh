#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -d .venv ]]; then
  studio_python="${CSV_STUDIO_PYTHON:-python3.12}"
  if ! command -v "$studio_python" >/dev/null 2>&1; then
    echo 'Install Python 3.12 first, or use Docker. See docs/LOCAL.md.' >&2
    exit 1
  fi
  "$studio_python" -m venv .venv
fi
studio_python='.venv/bin/python'
if [[ ! -x "$studio_python" ]]; then
  echo 'Existing .venv is incomplete. Rename it to .venv-backup and try again.' >&2
  exit 1
fi
"$studio_python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)'
if ! "$studio_python" scripts/check_environment.py --quiet; then
  "$studio_python" -m pip install -r requirements.lock.txt
  "$studio_python" scripts/check_environment.py
fi
if [[ "${1:-}" == '--setup-only' ]]; then exit 0; fi
exec "$studio_python" scripts/serve.py "$@"
