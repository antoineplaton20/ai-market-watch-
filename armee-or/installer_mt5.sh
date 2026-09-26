#!/usr/bin/env bash
# BRANCHEMENT METATRADER 5 (compte DÉMO) — appelé par installer_or.sh, relançable seul : bash installer_mt5.sh
# Ubuntu ne peut pas lancer MT5 directement : Wine (méthode officielle MetaQuotes pour Linux) + écran virtuel (Xvfb)
# + Python Windows avec la bibliothèque officielle MetaTrader5. Tout est installé dans un préfixe Wine DÉDIÉ
# (/home/bots/.wine-armee-or) : rien n'est partagé avec tes autres bots.
set -euo pipefail
DOSSIER=${DOSSIER:-/home/bots/armee-or}
COMPTE=${COMPTE:-bots}
PREFIXE=/home/$COMPTE/.wine-armee-or
CACHE=/home/$COMPTE/.cache/armee-or
PY_VERSION=3.11.9
TERMINAL="$PREFIXE/drive_c/Program Files/MetaTrader 5/terminal64.exe"
PYWIN="$PREFIXE/drive_c/Python311/python.exe"
V='\033[1;32m'; J='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
[ "$(id -u)" -eq 0 ] || { echo "Lance cette commande en root."; exit 1; }
en_bots() { runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all \
  WINEDLLOVERRIDES="mscoree,mshtml=" "$@"; }
ecran() { en_bots xvfb-run -a -s "-screen 0 1280x800x24" "$@"; }

echo "-- Wine et écran virtuel (plusieurs minutes la première fois)"
if ! command -v wine > /dev/null || ! command -v xvfb-run > /dev/null; then
  . /etc/os-release
  dpkg --add-architecture i386
  mkdir -pm755 /etc/apt/keyrings
  curl -fsSL -o /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key
  curl -fsSL -o "/etc/apt/sources.list.d/winehq-$VERSION_CODENAME.sources" \
    "https://dl.winehq.org/wine-builds/ubuntu/dists/$VERSION_CODENAME/winehq-$VERSION_CODENAME.sources"
  apt-get update -qq
  export DEBIAN_FRONTEND=noninteractive
  if ! apt-get install -y -qq --install-recommends winehq-stable xvfb xauth > /dev/null; then
    apt-get install -y -qq libgd3:i386 > /dev/null || true          # dépendance 32 bits parfois à installer d'abord
    apt-get install -y -qq --install-recommends winehq-stable xvfb xauth > /dev/null
  fi
fi
echo "   $(wine --version)"

echo "-- Préfixe Wine dédié : $PREFIXE"
mkdir -p "$CACHE"; chown -R "$COMPTE:$COMPTE" "/home/$COMPTE/.cache"
if [ ! -f "$PREFIXE/system.reg" ]; then
  ecran wineboot -i > /dev/null 2>&1 || true
  en_bots wineserver -w || true
  ecran wine winecfg -v=win10 > /dev/null 2>&1 || true
  en_bots wineserver -w || true
fi

echo "-- Terminal MetaTrader 5 (téléchargé chez MetaQuotes)"
if [ ! -f "$TERMINAL" ]; then
  curl -fsSL -o "$CACHE/mt5setup.exe" https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
  chown "$COMPTE:$COMPTE" "$CACHE/mt5setup.exe"
  ( ecran wine "$CACHE/mt5setup.exe" /auto > /dev/null 2>&1 || true ) &
  for _ in $(seq 1 90); do [ -f "$TERMINAL" ] && break; sleep 5; done
  sleep 20; en_bots wineserver -k || true; wait || true
  [ -f "$TERMINAL" ] || { echo -e "${R}✖ Installation de MT5 échouée (relance : bash $DOSSIER/installer_mt5.sh).${N}"; exit 1; }
fi
echo "   $TERMINAL"

echo "-- Python pour Windows + bibliothèque officielle MetaTrader5"
if [ ! -f "$PYWIN" ]; then
  curl -fsSL -o "$CACHE/python.exe" "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-amd64.exe"
  chown "$COMPTE:$COMPTE" "$CACHE/python.exe"
  ecran wine "$CACHE/python.exe" /quiet InstallAllUsers=0 'TargetDir=C:\Python311' Include_test=0 Include_doc=0 \
    Include_tcltk=0 Include_launcher=0 Shortcuts=0 AssociateFiles=0 PrependPath=0 > /dev/null 2>&1 || true
  en_bots wineserver -w || true
  [ -f "$PYWIN" ] || { echo -e "${R}✖ Installation de Python (Windows) échouée.${N}"; exit 1; }
fi
en_bots wine "$PYWIN" -m pip install -q --disable-pip-version-check --no-warn-script-location --upgrade MetaTrader5
en_bots wine "$PYWIN" -c "import MetaTrader5 as m; print('   MetaTrader5', m.__version__)"

echo "-- Compte MetaTrader 5"
if ! grep -q '^OR_MT5_LOGIN=' "$DOSSIER/.env" 2> /dev/null; then
  echo "Identifiants de ton compte DÉMO MT5 (l'armée refusera tout ordre sur un compte réel)."
  read -r -p "Login (numéro) : " LOGIN
  read -r -s -p "Mot de passe PRINCIPAL (invisible pendant la frappe) : " MDP; echo
  read -r -p "Serveur [MetaQuotes-Demo] : " SERVEUR
  umask 077
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
else
  echo "   compte déjà réglé dans $DOSSIER/.env (or mt5 compte pour le changer)"
fi

echo "-- Service du pont MT5"
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
ExecStopPost=-/usr/bin/wineserver -k
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

echo "-- Connexion au compte (jusqu'à 2 minutes)"
if ecran bash -c "cd '$DOSSIER' && PYTHONIOENCODING=utf-8 timeout 300 wine '$PYWIN' \"\$(winepath -w '$DOSSIER/armee_or/pont_mt5.py')\" --verifier"; then
  echo -e "${V}✔ MT5 connecté.${N}"
else
  echo -e "${J}⚠ Connexion MT5 pas encore établie : le service va réessayer sans fin (or mt5 pour voir l'état).${N}"
fi
en_bots wineserver -k 2> /dev/null || true
systemctl enable armee-or-mt5 > /dev/null 2>&1
systemctl restart armee-or-mt5
