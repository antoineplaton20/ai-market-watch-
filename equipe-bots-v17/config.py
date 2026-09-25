"""Réglages de l'équipe de bots v2. Tout se règle ici, rien à toucher ailleurs."""
import os
from dotenv import load_dotenv

load_dotenv()

# ============================== CONNEXIONS ==============================
MODE = os.getenv("MODE", "demo").lower()
# "demo"    : Binance Démo — vrais prix du marché, argent fictif (RECOMMANDÉ pour s'entraîner)
# "testnet" : ancien environnement de test — prix artificiels, données effacées chaque mois
# "reel"    : argent réel
REEL = MODE == "reel"
MARCHE_REEL = MODE in ("reel", "demo")      # vrais volumes : on applique les vrais seuils de liquidité
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CAPITAL_MAX_USDT = float(os.getenv("CAPITAL_MAX_USDT", "1000"))

# ================================ RYTHME ================================
DEVISE = "USDT"
UNITE_BOUGIE = "15m"             # à régler selon le verdict de : python backtest.py --comparer
MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
# Architecture v11 : chaque unité a un rôle précis. UNITE_BOUGIE reste le signal
# historique pour préserver la compatibilité avec le v10.
TIMEFRAME_ENTRY = os.getenv("TIMEFRAME_ENTRY", "5m")
TIMEFRAME_SIGNAL = os.getenv("TIMEFRAME_SIGNAL", "15m")
TIMEFRAME_TREND = os.getenv("TIMEFRAME_TREND", "1h")
TIMEFRAME_REGIME = os.getenv("TIMEFRAME_REGIME", "4h")
UNITE_BOUGIE = TIMEFRAME_SIGNAL
UNITES_SUP = {"15m": ("1h", "4h"), "1h": ("4h", "1d"), "4h": ("1d", "1w")}
HORIZON_H = {"15m": 12, "1h": 48, "4h": 120}

# v11 : marge minimale de gain NET au-dessus du coût aller-retour estimé.
OPPORTUNITE_MIN_NET_PCT = float(os.getenv("OPPORTUNITE_MIN_NET_PCT", "0.15"))
OPPORTUNITE_MARGE_SECURITE_PCT = float(os.getenv("OPPORTUNITE_MARGE_SECURITE_PCT", "0.05"))
PLATEFORME_EXECUTION = os.getenv("PLATEFORME_EXECUTION", "binance")
BINANCE_MAKER_FEE_PCT = float(os.getenv("BINANCE_MAKER_FEE_PCT", "0.10"))
BINANCE_TAKER_FEE_PCT = float(os.getenv("BINANCE_TAKER_FEE_PCT", "0.10"))
TRADE_REPUBLIC_SETTLEMENT_FEE_EUR = float(os.getenv("TRADE_REPUBLIC_SETTLEMENT_FEE_EUR", "1.0"))
TRADE_REPUBLIC_DIRECT_PRICE_FEE_EUR = float(os.getenv("TRADE_REPUBLIC_DIRECT_PRICE_FEE_EUR", "2.0"))
# v12 : univers Trade Republic (CSV ou JSON) chargé dans le registre, en SUIVI uniquement (aucun ordre).
UNIVERS_TR_FICHIER = os.getenv("UNIVERS_TR_FICHIER", "univers_trade_republic.csv")

