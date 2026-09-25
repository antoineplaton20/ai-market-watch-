"""GÈNES : chaque stratégie est un génome. Le même code décide en backtest (sur des colonnes entières)
et en réel (sur la dernière bougie fermée) : ce qui est évolué est exactement ce qui est tradé.

9 espèces, tirées des grandes techniques documentées du trading, se disputent la place :
  MOMENTUM   : acheter la force confirmée par l'équipe de bots (momentum de séries, Moskowitz)
  REVERSION  : acheter un creux dans une tendance de fond haussière
  BREAKOUT   : cassure d'un plus haut avec volume (canaux de Donchian, les Tortues de Richard Dennis)
  RANGE      : acheter le bas d'un couloir étroit
  BOLLINGER  : sortie de compression de volatilité (bandes de John Bollinger)
  MACD       : croisement de la MACD au-dessus de zéro (Gerald Appel)
  CONNORS    : RSI 2 périodes très bas au-dessus de la moyenne 200 (Larry Connors)
  CONTRARIAN : acheter la panique extrême (principe attribué à Rothschild, repris par Buffett)
  CHANDELIERS: figures de rebond des bougies japonaises après une baisse (Steve Nison), avec ou sans
               confirmation et volume — voir moteurs/chandeliers.py
Ce que l'évolution ne peut JAMAIS toucher : risque 1 % par trade, -5 % par jour, stop posé chez Binance."""
import json
import os
import random
import numpy as np
import config
from moteurs import chandeliers as CH

ESPECES = ["MOMENTUM", "REVERSION", "BREAKOUT", "RANGE", "BOLLINGER", "MACD", "CONNORS", "CONTRARIAN", "CHANDELIERS"]
MOTIFS = ["REBOND"] + list(CH.REBOND)          # REBOND = n'importe quelle figure de rebond
VOTANTS = ["TENDANCE", "MOMENTUM", "MULTI_UNITES", "CARNET", "DERIVES", "LIQUIDITE", "MACRO", "POSITIONNEMENT",
           "MARCHES_MONDIAUX"]
VETOS = ["METEO", "ANTI_HYPE", "DERIVES_VETO", "PEUR_AVIDITE", "CALENDRIER",
         "LIQUIDITE_VETO", "MACRO_VETO", "POSITIONNEMENT_VETO", "MARCHES_MONDIAUX_VETO", "ATTENTION_VETO"]
LOOKBACKS = [10, 20, 30, 50, 75, 100]
LOOKBACKS_STOP = [5, 10, 20]

# nom : (min, max) pour les gènes continus
CONTINUS = {
    "seuil_vote": (0.30, 0.95), "atr_min_pct": (0.10, 1.00), "atr_max_mult": (0.5, 2.0),
    "stop_atr": (0.8, 3.0), "secu_r": (0.5, 2.0), "trailing_atr": (1.0, 4.0),
    "objectif_atr": (2.0, 10.0), "horizon_mult": (0.5, 2.0),
    "rsi_seuil": (15.0, 45.0), "ecart_min_pct": (0.5, 5.0), "vol_x": (1.0, 4.0),
    "bande_pct": (0.3, 3.0), "largeur_max_pct": (3.0, 20.0),
    "bb_k": (1.0, 3.0), "squeeze_pct": (1.0, 10.0), "rsi2_seuil": (2.0, 25.0), "peur_seuil": (5.0, 35.0),
    "part_frac": (0.0, 0.7), "part_r": (0.5, 3.0),
}
CONTINUS.update({f"poids_{v}": (0.0, 2.0) for v in VOTANTS})

FICHIER_CHAMPION = "champion.json"
FICHIER_CHALLENGER = "challenger.json"


# ================================ GÉNOMES ================================
def genome_defaut():
    """Le comportement de la v3, pour démarrer : c'est le premier champion à battre."""
    g = {"espece": "MOMENTUM", "lookback": 20, "seuil_vote": config.SEUIL_VOTE,
         "atr_min_pct": config.ATR_MIN_PCT, "atr_max_mult": 1.0, "stop_atr": config.STOP_ATR,
         "secu_r": config.SECURISATION_R, "trailing_atr": config.TRAILING_ATR,
         "objectif_atr": config.OBJECTIF_ATR, "horizon_mult": 1.0, "rsi_seuil": 30.0,
         "ecart_min_pct": 2.0, "vol_x": 2.0, "bande_pct": 1.0, "largeur_max_pct": 8.0,
         "bb_k": 2.0, "squeeze_pct": 4.0, "rsi2_seuil": 10.0, "peur_seuil": 20.0,
         "part_frac": 0.0, "part_r": 1.0, "type_stop": "ATR", "lookback_stop": 10, "macd_zero": True,
         "motif": "REBOND", "confirmation": True, "bougie_volume": False}
    g.update({f"poids_{v}": 1.0 for v in VOTANTS})
    g.update({f"veto_{v}": True for v in VETOS})
    g["id"] = "defaut"
    return g


