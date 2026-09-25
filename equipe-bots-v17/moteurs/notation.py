"""NOTE DE 0 À 5 d'un titre (action, ETF, crypto) + moment d'achat ou de vente — calculs purs, sans réseau.

Cinq avis indépendants, chacun noté de 0 à 5 puis pondérés (un avis absent est simplement retiré) :
  technique 30 %  : tendance (moyennes 50/200 j), élan 3/6 mois, RSI, distance au plus haut d'un an
  analystes 20 %  : consensus des banques et bureaux d'analyse (Yahoo : 1 = achat fort ... 5 = vente) + objectif de cours
  fondamentaux 15 % : croissance du chiffre d'affaires et des bénéfices, marges, valorisation, endettement
  actualité 20 %  : ton des titres de presse des 7 derniers jours sur ce titre
  contexte 15 %   : effet du contexte mondial (géopolitique, taux, énergie, alimentation...) sur son secteur

5 = meilleure option du moment selon ces critères. Ce n'est PAS une promesse de gain : une note résume des
informations publiques déjà connues du marché.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

POIDS = {"technique": 0.30, "analystes": 0.20, "fondamentaux": 0.15, "actualite": 0.20, "contexte": 0.15}
LIBELLES = {5: "meilleure option", 4: "favorable", 3: "neutre", 2: "défavorable", 1: "à éviter", 0: "à éviter"}

POSITIFS = ["surge", "soar", "jump", "rally", "beat", "record high", "upgrade", "rises", "rose", "gain", "strong",
            "growth", "boost", "approval", "deal", "wins", "hausse", "bondit", "grimpe", "relève", "record", "progresse",
            "rebond", "dépasse", "depasse", "accord", "contrat", "succès", "succes", "optimis", "solide", "envol"]
NEGATIFS = ["plunge", "slump", "tumble", "falls", "fell", "drop", "miss", "downgrade", "lawsuit", "probe", "recall",
            "crisis", "war", "sanction", "tariff", "default", "bankrupt", "layoff", "warning", "strike", "shortage",
            "fraud", "chute", "recule", "plonge", "abaisse", "baisse", "crise", "guerre", "faillite", "licenci",
            "enquête", "enquete", "avertissement", "grève", "greve", "pénurie", "penurie", "fraude", "perte", "loss",
            "sell-off", "effondr", "inquiet", "tension"]
EXPRESSIONS_POSITIVES = ["rate cut", "rate cuts", "cuts rates", "baisse des taux", "baisse ses taux", "inflation cools",
                         "inflation ralentit", "ceasefire", "cessez-le-feu", "trade deal", "accord commercial"]


def _borne(x: float, bas: float = 0.0, haut: float = 5.0) -> float:
    return max(bas, min(haut, x))


def _ok(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# ------------------------------------------------------------------ indicateurs
def indicateurs(df: pd.DataFrame) -> Optional[Dict]:
    """df : bougies JOURNALIÈRES (Open, High, Low, Close), au moins 60 jours."""
    if df is None or len(df) < 60:
        return None
    c = df["Close"].astype(float)
    h, b = df["High"].astype(float), df["Low"].astype(float)
    if not np.isfinite(c.iloc[-1]) or c.iloc[-1] <= 0:
        return None
    delta = c.diff()
    hausse = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    baisse = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + hausse / baisse.replace(0, np.nan))
    tr = pd.concat([h - b, (h - c.shift()).abs(), (b - c.shift()).abs()], axis=1).max(axis=1)
    dernier = float(c.iloc[-1])

    def perf(n):
        return float(c.iloc[-1] / c.iloc[-n - 1] - 1) * 100 if len(c) > n else None
    return {
        "close": dernier,
        "sma20": float(c.rolling(20).mean().iloc[-1]),
        "sma50": float(c.rolling(50).mean().iloc[-1]),
        "sma200": float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None,
        "rsi": float(rsi.iloc[-1]) if np.isfinite(rsi.iloc[-1]) else 50.0,
        "atr": float(tr.rolling(14).mean().iloc[-1]),
        "perf_1m": perf(21), "perf_3m": perf(63), "perf_6m": perf(126), "perf_12m": perf(250),
        "haut_52s": float(c.iloc[-252:].max()),
        "dist_haut_pct": (dernier / float(c.iloc[-252:].max()) - 1) * 100,
    }


# ------------------------------------------------------------------ les cinq avis
def note_technique(ind: Optional[Dict]) -> Tuple[Optional[float], List[str]]:
    if not ind:
        return None, ["historique de cours insuffisant"]
    n, r = 0.0, []
    if ind["close"] > ind["sma50"]:
        n += 1
        r.append("au-dessus de sa moyenne 50 jours")
    else:
        r.append("sous sa moyenne 50 jours")
    if ind["sma200"] is not None:
        if ind["sma50"] > ind["sma200"]:
            n += 1
            r.append("tendance de fond haussière (50 j > 200 j)")
        else:
            r.append("tendance de fond baissière (50 j < 200 j)")
    else:
        n += 0.5
    if _ok(ind["perf_6m"]) and ind["perf_6m"] > 0:
        n += 1
    if _ok(ind["perf_3m"]) and ind["perf_3m"] > 0:
        n += 0.5
    rsi = ind["rsi"]
    if 40 <= rsi <= 70:
        n += 1
    elif rsi > 75:
        n -= 0.5
        r.append(f"surachat (RSI {rsi:.0f})")
    elif rsi < 30:
        r.append(f"survente (RSI {rsi:.0f})")
    if ind["dist_haut_pct"] > -15:
        n += 0.5
    else:
        r.append(f"{ind['dist_haut_pct']:.0f} % sous son plus haut d'un an")
    return _borne(n), r


def note_analystes(info: Dict) -> Tuple[Optional[float], List[str]]:
    rec, nb = info.get("recommendationMean"), info.get("numberOfAnalystOpinions")
    if not _ok(rec) or not _ok(nb) or nb < 3:
        return None, []
    n = (5 - float(rec)) * 5 / 4                     # 1 (achat fort) -> 5 ; 3 (conserver) -> 2,5 ; 5 (vente) -> 0
    r = [f"{int(nb)} analystes : {info.get('recommendationKey', '?').replace('_', ' ')} (moyenne {rec:.1f}/5)"]
    cible, cours = info.get("targetMeanPrice"), info.get("currentPrice") or info.get("regularMarketPrice")
    if _ok(cible) and _ok(cours) and cours > 0:
        pot = (cible / cours - 1) * 100
        r.append(f"objectif moyen {cible:.2f} ({pot:+.0f} %)")
        n += 0.5 if pot > 15 else (-0.5 if pot < 0 else 0)
    return _borne(n), r


def note_fondamentaux(info: Dict) -> Tuple[Optional[float], List[str]]:
    if (info.get("quoteType") or "").upper() != "EQUITY":
        return None, []
    n, r, vus = 2.5, [], 0
    ca, bn, marge = info.get("revenueGrowth"), info.get("earningsGrowth"), info.get("profitMargins")
    per, dette = info.get("forwardPE"), info.get("debtToEquity")
    if _ok(ca):
        vus += 1
        n += 0.75 if ca > 0.05 else (-0.75 if ca < 0 else 0)
        r.append(f"chiffre d'affaires {ca * 100:+.0f} %")
    if _ok(bn):
        vus += 1
        n += 0.5 if bn > 0.05 else (-0.5 if bn < 0 else 0)
        r.append(f"bénéfices {bn * 100:+.0f} %")
    if _ok(marge):
        vus += 1
        n += 0.5 if marge > 0.10 else (-1 if marge < 0 else 0)
    if _ok(per):
        vus += 1
        if 0 < per < 25:
            n += 0.5
        elif per > 50 or per <= 0:
            n -= 0.5
        r.append(f"PER attendu {per:.0f}")
    if _ok(dette) and dette > 200:
        n -= 0.5
        r.append("endettement élevé")
    return (_borne(n), r) if vus else (None, [])


def sentiment_lexical(titres: List[str]) -> Optional[float]:
    """Ton moyen de titres de presse, de -2 (très négatif) à +2 (très positif). Secours sans IA."""
    if not titres:
        return None
    scores = []
    for t in titres:
        t = t.lower()
        p = 0
        for expr in EXPRESSIONS_POSITIVES:            # « baisse des taux » est une bonne nouvelle pour les marchés
            if expr in t:
                p += 1
                t = t.replace(expr, " ")
        p += sum(1 for m in POSITIFS if re.search(rf"\b{re.escape(m)}", t))
        n = sum(1 for m in NEGATIFS if re.search(rf"\b{re.escape(m)}", t))
        scores.append((p > n) - (n > p))
    return _borne(sum(scores) / len(scores) * 2, -2, 2)


def ton_titre(titre: str) -> Optional[int]:
    """Ton d'UN titre : -1, 0 ou +1 ; None s'il ne contient aucun mot révélateur (on ne sait pas)."""
    t = titre.lower()
    p = 0
    for expr in EXPRESSIONS_POSITIVES:
        if expr in t:
            p += 1
            t = t.replace(expr, " ")
    p += sum(1 for m in POSITIFS if re.search(rf"\b{re.escape(m)}", t))
    n = sum(1 for m in NEGATIFS if re.search(rf"\b{re.escape(m)}", t))
    if not p and not n:
        return None
    return (p > n) - (n > p)


def note_depuis_ton(ton: Optional[float]) -> Optional[float]:
    return None if ton is None else _borne(2.5 + float(ton) * 1.25)


# ------------------------------------------------------------------ note finale et décision
def combiner(avis: Dict[str, Optional[float]]) -> Optional[float]:
    presents = {k: v for k, v in avis.items() if v is not None and k in POIDS}
    if "technique" not in presents:                   # sans cours fiables, pas de note
        return None
    total = sum(POIDS[k] for k in presents)
    brute = sum(POIDS[k] * v for k, v in presents.items()) / total
    return round(_borne(brute) * 2) / 2               # demi-points : 0 ; 0,5 ; ... ; 5


def fr(note: float) -> str:
    return f"{note:g}".replace(".", ",")


def etoiles(note: float) -> str:
    pleines = int(note)
    return "★" * pleines + ("½" if note - pleines >= 0.5 else "") + "☆" * (5 - pleines - (1 if note - pleines >= 0.5 else 0))


def libelle(note: float) -> str:
    return LIBELLES[int(note)]


def decision(note: float, ind: Dict, detenu: bool, cible: Optional[float] = None) -> Dict:
    """Que faire MAINTENANT : acheter, attendre, garder, alléger/vendre, éviter — avec les niveaux de prix."""
    close, atr = ind["close"], ind["atr"] if _ok(ind["atr"]) and ind["atr"] > 0 else ind["close"] * 0.02
    stop = max(close - 2 * atr, 0.0)
    objectif = cible if _ok(cible) and cible > close else close + 3 * atr
    sous_50 = close < ind["sma50"]
    elan_negatif = _ok(ind["perf_3m"]) and ind["perf_3m"] < 0
    if detenu:
        if note <= 2 or (sous_50 and elan_negatif):
            return {"action": "VENDRE / ALLÉGER", "urgence": True,
                    "texte": "les signaux se sont retournés : alléger ou vendre, ou au minimum protéger sous "
                             f"{stop:.4g}", "stop": stop, "objectif": None}
        if note >= 4:
            return {"action": "GARDER", "urgence": False, "stop": stop, "objectif": objectif,
                    "texte": f"garder ; renforcer seulement sur un repli vers {ind['sma20']:.4g} ; protection {stop:.4g}"}
        return {"action": "GARDER, SURVEILLER", "urgence": False, "stop": stop, "objectif": objectif,
                "texte": f"garder tant que le cours reste au-dessus de {stop:.4g}"}
    if note >= 4 and not sous_50:
        if ind["rsi"] >= 70:
            return {"action": "ATTENDRE UN REPLI", "urgence": False, "stop": stop, "objectif": objectif,
                    "texte": f"bon dossier mais déjà très monté (RSI {ind['rsi']:.0f}) : attendre un repli vers "
                             f"{ind['sma20']:.4g}"}
        return {"action": "ACHETER", "urgence": note >= 5, "stop": stop, "objectif": objectif,
                "texte": f"entrée autour de {close:.4g}, protection {stop:.4g}, objectif {objectif:.4g}"}
    if note >= 3:
        return {"action": "ATTENDRE", "urgence": False, "stop": stop, "objectif": objectif,
                "texte": "pas de signal net : à surveiller"}
    return {"action": "ÉVITER", "urgence": False, "stop": stop, "objectif": None,
            "texte": "trop de signaux défavorables pour l'instant"}


def noter(df: pd.DataFrame, info: Dict, ton_presse: Optional[float], impact_secteur: Optional[float],
          detenu: bool = False) -> Optional[Dict]:
    ind = indicateurs(df)
    nt, rt = note_technique(ind)
    na, ra = note_analystes(info or {})
    nf, rf = note_fondamentaux(info or {})
    avis = {"technique": nt, "analystes": na, "fondamentaux": nf, "actualite": note_depuis_ton(ton_presse),
            "contexte": note_depuis_ton(impact_secteur)}
    note = combiner(avis)
    if note is None:
        return None
    dec = decision(note, ind, detenu, (info or {}).get("targetMeanPrice"))
    try:                                          # lecture des bougies japonaises de la dernière journée FERMÉE
        from moteurs import chandeliers as CH
        bougies = CH.lire(df["Open"].to_numpy(), df["High"].to_numpy(), df["Low"].to_numpy(),
                          df["Close"].to_numpy(), -2)
    except Exception:
        bougies = []
    return {"note": note, "avis": avis, "raisons": rt + ra + rf, "indicateurs": ind, "bougies": bougies, **dec}