# ======================= VEILLE TRADE REPUBLIC (v13) =======================
# Processus séparé (veille_tr.py) : univers officiel TR -> Yahoo Finance -> signaux MANUELS sur Telegram.
# Aucun ordre n'est jamais passé chez Trade Republic.
TR_ACTIF = os.getenv("TR_ACTIF", "1") == "1"
TR_URLS_UNIVERS = [u.strip() for u in os.getenv("TR_URLS_UNIVERS", ",".join([
    "https://assets.traderepublic.com/assets/files/FR/liste_d_actions_et_etf_disponibles.pdf",
    "https://traderepublic.com/assets/files/FR/liste_d_actions_et_etf_disponibles.pdf",
    "https://assets.traderepublic.com/assets/files/DE/Instrument_Universe_DE_en.pdf",
])).split(",") if u.strip()]
TR_UNIVERS_MIN = 200                    # en dessous, la lecture du PDF est jugée ratée : on garde l'ancien univers
TR_UNIVERS_MAJ_H = 24                   # relecture de la liste officielle une fois par jour
TR_MONTANT_ORDRE_EUR = float(os.getenv("TR_MONTANT_ORDRE_EUR", "500"))   # sert au calcul du poids des frais fixes
TR_SPREAD_ESTIME_PCT = float(os.getenv("TR_SPREAD_ESTIME_PCT", "0.10"))  # Yahoo ne donne pas l'écart achat/vente de TR
TR_VOLUME_MIN_EUR = float(os.getenv("TR_VOLUME_MIN_EUR", "2000000"))     # échanges quotidiens médians (20 j)
TR_PRESELECTION = int(os.getenv("TR_PRESELECTION", "60"))               # titres surveillés en intraday
TR_INTERVALLE_MIN = int(os.getenv("TR_INTERVALLE_MIN", "15"))           # une analyse intraday toutes les 15 min
TR_SIGNAUX_MAX_JOUR = int(os.getenv("TR_SIGNAUX_MAX_JOUR", "5"))
TR_SUIVI_JOURS = int(os.getenv("TR_SUIVI_JOURS", "10"))                 # un signal est suivi 10 jours maximum
TR_PAUSE_TITRE_H = 72                   # pas de nouveau signal sur un titre dans les 72 h après la fin de son suivi
TR_DONNEES_AGE_MAX_MIN = int(os.getenv("TR_DONNEES_AGE_MAX_MIN", "35"))  # Yahoo diffère certaines bourses de 15-20 min
TR_PAUSE_YAHOO_MIN = 30                 # Yahoo limite les requêtes : pause puis reprise automatique
TR_BUDGET_LOT_S = 240                   # durée max d'un lot de travail de fond (correspondance, tri quotidien)
TR_OUVERTURE_MIN = 7 * 60 + 30          # Trade Republic ouvre à 7 h 30 (heure de Paris), du lundi au vendredi
TR_FIN_SIGNAUX_MIN = 22 * 60 + 30       # derniers signaux d'achat à 22 h 30 (fermeture à 23 h)


def echelle(unite=None):
    """Les seuils de volatilité s'élargissent avec l'unité (racine du temps)."""
    return (MINUTES[unite or UNITE_BOUGIE] / 15) ** 0.5
INTERVALLE_SCAN_S = 300          # un scan complet toutes les 5 min
INTERVALLE_BOUCLE_S = 20         # surveillance des positions toutes les 20 s

# ================================ SCOUT =================================
# v14 : 0 = TOUTES les paires USDT tradables de Binance (sinon : les N plus échangées)
SCOUT_MAX = int(os.getenv("SCOUT_MAX", "0"))
SCAN_DUREE_MAX_FRAC = 0.8        # un scan ne dépasse jamais 80 % d'une bougie de signal (reprise au scan suivant)

# ================== EXPLORATION (v14) — COMPTE DÉMO UNIQUEMENT ==================
# Les bots prennent volontairement plus de risques pour que des transactions aient lieu et que l'équipe
# apprenne de résultats réels. JAMAIS en argent réel : verrouillé ici, quel que soit le .env.
EXPLORATION_AUTORISEE = MODE in ("demo", "testnet")
EXPLORATION_NIVEAU_DEFAUT = int(os.getenv("EXPLORATION_NIVEAU", "2")) if EXPLORATION_AUTORISEE else 0
EXCLUS = {
    "USDC/USDT", "FDUSD/USDT", "TUSD/USDT", "DAI/USDT", "USDP/USDT", "BUSD/USDT",
    "EUR/USDT", "EURI/USDT", "AEUR/USDT", "USD1/USDT", "PAXG/USDT",
}

