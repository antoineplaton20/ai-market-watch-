"""Yahoo Finance pour la veille Trade Republic : ISIN -> symbole Yahoo (cache), cours, devises.

Yahoo est une source gratuite et non officielle : elle limite le nombre de requêtes et certaines bourses
sont différées de 15-20 min. Chaque fonction signale la limite (LimiteYahoo) pour que la veille fasse
une pause au lieu d'insister.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, Iterable, List, Optional

import pandas as pd

FICHIER_CACHE = "tr_yahoo.json"
BOURSES_OTC = {"PNK", "OQB", "OQX", "OEM", "OGM", "OBB", "YHD", "OTC"}
SUFFIXES_REGIONAUX = {"F", "BE", "DU", "HM", "MU", "SG", "HA"}       # places allemandes régionales, peu d'échanges
PREFERENCE_ETF = ["DE", "PA", "AS", "MI", "L", "SW", "BR", "MC", "VI", "IR"]
DEVISES = {"": "USD", "DE": "EUR", "F": "EUR", "BE": "EUR", "DU": "EUR", "HM": "EUR", "MU": "EUR", "SG": "EUR",
           "HA": "EUR", "PA": "EUR", "AS": "EUR", "BR": "EUR", "MI": "EUR", "MC": "EUR", "LS": "EUR", "VI": "EUR",
           "HE": "EUR", "IR": "EUR", "L": "GBp", "IL": "GBp", "SW": "CHF", "ST": "SEK", "CO": "DKK", "OL": "NOK",
           "TO": "CAD", "V": "CAD", "NE": "CAD", "AX": "AUD", "T": "JPY", "HK": "HKD", "WA": "PLN", "SI": "SGD",
           "NZ": "NZD", "TA": "ILA", "SA": "BRL", "MX": "MXN", "KS": "KRW", "KQ": "KRW", "TW": "TWD",
           "SS": "CNY", "SZ": "CNY", "JO": "ZAc", "PR": "CZK", "BD": "HUF", "IS": "TRY"}
# Sous-unités : cours en centimes / pence
SOUS_UNITES = {"GBp": ("GBP", 100), "ZAc": ("ZAR", 100), "ILA": ("ILS", 100)}   # cours en centièmes
# Taux de secours APPROXIMATIFS (unités par euro), utilisés seulement si Yahoo ne donne pas les changes,
# et seulement pour classer les titres par volume d'échanges.
TAUX_SECOURS = {"USD": 1.10, "GBP": 0.85, "CHF": 0.95, "SEK": 11.3, "DKK": 7.46, "NOK": 11.6, "CAD": 1.50,
                "AUD": 1.65, "JPY": 160.0, "HKD": 8.6, "PLN": 4.3, "SGD": 1.45, "NZD": 1.8, "ILS": 4.1,
                "BRL": 6.0, "MXN": 20.0, "KRW": 1500.0, "TWD": 35.0, "CNY": 7.9, "ZAR": 20.0, "CZK": 25.0,
                "HUF": 400.0, "TRY": 38.0}


class LimiteYahoo(Exception):
    """Yahoo refuse temporairement les requêtes (trop nombreuses)."""


def _est_limite(texte: str) -> bool:
    t = (texte or "").lower()
    return "rate limit" in t or "too many requests" in t or "429" in t or "ratelimit" in t


def suffixe(ticker: str) -> str:
    if "." not in ticker:
        return ""
    fin = ticker.rsplit(".", 1)[1]
    return fin if fin.isalpha() and len(fin) <= 3 else ""


def devise(ticker: str) -> Optional[str]:
    return DEVISES.get(suffixe(ticker))


# ============================ ISIN -> Yahoo ==============================
def choisir_cotation(quotes: List[Dict], genre: str = "stock") -> Optional[Dict]:
    """Meilleure cotation Yahoo pour un ISIN : actions -> place principale (1er résultat hors OTC et places
    régionales) ; ETF -> cotation européenne liquide (Xetra, Paris, Amsterdam, Milan, Londres...)."""
    cands = [q for q in quotes or []
             if q.get("symbol") and q.get("quoteType") in ("EQUITY", "ETF")
             and (q.get("exchange") or "").upper() not in BOURSES_OTC and devise(q["symbol"]) is not None]
    if not cands:
        return None

    def rang(q):
        suf = suffixe(q["symbol"])
        regional = suf in SUFFIXES_REGIONAUX
        if q.get("quoteType") == "ETF":           # le type donné par Yahoo prime sur la section du PDF
            pref = PREFERENCE_ETF.index(suf) if suf in PREFERENCE_ETF else len(PREFERENCE_ETF)
            return (regional, pref)
        return (regional, 0)                     # tri stable : l'ordre de pertinence Yahoo est conservé
    return sorted(cands, key=rang)[0]


def chercher_isin(isin: str, genre: str = "stock") -> Optional[Dict]:
    """Une requête Yahoo. Renvoie {"ticker", "devise", "nom"} ou None si Yahoo ne connaît pas l'ISIN."""
    import yfinance as yf
    try:
        try:
            res = yf.Search(isin, max_results=10, news_count=0, lists_count=0, recommended=0,
                            include_cb=False, enable_fuzzy_query=False, raise_errors=True)
        except TypeError:                         # anciennes versions de yfinance : moins d'options
            res = yf.Search(isin, max_results=10, news_count=0)
        quotes = res.quotes
    except Exception as e:
        if _est_limite(f"{type(e).__name__} {e}"):
            raise LimiteYahoo(str(e)[:120])
        raise
    q = choisir_cotation(quotes, genre)
    if not q:
        return None
    r = {"ticker": q["symbol"], "devise": q.get("currency") or devise(q["symbol"]), "type": q.get("quoteType"),
         "nom": q.get("shortname") or q.get("longname") or ""}
    if suffixe(q["symbol"]) in DEVISE_VARIABLE and not q.get("currency"):
        d = devise_reelle(q["symbol"])
        if d:
            r["devise"], r["devise_ok"] = d, True
    return r


