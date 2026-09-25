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
mkdir -p runtime
touch runtime/v17_demo.stop                        # le superviseur et le cron ne relancent plus rien
if command -v crontab > /dev/null 2>&1; then
  crontab -l 2>/dev/null | grep -vF "$ROOT' && ./termius_demo_start.sh --auto" | crontab - 2>/dev/null || true
fi
for f in runtime/v17_superviseur.pid runtime/v17_demo.pid; do
  if [ -f "$f" ]; then
    PID="$(cat "$f")"
    if kill -0 "$PID" 2>/dev/null; then kill "$PID"; fi
  fi
done
for _ in $(seq 30); do
  { [ -f runtime/v17_demo.pid ] && kill -0 "$(cat runtime/v17_demo.pid)" 2>/dev/null; } || break
  sleep 1
done
rm -f runtime/v17_demo.pid runtime/v17_superviseur.pid
echo "V17 Demo arrêtée (plus de relance automatique). Relancer : ./termius_demo_start.sh"
