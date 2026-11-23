#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python >= 3.10 required"; exit 1; }
command -v npm >/dev/null || { echo "npm (Node.js >= 20.19) required"; exit 1; }

[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev]"
npm --prefix binaural_loc/web install --no-fund --no-audit
npm --prefix binaural_loc/web run build

echo
echo "Done. Demo: .venv/bin/python examples/demo/run.py"
