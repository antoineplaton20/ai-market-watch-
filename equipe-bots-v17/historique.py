"""Archives historiques gratuites, téléchargées une fois puis gardées sur disque (dossier archives/).
- data.binance.vision : bougies spot depuis 2017, funding et positions des contrats à terme
- DefiLlama : offre totale de stablecoins (jour par jour)
- alternative.me : indice Peur & Avidité depuis 2018
- Yahoo Finance : Nasdaq et dollar (DXY)
Règle d'or : chaque donnée est datée au moment où elle était RÉELLEMENT connue (pas de triche sur le futur)."""
import datetime as dt
import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import requests
import config

DOSSIER = "archives"
VISION = "https://data.binance.vision/data"
os.makedirs(DOSSIER, exist_ok=True)


def _zip_csv(url, fichier_cache, definitif=True):
    """Télécharge un zip de data.binance.vision et renvoie son CSV (None s'il n'existe pas)."""
    chemin = os.path.join(DOSSIER, fichier_cache)
    if os.path.exists(chemin):
        return pd.read_csv(chemin) if os.path.getsize(chemin) > 0 else None
    try:
        r = requests.get(url, timeout=30)
    except Exception:
        return None                                      # réseau : on réessaiera au prochain lancement
    if r.status_code != 200:
        if definitif:                                    # absent pour de bon : on le note
            open(chemin, "w").close()
        return None                                      # pas encore publié : on réessaiera
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        brut = z.read(z.namelist()[0]).decode()
    df = pd.read_csv(io.StringIO(brut), header=None)
    if not str(df.iloc[0, 0]).replace(".", "").isdigit():  # certains fichiers ont un en-tête
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
    df.to_csv(chemin, index=False)
    return df


def _mois(debut, fin):
    m = dt.date(debut.year, debut.month, 1)
    while m <= fin:
        yield m
        m = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)


def _jours(debut, fin):
    j = debut
    while j <= fin:
        yield j
        j += dt.timedelta(days=1)


