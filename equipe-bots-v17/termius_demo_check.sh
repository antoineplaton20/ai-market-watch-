#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# Serveur de la plateforme (service equipe-bots) : la v17 y tourne en service systemd, avec Telegram et
# redémarrage automatique. Ce script passe alors la main à la télécommande « bots » (au lieu d'un nohup en root).
if [ -f /etc/systemd/system/equipe-bots.service ] && command -v bots > /dev/null 2>&1; then
  echo "Serveur de la plateforme détecté : test du compte démo avec « bots v17-demo-test »."
  exec bots v17-demo-test
fi
[ -x .venv/bin/python ] || { echo "Lance d'abord ./termius_demo_install.sh"; exit 1; }
.venv/bin/python - <<'PYCONFIG'
from v17_ops.core.config import settings
if not settings.demo_only or settings.mode != 'demo' or settings.entries_blocked:
    raise SystemExit('ERREUR : V17_MODE=demo, V17_DEMO_ONLY=1 et réglages valides requis dans .env')
PYCONFIG
.venv/bin/python -m v17_ops.verif_demo
