#!/usr/bin/env bash
# ASSISTANT DE CONFIGURATION : crée le fichier .env (tes clés) en te posant les questions une par une.
# Relançable à tout moment avec : bots config
# (Pour les essais automatiques, chaque réponse peut être fournie à l'avance par une variable BOTS_...)
set -uo pipefail
DOSSIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DOSSIER/.venv/bin/python"
V='\033[1;32m'; J='\033[1;33m'; R='\033[1;31m'; B='\033[1;36m'; N='\033[0m'

demander() {   # demander VARIABLE "question" "valeur par défaut"
  local var="$1" question="$2" defaut="${3:-}" val
  val="${!var:-}"
  if [ -z "$val" ]; then
    read -r -p "$(echo -e "${B}?${N} $question${defaut:+ [$defaut]} : ")" val
    val="${val:-$defaut}"
  fi
  val="$(echo "$val" | tr -d '[:space:]')"
  printf -v "$var" '%s' "$val"
}

echo -e "\n${V}=== Configuration de l'équipe de bots ===${N}"
echo "Astuce : sur téléphone, copie chaque clé puis colle-la ici (appui long > Coller). Entrée pour valider."

# 1. Mode
echo -e "\n${V}1. Mode de fonctionnement${N}"
echo "  demo    = vrais prix du marché, ARGENT FICTIF (recommandé pour commencer, 4 semaines minimum)"
echo "  reel    = ton argent réel (seulement après la liste de contrôle du guide)"
demander BOTS_MODE "Mode (demo ou reel)" "demo"
case "$BOTS_MODE" in
  demo|testnet) ;;
  reel)
    echo -e "${R}⚠️  MODE RÉEL : le bot va trader ton argent. Les pertes sont possibles.${N}"
    CONFIRMATION="${BOTS_CONFIRMATION:-}"
    [ -z "$CONFIRMATION" ] && read -r -p "Tape exactement JE CONFIRME pour continuer : " CONFIRMATION
    [ "$CONFIRMATION" = "JE CONFIRME" ] || { echo "Annulé : on reste en démo."; BOTS_MODE=demo; } ;;
  *) echo "Mode inconnu : démo choisie."; BOTS_MODE=demo ;;
esac

# 2. Binance
echo -e "\n${V}2. Clés API Binance${N}"
if [ "$BOTS_MODE" = "reel" ]; then
  echo "  binance.com > Profil > Gestion des API > Créer. Coche UNIQUEMENT « Enable Spot Trading »."
  echo "  NE COCHE JAMAIS « Enable Withdrawals ». Restreins la clé à l'adresse IP de ce serveur :"
else
  echo "  demo.binance.com > connexion > Gestion des API (API Management) > Créer une clé."
  echo "  Si une restriction d'adresse IP est proposée, mets celle de ce serveur :"
fi
IP="$(curl -sf --max-time 10 https://api.ipify.org || echo 'inconnue')"
echo -e "  Adresse IP du serveur : ${J}$IP${N}"
demander BOTS_BINANCE_KEY "Clé API (API Key)" ""
demander BOTS_BINANCE_SECRET "Clé secrète (Secret Key)" ""

# 3. Capital
echo -e "\n${V}3. Plafond absolu de capital${N}"
echo "  Le bot n'engagera jamais plus que ce montant, même si le compte contient davantage."
echo "  Les paliers (100 -> 300 -> 1000 -> 3000 USDT) restent en dessous et exigent ton approbation."
demander BOTS_CAPITAL "Plafond en USDT" "$([ "$BOTS_MODE" = reel ] && echo 100 || echo 1000)"

# 4. Telegram
echo -e "\n${V}4. Telegram (alertes et télécommande)${N}"
echo "  Dans Telegram : cherche @BotFather > /newbot > donne un nom > il te donne un TOKEN."
demander BOTS_TELEGRAM_TOKEN "Token du bot Telegram" ""
BOTS_TELEGRAM_CHAT="${BOTS_TELEGRAM_CHAT:-}"
if [ -n "$BOTS_TELEGRAM_TOKEN" ] && [ -z "$BOTS_TELEGRAM_CHAT" ]; then
  echo -e "  Ouvre ton nouveau bot dans Telegram, appuie sur ${J}Démarrer${N} et envoie-lui « bonjour »."
  read -r -p "  Puis appuie sur Entrée ici... " _
  BOTS_TELEGRAM_CHAT="$(curl -s --max-time 15 "https://api.telegram.org/bot$BOTS_TELEGRAM_TOKEN/getUpdates" | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin).get("result", [])
    ids = [u["message"]["chat"]["id"] for u in r if "message" in u]
    print(ids[-1] if ids else "")
