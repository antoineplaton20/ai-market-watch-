#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# Serveur de la plateforme (service equipe-bots) : la v17 y tourne en service systemd, avec Telegram et
# redémarrage automatique. Ce script passe alors la main à la télécommande « bots » (au lieu d'un nohup en root).
if [ -f /etc/systemd/system/equipe-bots.service ] && command -v bots > /dev/null 2>&1; then
  echo "Serveur de la plateforme détecté : rien à installer (la v17 arrive avec « bots mettre-a-jour »). Test du compte démo :"
  exec bots v17-demo-test
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 est requis. Sur Debian/Ubuntu : sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip wheel
.venv/bin/python -m pip install -r requirements.txt
mkdir -p runtime logs
chmod 700 runtime logs

if [ ! -f .env ]; then
  cp .env.termux.demo.example .env
  chmod 600 .env
  echo
  echo "Configuration créée : .env"
  echo "Édite-la maintenant : nano .env"
  echo "Renseigne V17_API_KEY et V17_API_SECRET avec TES clés Binance Demo."
else
  echo ".env déjà présent : conservé."
fi

# Vérification de sécurité avant démarrage
.venv/bin/python - <<'PY'
from dotenv import load_dotenv
import os
load_dotenv()
mode=os.getenv('V17_MODE','').strip().lower()
only=os.getenv('V17_DEMO_ONLY','0').strip().lower()
key=os.getenv('V17_API_KEY','').strip()
secret=os.getenv('V17_API_SECRET','').strip()
if only not in {'1','true','yes','on'} or mode != 'demo':
    raise SystemExit('ERREUR: la configuration doit rester V17_DEMO_ONLY=1 et V17_MODE=demo')
if not key or not secret:
    print('Installation OK. Il reste à renseigner les deux clés Binance Demo dans .env.')
else:
    print('Configuration présente. Les clés ne seront jamais affichées.')
PY

chmod +x termius_demo_*.sh
cat <<'TXT'

Installation terminée.

1) nano .env
2) renseigne V17_API_KEY et V17_API_SECRET
3) ./termius_demo_check.sh
4) ./termius_demo_start.sh

TXT
