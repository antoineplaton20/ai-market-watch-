#!/usr/bin/env bash
# API de supervision v17 (lecture seule). Écoute UNIQUEMENT sur 127.0.0.1 : jamais exposée sur Internet.
# Sur le serveur : bots v17-api-demarrer (service), puis redirection de port dans Termius.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
exec "$PY" -m uvicorn v17_ops.api.app:app --host 127.0.0.1 --port "${V17_API_PORT:-8080}"
