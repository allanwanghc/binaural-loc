#!/bin/bash
# Double-click to run the demo. Keep this window open; Ctrl+C (or closing it) stops the server.
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] && [ -f binaural_loc/web/dist/index.html ] || ./setup.sh || { read -r -p "Setup failed. Press Return."; exit 1; }
if curl -s -o /dev/null http://127.0.0.1:8000/api/config; then
  echo "The server is already running."; open http://127.0.0.1:8000/; exit 0
fi
.venv/bin/python examples/demo/run.py
read -r -p "Server stopped. Press Return to close."
