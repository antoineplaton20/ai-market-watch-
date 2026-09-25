"""L'équipe d'analyse v2.
Règle de conception : chaque bot regarde une source DIFFÉRENTE, pour qu'ils ne se trompent pas ensemble.
Votants : renvoient (vote 0..1 ou None si abstention, raison).
Vetos   : renvoient (autorisé True/False, raison)."""
import datetime
import json
import os
import re
import time
from collections import Counter
import config
import donnees
from indicateurs import bougies, enrichir


# ============================ OUTIL IA COMMUN ============================
_client_ia = None


def ia_json(modele, prompt, max_tokens=300):
    """Appelle Claude et renvoie un dict JSON, ou None si indisponible."""
    global _client_ia
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        if _client_ia is None:
            _client_ia = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        r = _client_ia.messages.create(model=modele, max_tokens=max_tokens, temperature=0,
                                       messages=[{"role": "user", "content": prompt}])
        texte = "".join(b.text for b in r.content if b.type == "text")
        texte = texte.replace("```json", "").replace("```", "").strip()
        debut, fin = texte.find("{"), texte.rfind("}")
        return json.loads(texte[debut:fin + 1])
    except Exception:
        return None


# =========================== BOTS GLOBAUX (marché) ======================
def calendrier():
    """VETO GLOBAL : pas de nouvelle position 2 h avant/après une annonce macro majeure."""
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    for quand, nom in config.EVENEMENTS_MACRO:
        t = datetime.datetime.strptime(quand, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
        if abs((t - maintenant).total_seconds()) <= config.CALENDRIER_MARGE_H * 3600:
            return False, f"{nom} ({quand} UTC) : aucune nouvelle position"
    return True, "aucun événement macro proche"


def meteo_marche(ex):
    """VETO GLOBAL : si le Bitcoin est sous sa moyenne 50 h, presque tout baisse avec lui."""
    df = enrichir(bougies(ex, "BTC/USDT", "1h", 100))
    der = df.iloc[-2]
    if der["c"] < der["ema50"]:
        return False, "BTC sous sa moyenne 50 h, marché baissier"
    return True, "marché sain"


def peur_avidite():
    """MODULATEUR : ajuste la taille des positions selon le sentiment global."""
    v = donnees.peur_avidite()
    if v is None:
        return 1.0, "indice indisponible", None
    if v >= config.AVIDITE_EXTREME:
        return 0.5, f"avidité extrême ({v}) : tailles divisées par 2", v
    if v >= config.AVIDITE_FORTE:
        return 0.75, f"avidité forte ({v}) : tailles réduites d'un quart", v
    if v <= config.PEUR_EXTREME:
        return 0.75, f"peur extrême ({v}) : marché nerveux, tailles réduites", v
    return 1.0, f"sentiment neutre ({v})", v


# ================================ SCOUT =================================
DERNIER_SCAN = {}      # résumé du dernier passage du scanner universel (commande Telegram /univers)


def registre_instruments(ex):
    """v12 : registre unifié. Binance spot depuis ex.markets ; Trade Republic depuis un fichier fourni
    (suivi uniquement : aucun ordre n'est jamais envoyé à Trade Republic)."""
    from moteurs.instrument_registry import InstrumentRegistry
    reg = InstrumentRegistry()
    reg.add_binance_markets(ex.markets)
    tr, erreur_tr = 0, None
    if config.UNIVERS_TR_FICHIER and os.path.exists(config.UNIVERS_TR_FICHIER):
        try:
            tr = reg.load_trade_republic_file(config.UNIVERS_TR_FICHIER)
        except Exception as e:           # un fichier TR mal formé ne doit jamais bloquer le trading Binance
            erreur_tr = str(e)[:120]
    return reg, tr, erreur_tr


def seuils_liquidite(niveau=0):
    """(volume 24 h min, spread max %, profondeur min) : stricts pour le champion ; au niveau 3 d'exploration
    (démo uniquement), volume et profondeur x0,2 et spread x2 — jamais moins : il faut pouvoir revendre."""
    if niveau >= 3:
        return config.VOLUME_24H_MIN * 0.2, config.SPREAD_MAX_PCT * 2, config.PROFONDEUR_MIN_USDT * 0.2
    return config.VOLUME_24H_MIN, config.SPREAD_MAX_PCT, config.PROFONDEUR_MIN_USDT


def scout(ex, niveau=0):
    """v12 : découverte par le registre, puis tri par le scanner universel (actif, coté, volume, spread,
    exclusions). v14 : TOUTES les paires USDT tradables (SCOUT_MAX=0), classées par volume."""
    from moteurs.universal_scanner import UniversalScanner
    tickers = ex.fetch_tickers()
    reg, n_tr, erreur_tr = registre_instruments(ex)
    vol_min, spread_max, _ = seuils_liquidite(niveau)
    scanner = UniversalScanner(min_volume_quote=vol_min, max_spread_pct=spread_max, excluded=config.EXCLUS)
    univers = [i for i in reg.active("binance") if i.quote == config.DEVISE]
    candidats, rejets = [], Counter()
    for r in scanner.scan(univers, tickers):
        t = tickers.get(r["symbol"]) or {}
        if r["tradable"] and t.get("last"):
            candidats.append({"symbole": r["symbol"], "ticker": t})
        else:
            rejets.update(r["reasons"] or ["sans_dernier_prix"])
    candidats.sort(key=lambda x: x["ticker"].get("quoteVolume") or 0, reverse=True)
    DERNIER_SCAN.clear()
    garde = candidats[: config.SCOUT_MAX] if config.SCOUT_MAX else candidats
    DERNIER_SCAN.update({"ts": time.time(), "univers": len(univers), "tradables": len(candidats),
                         "analyses": len(garde), "rejets": dict(rejets),
                         "trade_republic": n_tr, "erreur_tr": erreur_tr, "niveau": niveau})
    return garde


def texte_univers():
    if not DERNIER_SCAN:
        return "🔭 Pas encore de tour du marché : le premier arrive dans quelques minutes."
    d = DERNIER_SCAN
    noms = {"volume": "trop peu échangées", "spread": "écart trop grand entre prix d'achat et de vente",
            "no_quote": "sans prix affiché", "excluded": "exclues volontairement (cryptos stables comme USDC)",
            "inactive": "fermées", "sans_dernier_prix": "sans dernier prix"}
    rejets = "\n".join(f"• {v} {noms.get(k, k)}" for k, v in sorted(d["rejets"].items(), key=lambda x: -x[1])) or "• aucune"
    tr = (f"Trade Republic : {d['trade_republic']} titres suivis (signaux à passer toi-même)"
          if d["trade_republic"] else "Trade Republic : aucune liste chargée")
    if d.get("erreur_tr"):
        tr += f"\n⚠️ Liste Trade Republic illisible : {d['erreur_tr']}"
    return (f"🔭 Tour du marché de {datetime.datetime.fromtimestamp(d['ts']):%H:%M}\n"
            f"{d['univers']} cryptos cotées en {config.DEVISE} sur Binance\n"
            f"→ {d['tradables']} assez échangées pour être étudiées\n"
            f"→ {d['analyses']} étudiées ({'toutes' if not config.SCOUT_MAX else f'les {config.SCOUT_MAX} plus échangées'})"
            + (" · seuils élargis pour les essais niveau 3" if d.get("niveau", 0) >= 3 else "")
            + f"\nÉcartées :\n{rejets}\n{tr}")


# ================================ FILTRE ================================
def filtre(ex, cand, niveau=0):
    """garde = paire conforme aux règles STRICTES du champion.
    v14 : d["explorable"] = assez sûre pour l'EXPLORATION (démo) même si une règle stricte n'est pas remplie
    (fenêtre d'entrée, et au niveau 3 : liquidité réduite, pump). Jamais explorable : données périmées."""
    import controle_donnees as CD
    sym, t = cand["symbole"], cand["ticker"]
    raisons = []
    if not CD.ticker_frais(t):
        return False, ["prix périmé (ticker trop ancien)"], None
    vol_min, spread_max, prof_min = seuils_liquidite(niveau)
    volume = t.get("quoteVolume") or 0
    if volume < config.VOLUME_24H_MIN:
        raisons.append(f"volume 24 h trop faible ({volume:,.0f})")
    spread = (t["ask"] - t["bid"]) / t["ask"] * 100
    if spread > config.SPREAD_MAX_PCT:
        raisons.append(f"spread {spread:.2f} %")
    hausse = t.get("percentage") or 0
    if hausse > config.HAUSSE_24H_MAX_PCT:
        raisons.append(f"pump +{hausse:.0f} % en 24 h")
    explorable = (niveau > 0 and volume >= vol_min and spread <= spread_max
                  and (niveau >= 3 or hausse <= config.HAUSSE_24H_MAX_PCT))
    if raisons and not explorable:
        return False, raisons, None

    carnet_ordres = ex.fetch_order_book(sym, limit=100)
    milieu = (t["bid"] + t["ask"]) / 2
    prof_achat = sum(p * q for p, q in carnet_ordres["bids"] if p >= milieu * 0.99)
    prof_vente = sum(p * q for p, q in carnet_ordres["asks"] if p <= milieu * 1.01)
    if min(prof_achat, prof_vente) < config.PROFONDEUR_MIN_USDT:
        raisons.append("liquidité insuffisante, revente difficile")
    explorable = explorable and min(prof_achat, prof_vente) >= prof_min

    df = enrichir(bougies(ex, sym, config.UNITE_BOUGIE))
    if not CD.bougies_fraiches(df, config.UNITE_BOUGIE):
        return False, ["bougies périmées"], None
    if len(df) < config.BOUGIES_HISTORIQUE_MIN:
        raisons.append("historique trop court")
        explorable = False                        # indicateurs pas fiables : aucune leçon à en tirer
    der = df.iloc[-2]
    ecart = (der["c"] - der["ema20"]) / der["ema20"] * 100
    if abs(ecart) > config.ECART_EMA20_MAX_PCT * config.echelle():
        raisons.append(f"hors fenêtre d'entrée ({ecart:+.1f} % de l'EMA20)")

    donnees_paire = {"df": df, "spread": spread, "hausse24h": hausse, "volume24h": volume,
                     "carnet": {"achat": prof_achat, "vente": prof_vente}, "base": sym.split("/")[0],
                     "explorable": explorable, "raisons_strictes": list(raisons)}
    return len(raisons) == 0, raisons, donnees_paire


# ======================= VOTANTS TECHNIQUES (code) ======================
# On lit la dernière bougie FERMÉE (iloc[-2]).
def tech_tendance(d):
    der = d["df"].iloc[-2]
    ok = der["c"] > der["ema20"] > der["ema50"]
    return (1.0 if ok else 0.0), ("tendance haussière 15 min" if ok else "pas de tendance haussière")


def tech_momentum(d):
    der = d["df"].iloc[-2]
    ok = 50 <= der["rsi"] <= 68 and der["v"] > der["vol_moy"]
    return (1.0 if ok else 0.0), f"RSI {der['rsi']:.0f}, volume {'au-dessus' if der['v'] > der['vol_moy'] else 'sous'} la moyenne"


def multi_unites(ex, sym, cache_h1, d=None, mtf=None):
    """Les deux unités supérieures doivent confirmer (15 min -> 1 h et 4 h ; 4 h -> jour et semaine).
    MÊME définition que le backtest et l'évolution (sup1 / sup2) : c'est sur elle que les génomes sont entraînés.
    v12 : réutilise les bougies déjà chargées par le moteur MTF quand l'unité y figure (moins d'appels Binance)."""
    sup1, sup2 = config.UNITES_SUP[config.UNITE_BOUGIE]

    def charger(unite):
        if mtf and unite in mtf:
            return mtf[unite].df
        return enrichir(bougies(ex, sym, unite, 120))
    a, b = charger(sup1), charger(sup2)
    if sup1 == "1h":
        cache_h1[sym] = a
    if d is not None:
        d["sup1"] = 1.0 if (a.iloc[-2]["c"] > a.iloc[-2]["ema50"] and a.iloc[-2]["ema20"] > a.iloc[-2]["ema50"]) else 0.0
    points = sum(1 for df in (a, b)
                 if df.iloc[-2]["c"] > df.iloc[-2]["ema50"] and df.iloc[-2]["ema20"] > df.iloc[-2]["ema50"])
    return points / 2, f"{points}/2 unités supérieures ({sup1}, {sup2}) haussières"


# =========================== MULTI-TIMEFRAME v11 ========================
def multi_timeframe(ex, sym, cache=None):
    """Snapshot 4h/1h/15m/5m. Toutes les décisions utilisent la bougie fermée."""
    from moteurs import multi_timeframe as MTF
    return MTF.snapshot(ex, sym, cache)


# ====================== BOTS DE FLUX (argent réel) ======================
def lire_trades(ex, sym):
    """Transactions réellement exécutées ces 15 dernières minutes (impossibles à truquer comme un carnet)."""
    trades = ex.fetch_trades(sym, limit=1000)
    limite = (time.time() - config.BALEINE_FENETRE_MIN * 60) * 1000
    return [t for t in trades if (t.get("timestamp") or 0) >= limite]


def _cout(t):
    return t.get("cost") or (t["price"] * t["amount"])


def carnet(d, trades):
    """Carnet d'ordres (40 %) + flux réellement exécuté (60 %) : le faux carnet ne suffit plus à tromper."""
    ratio = d["carnet"]["achat"] / max(d["carnet"]["vente"], 1e-9)
    livre = 1.0 if ratio >= 1.2 else (0.5 if ratio >= 1.0 else 0.0)
    achats = sum(_cout(t) for t in trades if t.get("side") == "buy")
    ventes = sum(_cout(t) for t in trades if t.get("side") == "sell")
    if achats + ventes == 0:
        return livre, f"carnet {ratio:.2f}, aucun échange récent"
    part = achats / (achats + ventes)
    flux = 1.0 if part >= 0.55 else (0.5 if part >= 0.50 else 0.0)
    return 0.4 * livre + 0.6 * flux, f"carnet {ratio:.2f}, achats exécutés {part:.0%}"


def flux_seul(trades):
    """Vote CARNET tel que le backtest le calcule (flux exécuté uniquement) : utilisé par les génomes."""
    achats = sum(_cout(t) for t in trades if t.get("side") == "buy")
    ventes = sum(_cout(t) for t in trades if t.get("side") == "sell")
    if achats + ventes == 0:
        return None
    part = achats / (achats + ventes)
    return 1.0 if part >= 0.55 else (0.5 if part >= 0.50 else 0.0)


def baleines(trades):
    """VETO + VOTE : que font les très gros ordres ?"""
    gros_a = sum(_cout(t) for t in trades if t.get("side") == "buy" and _cout(t) >= config.BALEINE_MIN_USDT)
    gros_v = sum(_cout(t) for t in trades if t.get("side") == "sell" and _cout(t) >= config.BALEINE_MIN_USDT)
    total = gros_a + gros_v
    if total == 0:
        return True, None, "aucun gros ordre"
    if gros_v > 2 * gros_a:
        return False, 0.0, f"gros vendeurs dominent ({gros_v:,.0f} contre {gros_a:,.0f} USDT)"
    return True, gros_a / total, f"gros acheteurs {gros_a / total:.0%}"


def derives(base):
    """VETO + VOTE : marché à terme (funding + open interest), données publiques Binance."""
    sf = f"{base}USDT"
    fr = donnees.fundings().get(sf)
    if fr is None:
        return True, None, "pas de contrat à terme"
    if fr > config.FUNDING_MAX:
        return False, 0.0, f"funding {fr * 100:.3f} % : trop de levier acheteur, risque de liquidations"
    oi = donnees.open_interest(sf)
    if not oi or len(oi) < 2:
        return True, 0.5, f"funding {fr * 100:.3f} %"
    evol = oi[-1] / oi[0]
    vote = 1.0 if evol >= config.OI_HAUSSE_MIN else (0.5 if evol >= 0.99 else 0.2)
    return True, vote, f"funding {fr * 100:.3f} %, open interest {(evol - 1) * 100:+.1f} % sur 3 h"


# ========================== BOTS DE PROTECTION ==========================
def risk(sym, d, etat):
    der = d["df"].iloc[-2]
    atr_pct = der["atr"] / der["c"] * 100
    if atr_pct > config.ATR_MAX_PCT * config.echelle():
        return False, f"trop volatil (ATR {atr_pct:.1f} %)"
    if atr_pct < config.ATR_MIN_PCT:
        return False, "trop plat, les frais mangeraient le gain"
    if sym in etat["positions"]:
        return False, "déjà en position"
    if etat["quarantaine"].get(sym, 0) > time.time():
        return False, "en quarantaine après une perte"
    return True, "OK"


def anti_hype(d):
    """VETO : le buzz des influenceurs précède en moyenne une baisse. On s'en sert à l'envers."""
    df = d["df"]
    der = df.iloc[-2]
    if der["vol_moy"] and der["v"] > config.HYPE_VOLUME_X * der["vol_moy"]:
        return False, f"volume x{der['v'] / der['vol_moy']:.0f} : emballement"
    hausse_1h = (df["c"].iloc[-2] / df["c"].iloc[-6] - 1) * 100
    if hausse_1h > config.HYPE_HAUSSE_1H_PCT * config.echelle():
        return False, f"+{hausse_1h:.1f} % sur 4 bougies : trop tard pour entrer"
    if d["base"] in donnees.tendances():
        return False, "en tendance sur CoinGecko : pic de buzz"
    return True, "pas de buzz anormal"


def correlation(ex, sym, etat, cache_h1):
    """VETO : pas deux positions qui sont en réalité le même pari (rendements 1 h, moteur v12)."""
    from moteurs.correlation_engine import veto_against_open
    if not etat["positions"]:
        return True, "aucune position ouverte"
    rendements = {}
    for s in [sym, *etat["positions"]]:
        if s not in cache_h1:
            cache_h1[s] = enrichir(bougies(ex, s, "1h", 120))
        rendements[s] = cache_h1[s]["c"].pct_change().dropna().tail(100).tolist()
    veto, raisons = veto_against_open(sym, rendements, list(etat["positions"]), config.CORRELATION_MAX)
    if veto:
        autre, c = raisons[0][len("correlation:"):].rsplit(":", 1)
        return False, f"corrélé à {float(c):.2f} avec {autre} : même pari"
    return True, "décorrélé des positions ouvertes"


PROMPT_VEILLE = """Tu es VEILLE, le bot d'actualité d'une équipe de trading crypto. Ta seule mission : détecter un risque de BAISSE à court terme (prochaines 12 heures) sur {nom} ({base}).

Voici les titres de presse des dernières 24 heures qui le mentionnent :
{titres}

Classe l'impact comme NEGATIF uniquement si un titre décrit un ÉVÉNEMENT RÉEL et défavorable qui concerne directement {nom} : piratage ou faille, fonds volés, délisting, procès ou action d'un régulateur, faillite, arrêt des retraits, départ de l'équipe dirigeante, déblocage massif de tokens.
Classe NEUTRE : analyses de prix, prédictions, promotions, opinions, rumeurs non confirmées, articles où {nom} n'est cité qu'en passant.
Classe POSITIF : événement réel et favorable (partenariat majeur confirmé, listing important, mise à jour réussie).
N'invente rien qui ne figure pas dans les titres.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte ni balise autour :
{{"impact": "NEGATIF" | "NEUTRE" | "POSITIF", "titre_cle": "le titre décisif ou vide", "raison": "une phrase"}}"""


def actualite(base):
    """VETO : nouvelle grave repérée par l'armée de renseignement, mots dangereux (instantané), puis lecture par l'IA."""
    try:                                          # lecture seule, 0,3 s maximum : ne ralentit jamais le bot
        import lecture_renseignement as LR
        grave = LR.alerte_grave([LR.cle_actif(base)])
        if grave:
            return False, f"RENSEIGNEMENT : nouvelle grave « {grave['titre'][:90]} »"
    except Exception:
        pass
    nom = (donnees.annuaire().get(base) or (None, None))[1]
    limite = time.time() - config.ACTU_FENETRE_H * 3600
    motif_base = re.compile(rf"\b{re.escape(base)}\b")                    # symbole : sensible à la casse
    motif_nom = re.compile(rf"\b{re.escape(nom)}\b", re.I) if nom else None
    titres = [a["titre"] for a in donnees.actualites()
              if a["ts"] >= limite and (motif_base.search(a["titre"]) or (motif_nom and motif_nom.search(a["titre"])))]
    if not titres:
        return True, "aucune actualité récente"
    for t in titres:
        if any(m in t.lower() for m in config.MOTS_DANGER):
            return False, f"alerte presse : « {t[:90]} »"
    j = ia_json(config.MODELE_IA_VEILLE, PROMPT_VEILLE.format(
        nom=nom or base, base=base, titres="\n".join(f"- {t}" for t in titres[:15])))
    if j and j.get("impact") == "NEGATIF":
        return False, f"VEILLE : {j.get('raison', '')}"
    return True, f"{len(titres)} titres, rien d'alarmant"


# ========================= BOTS MARCHÉ ÉLARGI (v3) =======================
def liquidite():
    """VETO + VOTE : l'argent frais entre-t-il dans la crypto ? (offre de stablecoins, DefiLlama)"""
    v = donnees.stablecoins_7j()
    if v is None:
        return True, None, "offre de stablecoins indisponible"
    if v < config.LIQUIDITE_SORTIE_PCT:
        return False, 0.0, f"stablecoins {v:+.2f} % sur 7 j : l'argent sort de la crypto"
    vote = 1.0 if v > config.LIQUIDITE_ENTREE_PCT else 0.5
    return True, vote, f"stablecoins {v:+.2f} % sur 7 j"


def macro():
    """VETO + VOTE : appétit pour le risque (Nasdaq) et stress sur le dollar (DXY)."""
    m = donnees.macro()
    if m is None:
        return True, None, "données macro indisponibles"
    nasdaq_ok, dxy_stress = m
    if not nasdaq_ok and dxy_stress:
        return False, 0.0, "Nasdaq sous sa moyenne 50 j et dollar en forte hausse : aversion au risque"
    vote = (int(nasdaq_ok) + int(not dxy_stress)) / 2
    return True, vote, f"Nasdaq {'au-dessus' if nasdaq_ok else 'sous'} sa moyenne, dollar {'en stress' if dxy_stress else 'calme'}"


def positionnement(base):
    """VETO + VOTE : la foule est-elle trop acheteuse ? Les gros traders sont-ils plus optimistes qu'elle ?"""
    p = donnees.positionnement(f"{base}USDT")
    if p is None:
        return True, None, "pas de données de positionnement"
    foule, gros = p
    if foule > config.POS_FOULE_MAX:
        return False, 0.0, f"foule {foule:.2f}x plus acheteuse : trop de monde du même côté"
    vote = 1.0 if gros > foule * 1.05 else (0.5 if gros > foule * 0.95 else 0.2)
    return True, vote, f"foule {foule:.2f}, gros traders {gros:.2f}"


def marches_mondiaux():
    """VETO + VOTE : panique à Wall Street (VIX) et santé des actions américaines (S&P 500)."""
    m = donnees.marches_mondiaux()
    if m is None:
        return True, None, "marchés mondiaux indisponibles"
    spx_ok, vix_stress, vix = m
    if vix_stress:
        return False, 0.0, f"VIX à {vix:.0f} : panique sur les marchés mondiaux"
    return True, (1.0 if spx_ok else 0.3), f"S&P 500 {'au-dessus' if spx_ok else 'sous'} sa moyenne 50 j, VIX {vix:.0f}"


def attention():
    """VETO : quand le grand public se rue sur le sujet, le sommet n'est souvent pas loin."""
    a = donnees.attention()
    if a is None:
        return True, "attention du public indisponible"
    if a > config.ATTENTION_PIC_X:
        return False, f"consultations Wikipedia x{a:.1f} : le grand public arrive, prudence"
    return True, f"attention du public normale (x{a:.1f})"


def recherche(base):
    """VETO : la recherche fondamentale hebdomadaire a-t-elle exclu cette crypto ?"""
    import datetime as dt
    import os
    if not os.path.exists("recherche_hebdo.json"):
        return True, "pas de recherche fondamentale"
    try:
        with open("recherche_hebdo.json", encoding="utf-8") as f:
            r = json.load(f)
        age = (dt.date.today() - dt.date.fromisoformat(r["date"])).days
    except Exception:
        return True, "recherche fondamentale illisible"
    if age > config.RECHERCHE_AGE_MAX_J:
        return True, f"recherche fondamentale trop ancienne ({age} j), ignorée"
    f = r["fiches"].get(base)
    if f and f["verdict"] == "EXCLU":
        return False, "recherche fondamentale : " + "; ".join(f["raisons"])
    return True, "recherche fondamentale : rien à signaler" if f else "hors du champ de la recherche"


# ============================= DÉVELOPPEURS =============================
def developpeurs(base):
    """VOTE léger : projet vivant ou abandonné ? (utile surtout pour écarter les projets morts)"""
    c = donnees.commits_4_semaines(base)
    if c is None:
        return None, "données développeurs indisponibles"
    if c >= config.DEV_COMMITS_ACTIF:
        return 1.0, f"{c} commits en 4 semaines : projet actif"
    if c > 0:
        return 0.6, f"{c} commits en 4 semaines"
    return 0.2, "aucun commit en 4 semaines : projet à l'abandon ?"


# ============================ CONTRADICTEUR (IA) ========================
PROMPT_CONTRADICTEUR = """Tu es CONTRADICTEUR, le dernier contrôle d'une équipe de bots de trading crypto (Binance spot, achat uniquement, sans levier). Les autres bots ont voté majoritairement pour ACHETER {paire}. Ton unique mission : protéger le capital en cherchant activement les raisons de NE PAS acheter.

Plan prévu si tu valides : achat immédiat, stop-loss à 1,5 ATR sous l'entrée, stop remonté au prix d'entrée dès +1 ATR et demi de gain, puis stop suiveur à 2 ATR du plus haut. Horizon : quelques heures, 12 h maximum.

Réponds PASSE si au moins un de ces points est vrai :
- les bots se contredisent sur un point important ;
- la hausse est déjà avancée (RSI élevé, prix loin de sa moyenne, bougies récentes très grandes) ;
- le volume baisse pendant que le prix monte ;
- le funding est élevé ou l'open interest chute ;
- les gros ordres sont vendeurs ;
- le sentiment global est en avidité extrême ;
- tu as un doute, quel qu'il soit.
- le dossier viole un des principes ci-dessous.
Principes tirés de l'histoire financière (19e-21e siècle), à vérifier un par un :
1. Couper vite une perte, ne jamais renforcer une position perdante (leçon de Jesse Livermore).
2. Suivre la tendance de fond plutôt que la combattre (Livermore, les Tortues de Richard Dennis).
3. Prudence quand la foule est euphorique, opportunité quand elle panique mais que la tendance de fond tient (principe attribué à Nathan Rothschild, repris par Warren Buffett).
4. Marge de sécurité : pas d'achat quand le prix est déjà loin de sa valeur moyenne (Benjamin Graham).
5. Les bulles s'auto-entretiennent puis se retournent brutalement ; sortir dès que la thèse est invalidée (George Soros).
6. Défense d'abord : la priorité est de ne pas perdre, le gain vient ensuite (Paul Tudor Jones).
7. Éviter la ruine à tout prix, se méfier des événements rares et violents (Nassim Taleb, Ed Thorp).
8. Un avantage statistique modeste, répété avec discipline, bat les convictions fortes (Jim Simons).
Réponds ACHAT uniquement si toutes les données concordent et qu'aucun risque clair n'apparaît.
N'invente aucune information absente du dossier. Tu ne connais pas l'avenir : juge la solidité du dossier, pas l'espoir de gain.
La confiance (0-100) mesure la solidité du dossier. Un ACHAT avec une confiance sous 60 n'a pas de sens : dans ce cas, réponds PASSE.

Dossier :
{dossier}

Réponds UNIQUEMENT avec un objet JSON valide, sans texte ni balise autour :
{{"verdict": "ACHAT" | "PASSE", "confiance": 0-100, "risque_principal": "une phrase", "raison": "une phrase"}}"""


DERNIER_CONTRADICTEUR = {}


def contradicteur(sym, d, avis, sentiment):
    df = d["df"]
    der = df.iloc[-2]
    dossier = {
        "paire": sym,
        "clotures_15min_recentes": [round(float(x), 8) for x in df["c"].iloc[-26:-1]],
        "volumes_15min_recents": [round(float(x), 2) for x in df["v"].iloc[-13:-1]],
        "rsi": round(float(der["rsi"]), 1),
        "ecart_prix_ema20_pct": round(float((der["c"] / der["ema20"] - 1) * 100), 2),
        "atr_pct": round(float(der["atr"] / der["c"] * 100), 2),
        "variation_24h_pct": round(float(d["hausse24h"]), 2),
        "sentiment_global_0_100": sentiment,
        "avis_des_bots": avis,
    }
    DERNIER_CONTRADICTEUR.clear()
    j = ia_json(config.MODELE_IA_CONTRADICTEUR,
                PROMPT_CONTRADICTEUR.format(paire=sym, dossier=json.dumps(dossier, ensure_ascii=False, indent=1)))
    if not j or j.get("verdict") not in ("ACHAT", "PASSE"):
        return None, "IA indisponible ou réponse invalide"
    conf = max(0.0, min(float(j.get("confiance", 0)), 100.0))
    DERNIER_CONTRADICTEUR.update(verdict=j["verdict"], confiance=conf)       # pour la calibration
    vote = conf / 100 if j.get("verdict") == "ACHAT" and conf >= 60 else 0.0
    return vote, f"{j.get('verdict')} ({conf:.0f}) : {j.get('raison', '')} | risque : {j.get('risque_principal', '')}"


# ================================ LEADER ================================
def leader(votes, poids):
    """Score pondéré. Un bot noté sous 5/10 a un poids de 0 : il est coupé."""
    total = somme = 0.0
    for nom, (v, _) in votes.items():
        if v is None:
            continue
        w = poids.get(nom, 1.0)
        total += w
        somme += w * v
    return somme / total if total else 0.0