# =========================== FILTRE (6 checks) ==========================
VOLUME_24H_MIN = 5_000_000 if MARCHE_REEL else 0
SPREAD_MAX_PCT = 0.15 if MARCHE_REEL else 1.0
PROFONDEUR_MIN_USDT = 50_000 if MARCHE_REEL else 0
HAUSSE_24H_MAX_PCT = 40
BOUGIES_HISTORIQUE_MIN = 200
ECART_EMA20_MAX_PCT = 3.0

# ============================ RISK (veto) ===============================
ATR_MIN_PCT = 0.25
ATR_MAX_PCT = 3.0
QUARANTAINE_H = 6

# ============================ ANTI-HYPE (veto) ==========================
HYPE_VOLUME_X = 5                # volume > 5x la moyenne = emballement
HYPE_HAUSSE_1H_PCT = 8           # +8 % en 1 h = trop tard pour entrer

# ============================ DÉRIVÉS (veto + vote) =====================
FUNDING_MAX = 0.0005             # 0,05 % / 8 h : trop de levier acheteur
OI_HAUSSE_MIN = 1.03             # open interest +3 % en 3 h = argent frais qui entre

# ============================ BALEINES (veto + vote) ====================
BALEINE_MIN_USDT = 100_000 if MARCHE_REEL else 1_000
BALEINE_FENETRE_MIN = 15

# ============================ CORRÉLATION (veto) ========================
CORRELATION_MAX = 0.85

# ============================ PEUR & AVIDITÉ (taille) ===================
AVIDITE_EXTREME = 80             # taille x0,5
AVIDITE_FORTE = 70               # taille x0,75
PEUR_EXTREME = 20                # taille x0,75

# ============================ VEILLE / ACTUALITÉ (veto) =================
FLUX_RSS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
]
ACTU_FENETRE_H = 24
MOTS_DANGER = [
    "hack", "exploit", "drained", "delist", "lawsuit", "sues ", "charged", "insolven",
    "bankrupt", "halts withdrawals", "suspends withdrawals", "paused withdrawals",
    "rug pull", "vulnerability", "breach", "stolen",
]

# ============================ CALENDRIER (veto global) ==================
# Heures UTC. Sources : calendrier FOMC de la Fed, calendrier CPI du BLS.
# À compléter chaque année (les dates 2027 sont publiées fin 2026).
EVENEMENTS_MACRO = [
    ("2026-10-14 12:30", "Inflation US (CPI)"),
    ("2026-10-28 18:00", "Décision de la Fed"),
    ("2026-11-10 13:30", "Inflation US (CPI)"),
    ("2026-12-09 19:00", "Décision de la Fed"),
    ("2026-12-10 13:30", "Inflation US (CPI)"),
]
CALENDRIER_MARGE_H = 2

# ============================ LIQUIDITÉ (veto + vote) ===================
# Offre totale de stablecoins (DefiLlama, gratuit) : l'argent frais qui entre ou sort de la crypto
LIQUIDITE_SORTIE_PCT = -0.5      # offre en baisse de plus de 0,5 % sur 7 jours : veto
LIQUIDITE_ENTREE_PCT = 0.5       # offre en hausse de plus de 0,5 % sur 7 jours : vote favorable

# ============================ MACRO (veto + vote) =======================
# Nasdaq et dollar (DXY) via Yahoo Finance : la crypto suit souvent l'appétit pour le risque
MACRO_DXY_HAUSSE_5J_PCT = 1.0    # dollar +1 % en 5 jours au-dessus de sa moyenne 50 j = stress

# ============================ POSITIONNEMENT (veto + vote) ==============
# Ratios acheteurs/vendeurs des comptes Binance Futures (foule) et des 20 % plus gros traders
POS_FOULE_MAX = 2.5              # foule 2,5x plus acheteuse que vendeuse : trop de monde du même côté

# ============================ MARCHÉS MONDIAUX (veto + vote) ============
# S&P 500, VIX (indice de la peur à Wall Street), or, pétrole, taux US 10 ans, euro-dollar (Yahoo Finance)
VIX_PANIQUE = 30                 # VIX au-dessus de 30 = panique sur les marchés mondiaux
VIX_BOND_5J_PCT = 25             # ou VIX +25 % en 5 jours

