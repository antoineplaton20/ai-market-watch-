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
# Mono (.NET) et Gecko (HTML) sont installés dans le préfixe : l'installateur MT5 en a besoin (comme dans le
# script officiel MetaQuotes). Ils ne sont désactivés QUE pendant la création du préfixe, pour éviter une fenêtre
# de téléchargement que personne ne pourrait valider.
en_bots() { runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all "$@"; }
sans_composants() { runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all \
  WINEDLLOVERRIDES="mscoree,mshtml=" "$@"; }
ecran() { en_bots xvfb-run -a -s "-screen 0 1280x800x24" "$@"; }
# Wine Staging garde des services Windows en vie : « wineserver -w » peut attendre sans fin -> toujours borné.
attendre_wine() { timeout 20 runuser -u "$COMPTE" -- env WINEPREFIX="$PREFIXE" wineserver -w > /dev/null 2>&1 || true; }
arreter_wine() { runuser -u "$COMPTE" -- env WINEPREFIX="$PREFIXE" wineserver -k > /dev/null 2>&1 || true; }
photo() {
  [ -s "$1" ] || return 0
  runuser -u "$COMPTE" -- bash -c 'cd "$1" && .venv/bin/python -c "import sys; from armee_or import telegram; telegram.envoyer_photo(sys.argv[1], sys.argv[2])" "$2" "$3"' \
    _ "$DOSSIER" "$1" "$2" > /dev/null 2>&1 || true
}
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
  photo "$DOSSIER/runtime/ecran_mt5.png" "Écran virtuel de MT5 au moment de l'arrêt (étape « $ETAPE »)"
  telegram "✖ Installation MT5 arrêtée à l'étape « $ETAPE » (code $code). Fin du journal : $(tail -n 6 "$JOURNAL" | tr '\n' ' ' | cut -c1-700) — Relance : « or mt5 installer » dans Termius."
  exit "$code"
}
trap echec ERR
: > "$JOURNAL"

