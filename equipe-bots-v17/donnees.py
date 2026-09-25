"""Sources externes (sentiment, dérivés, presse, CoinGecko), toutes avec cache.
Si une source tombe, on garde la dernière valeur connue ; sinon le bot concerné s'abstient."""
import json
import os
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import requests
import config

_cache = {}
FAPI = "https://fapi.binance.com"   # données publiques des contrats à terme Binance


def _memo(cle, duree_s, fonction):
    v = _cache.get(cle)
    if v and time.time() - v[0] < duree_s:
        return v[1]
    try:
        r = fonction()
    except Exception:
        return v[1] if v else None
    _cache[cle] = (time.time(), r)
    return r


# ---------------------------- PEUR & AVIDITÉ ----------------------------
def peur_avidite():
    def f():
        j = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()
        return int(j["data"][0]["value"])
    return _memo("fng", 3600, f)


# ------------------------------- DÉRIVÉS --------------------------------
def fundings():
    def f():
        r = requests.get(f"{FAPI}/fapi/v1/premiumIndex", timeout=10).json()
        return {x["symbol"]: float(x["lastFundingRate"]) for x in r if x.get("lastFundingRate") not in (None, "")}
    return _memo("funding", 300, f) or {}


def open_interest(symbole_fut):
    def f():
        r = requests.get(f"{FAPI}/futures/data/openInterestHist",
                         params={"symbol": symbole_fut, "period": "15m", "limit": 13}, timeout=10).json()
        return [float(x["sumOpenInterestValue"]) for x in r] if isinstance(r, list) and r else None
    return _memo(f"oi_{symbole_fut}", 300, f)


# ------------------------------- PRESSE ---------------------------------
def actualites():
    def f():
        titres = []
        for url in config.FLUX_RSS:
            try:
                xml = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}).content
                for item in ET.fromstring(xml).iter("item"):
                    titre = (item.findtext("title") or "").strip()
                    date = item.findtext("pubDate")
                    try:
                        ts = parsedate_to_datetime(date).timestamp() if date else time.time()
                    except Exception:
                        ts = time.time()
                    if titre:
                        titres.append({"titre": titre, "ts": ts})
            except Exception:
                continue
        return titres
    return _memo("actus", 600, f) or []


# ------------------------------ COINGECKO -------------------------------
def _cg(chemin, params=None):
    entetes = {"x-cg-demo-api-key": config.COINGECKO_API_KEY} if config.COINGECKO_API_KEY else {}
    return requests.get(f"https://api.coingecko.com/api/v3{chemin}", params=params,
                        headers=entetes, timeout=15).json()


def tendances():
    def f():
        j = _cg("/search/trending")
        return {c["item"]["symbol"].upper() for c in j.get("coins", [])}
    return _memo("trending", 900, f) or set()


