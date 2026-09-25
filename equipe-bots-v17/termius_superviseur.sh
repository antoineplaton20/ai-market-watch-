#!/usr/bin/env bash
# SUPERVISEUR v17 hors plateforme (machine Linux sans « bots ») : relance le moteur SANS FIN.
# Lancé par termius_demo_start.sh (jamais à la main). S'arrête uniquement avec termius_demo_stop.sh
# (fichier runtime/v17_demo.stop). Attente croissante entre deux relances : 10 s, 20 s, 40 s... max 5 min ;
# remise à zéro après 10 min de fonctionnement sans plantage.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
STOP=runtime/v17_demo.stop
LOG=runtime/v17_stdout.log
attente=10
echo $$ > runtime/v17_superviseur.pid
trap 'kill -TERM "$ENFANT" 2>/dev/null; wait "$ENFANT" 2>/dev/null; exit 0' TERM INT
while [ ! -f "$STOP" ]; do
  debut=$(date +%s)
  env V17_MODE=demo V17_DEMO_ONLY=1 LIVE_TRADING_ENABLED=0 .venv/bin/python -m v17_ops >> "$LOG" 2>&1 &
  ENFANT=$!
  echo "$ENFANT" > runtime/v17_demo.pid
  wait "$ENFANT"
  code=$?
  [ -f "$STOP" ] && break
  duree=$(( $(date +%s) - debut ))
  [ "$duree" -ge 600 ] && attente=10
  echo "$(date '+%F %T') | superviseur | moteur arrêté (code $code) : relance dans ${attente} s" >> "$LOG"
  for _ in $(seq "$attente"); do [ -f "$STOP" ] && break; sleep 1; done
  attente=$(( attente * 2 )); [ "$attente" -gt 300 ] && attente=300
done
rm -f runtime/v17_superviseur.pid runtime/v17_demo.pid
echo "$(date '+%F %T') | superviseur | arrêt demandé" >> "$LOG"