def en_ms(dates):
    """Dates -> millisecondes, quelle que soit la version de pandas (évite les erreurs d'unité)."""
    x = pd.DatetimeIndex(dates)
    if x.tz is not None:
        x = x.tz_convert(None)
    return np.asarray((x - pd.Timestamp(0)) // pd.Timedelta(milliseconds=1), dtype="int64")


def _ms(serie):
    """Horodatages en millisecondes (Binance est passé aux microsecondes en 2025)."""
    s = pd.to_numeric(serie, errors="coerce")
    return s.where(s < 1e14, s // 1000).astype("int64")


# ============================== BOUGIES SPOT ==============================
def bougies_15m(symbole, jours):
    """Bougies 15 min + volume acheteur réellement exécuté, sur `jours` jours."""
    sym = symbole.replace("/", "")
    fin = dt.date.today() - dt.timedelta(days=1)
    debut = fin - dt.timedelta(days=jours)
    mois_courant = dt.date(fin.year, fin.month, 1)
    taches = [(f"{VISION}/spot/monthly/klines/{sym}/15m/{sym}-15m-{m:%Y-%m}.zip", f"k_{sym}_{m:%Y-%m}.csv",
               (fin - m).days > 40) for m in _mois(debut, fin) if m < mois_courant]
    taches += [(f"{VISION}/spot/daily/klines/{sym}/15m/{sym}-15m-{j}.zip", f"k_{sym}_{j}.csv", (fin - j).days > 2)
               for j in _jours(max(debut, mois_courant), fin)]
    with ThreadPoolExecutor(8) as pool:
        morceaux = [d for d in pool.map(lambda t: _zip_csv(*t), taches) if d is not None and len(d)]
    if not morceaux:
        return None
    df = pd.concat(morceaux, ignore_index=True).iloc[:, [0, 1, 2, 3, 4, 5, 9]]
    df.columns = ["t", "o", "h", "l", "c", "v", "v_achat"]
    df["t"] = _ms(df["t"])
    for c in ["o", "h", "l", "c", "v", "v_achat"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    debut_ms = int(dt.datetime.combine(debut, dt.time()).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    df = df[df["t"] >= debut_ms].dropna().drop_duplicates("t").sort_values("t").reset_index(drop=True)
    return controler(df, symbole)


QUALITE = {}


def controler(df, nom=""):
    """Contrôle qualité des archives : bougies impossibles retirées, trous comptés.
    (Les archives contiennent parfois des bougies aberrantes, par exemple pendant une maintenance.)"""
    if df is None or df.empty:
        return df
    o, h, l, c, v = df["o"], df["h"], df["l"], df["c"], df["v"]
    valide = (o > 0) & (h > 0) & (l > 0) & (c > 0) & (v >= 0) \
        & (h >= pd.concat([o, c], axis=1).max(axis=1) * 0.9999) \
        & (l <= pd.concat([o, c], axis=1).min(axis=1) * 1.0001)
    # Pic isolé : clôture à plus de 3x (ou moins d'un tiers) de ses deux voisines -> erreur de donnée
    prec, suiv = c.shift(1), c.shift(-1)
    pic = ((c > 3 * prec) & (c > 3 * suiv)) | ((c < prec / 3) & (c < suiv / 3))
    propre = df[valide & ~pic].reset_index(drop=True)
    trous = int((propre["t"].diff() > 3600 * 1000).sum())
    QUALITE[nom] = {"retirees": int(len(df) - len(propre)), "trous_plus_1h": trous}
    return propre


def regrouper(df, minutes):
    """15 min -> 1 h / 4 h, sans mélanger les bougies."""
    if minutes == 15:
        return df
    x = df.set_index(pd.to_datetime(df["t"], unit="ms"))
    g = x.resample(f"{minutes}min", label="left", closed="left").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum", "v_achat": "sum"}).dropna()
    g["t"] = en_ms(g.index)
    return g.reset_index(drop=True)[["t", "o", "h", "l", "c", "v", "v_achat"]]


# ========================== CONTRATS À TERME (UM) =========================
def fundings(base, jours):
    sym = f"{base}USDT"
    fin = dt.date.today()
    debut = fin - dt.timedelta(days=jours + 31)
    morceaux = []
    for m in _mois(debut, fin):
        d = _zip_csv(f"{VISION}/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{m:%Y-%m}.zip",
                     f"f_{sym}_{m:%Y-%m}.csv", (fin - m).days > 40)
        if d is not None and len(d):
            morceaux.append(d.iloc[:, [0, -1]].set_axis(["t_f", "funding"], axis=1))
    if not morceaux:
        return None
    f = pd.concat(morceaux, ignore_index=True)
    f["t_f"] = _ms(f["t_f"])
    f["funding"] = pd.to_numeric(f["funding"], errors="coerce")
    return f.dropna().sort_values("t_f").reset_index(drop=True)


def positions(base, jours):
    """Open interest + ratios acheteurs/vendeurs (foule et gros traders), fichiers journaliers."""
    sym = f"{base}USDT"
    fin = dt.date.today() - dt.timedelta(days=1)
    debut = fin - dt.timedelta(days=jours)
    taches = [(f"{VISION}/futures/um/daily/metrics/{sym}/{sym}-metrics-{j}.zip", f"m_{sym}_{j}.csv",
               (fin - j).days > 2) for j in _jours(debut, fin)]
    with ThreadPoolExecutor(8) as pool:
        morceaux = [d for d in pool.map(lambda t: _zip_csv(*t), taches) if d is not None and len(d)]
    if not morceaux:
        return None
    m = pd.concat(morceaux, ignore_index=True)
    m.columns = [str(c) for c in m.columns]
    if "create_time" not in m.columns:
        return None
    out = pd.DataFrame({
        "t_m": en_ms(pd.to_datetime(m["create_time"], utc=True)) + 5 * 60 * 1000,  # publié ~5 min après
        "oi": pd.to_numeric(m.get("sum_open_interest_value"), errors="coerce"),
        "ls_foule": pd.to_numeric(m.get("count_long_short_ratio"), errors="coerce"),
        "ls_gros": pd.to_numeric(m.get("sum_toptrader_long_short_ratio"), errors="coerce"),
    })
    return out.dropna().drop_duplicates("t_m").sort_values("t_m").reset_index(drop=True)


# ============================ DONNÉES DE MARCHÉ ===========================
def _jour_suivant_ms(dates):
    """Une donnée journalière n'est connue que le lendemain."""
    return en_ms(pd.DatetimeIndex(pd.to_datetime(dates, utc=True)).normalize() + pd.Timedelta(days=1))


def peur_avidite():
    try:
        j = requests.get("https://api.alternative.me/fng/?limit=0", timeout=20).json()["data"]
        return pd.DataFrame({"t_g": [int(x["timestamp"]) * 1000 + 86400000 for x in j],
                             "fng": [int(x["value"]) for x in j]}).sort_values("t_g").reset_index(drop=True)
    except Exception:
        return None


def stablecoins():
    """Variation sur 7 jours de l'offre totale de stablecoins (en %)."""
    try:
        j = requests.get("https://stablecoins.llama.fi/stablecoincharts/all", timeout=30).json()
        df = pd.DataFrame({"date": [int(x["date"]) for x in j],
                           "offre": [float((x.get("totalCirculatingUSD") or {}).get("peggedUSD", 0)) for x in j]})
        df = df[df["offre"] > 0].sort_values("date")
        df["liq_7j"] = (df["offre"] / df["offre"].shift(7) - 1) * 100
        df["t_l"] = _jour_suivant_ms(pd.to_datetime(df["date"], unit="s"))
        return df[["t_l", "liq_7j"]].dropna().reset_index(drop=True)
    except Exception:
        return None


def macro(jours):
    """Nasdaq au-dessus de sa moyenne 50 j ? Dollar en forte hausse ?"""
    try:
        import yfinance as yf
        debut = (dt.date.today() - dt.timedelta(days=jours + 120)).isoformat()
        res = {}
        for code, nom in (("^IXIC", "nasdaq"), ("DX-Y.NYB", "dxy")):
            d = yf.download(code, start=debut, progress=False, auto_adjust=True)
            c = d["Close"]
            c = c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c
            res[nom] = c.dropna()
        df = pd.DataFrame({"nasdaq": res["nasdaq"], "dxy": res["dxy"]}).ffill().dropna()
        df["nasdaq_ok"] = df["nasdaq"] > df["nasdaq"].rolling(50).mean()
        df["dxy_stress"] = (df["dxy"] > df["dxy"].rolling(50).mean()) & \
                           ((df["dxy"] / df["dxy"].shift(5) - 1) * 100 > config.MACRO_DXY_HAUSSE_5J_PCT)
        df["t_x"] = _jour_suivant_ms(df.index)
        return df[["t_x", "nasdaq_ok", "dxy_stress"]].dropna().reset_index(drop=True)
    except Exception:
        return None


# ======================= UNIVERS COMPLET (y compris disparues) =======================
def toutes_les_paires():
    """Toutes les paires spot USDT ayant existé sur Binance, y compris celles retirées depuis.
    Les inclure évite le biais du survivant : on apprend aussi des cryptos qui se sont effondrées."""
    chemin = os.path.join(DOSSIER, "univers_complet.txt")
    if os.path.exists(chemin) and (dt.datetime.now().timestamp() - os.path.getmtime(chemin)) < 7 * 86400:
        with open(chemin, encoding="utf-8") as f:
            return [x.strip() for x in f if x.strip()]
    import xml.etree.ElementTree as ET
    base = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
    prefixe, marqueur, symboles = "data/spot/monthly/klines/", "", []
    for _ in range(50):
        try:
            xml = requests.get(base, params={"delimiter": "/", "prefix": prefixe, "marker": marqueur}, timeout=30).text
        except Exception:
            break
        racine = ET.fromstring(xml)
        ns = racine.tag.split("}")[0] + "}" if racine.tag.startswith("{") else ""
        lot = [p.findtext(f"{ns}Prefix") for p in racine.iter(f"{ns}CommonPrefixes")]
        symboles += [x.rstrip("/").split("/")[-1] for x in lot if x]
        if racine.findtext(f"{ns}IsTruncated") != "true" or not lot:
            break
        marqueur = racine.findtext(f"{ns}NextMarker") or lot[-1]
    exclus = {s.replace("/", "") for s in config.EXCLUS}
    def levier(base):          # anciens jetons à levier (BTCUP, ETHBEAR...) : exclus
        return base.endswith(("UP", "DOWN", "BULL", "BEAR")) and base not in ("JUP", "SUP", "PUNDIX")
    paires = sorted({f"{s[:-4]}/USDT" for s in symboles
                     if s.endswith("USDT") and s not in exclus and len(s) > 4 and not levier(s[:-4])})
    if paires:
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(paires))
    return paires


# ============================== MARCHÉS MONDIAUX ==============================
MONDE = {"^GSPC": "spx", "^VIX": "vix", "GC=F": "or", "CL=F": "petrole", "^TNX": "taux10", "EURUSD=X": "eurusd"}


def marches_mondiaux(jours):
    """Actions US, peur à Wall Street, or, pétrole, taux, euro-dollar : connus le lendemain de chaque séance."""
    try:
        import yfinance as yf
        debut = (dt.date.today() - dt.timedelta(days=jours + 120)).isoformat()
        cols = {}
        for code, nom in MONDE.items():
            d = yf.download(code, start=debut, progress=False, auto_adjust=True)["Close"]
            cols[nom] = (d.iloc[:, 0] if isinstance(d, pd.DataFrame) else d).dropna()
        df = pd.DataFrame(cols).ffill().dropna(subset=["spx", "vix"])
        df["spx_ok"] = (df["spx"] > df["spx"].rolling(50).mean()).astype(float)
        df["vix_stress"] = ((df["vix"] > config.VIX_PANIQUE) |
                            ((df["vix"] / df["vix"].shift(5) - 1) * 100 > config.VIX_BOND_5J_PCT)).astype(float)
        df["t_w"] = _jour_suivant_ms(df.index)
        return df[["t_w", "spx_ok", "vix_stress"]].dropna().reset_index(drop=True)
    except Exception:
        return None


# ================================== ATTENTION ==================================
def attention(jours):
    """Consultations Wikipedia (Bitcoin + Cryptocurrency) rapportées à leur médiane sur 30 jours."""
    try:
        fin = dt.date.today() - dt.timedelta(days=1)
        debut = fin - dt.timedelta(days=jours + 60)
        total = None
        for page in ("Bitcoin", "Cryptocurrency"):
            url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
                   f"{page}/daily/{debut:%Y%m%d}/{fin:%Y%m%d}")
            j = requests.get(url, headers={"User-Agent": "equipe-bots/1.0 (recherche personnelle)"}, timeout=30).json()
            s = pd.Series({pd.to_datetime(x["timestamp"][:8]): x["views"] for x in j.get("items", [])})
            total = s if total is None else total.add(s, fill_value=0)
        df = pd.DataFrame({"vues": total}).sort_index()
        df["attention"] = df["vues"] / df["vues"].rolling(30).median()
        df["t_a"] = _jour_suivant_ms(df.index)
        return df[["t_a", "attention"]].dropna().reset_index(drop=True)
    except Exception:
        return None

# ============================= v11 =====================================
def bougies_1m(symbole, jours):
    """Source primaire v11 : bougies 1 minute, destinées à reconstruire 5m/15m/1h/4h."""
    return _bougies_intervalle(symbole, jours, "1m")


def _bougies_intervalle(symbole, jours, unite):
    sym = symbole.replace("/", "")
    fin = dt.date.today() - dt.timedelta(days=1)
    debut = fin - dt.timedelta(days=jours)
    mois_courant = dt.date(fin.year, fin.month, 1)
    taches = [(f"{VISION}/spot/monthly/klines/{sym}/{unite}/{sym}-{unite}-{m:%Y-%m}.zip", f"k_{sym}_{unite}_{m:%Y-%m}.csv",
               (fin - m).days > 40) for m in _mois(debut, fin) if m < mois_courant]
    taches += [(f"{VISION}/spot/daily/klines/{sym}/{unite}/{sym}-{unite}-{j}.zip", f"k_{sym}_{unite}_{j}.csv", (fin - j).days > 2)
               for j in _jours(max(debut, mois_courant), fin)]
    with ThreadPoolExecutor(8) as pool:
        morceaux = [d for d in pool.map(lambda t: _zip_csv(*t), taches) if d is not None and len(d)]
    if not morceaux:
        return None
    df = pd.concat(morceaux, ignore_index=True).iloc[:, [0, 1, 2, 3, 4, 5, 9]]
    df.columns = ["t", "o", "h", "l", "c", "v", "v_achat"]
    df["t"] = _ms(df["t"])
    for c in ["o", "h", "l", "c", "v", "v_achat"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    debut_ms = int(dt.datetime.combine(debut, dt.time()).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    df = df[df["t"] >= debut_ms].dropna().drop_duplicates("t").sort_values("t").reset_index(drop=True)
    return controler(df, symbole)


def reconstruire_timeframes(df1m):
    """Reconstruit les unités v11 depuis une seule source 1m, sans inventer de 5m depuis du 15m."""
    if df1m is None or len(df1m) == 0:
        return {}
    d = df1m.copy().sort_values("t")
    d["dt"] = pd.to_datetime(d["t"], unit="ms", utc=True)
    out = {"1m": d.drop(columns=["dt"])}
    for minutes, name in [(5,"5m"),(15,"15m"),(60,"1h"),(240,"4h")]:
        x = d.set_index("dt").resample(f"{minutes}min", label="left", closed="left").agg({
            "o":"first", "h":"max", "l":"min", "c":"last", "v":"sum", "v_achat":"sum"
        }).dropna().reset_index()
        x["t"] = en_ms(x["dt"])
        out[name] = x[["t","o","h","l","c","v","v_achat"]]
    return out
