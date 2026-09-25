#!/usr/bin/env bash
# INSTALLATION COMPLÈTE sur un serveur Ubuntu 24.04 neuf (Hetzner ou autre). Durée : 10 à 20 minutes.
# Lancement (en root) : bash installer.sh
# Refaire l'installation ne supprime ni tes clés (.env), ni l'historique, ni l'apprentissage.
set -euo pipefail
V='\033[1;32m'; J='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
etape()  { echo -e "\n${V}==> $1${N}"; }
erreur() { echo -e "\n${R}✖ $1${N}"; exit 1; }
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPTE=bots
DOSSIER=/home/$COMPTE/equipe-bots
ESSAI="${BOTS_ESSAI:-0}"            # 1 = essai en conteneur : ni pare-feu, ni horloge système, ni service
en_bots() { runuser -u "$COMPTE" -- env HOME="/home/$COMPTE" bash -c "cd '$DOSSIER' && $*"; }

[ "$(id -u)" -eq 0 ] || erreur "Lance ce script en root (c'est le cas par défaut sur un serveur neuf)."
grep -qi ubuntu /etc/os-release || echo -e "${J}Attention : ce n'est pas Ubuntu, installation non testée.${N}"
echo -e "${V}Installation de l'équipe de bots. Ne ferme pas l'application pendant l'installation.${N}"

etape "1/9 Mise à jour du serveur et outils nécessaires (2 à 5 min)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || echo -e "${J}Mise à jour des listes incomplète, on continue.${N}"
apt-get install -y -qq python3 python3-venv python3-pip unzip curl rsync sqlite3 chrony ufw fail2ban \
  unattended-upgrades > /dev/null

etape "2/9 Heure du serveur : fuseau de Paris + synchronisation automatique (les ordres Binance en dépendent)"
if [ "$ESSAI" != 1 ]; then
  timedatectl set-timezone Europe/Paris
  systemctl enable --now chrony > /dev/null 2>&1 || true
fi

etape "3/9 Sécurité : pare-feu (seul l'accès SSH reste ouvert), anti-intrusion, mises à jour de sécurité auto"
if [ "$ESSAI" != 1 ]; then
  ufw allow OpenSSH > /dev/null
  ufw --force enable > /dev/null
  systemctl enable --now fail2ban > /dev/null 2>&1 || true
  echo 'APT::Periodic::Update-Package-Lists "1"; APT::Periodic::Unattended-Upgrade "1";' \
    > /etc/apt/apt.conf.d/20auto-upgrades
fi

