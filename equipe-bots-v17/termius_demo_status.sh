#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# Serveur de la plateforme (service equipe-bots) : la v17 y tourne en service systemd, avec Telegram et
# redémarrage automatique. Ce script passe alors la main à la télécommande « bots » (au lieu d'un nohup en root).
if [ -f /etc/systemd/system/equipe-bots.service ] && command -v bots > /dev/null 2>&1; then
  echo "Serveur de la plateforme détecté : état avec « bots v17-etat »."
  exec bots v17-etat
fi
if [ -f runtime/v17_superviseur.pid ] && kill -0 "$(cat runtime/v17_superviseur.pid)" 2>/dev/null; then
  echo "SUPERVISEUR ACTIF — PID $(cat runtime/v17_superviseur.pid) (relance automatique sans fin)"
elif [ -f runtime/v17_demo.stop ]; then
  echo "ARRÊTÉE VOLONTAIREMENT (./termius_demo_start.sh pour relancer)"
else
  echo "SUPERVISEUR ABSENT (./termius_demo_start.sh)"
fi
if [ -f runtime/v17_demo.pid ] && kill -0 "$(cat runtime/v17_demo.pid)" 2>/dev/null; then
  echo "MOTEUR EN MARCHE — PID $(cat runtime/v17_demo.pid)"
else
  echo "MOTEUR EN COURS DE RELANCE OU ARRÊTÉ"
fi
[ -f runtime/v17_stdout.log ] && tail -n 20 runtime/v17_stdout.log || true