def annuaire():
    """Symbole -> (id CoinGecko, nom) pour les 250 plus grosses cryptos."""
    def f():
        j = _cg("/coins/markets", {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": 1})
        res = {}
        for c in j:
            s = c["symbol"].upper()
            if s not in res:          # en cas de doublon, on garde la plus grosse capitalisation
                res[s] = (c["id"], c["name"])
        return res
    return _memo("annuaire", 86400, f) or {}


FICHIER_DEV = "cache_developpeurs.json"


def commits_4_semaines(base):
    if not config.COINGECKO_API_KEY:
        return None
    entree = annuaire().get(base)
    if not entree:
        return None
    cache = {}
    if os.path.exists(FICHIER_DEV):
        try:
            with open(FICHIER_DEV, encoding="utf-8") as fch:
                cache = json.load(fch)
        except Exception:
            cache = {}
    c = cache.get(base)
    if c and time.time() - c["ts"] < 86400:
        return c["commits"]
    try:
        j = _cg(f"/coins/{entree[0]}", {"localization": "false", "tickers": "false", "market_data": "false",
                                         "community_data": "false", "developer_data": "true", "sparkline": "false"})
        commits = (j.get("developer_data") or {}).get("commit_count_4_weeks")
    except Exception:
        return None
    cache[base] = {"ts": time.time(), "commits": commits}
    with open(FICHIER_DEV, "w", encoding="utf-8") as fch:
        json.dump(cache, fch)
    return commits


# ------------------------------ LIQUIDITÉ -------------------------------
def stablecoins_7j():
    """Variation sur 7 jours de l'offre totale de stablecoins (DefiLlama), en %."""
    def f():
        j = requests.get("https://stablecoins.llama.fi/stablecoincharts/all", timeout=30).json()
        offres = [float((x.get("totalCirculatingUSD") or {}).get("peggedUSD", 0)) for x in j]
        offres = [o for o in offres if o > 0]
        return (offres[-1] / offres[-8] - 1) * 100
    return _memo("stables", 3600, f)


# -------------------------------- MACRO ---------------------------------
def macro():
    """(nasdaq au-dessus de sa moyenne 50 j, dollar en stress) via Yahoo Finance."""
    def f():
        import yfinance as yf
        res = {}
        for code, nom in (("^IXIC", "nasdaq"), ("DX-Y.NYB", "dxy")):
            d = yf.download(code, period="6mo", progress=False, auto_adjust=True)["Close"]
            res[nom] = (d.iloc[:, 0] if hasattr(d, "columns") else d).dropna()
        n, x = res["nasdaq"], res["dxy"]
        nasdaq_ok = bool(n.iloc[-1] > n.tail(50).mean())
        dxy_stress = bool(x.iloc[-1] > x.tail(50).mean() and (x.iloc[-1] / x.iloc[-6] - 1) * 100 > config.MACRO_DXY_HAUSSE_5J_PCT)
        return nasdaq_ok, dxy_stress
    return _memo("macro", 3600, f)


# ---------------------------- POSITIONNEMENT ----------------------------
def positionnement(symbole_fut):
    """(ratio acheteurs/vendeurs de la foule, ratio des 20 % plus gros traders) sur Binance Futures."""
    def f():
        p = {"symbol": symbole_fut, "period": "15m", "limit": 1}
        foule = requests.get(f"{FAPI}/futures/data/globalLongShortAccountRatio", params=p, timeout=10).json()
        gros = requests.get(f"{FAPI}/futures/data/topLongShortPositionRatio", params=p, timeout=10).json()
        if not (isinstance(foule, list) and foule and isinstance(gros, list) and gros):
            return None
        return float(foule[-1]["longShortRatio"]), float(gros[-1]["longShortRatio"])
    return _memo(f"pos_{symbole_fut}", 300, f)


# --------------------------- MARCHÉS MONDIAUX ---------------------------
def marches_mondiaux():
    """(S&P 500 au-dessus de sa moyenne 50 j, VIX en panique) via Yahoo Finance."""
    def f():
        import yfinance as yf
        res = {}
        for code in ("^GSPC", "^VIX"):
            d = yf.download(code, period="6mo", progress=False, auto_adjust=True)["Close"]
            res[code] = (d.iloc[:, 0] if hasattr(d, "columns") else d).dropna()
        spx, vix = res["^GSPC"], res["^VIX"]
        spx_ok = bool(spx.iloc[-1] > spx.tail(50).mean())
        vix_stress = bool(vix.iloc[-1] > config.VIX_PANIQUE or (vix.iloc[-1] / vix.iloc[-6] - 1) * 100 > config.VIX_BOND_5J_PCT)
        return spx_ok, vix_stress, float(vix.iloc[-1])
    return _memo("monde", 3600, f)


# ------------------------------- ATTENTION ------------------------------
def attention():
    """Consultations Wikipedia d'hier (Bitcoin + Cryptocurrency) / médiane des 30 jours précédents."""
    def f():
        import datetime as dt
        fin = dt.date.today() - dt.timedelta(days=1)
        debut = fin - dt.timedelta(days=40)
        total = {}
        for page in ("Bitcoin", "Cryptocurrency"):
            url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
                   f"{page}/daily/{debut:%Y%m%d}/{fin:%Y%m%d}")
            j = requests.get(url, headers={"User-Agent": "equipe-bots/1.0 (recherche personnelle)"}, timeout=20).json()
            for x in j.get("items", []):
                total[x["timestamp"]] = total.get(x["timestamp"], 0) + x["views"]
        vues = [total[k] for k in sorted(total)]
        mediane = sorted(vues[-31:-1])[len(vues[-31:-1]) // 2]
        return vues[-1] / mediane if mediane else None
    return _memo("attention", 6 * 3600, f)
