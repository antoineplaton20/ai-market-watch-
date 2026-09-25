#!/usr/bin/env bash
# Lance le moteur v17 à la main (sur le serveur, c'est le service equipe-bots-v17 qui le fait : bots v17-demarrer).
# Les réglages viennent du .env (V17_MODE, V17_SYMBOLS, V17_TIMEFRAME...). Paper par défaut.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
exec "$PY" -m v17_ops "$@"