# ============================ ATTENTION (veto) ==========================
# Consultations Wikipedia des pages Bitcoin et Cryptomonnaie (depuis 2015, gratuit)
ATTENTION_PIC_X = 2.5            # 2,5x la normale du mois = le grand public arrive, souvent près d'un sommet

# ============================ DÉVELOPPEURS (vote) =======================
DEV_COMMITS_ACTIF = 20           # commits sur 4 semaines

# ============================ IA ========================================
MODELE_IA_VEILLE = "claude-haiku-4-5-20251001"     # lit les titres de presse
MODELE_IA_CONTRADICTEUR = "claude-sonnet-5"        # dernier contrôle avant achat

# ======================= VEILLE MARCHÉS MONDIAUX (v17.3) =======================
# Processus séparé (veille_marches.py, service equipe-bots-marches) : presse mondiale (géopolitique, économie,
# banques centrales, Wall Street, Europe, énergie, alimentation, industrie, devises, défense, crypto), consensus
# des analystes (Yahoo), notes de 0 à 5 des titres Trade Republic. AUCUN ordre : c'est toi qui décides.
def _liste_env(nom, defaut=""):
    return [x.strip() for x in os.getenv(nom, defaut).replace(";", ",").split(",") if x.strip()]


MARCHES_ACTIF = os.getenv("MARCHES_ACTIF", "1") == "1"
MARCHES_BRIEFING_H = float(os.getenv("MARCHES_BRIEFING_H", "4"))          # lecture de la presse toutes les 4 h
MARCHES_RAPPORT_HEURE = int(os.getenv("MARCHES_RAPPORT_HEURE", "8"))       # rapport quotidien sur Telegram (heure de Paris)
MARCHES_NOTES_MAX = int(os.getenv("MARCHES_NOTES_MAX", "60"))              # titres TR notés par jour, en plus des tiens
MARCHES_NOTES_VALIDITE_H = 20                                              # une note est refaite après 20 h
MARCHES_PAR_TOUR = 6                                                       # titres notés par tour (charge répartie)
MARCHES_PORTEFEUILLE = _liste_env("MARCHES_PORTEFEUILLE")                  # ce que tu détiens chez TR (alertes de vente)
MARCHES_SUIVIS = _liste_env("MARCHES_SUIVIS")                              # ta liste de surveillance
MARCHES_CRYPTOS = _liste_env("MARCHES_CRYPTOS", "BTC-EUR,ETH-EUR,SOL-EUR,XRP-EUR,ADA-EUR,DOGE-EUR,LINK-EUR,"
                                                "DOT-EUR,LTC-EUR,AVAX-EUR")
MARCHES_DEVISES = _liste_env("MARCHES_DEVISES", "EURUSD=X,EURGBP=X,EURCHF=X,EURJPY=X")
MARCHES_INDICES = _liste_env("MARCHES_INDICES", "^FCHI,^STOXX50E,^GSPC,^IXIC,GC=F,BZ=F")
MARCHES_ALERTES_JOUR = 3                                                   # alertes « note 5 » au maximum par jour
MODELE_IA_MARCHES = os.getenv("MODELE_IA_MARCHES", "claude-sonnet-5")      # synthèse mondiale (6 appels / jour)

# ============================ LEADER ====================================
SEUIL_VOTE = 0.70
PRE_SCORE_MIN = 0.50             # en dessous, on n'appelle même pas les bots coûteux
VOTANTS_MIN = 4