except Exception:
    print("")')"
  if [ -z "$BOTS_TELEGRAM_CHAT" ]; then
    echo -e "  ${J}Identifiant non trouvé automatiquement.${N} Envoie un message à @userinfobot : il te donne ton « Id »."
    demander BOTS_TELEGRAM_CHAT "Ton identifiant Telegram (Id)" ""
  else
    echo -e "  ${V}✔ Identifiant détecté : $BOTS_TELEGRAM_CHAT${N}"
  fi
fi

# 5. Options
echo -e "\n${V}5. Options (Entrée pour passer)${N}"
echo "  Clé Anthropic (IA : CONTRADICTEUR, VEILLE, thèses) : console.anthropic.com > API Keys. Payant à l'usage."
demander BOTS_ANTHROPIC "Clé Anthropic (facultatif)" ""
echo "  Clé CoinGecko « Demo » (gratuite) : coingecko.com > Developers > API. Sert à la recherche et à DÉVELOPPEURS."
demander BOTS_COINGECKO "Clé CoinGecko (facultatif)" ""

# 6. Écriture du fichier .env (lisible uniquement par le compte « bots »)
# v17 : les autres réglages déjà présents (V17_..., TIMEFRAME_SIGNAL, TR_MONTANT_ORDRE_EUR...) sont CONSERVÉS
GERES='^(MODE|BINANCE_API_KEY|BINANCE_API_SECRET|CAPITAL_MAX_USDT|ANTHROPIC_API_KEY|COINGECKO_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)='
AUTRES=""
[ -f "$DOSSIER/.env" ] && AUTRES="$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$DOSSIER/.env" | grep -vE "$GERES" || true)"
umask 077
cat > "$DOSSIER/.env" << FIN
MODE=$BOTS_MODE
BINANCE_API_KEY=$BOTS_BINANCE_KEY
BINANCE_API_SECRET=$BOTS_BINANCE_SECRET
CAPITAL_MAX_USDT=$BOTS_CAPITAL
ANTHROPIC_API_KEY=$BOTS_ANTHROPIC
COINGECKO_API_KEY=$BOTS_COINGECKO
TELEGRAM_BOT_TOKEN=$BOTS_TELEGRAM_TOKEN
TELEGRAM_CHAT_ID=$BOTS_TELEGRAM_CHAT
FIN
[ -n "$AUTRES" ] && printf '%s\n' "$AUTRES" >> "$DOSSIER/.env"
chmod 600 "$DOSSIER/.env"
id -u bots >/dev/null 2>&1 && chown bots:bots "$DOSSIER/.env"
echo -e "\n${V}✔ Fichier .env enregistré (protégé : lisible uniquement par le compte du bot).${N}"

# 7. Tests de connexion
if [ "${BOTS_SANS_TEST_CONNEXION:-0}" != 1 ] && [ -x "$PY" ]; then
  echo -e "\n${V}Test de Telegram...${N}"
  (cd "$DOSSIER" && "$PY" notifier.py "✅ Le bot est bien relié à ton Telegram. Mode : $BOTS_MODE") \
    && echo "  Regarde Telegram : un message de confirmation doit être arrivé."
  echo -e "\n${V}Test de Binance...${N}"
  (cd "$DOSSIER" && "$PY" - << 'PYTEST'
from exchange import connecter
import config
try:
    ex = connecter()
    solde = ex.fetch_balance()["total"].get("USDT", 0)
    print(f"  ✔ Connexion Binance réussie (mode {config.MODE}). Solde USDT : {solde}")
except Exception as e:
    texte = str(e)
    print(f"  ✖ Connexion Binance impossible : {texte[:200]}")
    if "Invalid API-key" in texte or "API-key format" in texte or "-2015" in texte or "-2014" in texte:
        print("    → Clé fausse, clé du mauvais environnement (démo / réel), ou restriction d'IP : vérifie-les, puis : bots config")
    elif "restricted location" in texte.lower():
        print("    → Binance refuse le pays du serveur : choisis un serveur en Europe (Allemagne ou Finlande).")
PYTEST
  )
fi