etape "4/9 Mémoire de secours de 2 Go (évite les plantages pendant l'évolution)"
if [ "$ESSAI" != 1 ] && [ ! -f /swapfile ] && [ "$(free -m | awk '/Mem:/{print $2}')" -lt 6000 ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile > /dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

etape "5/9 Compte dédié « $COMPTE » : le bot ne tourne jamais en administrateur"
id -u "$COMPTE" > /dev/null 2>&1 || useradd -m -s /bin/bash "$COMPTE"
mkdir -p "$DOSSIER"
if [ "$SOURCE" != "$DOSSIER" ]; then
  # Copie du code SANS toucher aux données (clés, journal, champion, apprentissage)
  rsync -a --exclude .env --exclude '*.db' --exclude '*.json' --exclude '*.jsonl' --exclude archives \
    --exclude sauvegardes --exclude '*.log' --exclude .venv --exclude __pycache__ "$SOURCE/" "$DOSSIER/"
  [ -f "$DOSSIER/deblocages.csv" ] || cp "$SOURCE/deblocages.csv" "$DOSSIER/" 2> /dev/null || true
fi
chown -R "$COMPTE:$COMPTE" "/home/$COMPTE"
chmod 700 "/home/$COMPTE"

etape "6/9 Python et bibliothèques (3 à 8 min, c'est normal que ce soit long)"
[ -x "$DOSSIER/.venv/bin/python" ] || en_bots "python3 -m venv .venv"
en_bots ".venv/bin/pip install -q --upgrade pip"
en_bots ".venv/bin/pip install -q -r requirements.txt" || erreur "Installation des bibliothèques impossible (réseau ?). Relance : bash installer.sh"

etape "7/9 Vérification automatique : tous les tests, sans réseau ni argent"
en_bots ".venv/bin/python verifier.py" || erreur "Des tests échouent : copie ce qui est affiché au-dessus et envoie-le à Claude."

etape "8/9 Tes clés et ton Telegram"
install -m 755 "$DOSSIER/bots" /usr/local/bin/bots
if [ -f "$DOSSIER/.env" ] && [ "${BOTS_RECONFIGURER:-0}" != 1 ]; then
  echo "Configuration existante conservée. Pour la refaire plus tard : bots config"
else
  bash "$DOSSIER/configurer.sh"
fi

etape "9/9 Démarrage automatique (le bot redémarre seul si le serveur redémarre)"
if [ "$ESSAI" != 1 ]; then
  cat > /etc/systemd/system/equipe-bots.service << SERVICE
[Unit]
Description=Equipe de bots crypto (chien de garde)
After=network-online.target
Wants=network-online.target

[Service]
User=$COMPTE
WorkingDirectory=$DOSSIER
ExecStart=$DOSSIER/.venv/bin/python lanceur.py
Restart=on-failure
RestartSec=30
KillSignal=SIGINT
TimeoutStopSec=60
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE
  systemctl daemon-reload
  systemctl enable --now equipe-bots > /dev/null 2>&1
  sleep 5
  systemctl is-active --quiet equipe-bots && echo -e "${V}✔ Bot en marche.${N}" || echo -e "${R}Le bot ne démarre pas : bots etat${N}"
  /usr/local/bin/bots tr-demarrer > /dev/null 2>&1 && echo -e "${V}✔ Veille Trade Republic en marche.${N}" \
    || echo -e "${J}Veille Trade Republic non démarrée : bots tr-demarrer${N}"
  /usr/local/bin/bots renseignement-demarrer > /dev/null 2>&1 && echo -e "${V}✔ Armée de renseignement déployée.${N}" \
    || echo -e "${J}Armée de renseignement non démarrée : bots renseignement-demarrer${N}"
  /usr/local/bin/bots marches-demarrer > /dev/null 2>&1 && echo -e "${V}✔ Veille marchés mondiaux en marche.${N}" \
    || echo -e "${J}Veille marchés non démarrée : bots marches-demarrer${N}"
  /usr/local/bin/bots v17-demarrer > /dev/null 2>&1 && echo -e "${V}✔ Moteur v17 en marche (portefeuille fictif).${N}" \
    || echo -e "${J}Moteur v17 non démarré : bots v17-demarrer${N}"
  en_bots "nohup .venv/bin/python preparer.py > preparation.log 2>&1 &"
fi

echo -e "\n${V}════════════════════════════════════════════════════════════${N}"
echo -e "${V}  ✔ INSTALLATION TERMINÉE${N}"
echo -e "${V}════════════════════════════════════════════════════════════${N}"
echo "  • Le bot tourne en continu, en mode $(grep -oE '^MODE=.*' "$DOSSIER/.env" 2> /dev/null | cut -d= -f2)."
echo "  • Telegram : tu vas recevoir « Bots v17 démarrés », puis les résultats de la préparation"
echo "    (tests, backtest sur 2 ans, première évolution) dans les 30 à 90 minutes."
echo "  • Tu peux fermer Termius : le bot continue sans toi."
echo "  • Sur le serveur, tape « bots » pour voir la télécommande."
echo "  • Moteur v17 : /v17 sur Telegram (portefeuille fictif, aucun ordre sur ton compte Binance)."
echo "  • Suite du guide : étape 8 (verrouiller la clé Binance sur l'IP : bots ip)."