# ============================ GARDIEN + TRAILING (aucune IA) ============
RISQUE_PAR_TRADE_PCT = 1.0
POSITION_MAX_PCT = 20.0
POSITIONS_MAX = 3
PERTE_JOUR_MAX_PCT = 5.0
STOP_ATR = 1.5                   # stop initial
SECURISATION_R = 1.0             # stop remonté au prix d'entrée dès +1 R de gain
TRAILING_ATR = 2.0               # après sécurisation, le stop suit le plus haut à 2 ATR
TRAILING_PAS_ATR = 0.25          # on ne déplace le stop que par pas de 0,25 ATR
OBJECTIF_ATR = 6.0               # objectif lointain : le trailing fait l'essentiel du travail
DUREE_MAX_H = HORIZON_H[UNITE_BOUGIE]
FRAIS_ALLER_RETOUR_PCT = 0.2  # compatibilité v10; v11 utilise CostEngine
GLISSEMENT_PCT = 0.05            # utilisé par le backtest (entrée au marché, objectif, durée max)
# v17.5 : un stop est un STOP-LIMITE posé 0,5 % sous le déclenchement (gardien.poser_stop) : il peut s'exécuter
# nettement plus bas que le stop. Le backtest suppose désormais 0,25 % de glissement sur chaque sortie par stop.
GLISSEMENT_STOP_PCT = 0.25
# Stop « sécurisé » : au-dessus de l'entrée d'assez pour couvrir frais + glissement du stop (gain garanti réaliste)
SECURISATION_MARGE_PCT = FRAIS_ALLER_RETOUR_PCT + GLISSEMENT_STOP_PCT + 0.05

# ============================ BACKTEST ==================================
BACKTEST_UNIVERS = "complet"    # v17.5 : paires disparues incluses (biais du survivant) — "actuel" = top volumes du jour
BACKTEST_DSR_MIN = 0.95          # v17.5 : porte statistique — Sharpe dégonflé exigé pour recommander une unité
BACKTEST_PERIODES = 4            # l'historique est coupé en 4 : un bot doit tenir sur CHACUNE
METRICS_JOURS_MAX = 365          # historique des positions à terme (fichiers journaliers)

# ============================ ÉVOLUTION (gènes) =========================
EVO_UNITE = UNITE_BOUGIE         # l'évolution travaille TOUJOURS sur l'unité tradée en réel
EVO_JOURS = 730
EVO_PAIRES = 15
EVO_GENERATIONS = 25
EVO_PAR_ESPECE = 16              # 8 espèces x 16 = 128 stratégies par génération
EVO_ELITES = 3                   # les 3 meilleures de chaque espèce passent telles quelles
EVO_IMMIGRANTS = 2               # 2 nouvelles venues aléatoires par espèce et par génération
EVO_GENERATIONS_QUOTIDIEN = 6    # chaque jour : 6 générations d'entraînement (sans ouvrir le coffre)
EVO_UNIVERS = "complet"          # "complet" = toutes les paires USDT ayant existé, y compris les disparues
                                 # (tirées au sort chaque semaine) ; "actuel" = les plus échangées aujourd'hui
EVO_TAUX_MUTATION = 0.25
EVO_COFFRE_PCT = 20              # les 20 % les plus récents : jamais vus par l'évolution
EVO_TRADES_MIN = 60              # une stratégie qui trade trop peu ne prouve rien
EVO_DD_MAX = 0.10                # pire baisse autorisée : 10 %
EVO_MONTE_CARLO = 1000           # tirages pour estimer la pire baisse probable
PBO_TRANCHES = 12                # l'entraînement est coupé en 12 tranches -> 924 combinaisons passé / futur
PBO_MAX = 0.35                   # probabilité de sur-apprentissage maximale acceptée pour la sélection de la semaine
DSR_MIN = 0.90                   # Sharpe dégonflé minimum : 90 % de chances que l'avantage soit réel
EVO_AUTO = True                  # main.py lance lui-même l'évolution : chaque jour + grande évolution hebdomadaire
EVO_JOUR = 6                     # grande évolution (avec coffre-fort) : 0 = lundi ... 6 = dimanche
EVO_HEURE = 3                    # à 3 h du matin (heure du PC)
DUEL_JOURS_MIN = 14              # duel champion / challenger en conditions réelles
DUEL_JOURS_MAX = 42
DUEL_TRADES_MIN = 20
DUEL_AVANCE_R = 0.05             # le challenger doit battre le champion d'au moins 0,05 R par trade

