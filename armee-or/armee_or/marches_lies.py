"""VIGIE DES MARCHÉS LIÉS — ce qui fait bouger l'or : dollar, taux américains, argent, cuivre, pétrole, actions,
peur (VIX), euro, mines d'or, bitcoin, et l'or COMEX lui-même. Source : Yahoo Finance (gratuit, léger différé).

Relations documentées (voir bibliotheque.py) : l'or monte en général quand le dollar et les taux réels baissent
(Erb & Harvey 2013), et sert de refuge lors des crises boursières aiguës (Baur & Lucey 2010). Ces relations
changent avec le temps : la corrélation récente est recalculée à chaque passage, jamais supposée.
"""
from __future__ import annotations

import time

import numpy as np

TICKERS = {
    "GC=F": "Or COMEX", "DX-Y.NYB": "Dollar (DXY)", "^TNX": "Taux US 10 ans", "SI=F": "Argent", "HG=F": "Cuivre",
    "CL=F": "Pétrole WTI", "^GSPC": "S&P 500", "^VIX": "Peur (VIX)", "EURUSD=X": "Euro / dollar", "GDX": "Mines d'or",
    "BTC-USD": "Bitcoin",
}
# sens habituel de la relation avec l'or (+1 : montent ensemble, -1 : en sens inverse), pour le score de contexte
SENS_HABITUEL = {"DX-Y.NYB": -1, "^TNX": -1, "SI=F": 1, "EURUSD=X": 1, "GDX": 1, "^VIX": 1}


def telecharger(ticker, intervalle="1d", periode="6mo", session=None):
    """-> (horodatages en s, clôtures) depuis l'API publique de graphiques Yahoo."""
    import requests
    s = session or requests
    r = s.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
              params={"interval": intervalle, "range": periode}, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts = np.array(res.get("timestamp") or [], dtype=np.int64)
    c = np.array([np.nan if x is None else x for x in res["indicators"]["quote"][0]["close"]], dtype=float)
    ok = ~np.isnan(c)
    return ts[ok], c[ok]


def analyser(series):
    """series : {ticker: (ts, c)} en quotidien. -> tableau de bord + score de contexte pour l'or (-1 à +1)."""
    lignes, score, poids = [], 0.0, 0.0
    or_ts, or_c = series.get("GC=F", (np.array([]), np.array([])))
    or_ret = dict(zip(or_ts[1:] // 86400, np.diff(np.log(or_c)))) if len(or_c) > 1 else {}
    for t, (ts, c) in series.items():
        if len(c) < 6:
            continue
        v1 = (c[-1] / c[-2] - 1) * 100
        v5 = (c[-1] / c[-6] - 1) * 100
        rets = dict(zip(ts[1:] // 86400, np.diff(np.log(c))))
        jours = sorted(set(rets) & set(or_ret))[-60:]
        corr = None
        if t != "GC=F" and len(jours) >= 30:
            a, b = np.array([rets[j] for j in jours]), np.array([or_ret[j] for j in jours])
            if a.std() > 0 and b.std() > 0:
                corr = float(np.corrcoef(a, b)[0, 1])
        lignes.append({"ticker": t, "nom": TICKERS.get(t, t), "dernier": float(c[-1]), "var_1j": float(v1),
                       "var_5j": float(v5), "correlation_60j": corr})
        if t in SENS_HABITUEL:
            s = SENS_HABITUEL[t] * np.tanh(v5 / 2)
            score += s
            poids += 1
    return {"ts": time.time(), "marches": lignes, "contexte": float(score / poids) if poids else 0.0}


def releve(session=None):
    series = {}
    erreurs = {}
    for t in TICKERS:
        try:
            series[t] = telecharger(t, session=session)
        except Exception as ex:
            erreurs[t] = f"{type(ex).__name__}"
    out = analyser(series)
    out["erreurs"] = erreurs
    return out
