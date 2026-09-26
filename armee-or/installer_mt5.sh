#!/usr/bin/env bash
# BRANCHEMENT METATRADER 5 (compte DÉMO) — appelé par installer_or.sh, relançable seul : or mt5 installer
# Ubuntu ne peut pas lancer MT5 directement : Wine (méthode officielle MetaQuotes pour Linux) + écran virtuel (Xvfb)
# + Python Windows avec la bibliothèque officielle MetaTrader5. Tout est installé dans un préfixe Wine DÉDIÉ
# (/home/bots/.wine-armee-or) : rien n'est partagé avec tes autres bots.
# Identifiants demandés EN PREMIER ; chaque étape est journalisée et le résultat (réussite ou étape en échec)
# est envoyé sur Telegram : tout se diagnostique depuis le téléphone.
set -Eeuo pipefail
DOSSIER=${DOSSIER:-/home/bots/armee-or}
COMPTE=${COMPTE:-bots}
PREFIXE=/home/$COMPTE/.wine-armee-or
CACHE=/home/$COMPTE/.cache/armee-or
PY_VERSION=3.11.9
PYWIN="$PREFIXE/drive_c/Python311/python.exe"
JOURNAL="$DOSSIER/runtime/installation_mt5.log"
ETAT="$DOSSIER/runtime/installation_mt5.txt"
V='\033[1;32m'; J='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
[ "$(id -u)" -eq 0 ] || { echo "Lance cette commande en root."; exit 1; }
umask 022                       # jamais hériter d'un umask restrictif : apt doit pouvoir lire la clé de WineHQ
mkdir -p "$DOSSIER/runtime"; chown "$COMPTE:$COMPTE" "$DOSSIER/runtime"
en_bots() { runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all \
  WINEDLLOVERRIDES="mscoree,mshtml=" "$@"; }
ecran() { en_bots xvfb-run -a -s "-screen 0 1280x800x24" "$@"; }
telegram() {
  runuser -u "$COMPTE" -- bash -c 'cd "$1" && .venv/bin/python -c "import sys; from armee_or import telegram; telegram.envoyer(sys.argv[1], True)" "$2"' \
    _ "$DOSSIER" "$1" > /dev/null 2>&1 || true
}
ETAPE="préparation"
etape() { ETAPE="$1"; echo -e "${V}-- $1${N}"; echo "=== $(date '+%F %T') $1" >> "$JOURNAL"; echo "en cours|$1" > "$ETAT"; }
echec() {
  local code=$?
  trap - ERR
  echo "échec|$ETAPE" > "$ETAT"; chown "$COMPTE:$COMPTE" "$ETAT" "$JOURNAL" 2> /dev/null || true
  echo -e "${R}✖ Installation MT5 arrêtée à l'étape « $ETAPE » (code $code).${N}"
  echo "   Dernières lignes du journal :"; tail -n 8 "$JOURNAL" | sed 's/^/   /'
  telegram "✖ Installation MT5 arrêtée à l'étape « $ETAPE » (code $code). Fin du journal : $(tail -n 6 "$JOURNAL" | tr '\n' ' ' | cut -c1-700) — Relance : « or mt5 installer » dans Termius."
  exit "$code"
}
trap echec ERR
: > "$JOURNAL"