# ============================ SÉCURITÉ DE FONCTIONNEMENT (v6) ===========
BATTEMENT_MAX_S = 900            # sans signe de vie pendant 15 min, le chien de garde relance le bot
VIVANT_H = 6                     # message « je suis vivant » toutes les 6 h
PLANTAGES_MAX_H = 5              # plus de 5 plantages en 1 h : le chien de garde s'arrête et prévient
SAUVEGARDES_GARDEES = 30         # une sauvegarde par jour, les 30 dernières conservées
SAUVEGARDE_COPIE = ""            # optionnel : dossier synchronisé (ex. "C:/Users/Antoine/OneDrive/bots")
AVOIR_HORS_BOT_USDT = 20         # en réel : signale les avoirs que le bot ne connaît pas (jamais vendus d'office)

# ============================ DISJONCTEUR DE PERFORMANCE (v6) ===========
DISJONCTEUR_DD_MULT = 1.5        # pire baisse réelle > 1,5 x la pire baisse prévue : arrêt des achats
DISJONCTEUR_TRADES_MIN = 30      # test statistique de l'espérance à partir de 30 trades
PERTES_SUITE_MAX = 7             # 7 pertes d'affilée : pause de 24 h
PAUSE_PERTES_H = 24

# ============================ CONTRÔLE ET SÉCURITÉ (v9) =================
POLITIQUE_VERSION = "9.0"        # inscrite sur chaque décision et chaque ordre
COUPE_CIRCUIT_DD = 0.15          # -15 % depuis le plus haut : arrêt total, quoi qu'en dise la prévision
# États de risque gradués : la taille des positions baisse AVANT l'arrêt
RISQUE_PRUDENCE = {"baisse": 0.05, "perte_jour": 0.015, "pertes_suite": 3}    # taille x0,75
RISQUE_REDUCTION = {"baisse": 0.08, "perte_jour": 0.030, "pertes_suite": 5}   # taille x0,5
# Capital par paliers : monter d'un palier exige TON approbation, descendre est automatique
PALIERS_CAPITAL = [100, 300, 1000, 3000]
PALIER_TRADES_MIN = 30
PALIER_JOURS_MIN = 14
# Fraîcheur des données : un doute = aucun nouveau risque
DONNEES_AGE_MAX_BOUGIES = 2      # dernière bougie plus vieille que 2 unités de temps : périmée
TICKER_AGE_MAX_S = 120
HORLOGE_ECART_MAX_MS = 5000
ECHECS_RESEAU_MAX = 3            # 3 erreurs réseau d'affilée : arrêt des achats jusqu'au retour à la normale

# ============================ IA (v9) ===================================
IA_OBLIGATOIRE_SI_CLE = True     # clé IA configurée mais IA muette : pas de trade (jamais sans son avis)
CALIBRATION_ECHANTILLON_MIN = 50

# ============================ RECHERCHE FONDAMENTALE (v9) ===============
RECHERCHE_DILUTION_MIN = 0.35    # moins de 35 % de l'offre en circulation : dilution massive à venir -> veto
RECHERCHE_TVL_CHUTE_7J = -25     # TVL -25 % en 7 jours : fuite des utilisateurs -> veto
RECHERCHE_DEBLOCAGE_PCT = 2.0    # déblocage d'au moins 2 % de l'offre dans les 14 jours -> veto
RECHERCHE_AGE_MAX_J = 10         # recherche plus vieille que 10 jours : ignorée (et signalée)

# ============================ NOTIFICATIONS (v9) ========================
NOTIF_SIGNAUX_BLOQUES = True     # te prévenir aussi des signaux bloqués par un veto
NOTIF_BLOQUE_DELAI_H = 2         # au plus un message par paire bloquée toutes les 2 h
RAPPORT_QUOTIDIEN_HEURE = 21     # bilan de la journée sur Telegram

# ============================ AUDITEUR (notes /10) ======================
NOTE_FIABLE = 8.0                # >= 8 : poids x1,5
NOTE_COUPURE = 5.0               # < 5 : le votant est coupé (il fait pire que le hasard)
ECHANTILLON_MIN = 30             # trades minimum avant de noter un bot
FICHIER_NOTES_BACKTEST = f"notes_backtest_{UNITE_BOUGIE}.json"