etape "Compte MetaTrader 5"
if ! grep -q '^OR_MT5_LOGIN=' "$DOSSIER/.env" 2> /dev/null; then
  echo "Identifiants de ton compte DÉMO MT5 (l'armée refusera tout ordre sur un compte réel)."
  LOGIN=""
  # saisie masquée : si login et mot de passe sont collés ensemble par erreur, rien ne s'affiche à l'écran
  while ! [[ "$LOGIN" =~ ^[0-9]+$ ]]; do
    read -r -s -p "Login (numéro seul, ex. 5056…, invisible pendant la frappe) : " LOGIN || exit 1; echo
    LOGIN=${LOGIN// /}
    [[ "$LOGIN" =~ ^[0-9]+$ ]] || echo "   ✖ Le login ne contient que des chiffres (pas le mot de passe). Recommence."
  done
  echo "   ✔ login …${LOGIN: -3}"
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

etape "Wine Staging et écran virtuel (5 à 10 minutes la première fois)"
# L'édition « staging » de Wine est celle du script officiel MetaQuotes : avec l'édition « stable »,
# l'installateur MT5 s'arrête sur « A debugger has been found running in your system » (vérifié).
if ! wine --version 2> /dev/null | grep -qi staging; then
  . /etc/os-release
  export DEBIAN_FRONTEND=noninteractive
  dpkg --add-architecture i386
  mkdir -pm755 /etc/apt/keyrings
  curl -fsSL --retry 3 -o /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key >> "$JOURNAL" 2>&1
  curl -fsSL --retry 3 -o "/etc/apt/sources.list.d/winehq-$VERSION_CODENAME.sources" \
    "https://dl.winehq.org/wine-builds/ubuntu/dists/$VERSION_CODENAME/winehq-$VERSION_CODENAME.sources" >> "$JOURNAL" 2>&1
  chmod 644 /etc/apt/keyrings/winehq-archive.key "/etc/apt/sources.list.d/winehq-$VERSION_CODENAME.sources"
  apt-get update -qq >> "$JOURNAL" 2>&1
  if ! apt-get install -y -q --install-recommends winehq-staging >> "$JOURNAL" 2>&1; then
    echo "   premier essai refusé, correction des dépendances 32 bits…"
    apt-get install -y -q libgd3:i386 >> "$JOURNAL" 2>&1 || true
    apt-get install -y -q --install-recommends winehq-staging >> "$JOURNAL" 2>&1
  fi
  hash -r
fi
DEBIAN_FRONTEND=noninteractive apt-get install -y -q xvfb xauth imagemagick xdotool >> "$JOURNAL" 2>&1 || true
wine --version | grep -qi staging || { echo "Wine Staging absent : $(wine --version 2>&1)" >> "$JOURNAL"; false; }
echo "   $(wine --version)"

etape "Préfixe Wine dédié"
mkdir -p "$CACHE"; chown -R "$COMPTE:$COMPTE" "/home/$COMPTE/.cache"
if [ ! -f "$PREFIXE/system.reg" ]; then
  sans_composants xvfb-run -a wineboot -i >> "$JOURNAL" 2>&1 || true
  attendre_wine
  sans_composants xvfb-run -a wine winecfg -v=win10 >> "$JOURNAL" 2>&1 || true
  attendre_wine
fi
[ -f "$PREFIXE/system.reg" ]
if [ "$(cat "$PREFIXE/.armee-or-wine" 2> /dev/null)" != "$(wine --version)" ]; then     # préfixe créé par un autre Wine
  timeout 300 runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all \
    WINEDLLOVERRIDES="mscoree,mshtml=" xvfb-run -a wineboot -u >> "$JOURNAL" 2>&1 || true
  attendre_wine; arreter_wine
  wine --version > "$PREFIXE/.armee-or-wine"; chown "$COMPTE:$COMPTE" "$PREFIXE/.armee-or-wine"
fi
echo "   $PREFIXE"

etape "Composants Windows (Mono et Gecko, 2 à 5 minutes)"
# versions exactes attendues par CE Wine (lues dans sa propre bibliothèque appwiz.cpl)
read -r MONO GECKO < <(python3 - "$(dirname "$(readlink -f "$(command -v wine)")")/.." <<'PY'
import glob, re, sys
texte = ""
for f in glob.glob(sys.argv[1] + "/**/x86_64-windows/appwiz.cpl", recursive=True) + glob.glob(sys.argv[1] + "/**/appwiz.cpl*", recursive=True):
    b = open(f, "rb").read()
    texte += b.decode("utf-16-le", "ignore") + b.decode("latin-1")
mono = re.search(r"wine-mono-([0-9.]+[0-9])-x86\.msi", texte)
gecko = re.search(r"wine-gecko-([0-9.]+[0-9])-x86", texte)
print(mono.group(1) if mono else "11.3.0", gecko.group(1) if gecko else "2.47.4")
PY
)
echo "   Mono $MONO, Gecko $GECKO"
if [ "$(cat "$PREFIXE/.armee-or-composants" 2> /dev/null)" != "$MONO $GECKO" ]; then
  for f in "wine-mono/$MONO/wine-mono-$MONO-x86.msi" "wine-gecko/$GECKO/wine-gecko-$GECKO-x86.msi" \
           "wine-gecko/$GECKO/wine-gecko-$GECKO-x86_64.msi"; do
    [ -s "$CACHE/$(basename "$f")" ] || curl -fsSL --retry 3 -o "$CACHE/$(basename "$f")" "https://dl.winehq.org/wine/$f" >> "$JOURNAL" 2>&1
    chown "$COMPTE:$COMPTE" "$CACHE/$(basename "$f")"
    timeout 900 runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all WINEDLLOVERRIDES=mscoree=d \
      xvfb-run -a wine msiexec /i "$CACHE/$(basename "$f")" /qn >> "$JOURNAL" 2>&1 || true
  done
  attendre_wine; arreter_wine
  echo "$MONO $GECKO" > "$PREFIXE/.armee-or-composants"; chown "$COMPTE:$COMPTE" "$PREFIXE/.armee-or-composants"
fi
[ -d "$PREFIXE/drive_c/windows/mono" ] && [ -d "$PREFIXE/drive_c/windows/system32/gecko" ] \
  || { echo "Mono ou Gecko absent après installation" >> "$JOURNAL"; false; }
echo "   ✔ Mono et Gecko installés"

trouver_terminal() { find "$PREFIXE/drive_c" -iname terminal64.exe -path '*MetaTrader 5*' 2> /dev/null | head -n 1; }
ecran_libre() { for n in $(seq 90 99); do [ -e "/tmp/.X11-unix/X$n" ] || [ -e "/tmp/.X$n-lock" ] || { echo "$n"; return; }; done; echo 89; }
capture() { runuser -u "$COMPTE" -- env DISPLAY=":$AFFICHAGE" import -window root "$DOSSIER/runtime/ecran_mt5.png" > /dev/null 2>&1 || true; }
etape "Terminal MetaTrader 5 (1 à 20 minutes)"
TERMINAL=$(trouver_terminal)
if [ -z "$TERMINAL" ]; then
  rm -f "$DOSSIER/runtime/ecran_mt5.png"
  curl -fsSL --retry 3 -o "$CACHE/mt5setup.exe" https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe >> "$JOURNAL" 2>&1
  chown "$COMPTE:$COMPTE" "$CACHE/mt5setup.exe"
  AFFICHAGE=$(ecran_libre)
  runuser -u "$COMPTE" -- Xvfb ":$AFFICHAGE" -screen 0 1280x800x24 -nolisten tcp > /dev/null 2>&1 &
  XVFB=$!
  sleep 3
  x() { runuser -u "$COMPTE" -- env DISPLAY=":$AFFICHAGE" "$@"; }
  # installateur officiel en mode normal (comme le script MetaQuotes) : on valide la licence d'un « Entrée »
  runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all DISPLAY=":$AFFICHAGE" \
    wine "$CACHE/mt5setup.exe" >> "$JOURNAL" 2>&1 &
  CLICS=0; DERNIER_CLIC=0
  for i in $(seq 1 "${DELAI_TERMINAL:-240}"); do
    TERMINAL=$(trouver_terminal); [ -n "$TERMINAL" ] && break
    FENETRE=$(x xdotool search --onlyvisible --name "MetaTrader 5 Setup" 2> /dev/null | head -n 1 || true)
    # « Suivant » tant que l'installation n'a pas commencé (dossier MetaTrader 5 absent), au plus toutes les 30 s
    if [ -n "$FENETRE" ] && [ ! -d "$PREFIXE/drive_c/Program Files/MetaTrader 5" ] && [ $((i - DERNIER_CLIC)) -ge 6 ] \
       && [ "$CLICS" -lt 5 ]; then
      sleep 2; x xdotool windowfocus --sync "$FENETRE" > /dev/null 2>&1 || true; x xdotool key Return > /dev/null 2>&1 || true
      CLICS=$((CLICS + 1)); DERNIER_CLIC=$i
      echo "   licence acceptée (Entrée n°$CLICS), téléchargement du terminal…"
    fi
    if [ $((i % 12)) -eq 0 ]; then
      echo "   … installation du terminal en cours ($((i * 5 / 60)) min)"
      capture
    fi
    sleep 5
  done
  capture                                             # photo AVANT tout arrêt (sinon l'écran est noir)
  [ -n "$TERMINAL" ] && sleep 20                      # laisser l'installateur finir d'écrire ses fichiers
  arreter_wine
  kill "$XVFB" 2> /dev/null || true; wait 2> /dev/null || true
  [ -n "$TERMINAL" ] || { echo "terminal64.exe introuvable (installateur toujours ouvert après le délai)" >> "$JOURNAL"; false; }
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
  attendre_wine
  [ -f "$PYWIN" ] || { echo "python.exe absent après installation" >> "$JOURNAL"; false; }
fi
en_bots wine "$PYWIN" -m pip install -q --disable-pip-version-check --no-warn-script-location --upgrade MetaTrader5 >> "$JOURNAL" 2>&1 \
  || echo "   (mise à jour de MetaTrader5 impossible, version déjà présente utilisée)"
en_bots wine "$PYWIN" -c "import MetaTrader5 as m; print('   MetaTrader5', m.__version__)" 2>> "$JOURNAL"

etape "Service du pont MT5"
cat > "$DOSSIER/pont_mt5.sh" <<LANCEUR
#!/usr/bin/env bash
# Lancé par le service armee-or-mt5 : écran virtuel + Python Windows + pont (qui démarre le terminal MT5).
cd "$DOSSIER"
export PYTHONIOENCODING=utf-8
# Boucle d'appoint côté Linux (toutes les 5 s) :
#  - si le pont demande l'activation du trading algorithmique (runtime/activer_algo), appui sur Ctrl+E dans le
#    terminal MT5 (raccourci officiel du bouton « Algo Trading », éteint par défaut après installation) ;
#  - photo de l'écran virtuel chaque minute (commande Telegram /or_mt5_ecran).
exec xvfb-run -a -s "-screen 0 1280x800x24" bash -c '
  ( i=0
    while sleep 5; do
      i=\$((i + 1))
      if [ -f "$DOSSIER/runtime/activer_algo" ]; then
        rm -f "$DOSSIER/runtime/activer_algo"
        w=\$(xdotool search --onlyvisible --name "MetaTrader|MetaQuotes|^[0-9]+ " 2> /dev/null | head -n 1)
        if [ -n "\$w" ]; then                          # Échap : ferme une éventuelle fenêtre ouverte par-dessus
          xdotool windowfocus --sync "\$w" key Escape 2> /dev/null; sleep 1
          xdotool windowfocus --sync "\$w" key ctrl+e 2> /dev/null && echo "Ctrl+E envoyé au terminal"
        fi
      fi
      if [ \$((i % 12)) -eq 0 ]; then
        import -window root "png:$DOSSIER/runtime/ecran_pont.tmp" 2> /dev/null \\
          && mv "$DOSSIER/runtime/ecran_pont.tmp" "$DOSSIER/runtime/ecran_pont.png"
      fi
    done ) &
  exec wine "$PYWIN" "\$(winepath -w "$DOSSIER/armee_or/pont_mt5.py")"'
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
Environment=HOME=/home/$COMPTE WINEPREFIX=$PREFIXE WINEDEBUG=-all
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

etape "Connexion au compte (5 minutes au plus)"
trap - ERR
if [ "${VERIFIER_CONNEXION:-1}" = 1 ]; then
  # Sortie dans un FICHIER (jamais un tube) : le terminal MT5 lancé par la vérification garde ses sorties
  # ouvertes, un tube ne se fermerait jamais. Durée bornée pour tout le groupe (délai + arrêt forcé).
  VERIF="$DOSSIER/runtime/verification_mt5.txt"
  : > "$VERIF"; chown "$COMPTE:$COMPTE" "$VERIF"
  timeout -k 15 "${DELAI_VERIF:-330}" runuser -u "$COMPTE" -- env HOME=/home/$COMPTE WINEPREFIX="$PREFIXE" WINEDEBUG=-all \
    xvfb-run -a -s "-screen 0 1280x800x24" bash -c "cd '$DOSSIER' && PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 wine '$PYWIN' \"\$(winepath -w '$DOSSIER/armee_or/pont_mt5.py')\" --verifier > '$VERIF' 2>&1" \
    < /dev/null > /dev/null 2>&1 || true
  arreter_wine
  cat "$VERIF" >> "$JOURNAL"
  grep -E '"(connecte|balance|currency|erreur|leverage|bid|ask)"' "$VERIF" | sed 's/^/   /' || true
  CONNECTE=$(grep -c '"connecte": true' "$VERIF" || true)
else
  CONNECTE=0; echo "   (vérification de la connexion sautée)"
fi
arreter_wine
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
