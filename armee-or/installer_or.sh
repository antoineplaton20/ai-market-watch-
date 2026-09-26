#!/usr/bin/env bash
# INSTALLATION DE L'ARMÉE DE L'OR — indépendante des autres bots du serveur.
# Usage (en root, depuis Termius) :  bash /root/armee-or/installer_or.sh
# Ne touche à rien dans /home/bots/equipe-bots : dossier, environnement Python, base, services et journal séparés.
set -euo pipefail
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOSSIER=/home/bots/armee-or
COMPTE=bots
V='\033[1;32m'; J='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
etape() { echo -e "\n${V}== $1${N}"; }
[ "$(id -u)" -eq 0 ] || { echo "Lance cette commande en root (c'est le cas par défaut dans Termius)."; exit 1; }
command -v python3 > /dev/null || { apt-get update -qq && apt-get install -y -qq python3 python3-venv; }
python3 -c "import venv" 2> /dev/null || apt-get install -y -qq python3-venv
id -u $COMPTE > /dev/null 2>&1 || useradd --create-home --shell /bin/bash $COMPTE

etape "1/8 Copie du programme dans $DOSSIER"
mkdir -p "$DOSSIER"
if [ "$SOURCE" != "$DOSSIER" ]; then
  # .env, base et journal existants conservés (mise à jour sans perte)
  tar -C "$SOURCE" --exclude=./.env --exclude=./runtime --exclude=./.venv -cf - . | tar -C "$DOSSIER" -xf -
fi
mkdir -p "$DOSSIER/runtime"

etape "2/8 Environnement Python dédié"
[ -x "$DOSSIER/.venv/bin/python" ] || python3 -m venv "$DOSSIER/.venv"
"$DOSSIER/.venv/bin/pip" install -q --upgrade pip
"$DOSSIER/.venv/bin/pip" install -q -r "$DOSSIER/requirements.txt"

etape "3/8 Telegram"
if [ -f "$DOSSIER/.env" ]; then
  echo "Réglages existants conservés ($DOSSIER/.env)."
else
  echo "L'armée de l'or peut avoir SON PROPRE bot Telegram (recommandé : tu pourras lui envoyer /or, /or_levier...)."
  echo "  Pour le créer : Telegram > cherche @BotFather > /newbot > choisis un nom > copie le jeton donné."
  read -r -p "Colle le jeton du nouveau bot (ou Entrée pour réutiliser ton bot actuel, en envoi seul) : " JETON
  CHAT=""; CMD=0
  if [ -n "$JETON" ]; then
    echo "Envoie maintenant un message (par exemple « bonjour ») à ton NOUVEAU bot dans Telegram. J'attends 2 minutes..."
    CHAT=$("$DOSSIER/.venv/bin/python" - "$JETON" <<'PY'
import sys, time, requests
jeton = sys.argv[1]
for _ in range(40):
    try:
        r = requests.get(f"https://api.telegram.org/bot{jeton}/getUpdates", timeout=10).json()
        for u in r.get("result", []):
            chat = (u.get("message") or {}).get("chat", {}).get("id")
            if chat:
                print(chat); sys.exit(0)
    except Exception:
        pass
    time.sleep(3)
PY
) || true
    if [ -n "$CHAT" ]; then CMD=1; echo -e "${V}✔ Conversation trouvée.${N}"; else echo -e "${J}Aucun message reçu : l'armée fonctionnera sans Telegram (or config pour recommencer).${N}"; JETON=""; fi
  elif [ -f /home/bots/equipe-bots/.env ]; then
    JETON=$(grep -E '^TELEGRAM_BOT_TOKEN=' /home/bots/equipe-bots/.env | tail -n 1 | cut -d= -f2-)
    CHAT=$(grep -E '^TELEGRAM_CHAT_ID=' /home/bots/equipe-bots/.env | tail -n 1 | cut -d= -f2-)
    echo "Bot actuel réutilisé en ENVOI SEUL (messages préfixés 🟡 [or]) ; commandes via Termius : « or etat »..."
  fi
  umask 077
  cat > "$DOSSIER/.env" <<ENV
