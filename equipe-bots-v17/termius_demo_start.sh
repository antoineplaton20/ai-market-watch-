#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# Serveur de la plateforme (service equipe-bots) : la v17 y tourne en service systemd, avec Telegram et
# redémarrage automatique. Ce script passe alors la main à la télécommande « bots » (au lieu d'un nohup en root).
if [ -f /etc/systemd/system/equipe-bots.service ] && command -v bots > /dev/null 2>&1; then
  echo "Serveur de la plateforme détecté : démarrage avec « bots v17-demo »."
  exec bots v17-demo
fi
[ -x .venv/bin/python ] || { echo "Lance d'abord ./termius_demo_install.sh"; exit 1; }
set -a; source .env; set +a
mkdir -p runtime logs
chmod 600 .env
./termius_demo_check.sh
if [ -f runtime/v17_demo.pid ] && kill -0 "$(cat runtime/v17_demo.pid)" 2>/dev/null; then
  echo "V17 Demo déjà démarrée (PID $(cat runtime/v17_demo.pid))."
  exit 0
fi
nohup env V17_MODE=demo V17_DEMO_ONLY=1 LIVE_TRADING_ENABLED=0 .venv/bin/python -m v17_ops \
  >> runtime/v17_stdout.log 2>&1 &
echo $! > runtime/v17_demo.pid
sleep 2
if ! kill -0 "$(cat runtime/v17_demo.pid)" 2>/dev/null; then
  echo "Le moteur n'a pas démarré. Voir runtime/v17_stdout.log"
  exit 1
fi
echo "V17 Binance Demo démarrée. PID $(cat runtime/v17_demo.pid)"
echo "Logs : tail -f runtime/v17_stdout.log"
