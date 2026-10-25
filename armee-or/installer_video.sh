#!/usr/bin/env bash
# ÉQUIPE VIDÉO — 2e compte DÉMO MetaTrader 5 à fort levier, pour rejouer la méthode des vidéos À CÔTÉ de l'armée.
# Son propre terminal (copie du préfixe Wine de l'armée), son propre pont (127.0.0.1:18778), son propre service
# (armee-or-mt5-video). Le compte de l'armée, ses identifiants et ses positions ne sont jamais touchés.
# Relançable : or video installer · changer de compte : or video compte.
set -Eeuo pipefail
DOSSIER=${DOSSIER:-/home/bots/armee-or}
COMPTE=${COMPTE:-bots}
SOURCE=/home/$COMPTE/.wine-armee-or
PREFIXE=/home/$COMPTE/.wine-armee-or-video
PYWIN="$PREFIXE/drive_c/Python311/python.exe"
JOURNAL="$DOSSIER/runtime/installation_video.log"
V='\033[1;32m'; J='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
[ "$(id -u)" -eq 0 ] || { echo "Lance cette commande en root."; exit 1; }
umask 022
mkdir -p "$DOSSIER/runtime"; chown "$COMPTE:$COMPTE" "$DOSSIER/runtime"
en_video() { runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all "$@"; }
arreter_wine() { runuser -u "$COMPTE" -- env WINEPREFIX="$PREFIXE" wineserver -k > /dev/null 2>&1 || true; }
telegram() {
  runuser -u "$COMPTE" -- bash -c 'cd "$1" && .venv/bin/python -c "import sys; from armee_or import telegram; telegram.envoyer(sys.argv[1], True)" "$2"' \
    _ "$DOSSIER" "$1" > /dev/null 2>&1 || true
}
ARMEE_ARRETEE=0                     # le pont de l'armée est arrêté pendant la copie : toujours relancé, même en cas d'échec
relancer_armee() { [ "$ARMEE_ARRETEE" = 1 ] && systemctl start armee-or-mt5 2> /dev/null || true; ARMEE_ARRETEE=0; }
ETAPE="préparation"
etape() { ETAPE="$1"; echo -e "${V}-- $1${N}"; echo "=== $(date '+%F %T') $1" >> "$JOURNAL"; }
echec() {
  local code=$?
  trap - ERR
  relancer_armee
  rm -rf "$PREFIXE.copie"
  chown "$COMPTE:$COMPTE" "$JOURNAL" 2> /dev/null || true
  echo -e "${R}✖ Équipe vidéo : installation arrêtée à l'étape « $ETAPE » (code $code).${N}"
  tail -n 8 "$JOURNAL" | sed 's/^/   /'
  telegram "✖ Équipe vidéo : installation arrêtée à l'étape « $ETAPE » (code $code). Fin du journal : $(tail -n 6 "$JOURNAL" | tr '\n' ' ' | cut -c1-600) — Relance : « or video installer »."
  exit "$code"
}
trap echec ERR
: > "$JOURNAL"

etape "2e compte DÉMO (équipe vidéo)"
if ! grep -q '^OR_VIDEO_LOGIN=' "$DOSSIER/.env" 2> /dev/null; then
  cat <<TEXTE
Il faut un 2e compte DÉMO à fort levier, avec un petit solde (2 à 10 \$), comme dans les vidéos :
  - app MetaTrader 5 de l'iPhone > Réglages > Nouveau compte > ton courtier (les vidéos utilisent XAUUSDm,
    le nom de l'or chez Exness) > compte DÉMO > levier le plus haut, plus petit dépôt ;
  - ou l'espace client du courtier (comptes démo : levier et solde réglables).
  Le nom exact du serveur se lit dans l'app : Réglages > touche le compte (ex. Exness-MT5Trial7).
