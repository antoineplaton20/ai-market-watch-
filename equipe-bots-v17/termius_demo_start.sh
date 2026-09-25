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
AUTO=0; [ "${1:-}" = "--auto" ] && AUTO=1          # appel automatique (cron) : silencieux, sans test réseau
set -a; source .env; set +a
mkdir -p runtime logs
chmod 600 .env
if [ -f runtime/v17_superviseur.pid ] && kill -0 "$(cat runtime/v17_superviseur.pid)" 2>/dev/null; then
  [ "$AUTO" = 1 ] || echo "V17 Demo déjà démarrée (superviseur PID $(cat runtime/v17_superviseur.pid))."
  exit 0
fi
if [ "$AUTO" = 1 ]; then
  [ -f runtime/v17_demo.stop ] && exit 0            # arrêtée volontairement : on ne la relance pas
else
  ./termius_demo_check.sh
  rm -f runtime/v17_demo.stop
fi
# Superviseur : relance le moteur sans fin, détaché de Termius (on peut fermer l'application)
setsid nohup ./termius_superviseur.sh > /dev/null 2>&1 < /dev/null &
# Relance après redémarrage de la machine et contrôle toutes les 5 min (si cron est disponible)
if command -v crontab > /dev/null 2>&1; then
  LIGNE="*/5 * * * * cd '$ROOT' && ./termius_demo_start.sh --auto > /dev/null 2>&1"
  REBOOT="@reboot cd '$ROOT' && sleep 30 && ./termius_demo_start.sh --auto > /dev/null 2>&1"
  { crontab -l 2>/dev/null | grep -vF "$ROOT' && ./termius_demo_start.sh --auto"; echo "$LIGNE"; echo "$REBOOT"; } | crontab - \
    || echo "Note : cron indisponible, pas de relance automatique après redémarrage de la machine."
fi
sleep 3
if ! { [ -f runtime/v17_superviseur.pid ] && kill -0 "$(cat runtime/v17_superviseur.pid)" 2>/dev/null; }; then
  echo "Le superviseur n'a pas démarré. Voir runtime/v17_stdout.log"
  exit 1
fi
[ "$AUTO" = 1 ] && exit 0
echo "V17 Binance Demo démarrée sous superviseur (PID $(cat runtime/v17_superviseur.pid)) : relance automatique sans fin,"
echo "y compris après un redémarrage de la machine (cron). Arrêt : ./termius_demo_stop.sh"
echo "Logs : tail -f runtime/v17_stdout.log"