# Armée de l'or — réglages (ne jamais partager ce fichier)
OR_TELEGRAM_BOT_TOKEN=$JETON
OR_TELEGRAM_CHAT_ID=$CHAT
OR_TELEGRAM_COMMANDES=$CMD
OR_RAPPORT_HEURES=6
OR_CAPITAL_PAPIER=1000
OR_SEUIL_CONSENSUS=0.56
ENV
fi
chown -R $COMPTE:$COMPTE "$DOSSIER"; chmod 600 "$DOSSIER/.env"

etape "4/8 Vérification automatique (tests, sans réseau ni argent)"
if ! runuser -u $COMPTE -- bash -c "cd '$DOSSIER' && .venv/bin/python -m pytest -q -p no:cacheprovider tests"; then
  echo -e "${R}✖ Des tests échouent : l'armée n'est PAS démarrée. Envoie une capture de l'écran.${N}"; exit 1
fi

etape "5/8 Historique de l'or dans la base (1833 → aujourd'hui)"
runuser -u $COMPTE -- bash -c "cd '$DOSSIER' && .venv/bin/python -m armee_or importer"

etape "6/8 MetaTrader 5 (compte DÉMO, ordres automatiques)"
if grep -q '^OR_MT5_LOGIN=' "$DOSSIER/.env"; then
  DOSSIER=$DOSSIER COMPTE=$COMPTE bash "$DOSSIER/installer_mt5.sh" || echo -e "${J}⚠ MT5 non branché pour l'instant (or mt5 installer pour réessayer).${N}"
else
  read -r -p "Brancher ton compte DÉMO MetaTrader 5 pour que l'armée s'entraîne avec de vrais ordres ? [O/n] " REP
  if [[ ! "${REP:-O}" =~ ^[nN] ]]; then
    DOSSIER=$DOSSIER COMPTE=$COMPTE bash "$DOSSIER/installer_mt5.sh" || echo -e "${J}⚠ MT5 non branché pour l'instant (or mt5 installer pour réessayer).${N}"
  fi
fi

etape "7/8 Services (relance automatique sans fin, priorité modérée)"
for NOM in flux chef; do
  MEM=$([ $NOM = chef ] && echo 900M || echo 300M)
  cat > /etc/systemd/system/armee-or-$NOM.service <<UNITE
[Unit]
Description=Armée de l'or : $NOM
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
User=$COMPTE
WorkingDirectory=$DOSSIER
ExecStart=$DOSSIER/.venv/bin/python -m armee_or $NOM
Restart=always
RestartSec=15
RestartSteps=6
RestartMaxDelaySec=300
WatchdogSec=600
NotifyAccess=main
Nice=5
CPUQuota=60%
MemoryMax=$MEM
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNITE
done
install -m 755 "$DOSSIER/or" /usr/local/bin/or
systemctl daemon-reload
systemctl enable armee-or-flux armee-or-chef > /dev/null 2>&1
systemctl restart armee-or-flux armee-or-chef

etape "8/8 Contrôle"
sleep 8
NOMS="flux chef"; [ -f /etc/systemd/system/armee-or-mt5.service ] && NOMS="mt5 flux chef"
for NOM in $NOMS; do
  systemctl is-active --quiet armee-or-$NOM && echo -e "${V}● armee-or-$NOM en marche${N}" || echo -e "${R}● armee-or-$NOM arrêté${N} (or journal)"
done
echo -e "\n${V}✔ Armée de l'or installée.${N} Tes autres bots n'ont pas été touchés."
echo "  Termius : or etat · or mt5 · or levier · or bilan · or journal · or pause · or reprise · or aide"
if grep -q '^OR_MT5_ACTIF=1' "$DOSSIER/.env"; then
  echo "  MT5 démo : ordres automatiques (profil « pro 1 % risqué », or mt5 profil x20 pour changer) + équipe d'entraînement."
  echo "  Ouvre l'app MetaTrader 5 sur ton iPhone avec le même compte démo pour voir les positions en direct."
else
  echo "  Premier rapport Telegram dans 5 minutes. Tout est simulé sur papier : aucun ordre réel."
fi
