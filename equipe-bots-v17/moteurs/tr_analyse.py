"""Analyse de la veille Trade Republic — aucun réseau ici (testable hors ligne).

Mêmes règles que pour Binance :
- uniquement des bougies FERMÉES (la bougie en cours est écartée d'après son heure de fin) ;
- 4h régime -> 1h tendance -> 15m signal -> 5m entrée : les 4 doivent être haussières ;
- porte d'opportunité v11 : potentiel brut > coûts Trade Republic (1 € par ordre + écart estimé) + marges.
Le 15m est reconstruit à partir du 5m et le 4h à partir du 1h (Yahoo ne fournit pas de 4h) :
moins de requêtes, et aucune bougie inventée.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import pandas as pd

import config
from indicateurs import enrichir
from moteurs.cost_engine import estimate
from moteurs.opportunity_engine import evaluate

MIN_MS = 60_000
_EPOQUE = pd.Timestamp("1970-01-01", tz="UTC")
BOUGIES_MIN = 60                  # l'EMA 50 a besoin d'un historique suffisant pour être fiable


def prix_lisible(x: float) -> str:
    """23080.0 -> « 23 080 » ; 182.35 -> « 182,35 » ; 0.012345 -> « 0,01235 »."""
    if x >= 1000:
        return f"{x:,.0f}".replace(",", "\u202f")
    if x >= 1:
        return f"{x:,.2f}".replace(",", "\u202f").replace(".", ",")
    return f"{x:.4g}".replace(".", ",")


def _signe(x: float) -> str:
    return ("+" if x >= 0 else "−") + f"{abs(x):.1f}".replace(".", ",") + " %"


def fermees(df: Optional[pd.DataFrame], minutes: int, maintenant_ms: float) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    return df[df["t"] + minutes * MIN_MS <= maintenant_ms].reset_index(drop=True)


def regrouper(df: pd.DataFrame, minutes: int, fin_ms: float) -> pd.DataFrame:
    """Regroupe des bougies FERMÉES en bougies de `minutes`, et ne garde que les bougies entièrement écoulées."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    x = df.set_index(pd.to_datetime(df["t"], unit="ms", utc=True))
    r = (x.resample(f"{minutes}min", origin="start_day", label="left", closed="left")
          .agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"})
          .dropna(subset=["c"]))
    t = (r.index - _EPOQUE) // pd.Timedelta("1ms")
    r = r.reset_index(drop=True)
    r.insert(0, "t", pd.Series(t, dtype="int64").to_numpy())
    return r[r["t"] + minutes * MIN_MS <= fin_ms].reset_index(drop=True)


def haussier(ligne) -> bool:
    return bool(ligne["c"] > ligne["ema50"] and ligne["ema20"] > ligne["ema50"])


def baissier(ligne) -> bool:
    return bool(ligne["c"] < ligne["ema50"] and ligne["ema20"] < ligne["ema50"])


def journalier(df: Optional[pd.DataFrame], taux: Optional[float], maintenant_ms: float) -> Optional[Dict]:
    """Tri quotidien : échanges médians sur 20 jours convertis en euros + tendance journalière (bougies fermées).
    taux = unités de la devise du titre pour 1 euro."""
    d = fermees(df, 1440, maintenant_ms)
    if len(d) < BOUGIES_MIN or not taux or taux != taux:
        return None
    e = enrichir(d)
    liq = float((d["c"] * d["v"]).tail(20).median()) / taux
    return {"ok": True, "liq": liq, "haussier": haussier(e.iloc[-1]),
            "age_j": (maintenant_ms - float(d["t"].iloc[-1])) / 86_400_000}


def analyser_titre(df5: Optional[pd.DataFrame], df1h: Optional[pd.DataFrame],
                   maintenant_ms: Optional[float] = None) -> Dict:
    """Lecture 4 unités d'un titre. Renvoie ok=False (+ raison) si les données ne permettent pas de conclure."""
    maintenant_ms = maintenant_ms if maintenant_ms is not None else time.time() * 1000
    c5, c1 = fermees(df5, 5, maintenant_ms), fermees(df1h, 60, maintenant_ms)
    if len(c5) < BOUGIES_MIN * 3 or len(c1) < BOUGIES_MIN:
        return {"ok": False, "raison": "historique insuffisant"}
    fin5, fin1 = float(c5["t"].iloc[-1]) + 5 * MIN_MS, float(c1["t"].iloc[-1]) + 60 * MIN_MS
    u = {"4h": enrichir(regrouper(c1, 240, fin1)), "1h": enrichir(c1),
         "15m": enrichir(regrouper(c5, 15, fin5)), "5m": enrichir(c5)}
    courts = [k for k, d in u.items() if len(d) < BOUGIES_MIN]
    if courts:
        return {"ok": False, "raison": "historique insuffisant en " + ", ".join(courts)}
    checks = {k: haussier(d.iloc[-1]) for k, d in u.items()}
    age_min = (maintenant_ms - fin5) / MIN_MS
    return {"ok": True, "checks": checks, "prix": float(u["5m"]["c"].iloc[-1]),
            "atr": float(u["15m"]["atr"].iloc[-1]), "age_min": age_min,
            "donnees_ok": age_min <= config.TR_DONNEES_AGE_MAX_MIN, "fin_bougie_ms": fin5,
            "haut": float(u["5m"]["h"].tail(3).max()), "bas": float(u["5m"]["l"].tail(3).min()),
            "b5": c5[["t", "h", "l"]].tail(600), "baissier_1h": baissier(u["1h"].iloc[-1])}