JAMAIS de compte réel : l'équipe vidéo refuse d'y passer le moindre ordre.
TEXTE
  LOGIN=""
  while ! [[ "$LOGIN" =~ ^[0-9]+$ ]]; do
    read -r -s -p "Login du compte démo vidéo (chiffres, invisible pendant la frappe) : " LOGIN || exit 1; echo
    LOGIN=${LOGIN// /}
    [[ "$LOGIN" =~ ^[0-9]+$ ]] || echo "   ✖ Le login ne contient que des chiffres. Recommence."
  done
  echo "   ✔ login …${LOGIN: -3}"
  MDP=""
  while [ -z "$MDP" ]; do
    read -r -s -p "Mot de passe PRINCIPAL de ce compte (invisible pendant la frappe) : " MDP || exit 1; echo
  done
  SERVEUR=""
  while [ -z "$SERVEUR" ]; do
    read -r -p "Serveur, nom exact (ex. Exness-MT5Trial7) : " SERVEUR || exit 1
    SERVEUR=$(echo "$SERVEUR" | sed 's/^ *//;s/ *$//')
  done
  sed -i '/^# Équipe vidéo/d;/^OR_VIDEO_/d' "$DOSSIER/.env" 2> /dev/null || true
  touch "$DOSSIER/.env"; chmod 600 "$DOSSIER/.env"
  cat >> "$DOSSIER/.env" <<ENV
# Équipe vidéo — 2e compte DÉMO MT5 (méthode des vidéos), jamais celui de l'armée
OR_VIDEO_ACTIF=1
OR_VIDEO_LOGIN=$LOGIN
OR_VIDEO_MOT_DE_PASSE=$MDP
OR_VIDEO_SERVEUR=$SERVEUR
OR_VIDEO_SYMBOLE=XAUUSD
OR_VIDEO_TERMINAL=C:\\Program Files\\MetaTrader 5\\terminal64.exe
OR_VIDEO_PORT=18778
ENV
  chown "$COMPTE:$COMPTE" "$DOSSIER/.env"; chmod 600 "$DOSSIER/.env"
  echo "   ✔ identifiants enregistrés (compte …${LOGIN: -3}, serveur $SERVEUR)"
else
  echo "   compte déjà réglé (or video compte pour le changer)"
fi

etape "Terminal de l'équipe vidéo (copie de celui de l'armée, 2 à 5 minutes)"
[ -f "$SOURCE/system.reg" ] && [ -f "$SOURCE/drive_c/Python311/python.exe" ] \
  || { echo "MT5 de l'armée absent : installe-le d'abord (or mt5 installer)" | tee -a "$JOURNAL"; false; }
if [ ! -f "$PREFIXE/system.reg" ]; then
  BESOIN=$(( $(du -sm "$SOURCE" | cut -f1) + 1024 ))
  DISPO=$(df -Pm "/home/$COMPTE" | awk 'NR==2 {print $4}')
  [ "$DISPO" -ge "$BESOIN" ] || { echo "Place insuffisante : $DISPO Mo libres, $BESOIN Mo nécessaires" | tee -a "$JOURNAL"; false; }
  if systemctl is-active --quiet armee-or-mt5; then
    echo "   pont MT5 de l'armée arrêté le temps de la copie (ses positions gardent leurs stops chez le courtier)"
    ARMEE_ARRETEE=1; systemctl stop armee-or-mt5
  fi
  rm -rf "$PREFIXE.copie"
  cp -a "$SOURCE" "$PREFIXE.copie"
  relancer_armee
  # rien du compte de l'armée dans la copie : comptes mémorisés, journaux, historique téléchargé
  find "$PREFIXE.copie/drive_c" -ipath '*MetaTrader 5*' \( -iname accounts.dat -o -iname '*.log' \) -delete 2> /dev/null || true
  find "$PREFIXE.copie/drive_c" -maxdepth 4 -type d -ipath '*MetaTrader 5/Bases' -exec rm -rf {} + 2> /dev/null || true
  mv "$PREFIXE.copie" "$PREFIXE"
  chown -R "$COMPTE:$COMPTE" "$PREFIXE"
fi
TERMINAL=$(find "$PREFIXE/drive_c" -iname terminal64.exe -path '*MetaTrader 5*' 2> /dev/null | head -n 1)
[ -n "$TERMINAL" ] || { echo "terminal64.exe absent de la copie" >> "$JOURNAL"; false; }
TERMINAL_WIN=$(en_video winepath -w "$TERMINAL" 2> /dev/null | tr -d '\r')
[ -n "$TERMINAL_WIN" ] && sed -i "s#^OR_VIDEO_TERMINAL=.*#OR_VIDEO_TERMINAL=${TERMINAL_WIN//\\/\\\\}#" "$DOSSIER/.env"
arreter_wine
echo "   $PREFIXE"

etape "Service du pont de l'équipe vidéo"
cat > "$DOSSIER/pont_mt5_video.sh" <<LANCEUR
#!/usr/bin/env bash
# Lancé par le service armee-or-mt5-video : écran virtuel + Python Windows + pont du 2e compte (port 18778).
cd "$DOSSIER"
export PYTHONIOENCODING=utf-8
# Boucle d'appoint (toutes les 5 s) : Ctrl+E (bouton « Algo Trading ») quand le pont le demande, photo de l'écran.
exec xvfb-run -a -s "-screen 0 1280x800x24" bash -c '
  ( i=0
    while sleep 5; do
      i=\$((i + 1))
      if [ -f "$DOSSIER/runtime/activer_algo_video" ]; then
        rm -f "$DOSSIER/runtime/activer_algo_video"
        w=\$(xdotool search --onlyvisible --name "MetaTrader|MetaQuotes|^[0-9]+ " 2> /dev/null | head -n 1)
        if [ -n "\$w" ]; then
          xdotool windowfocus --sync "\$w" key Escape 2> /dev/null; sleep 1
          xdotool windowfocus --sync "\$w" key ctrl+e 2> /dev/null && echo "Ctrl+E envoyé au terminal vidéo"
        fi
      fi
      if [ \$((i % 12)) -eq 0 ]; then
        import -window root "png:$DOSSIER/runtime/ecran_video.tmp" 2> /dev/null \\
          && mv "$DOSSIER/runtime/ecran_video.tmp" "$DOSSIER/runtime/ecran_video.png"
      fi
    done ) &
  exec wine "$PYWIN" "\$(winepath -w "$DOSSIER/armee_or/pont_mt5.py")" --instance video'
LANCEUR
chmod 755 "$DOSSIER/pont_mt5_video.sh"; chown "$COMPTE:$COMPTE" "$DOSSIER/pont_mt5_video.sh"
cat > /etc/systemd/system/armee-or-mt5-video.service <<UNITE
[Unit]
Description=Armée de l'or : pont MetaTrader 5 de l'équipe vidéo (2e compte démo)
After=network-online.target armee-or-mt5.service
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
User=$COMPTE
WorkingDirectory=$DOSSIER
Environment=HOME=/home/$COMPTE WINEPREFIX=$PREFIXE WINEDEBUG=-all
ExecStart=$DOSSIER/pont_mt5_video.sh
ExecStopPost=-/usr/bin/env WINEPREFIX=$PREFIXE wineserver -k
Restart=always
RestartSec=30
KillMode=control-group
TimeoutStopSec=30
Nice=5
CPUQuota=60%
MemoryMax=1200M

[Install]
WantedBy=multi-user.target
UNITE
systemctl daemon-reload
systemctl stop armee-or-mt5-video 2> /dev/null || true

etape "Connexion au 2e compte (5 minutes au plus)"
trap - ERR
VERIF="$DOSSIER/runtime/verification_video.txt"
: > "$VERIF"; chown "$COMPTE:$COMPTE" "$VERIF"
timeout -k 15 "${DELAI_VERIF:-330}" runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all \
  xvfb-run -a -s "-screen 0 1280x800x24" bash -c "cd '$DOSSIER' && PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 wine '$PYWIN' \"\$(winepath -w '$DOSSIER/armee_or/pont_mt5.py')\" --instance video --verifier > '$VERIF' 2>&1" \
  < /dev/null > /dev/null 2>&1 || true
arreter_wine
cat "$VERIF" >> "$JOURNAL"
grep -E '"(connecte|server|balance|currency|leverage|demo|erreur|name)"' "$VERIF" | sed 's/^/   /' || true
CONNECTE=$(grep -c '"connecte": true' "$VERIF" || true)
DEMO=$(grep -c '"demo": true' "$VERIF" || true)
systemctl enable armee-or-mt5-video > /dev/null 2>&1
systemctl restart armee-or-mt5-video
systemctl is-enabled --quiet armee-or-chef 2> /dev/null && systemctl restart armee-or-chef   # le chef lit OR_VIDEO_*
chown "$COMPTE:$COMPTE" "$JOURNAL" 2> /dev/null || true
if [ "${CONNECTE:-0}" -gt 0 ] && [ "${DEMO:-0}" -gt 0 ]; then
  echo -e "${V}✔ Équipe vidéo branchée sur le 2e compte démo. Elle joue sa première loterie dans la minute.${N}"
  telegram "✔ Équipe vidéo branchée sur ton 2e compte DÉMO. Touche /or_video pour suivre ses paniers et ses loteries."
elif [ "${CONNECTE:-0}" -gt 0 ]; then
  echo -e "${R}⛔ Ce compte n'est PAS un compte démo : l'équipe vidéo ne passera aucun ordre. « or video compte » pour en régler un autre.${N}"
  telegram "⛔ Le 2e compte n'est pas un compte démo : l'équipe vidéo ne passera aucun ordre. « or video compte » pour régler un compte démo."
else
  echo -e "${J}⚠ Terminal vidéo installé mais pas encore connecté : le service réessaie sans fin. /or_video dans 5 minutes.${N}"
  telegram "⚠ Équipe vidéo installée, connexion au 2e compte pas encore établie (le service réessaie seul). Si /or_video dit toujours « non connecté » dans 10 minutes : login, mot de passe PRINCIPAL et nom exact du serveur à revérifier (or video compte)."
fi
