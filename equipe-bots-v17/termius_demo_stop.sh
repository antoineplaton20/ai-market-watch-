#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# Serveur de la plateforme (service equipe-bots) : la v17 y tourne en service systemd, avec Telegram et
# redémarrage automatique. Ce script passe alors la main à la télécommande « bots » (au lieu d'un nohup en root).
if [ -f /etc/systemd/system/equipe-bots.service ] && command -v bots > /dev/null 2>&1; then
  echo "Serveur de la plateforme détecté : arrêt avec « bots v17-arreter »."
  exec bots v17-arreter
fi
if [ -f runtime/v17_demo.pid ]; then
  PID="$(cat runtime/v17_demo.pid)"
  if kill -0 "$PID" 2>/dev/null; then kill "$PID"; fi
  rm -f runtime/v17_demo.pid
fi
echo "V17 Demo arrêtée."