def aleatoire(espece):
    g = {"espece": espece, "lookback": random.choice(LOOKBACKS), "lookback_stop": random.choice(LOOKBACKS_STOP),
         "type_stop": random.choice(["ATR", "STRUCTURE"]), "macd_zero": random.random() < 0.5,
         "motif": random.choice(MOTIFS), "confirmation": random.random() < 0.5, "bougie_volume": random.random() < 0.3}
    for k, (a, b) in CONTINUS.items():
        g[k] = random.uniform(a, b)
    for v in VETOS:
        g[f"veto_{v}"] = random.random() < 0.7
    g["id"] = _nouvel_id()
    return g


def muter(g, taux=None):
    taux = config.EVO_TAUX_MUTATION if taux is None else taux
    e = dict(g)
    for k, (a, b) in CONTINUS.items():
        if random.random() < taux:
            e[k] = float(np.clip(e[k] + random.gauss(0, 0.15 * (b - a)), a, b))
    if random.random() < taux:
        e["lookback"] = random.choice(LOOKBACKS)
    if random.random() < taux:
        e["lookback_stop"] = random.choice(LOOKBACKS_STOP)
    if random.random() < taux / 2:
        e["type_stop"] = "STRUCTURE" if e.get("type_stop") == "ATR" else "ATR"
    if random.random() < taux / 2:
        e["macd_zero"] = not e.get("macd_zero", True)
    if random.random() < taux:
        e["motif"] = random.choice(MOTIFS)
    if random.random() < taux / 2:
        e["confirmation"] = not e.get("confirmation", True)
    if random.random() < taux / 2:
        e["bougie_volume"] = not e.get("bougie_volume", False)
    for v in VETOS:
        if random.random() < taux / 3:
            e[f"veto_{v}"] = not e[f"veto_{v}"]
    e["id"] = _nouvel_id()
    return e


def croiser(p1, p2):
    """Enfant = mélange gène par gène de deux parents de la même espèce."""
    e = {k: (p1[k] if random.random() < 0.5 else p2[k]) for k in p1 if k not in ("id", "espece")}
    e["espece"] = p1["espece"]
    e["id"] = _nouvel_id()
    return e


def _nouvel_id():
    return "%08x" % random.getrandbits(32)


def charger(fichier):
    if not os.path.exists(fichier):
        return None
    try:
        with open(fichier, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None                    # fichier en cours d'écriture ou abîmé : on garde le comportement sûr


def completer(g):
    """Un génome d'une version précédente reçoit les nouveaux gènes avec leur valeur par défaut."""
    if g is None:
        return None
    base = genome_defaut()
    base.update(g)
    return base


def _compatible(c):
    """Un génome évolué en 1 h n'a pas de sens en 15 min : on l'ignore si l'unité a changé."""
    return c and c.get("unite", config.UNITE_BOUGIE) == config.UNITE_BOUGIE


def champion():
    c = charger(FICHIER_CHAMPION)
    return completer(c["genome"]) if _compatible(c) else genome_defaut()


def challenger():
    c = charger(FICHIER_CHALLENGER)
    return completer(c["genome"]) if _compatible(c) else None


def distance_stop(g, F):
    """Distance du stop en ATR. ATR : fixe. STRUCTURE : sous le plus bas récent (là où la thèse est invalidée)."""
    if g.get("type_stop", "ATR") == "STRUCTURE":
        ll = F[f"ll_{g['lookback_stop']}"]
        d = (F["c"] - ll) / F["atr"] + 0.2
        return np.clip(np.nan_to_num(d, nan=g["stop_atr"]), 0.5, 4.0)
    return np.full_like(np.asarray(F["c"], dtype=float), g["stop_atr"])


def params_sortie(g, unite=None):
    unite = unite or config.UNITE_BOUGIE
    return {"stop_atr": g["stop_atr"], "secu_r": g["secu_r"], "trailing_atr": g["trailing_atr"],
            "objectif_atr": g["objectif_atr"], "part_frac": g.get("part_frac", 0.0), "part_r": g.get("part_r", 1.0),
            "horizon_bougies": max(4, int(config.HORIZON_H[unite] * g["horizon_mult"] * 60 / config.MINUTES[unite]))}


# ============================ DÉCISION COMMUNE ============================
def decider(g, F, unite):
    """F : dictionnaire de caractéristiques (tableaux numpy en backtest, scalaires en réel).
    Renvoie (signal booléen, score de l'équipe)."""
    ech = config.echelle(unite)
    num = 0.0
    den = 0.0
    for v in VOTANTS:
        x = np.asarray(F[f"vote_{v}"], dtype=float)
        w = g[f"poids_{v}"]
        ok = ~np.isnan(x)
        num = num + np.where(ok, w * np.nan_to_num(x), 0.0)
        den = den + np.where(ok, w, 0.0)
    score = np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)
    bloque = np.zeros_like(score, dtype=bool)
    for v in VETOS:
        if g[f"veto_{v}"]:
            bloque = bloque | np.asarray(F[f"veto_{v}"], dtype=bool)
    atr_pct = F["atr"] / F["c"] * 100
    base = (score >= g["seuil_vote"]) & ~bloque & (F["hausse_24h"] <= config.HAUSSE_24H_MAX_PCT) \
        & (atr_pct >= g["atr_min_pct"]) & (atr_pct <= config.ATR_MAX_PCT * ech * g["atr_max_mult"])
    cond = condition_espece(g, F, unite)
    return base & cond, score