etape "Compte MetaTrader 5"
if ! grep -q '^OR_MT5_LOGIN=' "$DOSSIER/.env" 2> /dev/null; then
  echo "Identifiants de ton compte DÉMO MT5 (l'armée refusera tout ordre sur un compte réel)."
  LOGIN=""
  while ! [[ "$LOGIN" =~ ^[0-9]+$ ]]; do
    read -r -p "Login (numéro, ex. 5056…) : " LOGIN || exit 1; LOGIN=${LOGIN// /}
  done
  MDP=""
  while [ -z "$MDP" ]; do
    read -r -s -p "Mot de passe PRINCIPAL (invisible pendant la frappe, collage possible) : " MDP || exit 1; echo
  done
  read -r -p "Serveur [MetaQuotes-Demo] : " SERVEUR || SERVEUR=""
  SERVEUR=${SERVEUR// /}
  sed -i '/^# MetaTrader 5/d;/^OR_MT5_/d' "$DOSSIER/.env" 2> /dev/null || true
  touch "$DOSSIER/.env"; chmod 600 "$DOSSIER/.env"
  cat >> "$DOSSIER/.env" <<ENV
# MetaTrader 5 (démo) — ordres automatiques de l'armée
OR_MT5_ACTIF=1
OR_MT5_LOGIN=$LOGIN
OR_MT5_MOT_DE_PASSE=$MDP
OR_MT5_SERVEUR=${SERVEUR:-MetaQuotes-Demo}
OR_MT5_SYMBOLE=XAUUSD
OR_MT5_TERMINAL=C:\\Program Files\\MetaTrader 5\\terminal64.exe
OR_MT5_PROFIL=pro 1 % risqué
OR_MT5_ENTRAINEMENT=1
OR_MT5_PORT=18777
ENV
  chown "$COMPTE:$COMPTE" "$DOSSIER/.env"; chmod 600 "$DOSSIER/.env"
  echo "   ✔ identifiants enregistrés (compte …${LOGIN: -3})"
else
  echo "   compte déjà réglé (or mt5 compte pour le changer)"
fi

etape "Wine et écran virtuel (5 à 10 minutes la première fois)"
if ! command -v wine > /dev/null || ! command -v xvfb-run > /dev/null; then
  . /etc/os-release
  export DEBIAN_FRONTEND=noninteractive
  dpkg --add-architecture i386
  mkdir -pm755 /etc/apt/keyrings
  curl -fsSL --retry 3 -o /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key >> "$JOURNAL" 2>&1
  curl -fsSL --retry 3 -o "/etc/apt/sources.list.d/winehq-$VERSION_CODENAME.sources" \
    "https://dl.winehq.org/wine-builds/ubuntu/dists/$VERSION_CODENAME/winehq-$VERSION_CODENAME.sources" >> "$JOURNAL" 2>&1
  chmod 644 /etc/apt/keyrings/winehq-archive.key "/etc/apt/sources.list.d/winehq-$VERSION_CODENAME.sources"
  apt-get update -qq >> "$JOURNAL" 2>&1
  if ! apt-get install -y -q --install-recommends winehq-stable xvfb xauth >> "$JOURNAL" 2>&1; then
    echo "   premier essai refusé, correction des dépendances 32 bits…"
    apt-get install -y -q libgd3:i386 >> "$JOURNAL" 2>&1 || true
    if ! apt-get install -y -q --install-recommends winehq-stable xvfb xauth >> "$JOURNAL" 2>&1; then
      echo "   WineHQ indisponible : Wine d'Ubuntu à la place…"
      apt-get install -y -q wine wine64 xvfb xauth >> "$JOURNAL" 2>&1
    fi
  fi
fi
echo "   $(wine --version)"

etape "Préfixe Wine dédié"
mkdir -p "$CACHE"; chown -R "$COMPTE:$COMPTE" "/home/$COMPTE/.cache"
if [ ! -f "$PREFIXE/system.reg" ]; then
  ecran wineboot -i >> "$JOURNAL" 2>&1 || true
  en_bots wineserver -w || true
  ecran wine winecfg -v=win10 >> "$JOURNAL" 2>&1 || true
  en_bots wineserver -w || true
fi
[ -f "$PREFIXE/system.reg" ]
echo "   $PREFIXE"

trouver_terminal() { find "$PREFIXE/drive_c" -iname terminal64.exe -path '*MetaTrader 5*' 2> /dev/null | head -n 1; }
etape "Terminal MetaTrader 5 (téléchargé chez MetaQuotes, jusqu'à 15 minutes)"
TERMINAL=$(trouver_terminal)
if [ -z "$TERMINAL" ]; then
  if [ ! -f "$CACHE/webview2.exe" ]; then        # composant Microsoft utilisé par les versions récentes de MT5
    curl -fsSL --retry 3 -o "$CACHE/webview2.exe" "https://go.microsoft.com/fwlink/p/?LinkId=2124703" >> "$JOURNAL" 2>&1 || true
    chown "$COMPTE:$COMPTE" "$CACHE/webview2.exe" 2> /dev/null || true
    if [ -f "$CACHE/webview2.exe" ]; then
      timeout 600 runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all \
        xvfb-run -a wine "$CACHE/webview2.exe" /silent /install >> "$JOURNAL" 2>&1 || true
      en_bots wineserver -k || true
    fi
  fi
  curl -fsSL --retry 3 -o "$CACHE/mt5setup.exe" https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe >> "$JOURNAL" 2>&1
  chown "$COMPTE:$COMPTE" "$CACHE/mt5setup.exe"
  ( ecran wine "$CACHE/mt5setup.exe" /auto >> "$JOURNAL" 2>&1 || true ) &
  for i in $(seq 1 180); do
    TERMINAL=$(trouver_terminal); [ -n "$TERMINAL" ] && break
    [ $((i % 12)) -eq 0 ] && echo "   … téléchargement du terminal en cours ($((i * 5 / 60)) min)"
    sleep 5
  done
  sleep 30; en_bots wineserver -k || true; wait || true
  TERMINAL=$(trouver_terminal)
  [ -n "$TERMINAL" ] || { echo "terminal64.exe introuvable après 15 minutes" >> "$JOURNAL"; false; }
fi
echo "   $TERMINAL"
TERMINAL_WIN=$(en_bots winepath -w "$TERMINAL" 2> /dev/null | tr -d '\r')
[ -n "$TERMINAL_WIN" ] && sed -i "s#^OR_MT5_TERMINAL=.*#OR_MT5_TERMINAL=${TERMINAL_WIN//\\/\\\\}#" "$DOSSIER/.env"

etape "Python pour Windows + bibliothèque officielle MetaTrader5"
if [ ! -f "$PYWIN" ]; then
  curl -fsSL --retry 3 -o "$CACHE/python.exe" "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-amd64.exe" >> "$JOURNAL" 2>&1
  chown "$COMPTE:$COMPTE" "$CACHE/python.exe"
  ecran wine "$CACHE/python.exe" /quiet InstallAllUsers=0 'TargetDir=C:\Python311' Include_test=0 Include_doc=0 \
    Include_tcltk=0 Include_launcher=0 Shortcuts=0 AssociateFiles=0 PrependPath=0 >> "$JOURNAL" 2>&1 || true
  en_bots wineserver -w || true
  [ -f "$PYWIN" ] || { echo "python.exe absent après installation" >> "$JOURNAL"; false; }
fi
en_bots wine "$PYWIN" -m pip install -q --disable-pip-version-check --no-warn-script-location --upgrade MetaTrader5 >> "$JOURNAL" 2>&1
en_bots wine "$PYWIN" -c "import MetaTrader5 as m; print('   MetaTrader5', m.__version__)" 2>> "$JOURNAL"

etape "Service du pont MT5"
cat > "$DOSSIER/pont_mt5.sh" <<LANCEUR
#!/usr/bin/env bash
# Lancé par le service armee-or-mt5 : écran virtuel + Python Windows + pont (qui démarre le terminal MT5).
cd "$DOSSIER"
export PYTHONIOENCODING=utf-8
exec xvfb-run -a -s "-screen 0 1280x800x24" wine "$PYWIN" "\$(winepath -w "$DOSSIER/armee_or/pont_mt5.py")"
LANCEUR
chmod 755 "$DOSSIER/pont_mt5.sh"; chown "$COMPTE:$COMPTE" "$DOSSIER/pont_mt5.sh"
cat > /etc/systemd/system/armee-or-mt5.service <<UNITE
[Unit]
Description=Armée de l'or : pont MetaTrader 5 (démo)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
User=$COMPTE
WorkingDirectory=$DOSSIER
Environment=HOME=/home/$COMPTE WINEPREFIX=$PREFIXE WINEDEBUG=-all WINEDLLOVERRIDES=mscoree,mshtml=
ExecStart=$DOSSIER/pont_mt5.sh
ExecStopPost=-/usr/bin/env WINEPREFIX=$PREFIXE wineserver -k
Restart=always
RestartSec=30
KillMode=control-group
TimeoutStopSec=30
Nice=5
CPUQuota=80%
MemoryMax=1500M

[Install]
WantedBy=multi-user.target
UNITE
systemctl daemon-reload
systemctl stop armee-or-mt5 2> /dev/null || true

etape "Connexion au compte (jusqu'à 3 minutes)"
trap - ERR
ecran bash -c "cd '$DOSSIER' && PYTHONIOENCODING=utf-8 timeout 300 wine '$PYWIN' \"\$(winepath -w '$DOSSIER/armee_or/pont_mt5.py')\" --verifier" 2>> "$JOURNAL" \
  | tee -a "$JOURNAL" | grep -E '"(connecte|balance|currency|erreur|bid|ask)"' | sed 's/^/   /' || true
CONNECTE=$(grep -c '"connecte": true' "$JOURNAL" || true)
en_bots wineserver -k 2> /dev/null || true
systemctl enable armee-or-mt5 > /dev/null 2>&1
systemctl restart armee-or-mt5
for s in armee-or-flux armee-or-chef; do systemctl is-enabled --quiet "$s" 2> /dev/null && systemctl restart "$s"; done
chown "$COMPTE:$COMPTE" "$JOURNAL" "$ETAT" 2> /dev/null || true
if [ "${CONNECTE:-0}" -gt 0 ]; then
  echo "ok|connecté" > "$ETAT"
  echo -e "${V}✔ MT5 connecté. L'armée passera ses ordres sur ton compte démo.${N}"
  telegram "✔ MetaTrader 5 branché : compte démo connecté. Touche /or_mt5 pour voir le compte."
else
  echo "installé|connexion pas encore établie" > "$ETAT"
  echo -e "${J}⚠ MT5 installé mais pas encore connecté : le service réessaie sans fin. Vérifie avec /or_mt5 dans 5 minutes.${N}"
  telegram "⚠ MT5 installé mais la connexion au compte n'est pas encore établie ; le service réessaie seul. Si /or_mt5 dit toujours « non connecté » dans 10 minutes : login, mot de passe PRINCIPAL et serveur à revérifier (or mt5 compte)."
fi