# À Londres (et Tel-Aviv), une cotation peut être en pence, en livres, en dollars ou en euros (IWDA.L : dollars) :
# le suffixe ne suffit pas, on demande la devise à Yahoo.
DEVISE_VARIABLE = {"L", "IL", "TA"}
_NORMALISE = {"GBX": "GBp", "GBP": "GBP", "GBp": "GBp", "ZAC": "ZAc", "ZAc": "ZAc", "ILA": "ILA", "ILS": "ILS"}


def devise_reelle(ticker: str, fabrique=None) -> Optional[str]:
    """Devise réelle d'une cotation d'après Yahoo (une requête). None si Yahoo ne répond pas."""
    import yfinance as yf
    try:
        info = (fabrique or yf.Ticker)(ticker).fast_info
        d = info["currency"] if not hasattr(info, "currency") else info.currency
    except Exception as e:
        if _est_limite(f"{type(e).__name__} {e}"):
            raise LimiteYahoo(str(e)[:120])
        return None
    if not d:
        return None
    return _NORMALISE.get(d, d.upper() if d.upper() in TAUX_SECOURS or d.upper() == "EUR" else d)


def verifier_devises(cache: Dict, budget_s: float, pause_s: float = 0.6, verifier=None) -> int:
    """Corrige les devises des cotations déjà en cache (ex. IWDA.L notée en pence alors qu'elle est en dollars)."""
    verifier = verifier or devise_reelle
    debut, faits = time.time(), 0
    for isin, e in cache.items():
        if time.time() - debut > budget_s:
            break
        t = e.get("ticker")
        if not t or e.get("devise_ok") or suffixe(t) not in DEVISE_VARIABLE:
            continue
        d = verifier(t)
        if d:
            e["devise"] = d
        e["devise_ok"] = True
        faits += 1
        time.sleep(pause_s)
    return faits


def charger_cache(fichier: str = FICHIER_CACHE) -> Dict:
    try:
        with open(fichier, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def sauver_cache(cache: Dict, fichier: str = FICHIER_CACHE) -> None:
    tmp = fichier + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, fichier)


def a_chercher(univers: Iterable[Dict], cache: Dict, maintenant: float) -> List[Dict]:
    """ISIN jamais cherchés, puis échecs anciens (nouvel essai après 7 jours, 3 essais maximum)."""
    neufs, a_refaire = [], []
    for i in univers:
        if i["kind"] not in ("stock", "etf"):
            continue                              # Yahoo ne couvre ni les dérivés ni les obligations TR
        e = cache.get(i["isin"])
        if e is None:
            neufs.append(i)
        elif not e.get("ticker") and e.get("essais", 0) < 3 and maintenant - e.get("ts", 0) > 7 * 86400:
            a_refaire.append(i)
    return neufs + a_refaire