def cout(montant: Optional[float] = None):
    return estimate("trade_republic", montant or config.TR_MONTANT_ORDRE_EUR,
                    spread_pct=config.TR_SPREAD_ESTIME_PCT, slippage_pct=config.GLISSEMENT_PCT)


def opportunite(a: Dict, montant: Optional[float] = None):
    """Porte v11 appliquée à Trade Republic. Le risque (quota, doublons) est géré par la veille."""
    brut = config.OBJECTIF_ATR * a["atr"] / max(a["prix"], 1e-12) * 100
    return evaluate("BUY", a["checks"], risk_ok=True, data_ok=a["donnees_ok"], liquidity_ok=True,
                    spread_ok=config.TR_SPREAD_ESTIME_PCT <= config.SPREAD_MAX_PCT,
                    cost=cout(montant), gross_potential_pct=brut,
                    min_net_pct=config.OPPORTUNITE_MIN_NET_PCT,
                    safety_margin_pct=config.OPPORTUNITE_MARGE_SECURITE_PCT)


def nouvelle_position(instrument: Dict, a: Dict, opp, maintenant: Optional[float] = None) -> Dict:
    prix, atr = a["prix"], a["atr"]
    stop = prix - config.STOP_ATR * atr
    return {**instrument, "entree": prix, "stop": stop, "stop_initial": stop,
            "objectif": prix + config.OBJECTIF_ATR * atr, "atr": atr, "r": prix - stop,
            "plus_haut": prix, "securise": False, "ts": maintenant or time.time(),
            "controle_ms": a.get("fin_bougie_ms"),
            "cout_pct": opp.cost_pct, "net_pct": opp.net_potential_pct, "brut_pct": opp.gross_potential_pct}


def suivre(pos: Dict, a: Optional[Dict], maintenant: Optional[float] = None) -> Tuple[List[Tuple[str, str, bool]], Optional[Dict]]:
    """Fait avancer le suivi d'un signal. Renvoie (événements [(code, texte, important)], clôture ou None).
    Même logique que le GARDIEN Binance : stop, sécurisation à +1 R, stop suiveur, objectif, retournement."""
    maintenant = maintenant or time.time()
    evts, cloture = [], None

    def clore(raison, prix):
        brut = (prix / pos["entree"] - 1) * 100
        return {"isin": pos["isin"], "nom": pos["nom"], "ticker": pos["ticker"], "raison": raison,
                "entree": pos["entree"], "sortie": prix, "brut_pct": brut, "net_pct": brut - pos["cout_pct"],
                "debut": pos["ts"], "fin": maintenant}

    haut = bas = None
    if a and a.get("ok") and a.get("donnees_ok"):
        haut, bas = a["haut"], a["bas"]
        b5 = a.get("b5")
        if b5 is not None and pos.get("controle_ms"):
            # toutes les bougies 5 min fermées depuis le dernier contrôle (même après une pause de Yahoo)
            fen = b5[b5["t"] + 5 * MIN_MS > pos["controle_ms"]]
            haut, bas = (float(fen["h"].max()), float(fen["l"].min())) if len(fen) else (None, None)
            pos["controle_ms"] = a["fin_bougie_ms"]
    if haut is not None:
        pos["plus_haut"] = max(pos["plus_haut"], haut)
        if bas <= pos["stop"]:
            cloture = clore("stop", pos["stop"])
        elif haut >= pos["objectif"]:
            cloture = clore("objectif", pos["objectif"])
        elif a["baissier_1h"]:
            cloture = clore("retournement", a["prix"])
        else:
            if not pos["securise"] and pos["plus_haut"] >= pos["entree"] + config.SECURISATION_R * pos["r"]:
                pos["securise"] = True
                pos["stop"] = max(pos["stop"], pos["entree"])
                evts.append(("securiser", f"🔒 {_signe((pos['plus_haut'] / pos['entree'] - 1) * 100)} atteint : remonte ton ordre stop à ton prix d'achat. "
                             "Tu ne peux plus perdre sur cette ligne.", True))
            if pos["securise"]:
                suiveur = pos["plus_haut"] - config.TRAILING_ATR * pos["atr"]
                if suiveur >= pos["stop"] + pos["atr"]:              # pas de 1 ATR : pas de message à chaque bougie
                    pos["stop"] = suiveur
                    evts.append(("suiveur", f"↗️ remonte ton ordre stop à {_signe((suiveur / pos['entree'] - 1) * 100)} au-dessus de ton prix d'achat "
                                 f"(prix Yahoo {prix_lisible(suiveur)}) : ce gain est protégé.", False))
    if cloture is None and maintenant - pos["ts"] > config.TR_SUIVI_JOURS * 86400:
        prix = a["prix"] if a and a.get("ok") else pos["entree"]
        cloture = clore("duree", prix)
    return evts, cloture