def condition_espece(g, F, unite):
    """Le déclencheur propre à chaque espèce (sans le vote de l'équipe ni les vetos)."""
    ech = config.echelle(unite)
    c, e20 = F["c"], F["ema20"]
    hh, ll = F[f"hh_{g['lookback']}"], F[f"ll_{g['lookback']}"]
    esp = g["espece"]
    if esp == "MOMENTUM":
        return np.abs(c / e20 - 1) * 100 <= config.ECART_EMA20_MAX_PCT * ech
    if esp == "REVERSION":
        return (F["rsi"] < g["rsi_seuil"]) & (c < e20 * (1 - g["ecart_min_pct"] / 100)) & (F["sup1"] == 1)
    if esp == "BREAKOUT":
        return (c > hh) & (F["v"] > g["vol_x"] * F["vol_moy"])
    if esp == "RANGE":
        return ((hh - ll) / c * 100 < g["largeur_max_pct"]) & (c <= ll * (1 + g["bande_pct"] / 100))
    if esp == "BOLLINGER":
        return (F["bb_largeur_prec"] < g["squeeze_pct"]) & (c > F["sma20"] + g["bb_k"] * F["std20"])
    if esp == "MACD":
        croise = (F["macd_hist"] > 0) & (F["macd_hist_prec"] <= 0)
        return croise & (F["macd"] > 0) if g.get("macd_zero", True) else croise
    if esp == "CONNORS":
        return (F["rsi2"] < g["rsi2_seuil"]) & (c > F["sma200"])
    if esp == "CHANDELIERS":
        motif = g.get("motif", "REBOND")
        if g.get("confirmation", True):         # la figure d'hier + clôture d'aujourd'hui au-dessus de son plus haut
            ok = np.asarray(F[f"bougie_{motif}_prec"], dtype=bool) & (np.nan_to_num(c - F["h_prec"], nan=-1.0) > 0)
        else:
            ok = np.asarray(F[f"bougie_{motif}"], dtype=bool)
        ok = ok & ~np.asarray(F["bougie_CHUTE"], dtype=bool)          # jamais sur une figure de chute
        if g.get("bougie_volume", False):
            ok = ok & (F["v"] > g["vol_x"] * F["vol_moy"])
        return ok
    return (np.nan_to_num(F["fng"], nan=50) <= g["peur_seuil"]) & (F["rsi"] < g["rsi_seuil"])   # CONTRARIAN