def cartographier(univers: List[Dict], cache: Dict, budget_s: float, pause_s: float = 0.6,
                  chercher=None) -> Dict:
    """Traite des ISIN jusqu'à épuisement du budget de temps. Lève LimiteYahoo si Yahoo bloque ou si le réseau
    échoue 5 fois de suite (le cache déjà rempli est conservé par l'appelant).
    « Introuvable sur Yahoo » est mémorisé ; une ERREUR réseau ne l'est jamais (l'ISIN sera recherché à nouveau)."""
    chercher = chercher or chercher_isin
    debut, faits, trouves, erreurs_suite = time.time(), 0, 0, 0
    for i in a_chercher(univers, cache, time.time()):
        if time.time() - debut > budget_s:
            break
        ancien = cache.get(i["isin"], {})
        try:
            r = chercher(i["isin"], i["kind"])
        except LimiteYahoo:
            raise
        except Exception as e:
            erreurs_suite += 1
            if erreurs_suite >= 5:
                raise LimiteYahoo(f"erreurs réseau répétées ({type(e).__name__})")
            time.sleep(pause_s)
            continue
        erreurs_suite = 0
        cache[i["isin"]] = {**(r or {"ticker": None}), "ts": time.time(),
                            "essais": ancien.get("essais", 0) + (0 if r else 1)}
        faits += 1
        trouves += bool(r)
        time.sleep(pause_s)
    return {"faits": faits, "trouves": trouves, "restants": len(a_chercher(univers, cache, time.time()))}


# ============================== COURS =====================================
def normaliser(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame Yahoo (Open/High/Low/Close/Volume, index date) -> colonnes t (ms UTC), o, h, l, c, v."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    d = df.rename(columns=str.lower)
    d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"})
    d = d[[c for c in ("o", "h", "l", "c", "v") if c in d.columns]].dropna(subset=["c"])
    idx = pd.DatetimeIndex(d.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    t = (idx - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1ms")
    d = d.reset_index(drop=True)
    d.insert(0, "t", pd.Series(t, dtype="int64").to_numpy())
    if "v" not in d:
        d["v"] = 0.0
    d["v"] = d["v"].fillna(0.0)
    return d


class _Capteur(logging.Handler):
    """Récupère les messages d'erreur de yfinance (c'est là qu'il signale « Rate limited »)."""
    def __init__(self):
        super().__init__(logging.ERROR)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def telecharger(tickers: List[str], periode: str, intervalle: str, lot: int = 50,
                pause_s: float = 1.0, telechargeur=None) -> Dict[str, pd.DataFrame]:
    """Cours de plusieurs titres, par lots. Lève LimiteYahoo si Yahoo bloque (message explicite,
    ou lot entier sans aucune donnée)."""
    import yfinance as yf
    telechargeur = telechargeur or yf.download
    resultat = {}
    journal_yf = logging.getLogger("yfinance")
    for k in range(0, len(tickers), lot):
        paquet = tickers[k:k + lot]
        capteur = _Capteur()
        journal_yf.addHandler(capteur)
        try:
            brut = telechargeur(paquet, period=periode, interval=intervalle, group_by="ticker",
                                auto_adjust=True, threads=True, progress=False, multi_level_index=True)
        except Exception as e:
            if _est_limite(f"{type(e).__name__} {e}"):
                raise LimiteYahoo(str(e)[:120])
            continue
        finally:
            journal_yf.removeHandler(capteur)
        recus = 0
        for t in paquet:
            sous = None
            if brut is not None and isinstance(brut.columns, pd.MultiIndex):
                for cle in (t, t.upper()):                     # yfinance met les symboles en majuscules
                    if cle in brut.columns.get_level_values(0):
                        sous = brut[cle]
                        break
            elif brut is not None and len(paquet) == 1:
                sous = brut
            d = normaliser(sous) if sous is not None else None
            if d is not None and len(d):
                resultat[t] = d
                recus += 1
        if recus == 0 and (_est_limite(" ".join(capteur.messages)) or len(paquet) >= 5):
            raise LimiteYahoo("téléchargement refusé (" + (" ".join(capteur.messages)[:80] or "aucune donnée") + ")")
        if k + lot < len(tickers):
            time.sleep(pause_s)
    return resultat


def taux_de_change(devises: Iterable[str], telechargeur=None) -> Dict[str, float]:
    """Unités de chaque devise pour 1 euro (sous-unités comprises : GBp = GBP x 100)."""
    besoins = {SOUS_UNITES.get(d, (d, 1))[0] for d in devises if d and d != "EUR"}
    taux = {"EUR": 1.0}
    if besoins:
        try:
            cours = telecharger([f"EUR{d}=X" for d in sorted(besoins)], "5d", "1d", telechargeur=telechargeur)
        except LimiteYahoo:
            cours = {}
        for d in besoins:
            c = cours.get(f"EUR{d}=X")
            taux[d] = float(c["c"].iloc[-1]) if c is not None and len(c) else TAUX_SECOURS.get(d, float("nan"))
    for sous, (mere, facteur) in SOUS_UNITES.items():
        if mere in taux:
            taux[sous] = taux[mere] * facteur
    return taux
