#!/usr/bin/env bash
# Télécommande de Jarvis sur le serveur (Termius).
#   ./jarvis/jarvis.sh installer   environnement Python + fichier .env
#   ./jarvis/jarvis.sh demarrer    Jarvis Telegram en arrière-plan (relance auto, survit à la fermeture de Termius)
#   ./jarvis/jarvis.sh arreter
#   ./jarvis/jarvis.sh etat        état + dernières lignes du journal
#   ./jarvis/jarvis.sh parler      discuter avec Jarvis dans le terminal
set -euo pipefail
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RACINE="$(dirname "$ICI")"
PY="$ICI/.venv/bin/python"
PID="$ICI/data/jarvis.pid"
STOP="$ICI/data/jarvis.stop"
mkdir -p "$ICI/data"
cd "$RACINE"

vivant() { [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; }

case "${1:-aide}" in
  installer)
    command -v python3 > /dev/null || { echo "Installez python3 (3.10 minimum)."; exit 1; }
    python3 -m venv "$ICI/.venv"
    "$ICI/.venv/bin/pip" install -q --upgrade pip
    "$ICI/.venv/bin/pip" install -q -r "$ICI/requirements.txt"
    command -v ffmpeg > /dev/null || echo "Conseil : « sudo apt install ffmpeg » pour des réponses en vraies notes vocales."
    if [ ! -f "$ICI/.env" ]; then
      cp "$ICI/.env.example" "$ICI/.env"
      chmod 600 "$ICI/.env"
      echo "Remplissez maintenant $ICI/.env (nano $ICI/.env), puis : ./jarvis/jarvis.sh demarrer"
    fi
    echo "Installation terminée."
    ;;
  demarrer)
    [ -x "$PY" ] || { echo "Lancez d'abord : ./jarvis/jarvis.sh installer"; exit 1; }
    if vivant; then echo "Jarvis tourne déjà (PID $(cat "$PID"))."; exit 0; fi
    [ "${2:-}" = "--auto" ] && [ -f "$STOP" ] && exit 0      # arrêté volontairement : pas de relance cron
    rm -f "$STOP"
    # Superviseur : relance Jarvis s'il s'arrête, jusqu'à « arreter »
    setsid nohup bash -c "
      echo \$\$ > '$PID'
      while [ ! -f '$STOP' ]; do
        '$PY' -m jarvis telegram >> '$ICI/data/stdout.log' 2>&1 || true
        [ -f '$STOP' ] || sleep 10
      done" > /dev/null 2>&1 < /dev/null &
    if command -v crontab > /dev/null 2>&1; then
      LIGNE="@reboot sleep 30 && '$ICI/jarvis.sh' demarrer --auto > /dev/null 2>&1"
      { crontab -l 2>/dev/null | grep -vF "$ICI/jarvis.sh' demarrer" || true; echo "$LIGNE"; } | crontab - || true
    fi
    sleep 5
    if vivant; then echo "Jarvis est en ligne sur Telegram. Journal : ./jarvis/jarvis.sh etat"
    else echo "Démarrage échoué, voir $ICI/data/stdout.log"; exit 1; fi
    ;;
  arreter)
    touch "$STOP"
    if vivant; then
      pkill -TERM -g "$(ps -o pgid= "$(cat "$PID")" | tr -d ' ')" 2>/dev/null || kill "$(cat "$PID")"
    fi
    rm -f "$PID"
    echo "Jarvis arrêté."
    ;;
  etat)
    if vivant; then echo "JARVIS EN LIGNE (PID $(cat "$PID"))"; else echo "JARVIS ARRÊTÉ"; fi
    [ -f "$ICI/data/stdout.log" ] && tail -n 20 "$ICI/data/stdout.log" || true
    ;;
  parler)
    [ -x "$PY" ] || { echo "Lancez d'abord : ./jarvis/jarvis.sh installer"; exit 1; }
    exec "$PY" -m jarvis terminal
    ;;
  *)
    sed -n '2,7p' "$0"
    ;;
esac