def indicateurs_encyclopedie(c):
    """Indicateurs des techniques classiques, calculés de la même façon en backtest et en réel."""
    import pandas as pd
    s = pd.Series(np.asarray(c, dtype=float))
    sma20, std20 = s.rolling(20).mean(), s.rolling(20).std()
    ema12, ema26 = s.ewm(span=12, adjust=False).mean(), s.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    perte = (-delta.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    largeur = 4 * std20 / sma20 * 100
    return {"sma20": sma20.to_numpy(), "std20": std20.to_numpy(), "sma200": s.rolling(200).mean().to_numpy(),
            "macd": macd.to_numpy(), "macd_hist": hist.to_numpy(), "macd_hist_prec": hist.shift(1).to_numpy(),
            "rsi2": (100 - 100 / (1 + gain / perte.replace(0, 1e-12))).to_numpy(),
            "bb_largeur_prec": largeur.shift(1).to_numpy()}


def caracteristiques_live(d, votes, vetos, contexte, flux=None):
    """Mêmes caractéristiques qu'en backtest, lues sur la dernière bougie FERMÉE."""
    df = d["df"]
    der = df.iloc[-2]
    F = {"c": float(der["c"]), "ema20": float(der["ema20"]), "rsi": float(der["rsi"]), "atr": float(der["atr"]),
         "v": float(der["v"]), "vol_moy": float(der["vol_moy"]), "sup1": d.get("sup1", np.nan),
         "hausse_24h": float(d["hausse24h"])}
    for n in sorted(set(LOOKBACKS + LOOKBACKS_STOP)):
        hh, ll = extremes(df["h"].to_numpy(), df["l"].to_numpy(), n)
        F[f"hh_{n}"], F[f"ll_{n}"] = float(hh[-2]), float(ll[-2])
    for k, x in indicateurs_encyclopedie(df["c"].to_numpy()).items():
        F[k] = float(x[-2])
    for k, x in CH.caracteristiques(df["o"].to_numpy(), df["h"].to_numpy(), df["l"].to_numpy(),
                                    df["c"].to_numpy()).items():
        F[k] = float(x[-2]) if k == "h_prec" else bool(x[-2])
    F["fng"] = contexte.get("sentiment") if contexte.get("sentiment") is not None else np.nan
    for v in VOTANTS:
        x = votes.get(v, (None, ""))[0]
        F[f"vote_{v}"] = np.nan if x is None else float(x)
    for v in VETOS:
        F[f"veto_{v}"] = (v in vetos) or bool(contexte.get(f"veto_{v}", False))
    if flux is not None:
        F["vote_CARNET"] = float(flux)      # même définition qu'en backtest
    return F


def extremes(h, l, n):
    """Plus haut / plus bas des n bougies PRÉCÉDENTES (sans la bougie en cours)."""
    import pandas as pd
    return (pd.Series(h).shift(1).rolling(n).max().to_numpy(),
            pd.Series(l).shift(1).rolling(n).min().to_numpy())


def decrire(g):
    esp = {"MOMENTUM": "acheter la force", "REVERSION": f"acheter les creux (RSI < {g['rsi_seuil']:.0f})",
           "BREAKOUT": f"cassure du plus haut {g['lookback']} bougies (volume x{g['vol_x']:.1f})",
           "RANGE": f"bas d'un couloir de {g['lookback']} bougies",
           "BOLLINGER": f"sortie de compression (bande {g['bb_k']:.1f} écarts-types)",
           "MACD": "croisement MACD" + (" au-dessus de zéro" if g.get("macd_zero", True) else ""),
           "CONNORS": f"RSI 2 < {g['rsi2_seuil']:.0f} au-dessus de la moyenne 200",
           "CONTRARIAN": f"panique extrême (peur <= {g['peur_seuil']:.0f})",
           "CHANDELIERS": f"bougies japonaises : {g.get('motif', 'REBOND').lower().replace('_', ' ')}"
                          + (" confirmée" if g.get("confirmation", True) else "")
                          + (" avec volume" if g.get("bougie_volume") else "")}[g["espece"]]
    vetos = [v for v in VETOS if g[f"veto_{v}"]]
    stop = "structure" if g.get("type_stop") == "STRUCTURE" else f"{g['stop_atr']:.1f} ATR"
    partiel = f" | prise partielle {g['part_frac']:.0%} à {g['part_r']:.1f} R" if g.get("part_frac", 0) > 0.05 else ""
    return (f"{g['espece']} ({esp}) | seuil {g['seuil_vote']:.2f} | stop {stop}{partiel} | "
            f"sécurisation {g['secu_r']:.1f} R | trailing {g['trailing_atr']:.1f} ATR | objectif {g['objectif_atr']:.1f} ATR"
            f" | vetos actifs : {len(vetos)}/{len(VETOS)}")
