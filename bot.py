# -*- coding: utf-8 -*-
"""
AI MARKET BOTS v2 — Surveillance multi-marchés pour Trade Republic -> alertes Telegram

6 modules : IA Infrastructure · Power & Cooling · Semi-conducteurs · Matières premières IA
            · Scanner tous marchés (≈230 titres TR re-classés chaque heure) · Crypto
+ filtre actualités / géopolitique (Google News, Yahoo Finance, GDELT) vérifié par une IA
+ calendrier macro (Fed, BCE, inflation, emploi...) + régime de marché (VIX, futures, taux)
+ briefings matin / avant Wall Street, bilan hebdo, portefeuille virtuel 20 € avec frais TR
+ commandes Telegram (/etat, /analyse, /achete, /vendu, /capital, /pause...)

Lancement : GitHub Actions toutes les 5 min (voir .github/workflows/bots.yml)
  python bot.py            scan normal
  python bot.py --force    scan même marchés fermés (test)
  python bot.py --test     message de test Telegram
  python bot.py --matin | --preus | --recap    forcer un briefing / le bilan
"""
import json, math, os, re, sys, time, pickle
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

import univers as U

# ═════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

CAPITAL_DEFAUT = 20.0        # € (modifiable depuis Telegram : /capital 25)
FRAIS_ORDRE = 1.0            # € par ordre chez Trade Republic (achat ET vente)
MISE_PART = 1.0              # part du capital par trade. Frais fixes => mieux vaut 1 seul trade à la fois
RATIO_MIN_APRES_FRAIS = 1.0  # gain espéré ≥ perte possible, APRÈS les 2 € de frais (sinon pas d'alerte "acheter")
STOP_ATR, OBJECTIF_ATR = 1.5, 3.0   # stop / objectif en multiples de la volatilité journalière (ATR 14j)
# Petit capital (< 100 €) : les 2 € de frais pèsent trop sur des petits mouvements -> on vise des
# mouvements plus grands sur 1 à 4 semaines (même rapport gain/perte de 2 pour 1).
PETIT_CAPITAL, STOP_ATR_PETIT, OBJECTIF_ATR_PETIT = 100, 2.5, 5.0
_NIV = {"stop": STOP_ATR, "obj": OBJECTIF_ATR, "horizon": "1 à 5 jours"}

def regler_niveaux(capital):
    if capital < PETIT_CAPITAL:
        _NIV.update(stop=STOP_ATR_PETIT, obj=OBJECTIF_ATR_PETIT, horizon="1 à 4 semaines")
    else:
        _NIV.update(stop=STOP_ATR, obj=OBJECTIF_ATR, horizon="1 à 5 jours")

SCORE_MIN = 4                # score mini pour alerter (4 ≈ ★★★). 5 = plus exigeant, 3 = plus d'alertes
MIN_CONDITIONS = 2           # conditions techniques indépendantes minimum
VIRTUEL_ETOILES_MIN = 4      # le portefeuille virtuel ne suit que les signaux ★★★★ et plus
ALERTER_VENTES_NON_DETENUES = False   # TR ne permet pas la vente à découvert : ventes = titres détenus seulement
MAX_ALERTES_PAR_SCAN = 4
MAX_ALERTES_PAR_JOUR = 25
COOLDOWN_GLOBAL_MIN = 30     # même titre + même sens, tous modules confondus

ATTENTE_OUVERTURE = {"US": 30, "EU": 15, "UK": 15, "CRYPTO": 0, "FUT": 0}   # minutes ignorées après l'ouverture
FRAICHEUR_MAX_MIN = 25       # donnée plus vieille que ça = ignorée (jamais de signal sur un cours périmé)
FENETRE_CRYPTO = ((7, 0), (23, 0))   # heures de Paris où les alertes crypto sont envoyées
BLACKOUT_AVANT, BLACKOUT_APRES = 30, 15   # minutes sans nouvelle alerte autour d'une annonce macro majeure
DEVISES_CALENDRIER = {"USD", "EUR", "CNY", "JPY", "GBP"}
NB_CHAUDS = 25               # titres retenus par le scanner tous marchés
MODE_SIMPLE_DEFAUT = True    # alertes courtes en français simple (/complet pour la version technique)
DIGEST_HEURES = [(12, 30), (18, 0), (22, 10)]   # récap des titres "à surveiller" (Paris, jours ouvrés)

LLM_BASE = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MAX_PAR_SCAN, LLM_MAX_PAR_JOUR = 2, 80   # quota gratuit Groq ≈ 200k jetons/jour

MODULES = {
    "ia": {"nom": "AI INFRASTRUCTURE", "emoji": "🚀", "liste": U.IA_INFRA, "cooldown": 45, "regles": [
        ("rsi", {"tf": "h1", "bas": 32, "haut": 68, "mode": "retour"}),
        ("rsi", {"tf": "h4", "bas": 32, "haut": 68, "mode": "retour"}),
        ("momentum", {"min": 60, "seuil": 4.5, "vol": 1.8, "pts": 2}),
        ("croise_prix_mm", {"tf": "h1", "n": 20, "vol": 1.5}),
        ("vwap", {"vol": 1.5}),
        ("tendance_tf", {"tf": "h4", "n": 21})]},
    "power": {"nom": "POWER/COOLING ALERT", "emoji": "⚡", "liste": U.POWER_COOLING, "cooldown": 60, "regles": [
        ("momentum", {"min": 120, "seuil": 3.8, "vol": 0, "pts": 2}),
        ("volume", {"min": 60, "mult": 2.0}),
        ("rsi", {"tf": "h1", "bas": 35, "haut": 65, "mode": "sortie"}),
        ("ecart_mm", {"tf": "h1", "n": 50, "seuil": 4.0}),
        ("tendance_tf", {"tf": "h4", "n": 21})]},
    "semi": {"nom": "SEMI MOMENTUM", "emoji": "🔥", "liste": U.SEMIS, "cooldown": 40, "vol_min": 1.3, "regles": [
        ("breakout", {"tf": "h1", "n": 20, "vol": 2.2, "pts": 2}),
        ("divergence", {"tf": "h1"}),
        ("croise_mm", {"tf": "h1", "rapide": 9, "lente": 21}),
        ("momentum", {"min": 60, "seuil": 5.0, "vol": 0, "pts": 2}),
        ("tendance_tf", {"tf": "h4", "n": 21}),
        ("croise_mm", {"tf": "m15", "rapide": 9, "lente": 21, "confirmation": True})]},
    "matieres": {"nom": "RAW MATERIALS AI", "emoji": "🪨", "liste": U.MATIERES, "cooldown": 120, "max_jour": 2, "regles": [
        ("var_jour", {"seuil": 3.5, "pts": 2}),
        ("volume_jour", {"mult": 1.7}),
        ("range_jours", {"n": 10}),
        ("correlation", {"refs": ["NVDA", "SMCI"], "min": 0.5})]},
    "commo": {"nom": "MATIÈRES PREMIÈRES (ETC)", "emoji": "🥇", "liste": list(U.COMMOS), "cooldown": 120, "max_jour": 2, "regles": [
        ("momentum", {"min": 120, "seuil": 2.0, "vol": 1.5, "pts": 2}),
        ("breakout", {"tf": "h1", "n": 24, "vol": 1.5, "pts": 2}),
        ("range_jours", {"n": 10}),
        ("rsi", {"tf": "h1", "bas": 28, "haut": 72, "mode": "retour"}),
        ("croise_mm", {"tf": "h1", "rapide": 9, "lente": 21}),
        ("tendance_tf", {"tf": "h4", "n": 21})]},
    "scanner": {"nom": "SCANNER TOUS MARCHÉS", "emoji": "🌍", "liste": "chauds", "cooldown": 60, "vol_min": 1.5, "regles": [
        ("breakout", {"tf": "h1", "n": 20, "vol": 2.0, "pts": 2}),
        ("momentum", {"min": 60, "seuil": 3.0, "vol": 2.0, "pts": 2}),
        ("vwap", {"vol": 1.5}),
        ("croise_mm", {"tf": "h1", "rapide": 9, "lente": 21}),
        ("rsi", {"tf": "h1", "bas": 28, "haut": 72, "mode": "retour"}),
        ("tendance_tf", {"tf": "h4", "n": 21})]},
    "crypto": {"nom": "CRYPTO TR", "emoji": "🪙", "liste": U.CRYPTO, "cooldown": 60, "regles": [
        ("momentum", {"min": 60, "seuil": 3.0, "vol": 1.8, "pts": 2}),
        ("breakout", {"tf": "h1", "n": 24, "vol": 1.8, "pts": 2}),
        ("rsi", {"tf": "h1", "bas": 28, "haut": 72, "mode": "retour"}),
        ("croise_mm", {"tf": "h1", "rapide": 9, "lente": 21}),
        ("tendance_tf", {"tf": "h4", "n": 21})]},
}
REGLES_CONFIRMATION = {"tendance_tf", "correlation"}   # ne comptent pas comme condition principale

PARIS, NY, LONDRES = ZoneInfo("Europe/Paris"), ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
SUFFIXES_EU = {"DE", "PA", "AS", "MI", "MC", "SW", "CO", "ST", "HE", "BR", "LS", "VI", "OL", "IR"}
SEANCES = {"US": (NY, (9, 30), (16, 0)), "EU": (PARIS, (9, 0), (17, 30)), "UK": (LONDRES, (8, 0), (16, 30)),
           "FUT": (PARIS, (8, 0), (22, 0))}   # matières premières : heures où les ETC se négocient bien sur TR
ICI = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ICI, "state.json")
CACHE_D1 = os.path.join(ICI, "cache_d1.pkl")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36"}
FORCE = "--force" in sys.argv

def maintenant():
    return datetime.now(timezone.utc)

def log(*a):
    print(datetime.now(PARIS).strftime("%H:%M:%S"), *a, flush=True)

# ═════════════════════════════════════════════════════════════════════════════
# 2. MARCHÉS & SÉANCES
# ═════════════════════════════════════════════════════════════════════════════

def marche(sym):
    if sym.endswith("=F"):
        return "FUT"
    if sym.endswith("-EUR") or sym.endswith("-USD"):
        return "CRYPTO"
    suf = sym.rsplit(".", 1)[-1] if "." in sym else ""
    if suf == "L":
        return "UK"
    if suf in SUFFIXES_EU:
        return "EU"
    return "US"

def seance_ouverte(m, t=None, avec_attente=True):
    if FORCE:
        return True
    t = t or maintenant()
    if m == "CRYPTO":
        p = t.astimezone(PARIS)
        (h1, m1), (h2, m2) = FENETRE_CRYPTO
        return h1 * 60 + m1 <= p.hour * 60 + p.minute < h2 * 60 + m2
    tz, (h1, m1), (h2, m2) = SEANCES[m]
    loc = t.astimezone(tz)
    if loc.weekday() >= 5:
        return False
    mins = loc.hour * 60 + loc.minute
    debut = h1 * 60 + m1 + (ATTENTE_OUVERTURE[m] if avec_attente else 0)
    return debut <= mins < h2 * 60 + m2

def fraction_seance(m):
    if m == "CRYPTO":
        p = maintenant().astimezone(PARIS)
        return max(0.05, (p.hour * 60 + p.minute) / 1440)
    tz, (h1, m1), (h2, m2) = SEANCES[m]
    loc = maintenant().astimezone(tz)
    f = ((loc.hour * 60 + loc.minute) - (h1 * 60 + m1)) / ((h2 * 60 + m2) - (h1 * 60 + m1))
    return min(1.0, max(0.08, f)) if seance_ouverte(m, avec_attente=False) else 1.0

# ═════════════════════════════════════════════════════════════════════════════
# 3. INDICATEURS
# ═════════════════════════════════════════════════════════════════════════════

def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def atr(df, n=14):
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()

def pct(a, b):
    return (a / b - 1) * 100 if b and not pd.isna(b) else np.nan

def reechantillonner(df, minutes, m):
    off = "30min" if (m == "US" and minutes >= 60) else "0min"
    r = df.resample(f"{minutes}min", offset=off, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    return r.dropna(subset=["Close"])

def terminees(df, minutes):
    """Retire la bougie en cours (volume partiel = faux signal)."""
    if df is None or df.empty:
        return df
    if df.index[-1] + pd.Timedelta(minutes=minutes) > maintenant():
        return df.iloc[:-1]
    return df

def vol_rel_horaire(m5, nb_barres, jours=10):
    """Volume des nb_barres dernières bougies 5 min / volume moyen AU MÊME HORAIRE les jours précédents.
    (Compare 10h-11h à 10h-11h : l'ouverture et la clôture sont toujours plus actives.)"""
    if m5 is None or len(m5) < nb_barres + 10:
        return np.nan
    fen = m5.iloc[-nb_barres:]
    v = fen["Volume"].sum()
    t0, t1 = fen.index[0].time(), fen.index[-1].time()
    d_now = fen.index[-1].date()
    hist = m5[m5.index.date != d_now]
    if hist.empty:
        return np.nan
    tt = hist.index.time
    masque = (tt >= t0) & (tt <= t1) if t0 <= t1 else ((tt >= t0) | (tt <= t1))
    par_jour = hist[masque].groupby(hist[masque].index.date)["Volume"].sum()
    par_jour = par_jour[par_jour > 0].iloc[-jours:]
    if len(par_jour) < 3 or par_jour.mean() <= 0:
        return np.nan
    return float(v / par_jour.mean())

def croisement(rapide, lente):
    if len(rapide) < 2 or pd.isna(lente.iloc[-2]) or pd.isna(lente.iloc[-1]):
        return 0
    a, b = rapide.iloc[-2] - lente.iloc[-2], rapide.iloc[-1] - lente.iloc[-1]
    return 1 if a <= 0 < b else (-1 if a >= 0 > b else 0)

def pivots(s, g=3, d=2):
    v = s.values
    hauts, bas = [], []
    for i in range(g, len(v) - d):
        w = v[i - g:i + d + 1]
        if v[i] == w.max():
            hauts.append(i)
        if v[i] == w.min():
            bas.append(i)
    return hauts, bas

def divergence(df, r, fenetre=40, recence=6):
    d, rr = df.iloc[-fenetre:], r.iloc[-fenetre:]
    n = len(d)
    hauts, bas = pivots(d["High"])[0], pivots(d["Low"])[1]
    if len(hauts) >= 2 and hauts[-1] >= n - recence:
        a, b = hauts[-2], hauts[-1]
        if d["High"].iloc[b] > d["High"].iloc[a] and rr.iloc[b] < rr.iloc[a] - 2 and rr.iloc[a] > 55:
            return -1
    if len(bas) >= 2 and bas[-1] >= n - recence:
        a, b = bas[-2], bas[-1]
        if d["Low"].iloc[b] < d["Low"].iloc[a] and rr.iloc[b] > rr.iloc[a] + 2 and rr.iloc[a] < 45:
            return 1
    return 0

def vwap_jour(m5):
    j = m5[m5.index.date == m5.index[-1].date()]
    if j.empty or j["Volume"].sum() <= 0:
        return None
    tp = (j["High"] + j["Low"] + j["Close"]) / 3
    return (tp * j["Volume"]).cumsum() / j["Volume"].cumsum(), j

def cloture_veille(d1, date_jour):
    if d1 is None or d1.empty:
        return np.nan
    avant = d1[d1.index.date < date_jour]
    return float(avant["Close"].iloc[-1]) if len(avant) else np.nan

# ═════════════════════════════════════════════════════════════════════════════
# 4. DONNÉES DE MARCHÉ (Yahoo Finance via yfinance, gratuit)
# ═════════════════════════════════════════════════════════════════════════════

def telecharger(tickers, period, interval, lot=40):
    out = {}
    tickers = list(dict.fromkeys(tickers))
    for i in range(0, len(tickers), lot):
        paquet = tickers[i:i + lot]
        data = None
        for essai in range(3):
            try:
                data = yf.download(paquet, period=period, interval=interval, group_by="ticker",
                                   auto_adjust=False, progress=False, threads=True, prepost=False)
                if data is not None and not data.empty:
                    break
            except Exception as e:
                log(f"[yahoo] {interval} essai {essai + 1} : {e}")
            time.sleep(4 * (essai + 1))
        if data is None or data.empty:
            continue
        for t in paquet:
            try:
                df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
                df["Volume"] = df["Volume"].fillna(0)
                if len(df) >= 5:
                    out[t] = df
            except Exception:
                pass
    return out

def donnees_jour(tickers, s, max_age_min=60):
    """Données journalières (1 an) mises en cache 1 h pour ménager Yahoo."""
    cache, frais_ = {}, False
    try:
        if os.path.exists(CACHE_D1) and time.time() - s.get("cache_d1_ts", 0) < max_age_min * 60:
            with open(CACHE_D1, "rb") as f:
                cache = pickle.load(f)
            frais_ = True
    except Exception:
        cache = {}
    manquants = [t for t in tickers if t not in cache]
    if manquants:
        neuf = telecharger(manquants, "1y", "1d")
        cache.update(neuf)
        if not frais_:
            s["cache_d1_ts"] = time.time()
        try:
            with open(CACHE_D1, "wb") as f:
                pickle.dump(cache, f)
        except Exception:
            pass
    return cache

# ═════════════════════════════════════════════════════════════════════════════
# 5. ACTUALITÉS, GÉOPOLITIQUE, CALENDRIER, IA
# ═════════════════════════════════════════════════════════════════════════════

def http_get(url, timeout=12):
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        return r if r.ok else None
    except Exception:
        return None

def lire_rss(url, max_h=48, n=10):
    r = http_get(url)
    if r is None:
        return []
    try:
        root = ET.fromstring(r.content)
    except Exception:
        return []
    out, limite = [], maintenant() - timedelta(hours=max_h)
    for it in root.iter("item"):
        titre = (it.findtext("title") or "").strip()
        src = it.find("source")
        source = src.text.strip() if src is not None and src.text else ""
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate"))
            dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = maintenant()
        if titre and dt >= limite:
            if source and titre.endswith(" - " + source):
                titre = titre[: -len(source) - 3]
            out.append({"dt": dt, "src": source, "titre": titre})
    return out[:n]

def google_news(requete, langue="fr", max_h=24, n=10):
    hl, gl, ceid = ("fr", "FR", "FR:fr") if langue == "fr" else ("en-US", "US", "US:en")
    j = max(1, math.ceil(max_h / 24))
    url = f"https://news.google.com/rss/search?q={quote(requete + f' when:{j}d')}&hl={hl}&gl={gl}&ceid={ceid}"
    return lire_rss(url, max_h, n)

def gdelt(requete, fenetre="6h", n=15):
    url = (f"https://api.gdeltproject.org/api/v2/doc/doc?query={quote(requete)}&mode=artlist&format=json"
           f"&timespan={fenetre}&maxrecords={n}&sort=datedesc")
    r = http_get(url, 20)
    if r is None:
        return []
    try:
        arts = r.json().get("articles", [])
    except Exception:
        return []
    out = []
    for a in arts:
        try:
            dt = datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            dt = maintenant()
        out.append({"dt": dt, "src": a.get("domain", ""), "titre": a.get("title", "").strip()})
    return out

def dedoublonner(items, n):
    vus, out = set(), []
    for it in sorted(items, key=lambda x: x["dt"], reverse=True):
        k = re.sub(r"\W+", "", it["titre"].lower())[:60]
        if k and k not in vus:
            vus.add(k)
            out.append(it)
    return out[:n]

COMMOS_EN = {"GC=F": "gold", "SI=F": "silver", "PL=F": "platinum", "HG=F": "copper", "CL=F": "WTI crude oil",
             "BZ=F": "Brent oil", "NG=F": "natural gas", "ZW=F": "wheat", "ZC=F": "corn", "ZS=F": "soybeans",
             "KC=F": "coffee", "CC=F": "cocoa", "SB=F": "sugar"}

def actus_symbole(sym):
    if sym in U.COMMOS:
        en, fr = COMMOS_EN.get(sym, sym), U.COMMOS[sym][0].lower()
        return dedoublonner(google_news(f"{en} price", "en", 24, 8) + google_news(f"cours {fr} matière première", "fr", 48, 5), 10)
    nom = U.NOMS.get(sym, sym.split(".")[0].split("-")[0])
    items = []
    if marche(sym) == "US":
        items += lire_rss(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US", 48, 8)
    if marche(sym) == "CRYPTO":
        items += google_news(f"{nom} crypto", "en", 24, 8) + google_news(f"{nom} crypto", "fr", 24, 5)
    else:
        items += google_news(f'"{nom}" stock', "en", 48, 8) + google_news(f'"{nom}" action bourse', "fr", 48, 6)
    return dedoublonner(items, 10)

_ACTUS_MONDE = None
def actus_monde():
    global _ACTUS_MONDE
    if _ACTUS_MONDE is None:
        items = (google_news("bourse OR marchés OR géopolitique OR Fed OR BCE", "fr", 12, 10)
                 + google_news("stock market OR geopolitics OR tariffs OR sanctions OR Fed OR OPEC", "en", 12, 12)
                 + gdelt('(sanctions OR tariffs OR missile OR invasion OR ceasefire OR "export controls" OR OPEC '
                         'OR "interest rates" OR semiconductors OR Taiwan) sourcelang:english', "6h", 15))
        _ACTUS_MONDE = dedoublonner(items, 20)
    return _ACTUS_MONDE

def fmt_actus(items, n=8):
    if not items:
        return "(aucune actualité trouvée)"
    return "\n".join(f"- [{it['dt'].astimezone(PARIS):%d/%m %H:%M}] {it['titre']} ({it['src']})" for it in items[:n])

def calendrier(s):
    """Annonces macro à fort impact (source : calendrier ForexFactory, gratuit). Rafraîchi toutes les 3 h."""
    if time.time() - s.get("cal_ts", 0) > 3 * 3600:
        r = http_get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", 15)
        if r is not None:
            try:
                s["cal"] = [e for e in r.json() if e.get("impact") == "High" and e.get("country") in DEVISES_CALENDRIER]
                s["cal_ts"] = time.time()
            except Exception:
                pass
    out = []
    for e in s.get("cal", []):
        try:
            out.append((datetime.fromisoformat(e["date"]).astimezone(timezone.utc), e["country"], e["title"]))
        except Exception:
            pass
    return sorted(out)

def blackout_macro(evts):
    t = maintenant()
    for dt, pays, titre in evts:
        if dt - timedelta(minutes=BLACKOUT_AVANT) <= t <= dt + timedelta(minutes=BLACKOUT_APRES):
            return f"{titre} ({pays}) à {dt.astimezone(PARIS):%H:%M}"
    return None

def llm(messages, json_mode=False, max_tokens=500, s=None):
    if not LLM_KEY:
        return None
    if s is not None:
        jour = datetime.now(PARIS).strftime("%Y-%m-%d")
        if s.setdefault("llm_jour", {}).get(jour, 0) >= LLM_MAX_PAR_JOUR:
            return None
        s["llm_jour"] = {jour: s["llm_jour"].get(jour, 0) + 1}
    corps = {"model": LLM_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    if "gpt-oss" in LLM_MODEL:           # modèle "qui réfléchit" : on limite la réflexion et on laisse de la place
        corps["reasoning_effort"] = "low"
        corps["max_tokens"] = max_tokens + 800
    if json_mode:
        corps["response_format"] = {"type": "json_object"}
    for essai in range(3):
        try:
            r = requests.post(f"{LLM_BASE}/chat/completions", json=corps, timeout=45,
                              headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"})
            if r.status_code == 429:
                time.sleep(min(30, float(r.headers.get("retry-after", 10 * (essai + 1)))))
                continue
            if r.status_code == 400 and "reasoning_effort" in corps:
                corps.pop("reasoning_effort")
                continue
            if r.status_code == 400 and "response_format" in corps:
                corps.pop("response_format")   # modèle sans mode JSON : on réessaie en texte libre
                continue
            if not r.ok:
                log("[ia] erreur", r.status_code, r.text[:200])
                return None
            txt = r.json()["choices"][0]["message"]["content"]
            if not json_mode:
                return txt.strip()
            m = re.search(r"\{.*\}", txt, re.S)
            return json.loads(m.group(0)) if m else None
        except Exception as e:
            log("[ia] exception", e)
            time.sleep(3)
    return None

SYSTEME_ANALYSTE = (
    "Tu es un analyste marchés senior (actions, crypto, macro, géopolitique) qui travaille pour un particulier "
    "français utilisant Trade Republic. Règles absolues : tu n'utilises QUE les données et titres fournis, tu "
    "n'inventes aucun chiffre, aucun fait, aucune actualité ; si l'information manque tu le dis. Tu es exigeant : "
    "dans le doute, tu choisis PRUDENCE. Tu écris en français, phrases courtes et concrètes.")

MOTS_POS = ["beat", "beats", "record", "upgrade", "raises", "raised guidance", "surge", "soar", "jump", "rally",
            "contract", "partnership", "approval", "buyback", "hausse", "relève", "bondit", "envolée", "contrat",
            "accord", "record", "rachat"]
MOTS_NEG = ["miss", "misses", "downgrade", "cuts", "cut guidance", "probe", "investigation", "lawsuit", "plunge",
            "tumble", "fraud", "recall", "sanction", "tariff", "ban", "delay", "warning", "baisse", "abaisse",
            "chute", "plonge", "enquête", "avertissement", "retard", "droits de douane"]

def verdict_actus(c, s):
    """Confronte le signal technique aux actualités du titre et du monde. Retourne un dict verdict."""
    actus = actus_symbole(c["sym"])
    monde = actus_monde()
    sens = "ACHAT" if c["dir"] > 0 else "VENTE"
    donnees = (
        f"Titre : {c['sym']} ({nom_tr(c['sym'])}) — {U.CONTEXTE.get(c['sym'], '')}\n"
        f"Signal technique : {sens} ({c['module_nom']}), score {c['score']}\n"
        f"Conditions : {'; '.join(t for _, _, t, _ in c['conds'])}\n"
        f"Prix {c['prix']:.4g} · variation {c['var_label']} {f1(c['var'])} · jour {f1(c['var_jour'])} · "
        f"RSI 1h {f1(c['rsi'], '{:.0f}')} · volume {f1(c['vol'], '{:.1f}×')} la normale · "
        f"tendance de fond {c['tendance_txt']}\n"
        f"Régime de marché : {c['regime_txt']}\n"
        f"Annonces macro à venir aujourd'hui : {c['evts_txt']}\n\n"
        f"ACTUALITÉS DU TITRE (48 h) :\n{fmt_actus(actus, 8)}\n\n"
        f"ACTUALITÉS MONDE / GÉOPOLITIQUE (12 h) :\n{fmt_actus(monde, 10)}")
    rep = None
    if LLM_KEY and len(s.get("_llm_scan", [])) >= LLM_MAX_PAR_SCAN:
        return None   # budget IA du passage épuisé : ce signal sera revu au prochain passage (5 min)
    if len(s.get("_llm_scan", [])) < LLM_MAX_PAR_SCAN:
        s.setdefault("_llm_scan", []).append(c["sym"])
        rep = llm([
            {"role": "system", "content": SYSTEME_ANALYSTE},
            {"role": "user", "content": donnees + "\n\nDis si les actualités CONFIRMENT, rendent PRUDENT, ou "
             "CONTREDISENT (REJETE) ce signal. REJETE si une actu majeure va clairement dans le sens opposé "
             "(résultats ratés, abaissement d'objectifs, enquête, sanction, escalade géopolitique qui touche "
             "directement ce titre/secteur) ou si le mouvement semble déjà totalement fini. CONFIRME seulement "
             "si une actu identifiable explique et soutient le mouvement. Sinon PRUDENCE.\n"
             'Réponds en JSON : {"verdict":"CONFIRME|PRUDENCE|REJETE","impact":-2..2,'
             '"actu":"cause probable du mouvement en 20 mots max, ou \'aucune actu identifiée\'",'
             '"risque":"principal risque macro/géopolitique pour ce titre, 15 mots max",'
             '"avis":"avis clair en 25 mots max",'
             '"simple":"UNE phrase pour un débutant, sans aucun jargon (pas de RSI, MM, volume...), qui dit ce qui se passe et pourquoi, 30 mots max"}'}],
            json_mode=True, max_tokens=350, s=s)
    if isinstance(rep, dict) and rep.get("verdict") in ("CONFIRME", "PRUDENCE", "REJETE"):
        rep["source"] = "ia"
        return rep
    # Repli sans IA : analyse par mots-clés
    txt = " ".join(a["titre"].lower() for a in actus[:8])
    sc = sum(txt.count(m) for m in MOTS_POS) - sum(txt.count(m) for m in MOTS_NEG)
    if not actus:
        v = "PRUDENCE"
    elif sc * c["dir"] >= 2:
        v = "CONFIRME"
    elif sc * c["dir"] <= -2:
        v = "REJETE"
    else:
        v = "PRUDENCE"
    return {"verdict": v, "impact": int(np.sign(sc)) * min(2, abs(sc)), "source": "mots-clés",
            "actu": actus[0]["titre"][:140] if actus else "aucune actu identifiée",
            "risque": "", "avis": ""}

# ═════════════════════════════════════════════════════════════════════════════
# 6. RÉGIME DE MARCHÉ
# ═════════════════════════════════════════════════════════════════════════════

def variation_jour(df):
    if df is None or len(df) < 2:
        return np.nan
    return pct(float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2]))

def regime_marche(macro):
    vix = macro.get("^VIX")
    nq = variation_jour(macro.get("NQ=F"))
    vix_niv = float(vix["Close"].iloc[-1]) if vix is not None else np.nan
    vix_var = variation_jour(vix)
    r, raisons = 0, []
    if (not np.isnan(vix_niv) and vix_niv >= 25) or (not np.isnan(vix_var) and vix_var >= 15):
        r = -1
        raisons.append(f"VIX {vix_niv:.1f} ({vix_var:+.0f}%)")
    if not np.isnan(nq) and nq <= -1.5:
        r = -1
        raisons.append(f"Nasdaq futures {nq:+.1f}%")
    if r == 0 and not np.isnan(vix_niv) and vix_niv < 17 and not np.isnan(nq) and nq > 0.4:
        r = 1
        raisons.append(f"VIX bas {vix_niv:.1f}, Nasdaq futures {nq:+.1f}%")
    label = {1: "🟢 Marché confiant", 0: "⚪ Marché neutre", -1: "🔴 Marché inquiet"}[r]
    if not raisons and not np.isnan(vix_niv):
        raisons.append(f"VIX {vix_niv:.1f}" + (f", Nasdaq fut. {nq:+.1f}%" if not np.isnan(nq) else ""))
    return r, f"{label} ({', '.join(raisons)})" if raisons else label

DEVISES_SUFFIXE = {"SW": "CHF", "CO": "DKK", "ST": "SEK", "L": "GBp", "OL": "NOK"}

def devise(sym):
    m = marche(sym)
    if m in ("US", "FUT"):
        return "USD"
    if m == "CRYPTO":
        return "EUR"
    return DEVISES_SUFFIXE.get(sym.rsplit(".", 1)[-1] if "." in sym else "", "EUR")

def taux_change(macro):
    """Multiplicateurs devise locale -> euro (Trade Republic affiche tout en €)."""
    def dernier(k):
        df = macro.get(k)
        return float(df["Close"].iloc[-1]) if df is not None and len(df) else np.nan
    eu = dernier("EURUSD=X")
    t = {"EUR": 1.0, "USD": 1 / eu if eu and not np.isnan(eu) else np.nan}
    g = dernier("GBPEUR=X")
    t["GBp"] = g / 100 if not np.isnan(g) else np.nan
    for dv in ("CHF", "DKK", "SEK", "NOK"):
        t[dv] = dernier(f"{dv}EUR=X")
    return t

def en_eur(sym, p, fx):
    r = (fx or {}).get(devise(sym), np.nan)
    return p * r if p is not None and r and not np.isnan(r) else np.nan

# ═════════════════════════════════════════════════════════════════════════════
# 7. RÈGLES D'ANALYSE — chaque règle renvoie [(points, sens, texte, principale)]
#    sens : +1 achat · -1 vente · 0 amplificateur (volume, écart...)
# ═════════════════════════════════════════════════════════════════════════════

def var_minutes(ctx, minutes):
    m5 = ctx["m5_brut"]
    jour = m5[m5.index.date == m5.index[-1].date()]
    k = minutes // 5
    if len(jour) > k:
        ref = float(jour["Close"].iloc[-1 - k])
    elif len(jour):
        ref = float(jour["Open"].iloc[0])
    else:
        return np.nan
    return pct(ctx["prix"], ref)

def R_rsi(ctx, p):
    df = ctx.get(p["tf"])
    if df is None or len(df) < 20:
        return []
    r = rsi(df["Close"])
    now, prev = float(r.iloc[-1]), float(r.iloc[-2])
    tf = p["tf"].upper()
    if p["mode"] == "retour":
        if now < p["bas"]:
            return [(1, 1, f"RSI {tf} en survente ({now:.0f})", True)]
        if now > p["haut"]:
            return [(1, -1, f"RSI {tf} en surachat ({now:.0f})", True)]
    else:
        if now > p["haut"] >= prev:
            return [(1, 1, f"RSI {tf} sort par le haut de la zone {p['bas']}-{p['haut']} ({now:.0f})", True)]
        if now < p["bas"] <= prev:
            return [(1, -1, f"RSI {tf} sort par le bas de la zone {p['bas']}-{p['haut']} ({now:.0f})", True)]
    return []

def R_momentum(ctx, p):
    v = var_minutes(ctx, p["min"])
    vr = vol_rel_horaire(ctx["m5"], p["min"] // 5)
    if np.isnan(v) or abs(v) < p["seuil"]:
        return []
    if p["vol"] and (np.isnan(vr) or vr < p["vol"]):
        return []
    h = f"{p['min'] // 60}h" if p["min"] >= 60 else f"{p['min']}min"
    extra = f", volume {vr:.1f}×" if p["vol"] else ""
    return [(p.get("pts", 2), 1 if v > 0 else -1, f"{'hausse' if v > 0 else 'baisse'} de {v:+.1f}% en {h}{extra}", True)]

def R_volume(ctx, p):
    vr = vol_rel_horaire(ctx["m5"], p["min"] // 5)
    return [(1, 0, f"volume {vr:.1f}× la normale à cette heure", True)] if vr >= p["mult"] else []

def R_croise_prix_mm(ctx, p):
    df = ctx.get(p["tf"])
    if df is None or len(df) < p["n"] + 2:
        return []
    x = croisement(df["Close"], df["Close"].rolling(p["n"]).mean())
    vr = vol_rel_horaire(ctx["m5"], 12)
    if x and vr >= p["vol"]:
        return [(1, x, f"prix {'repasse au-dessus' if x > 0 else 'casse'} la MM{p['n']} {p['tf'].upper()} (volume {vr:.1f}×)", True)]
    return []

def R_croise_mm(ctx, p):
    df = ctx.get(p["tf"])
    if df is None or len(df) < p["lente"] + 2:
        return []
    x = croisement(df["Close"].ewm(span=p["rapide"]).mean(), df["Close"].ewm(span=p["lente"]).mean())
    if not x:
        return []
    return [(1, x, f"croisement MM{p['rapide']}/MM{p['lente']} {'haussier' if x > 0 else 'baissier'} en {p['tf'].upper()}",
             not p.get("confirmation", False))]

def R_breakout(ctx, p):
    df = ctx.get(p["tf"])
    n = p["n"]
    if df is None or len(df) < n + 2:
        return []
    hi, lo = df["High"].iloc[-n - 1:-1].max(), df["Low"].iloc[-n - 1:-1].min()
    vr = vol_rel_horaire(ctx["m5"], 12)
    last = float(df["Close"].iloc[-1])
    if np.isnan(vr) or vr < p["vol"]:
        return []
    if last > hi:
        return [(p.get("pts", 2), 1, f"cassure du plus haut {n} bougies {p['tf'].upper()} ({hi:.4g}), volume {vr:.1f}×", True)]
    if last < lo:
        return [(p.get("pts", 2), -1, f"cassure du plus bas {n} bougies {p['tf'].upper()} ({lo:.4g}), volume {vr:.1f}×", True)]
    return []

def R_divergence(ctx, p):
    df = ctx.get(p["tf"])
    if df is None or len(df) < 40:
        return []
    d = divergence(df, rsi(df["Close"]))
    return [(1, d, f"divergence RSI {'haussière' if d > 0 else 'baissière'} en {p['tf'].upper()}", True)] if d else []

def R_ecart_mm(ctx, p):
    df = ctx.get(p["tf"])
    if df is None or len(df) < p["n"]:
        return []
    e = pct(float(df["Close"].iloc[-1]), float(df["Close"].rolling(p["n"]).mean().iloc[-1]))
    return [(1, 0, f"écart de {e:+.1f}% avec la MM{p['n']} {p['tf'].upper()}", True)] if abs(e) > p["seuil"] else []

def R_vwap(ctx, p):
    res = vwap_jour(ctx["m5"])
    if res is None:
        return []
    vw, j = res
    if len(j) < 6:
        return []
    x = croisement(j["Close"], vw)
    vr = vol_rel_horaire(ctx["m5"], 6)
    if x and vr >= p["vol"]:
        return [(1, x, f"prix {'reprend' if x > 0 else 'perd'} le VWAP du jour ({float(vw.iloc[-1]):.4g}), volume {vr:.1f}×", True)]
    return []

def R_tendance_tf(ctx, p):
    df = ctx.get(p["tf"])
    if df is None or len(df) < p["n"] + 1:
        return []
    t = 1 if df["Close"].iloc[-1] > df["Close"].ewm(span=p["n"]).mean().iloc[-1] else -1
    return [(1, t, f"tendance {p['tf'].upper()} {'haussière' if t > 0 else 'baissière'}", False)]

def R_var_jour(ctx, p):
    v = ctx["var_jour"]
    if np.isnan(v) or abs(v) < p["seuil"]:
        return []
    return [(p.get("pts", 2), 1 if v > 0 else -1, f"variation du jour {v:+.1f}%", True)]

def R_volume_jour(ctx, p):
    d1 = ctx["d1"]
    if d1 is None or len(d1) < 22:
        return []
    date_j = ctx["m5_brut"].index[-1].date()
    hist = d1[d1.index.date < date_j]["Volume"].iloc[-20:]
    vj = ctx["m5_brut"][ctx["m5_brut"].index.date == date_j]["Volume"].sum()
    if hist.mean() <= 0:
        return []
    vr = vj / fraction_seance(ctx["marche"]) / hist.mean()
    return [(1, 0, f"volume du jour projeté {vr:.1f}× la moyenne 20 j", True)] if vr >= p["mult"] else []

def R_range_jours(ctx, p):
    d1 = ctx["d1"]
    if d1 is None or len(d1) < p["n"] + 2:
        return []
    date_j = ctx["m5_brut"].index[-1].date()
    h = d1[d1.index.date < date_j].iloc[-p["n"]:]
    hi, lo = h["High"].max(), h["Low"].min()
    if ctx["prix"] > hi:
        return [(1, 1, f"sortie par le haut du range {p['n']} jours ({hi:.4g})", True)]
    if ctx["prix"] < lo:
        return [(1, -1, f"sortie par le bas du range {p['n']} jours ({lo:.4g})", True)]
    return []

def R_correlation(ctx, p):
    d1 = ctx["d1"]
    if d1 is None or np.isnan(ctx["var_jour"]):
        return []
    for ref in p["refs"]:
        rd, rc = ctx["_d1_all"].get(ref), ctx["_ctx_all"].get(ref)
        if rd is None or rc is None:
            continue
        j = d1["Close"].pct_change().iloc[-21:-1]
        corr = j.corr(rd["Close"].pct_change().reindex(j.index))
        rv = rc["var_jour"]
        if corr >= p["min"] and not np.isnan(rv) and np.sign(rv) == np.sign(ctx["var_jour"]) and abs(rv) > 1.5:
            return [(1, int(np.sign(rv)), f"mouvement aligné avec {ref} ({rv:+.1f}%, corrélation {corr:.2f})", False)]
    return []

REGLES = {"rsi": R_rsi, "momentum": R_momentum, "volume": R_volume, "croise_prix_mm": R_croise_prix_mm,
          "croise_mm": R_croise_mm, "breakout": R_breakout, "divergence": R_divergence, "ecart_mm": R_ecart_mm,
          "vwap": R_vwap, "tendance_tf": R_tendance_tf, "var_jour": R_var_jour, "volume_jour": R_volume_jour,
          "range_jours": R_range_jours, "correlation": R_correlation}

# ═════════════════════════════════════════════════════════════════════════════
# 8. CONTEXTE PAR TITRE + ÉVALUATION
# ═════════════════════════════════════════════════════════════════════════════

def construire_ctx(sym, m5_all, d1_all, tolerer_perime=False):
    m5 = m5_all.get(sym)
    if m5 is None or len(m5) < 60:
        return None
    age = (maintenant() - m5.index[-1]).total_seconds() / 60 - 5
    if age > FRAICHEUR_MAX_MIN and not FORCE and not tolerer_perime:
        return None
    mk = marche(sym)
    d1 = d1_all.get(sym)
    prix = float(m5["Close"].iloc[-1])
    date_j = m5.index[-1].date()
    ctx = {"sym": sym, "marche": mk, "prix": prix, "age": max(0, age), "ts": m5.index[-1], "d1": d1,
           "m5_brut": m5, "m5": terminees(m5, 5), "m15": terminees(reechantillonner(m5, 15, mk), 15),
           "h1": terminees(reechantillonner(m5, 60, mk), 60), "h4": reechantillonner(m5, 240, mk)}
    ctx["var_jour"] = pct(prix, cloture_veille(d1, date_j)) if mk != "CRYPTO" else pct(prix, float(m5["Close"].iloc[-289])) if len(m5) > 289 else np.nan
    h1 = ctx["h1"]
    ctx["rsi"] = float(rsi(h1["Close"]).iloc[-1]) if h1 is not None and len(h1) > 15 else np.nan
    ctx["tendance"], ctx["atr_pct"] = 0, np.nan
    if d1 is not None and len(d1) > 60:
        c = d1["Close"]
        mm50, mm20 = c.rolling(50).mean().iloc[-1], c.rolling(20).mean().iloc[-1]
        ctx["tendance"] = 1 if prix > mm50 and mm20 > mm50 else (-1 if prix < mm50 and mm20 < mm50 else 0)
        ctx["atr_pct"] = float(atr(d1).iloc[-1]) / float(c.iloc[-1]) * 100
    return ctx

def analyser(mod, cfg, ctx):
    if cfg.get("vol_min"):
        vr = vol_rel_horaire(ctx["m5"], 12)
        if np.isnan(vr) or vr < cfg["vol_min"]:
            return []
    conds = []
    for nom, p in cfg["regles"]:
        if nom in REGLES_CONFIRMATION and not conds:
            continue
        try:
            conds += REGLES[nom](ctx, p)
        except Exception as e:
            log(f"  règle {nom} {ctx['sym']} : {e}")
    return conds

def evaluer(conds, ctx, regime):
    principales = [c for c in conds if c[3]]
    sens = {c[1] for c in conds if c[1] != 0}
    if len(principales) < MIN_CONDITIONS or len(sens) != 1 or not any(c[1] for c in principales):
        return 0, 0
    d = sens.pop()
    score = sum(c[0] for c in conds)
    score += 1 if ctx["tendance"] == d else (-1 if ctx["tendance"] == -d else 0)
    if regime == -1 and d > 0:
        score -= 1
    return d, score

def etoiles(score):
    return int(min(5, max(1, score - 1)))

def niveaux(ctx, d):
    a = ctx["atr_pct"]
    if np.isnan(a):
        a = 3.0 if ctx["marche"] == "CRYPTO" else 2.0
    p = ctx["prix"]
    k_s, k_o = _NIV["stop"], _NIV["obj"]
    stop, obj = p * (1 - d * k_s * a / 100), p * (1 + d * k_o * a / 100)
    return stop, obj, k_s * a, k_o * a

def rentabilite(capital, obj_pct, stop_pct):
    mise = capital * MISE_PART
    return mise, mise * obj_pct / 100 - 2 * FRAIS_ORDRE, mise * stop_pct / 100 + 2 * FRAIS_ORDRE

def rentable(capital, obj_pct, stop_pct):
    """Vrai si, frais inclus, ce qu'on gagne quand ça marche vaut au moins RATIO_MIN × ce qu'on perd quand ça rate."""
    _, gain, perte = rentabilite(capital, obj_pct, stop_pct)
    return gain > 0 and gain >= RATIO_MIN_APRES_FRAIS * perte

# ═════════════════════════════════════════════════════════════════════════════
# 9. FORMAT DES ALERTES
# ═════════════════════════════════════════════════════════════════════════════

def feur(x):
    if x is None or np.isnan(x):
        return "n/d"
    return (f"{x:,.2f} €" if abs(x) >= 1 else f"{x:.4g} €").replace(",", " ")

def fprix(sym, p, fx):
    dv = devise(sym)
    if dv == "EUR":
        return feur(p)
    loc = {"USD": f"${p:,.2f}", "GBp": f"{p:,.1f} GBp"}.get(dv, f"{p:,.2f} {dv}").replace(",", " ")
    if marche(sym) == "FUT":
        return f"{loc} (contrat de référence)"
    e = en_eur(sym, p, fx)
    return f"{loc} (≈ {feur(e)} sur TR)" if not np.isnan(e) else loc

def f1(x, fmt="{:+.1f}%"):
    return "n/d" if x is None or (isinstance(x, float) and np.isnan(x)) else fmt.format(x)

def formater_alerte(c, s, fx):
    sym, d, cfg = c["sym"], c["dir"], MODULES[c["mod"]]
    capital = s.get("capital", CAPITAL_DEFAUT)
    et = c["etoiles"]
    sens = "ACHAT" if d > 0 else "VENTE"
    v = c["verdict"]
    lignes = [f"{cfg['emoji']} {cfg['nom']} – {sym} ({U.NOMS.get(sym, sym)})",
              f"Signal : {sens} · Confiance {'★' * et}{'☆' * (5 - et)}",
              f"Prix : {fprix(sym, c['prix'], fx)}",
              f"Variation {c['var_label']} : {f1(c['var'])}" + (f" · jour : {f1(c['var_jour'])}" if c["var_label"] != "jour" else ""),
              f"RSI 1h : {f1(c['rsi'], '{:.0f}')} · Volume : {f1(c['vol'], '{:.1f}×')} la normale",
              f"Tendance de fond : {c['tendance_txt']}",
              f"Marché : {c['regime_txt']}",
              f"Raison : {'; '.join(t for _, _, t, _ in c['conds']) or 'aucune condition technique réunie'}."]
    if U.CONTEXTE.get(sym):
        lignes.append(f"Contexte : {U.CONTEXTE[sym]}.")
    lignes.append(f"📰 Actu : {v.get('actu') or 'aucune actu identifiée'}")
    if v.get("risque"):
        lignes.append(f"🌍 Risque : {v['risque']}")
    if v.get("avis"):
        lignes.append(f"🧠 Avis : {v['avis']}")
    lignes.append(f"✅ Vérif. actus ({v.get('source')}) : {v['verdict']}")
    if d > 0:
        mise, gain, perte = rentabilite(capital, c["obj_pct"], c["stop_pct"])
        lignes += [f"🎯 Objectif : {fprix(sym, c['obj'], fx)} (+{c['obj_pct']:.1f}%) · horizon {_NIV['horizon']}",
                   f"🛑 Stop : {fprix(sym, c['stop'], fx)} (−{c['stop_pct']:.1f}%)",
                   f"💶 Avec {mise:.0f} € : gain net à l'objectif {gain:+.2f} € / perte au stop −{perte:.2f} € "
                   f"(frais TR {2 * FRAIS_ORDRE:.0f} € inclus)"]
    lignes.append(f"👉 Action suggérée : {c['action']}")
    if sym in U.NON_TR:
        lignes.append("ℹ️ Non achetable sur TR : sers-t'en comme indicateur pour les minières du cuivre.")
    lignes.append(f"🕒 Cours de {c['ts'].astimezone(PARIS):%H:%M} (Paris), analyse {datetime.now(PARIS):%H:%M}")
    return "\n".join(lignes)

# ─── Version simple (pour débutant) ─────────────────────────────────────────

TRADUCTIONS = [   # (motif dans la condition technique, sens, explication sans jargon)
    ("cassure du plus haut", 1, "le prix dépasse son plus haut des derniers jours"),
    ("cassure du plus bas", -1, "le prix passe sous son plus bas des derniers jours"),
    ("sortie par le haut", 1, "le prix atteint son plus haut depuis 2 semaines"),
    ("sortie par le bas", -1, "le prix tombe à son plus bas depuis 2 semaines"),
    ("hausse de", 1, "le prix monte fort depuis quelques heures"),
    ("baisse de", -1, "le prix chute fort depuis quelques heures"),
    ("variation du jour", 0, "grosse variation aujourd'hui"),
    ("survente", 1, "il a beaucoup baissé en peu de temps : un rebond arrive souvent"),
    ("surachat", -1, "il a beaucoup monté en peu de temps : une pause ou une baisse arrive souvent"),
    ("sort par le haut", 1, "les acheteurs prennent nettement le dessus"),
    ("sort par le bas", -1, "les vendeurs prennent nettement le dessus"),
    ("divergence rsi haussière", 1, "la baisse s'essouffle"),
    ("divergence rsi baissière", -1, "la hausse s'essouffle"),
    ("croisement", 0, "la tendance à court terme vient de changer de sens"),
    ("vwap", 0, "le prix repasse de l'autre côté du prix moyen payé aujourd'hui"),
    ("repasse au-dessus", 1, "le prix repasse au-dessus de sa moyenne récente"),
    ("casse la mm", -1, "le prix passe sous sa moyenne récente"),
    ("écart de", 0, "le prix est très éloigné de sa moyenne récente"),
    ("aligné avec", 0, "il suit le mouvement de Nvidia / du secteur IA"),
    ("volume", 0, "beaucoup plus d'échanges que d'habitude : le mouvement est sérieux"),
]

def expliquer(conds, nmax=3):
    out = []
    for _, _, texte, principale in conds:
        if not principale:
            continue
        t = texte.lower()
        for motif, _, phrase in TRADUCTIONS:
            if motif in t:
                if phrase not in out:
                    out.append(phrase)
                break
    if any("volume" in c[2].lower() for c in conds) and TRADUCTIONS[-1][2] not in out:
        out.append(TRADUCTIONS[-1][2])
    return out[:nmax]

def nom_tr(sym):
    """Ce qu'il faut taper dans la recherche de l'appli Trade Republic."""
    if sym in U.COMMOS:
        return U.COMMOS[sym][1]
    return U.NOMS.get(sym, sym)

def formater_simple(c, s, fx):
    sym, d = c["sym"], c["dir"]
    capital = s.get("capital", CAPITAL_DEFAUT)
    et = c["etoiles"]
    v = c["verdict"]
    nom = U.COMMOS[sym][0] if sym in U.COMMOS else U.NOMS.get(sym, sym)
    act = c["action"]
    if d > 0 and act == "Acheter":
        tete = f"🟢 ACHETER {nom}"
    elif d > 0:
        tete = f"🟡 ACHAT POSSIBLE (petite mise) : {nom}"
    else:
        tete = f"🔴 VENDRE {nom}"
    lignes = [tete, f"Fiabilité : {'●' * et}{'○' * (5 - et)} ({et}/5)", ""]
    pourquoi = v.get("simple") or ""
    raisons = expliquer(c["conds"])
    lignes.append("Pourquoi :")
    if pourquoi:
        lignes.append(f"• {pourquoi}")
    lignes += [f"• {r[0].upper() + r[1:]}" for r in raisons[: (2 if pourquoi else 3)]]
    actu = v.get("actu") or ""
    if actu and "aucune" not in actu.lower() and not pourquoi:
        lignes.append(f"• Actu : {actu}")
    lignes.append("")
    commo = sym in U.COMMOS
    if d > 0:
        mise, gain, perte = rentabilite(capital, c["obj_pct"], c["stop_pct"])
        prix_eur = en_eur(sym, c["prix"], fx)
        lignes.append("Sur Trade Republic :")
        lignes.append(f"1. Cherche « {nom_tr(sym)} »")
        lignes.append(f"2. Achète pour {mise:.0f} € (ordre au marché)"
                      + (f" — prix actuel ≈ {feur(prix_eur)}" if not commo and not np.isnan(prix_eur) else ""))
        if commo:
            lignes.append(f"3. Revends quand ta ligne affiche +{c['obj_pct']:.0f}% (objectif) "
                          f"ou −{c['stop_pct']:.0f}% (on coupe la perte)")
        else:
            lignes.append(f"3. Revends si le prix monte vers {feur(en_eur(sym, c['obj'], fx))} (+{c['obj_pct']:.0f}%) "
                          f"ou descend vers {feur(en_eur(sym, c['stop'], fx))} (−{c['stop_pct']:.0f}%)")
        lignes.append(f"💶 Résultat attendu, frais de 2 € inclus : {gain:+.2f} € si ça marche / "
                      f"−{perte:.2f} € si ça rate · durée {_NIV['horizon']}")
        lignes.append("👉 Après l'achat, appuie sur « ✅ J'ai acheté » : je te préviendrai quand revendre.")
    else:
        lignes.append("Sur Trade Republic :")
        lignes.append(f"1. Ouvre ta ligne « {nom_tr(sym)} » → Vendre (tout).")
        lignes.append("2. Puis appuie sur « ✅ J'ai vendu ».")
    if v.get("risque"):
        lignes.append(f"⚠️ Risque : {v['risque']}")
    lignes.append(f"🕒 {datetime.now(PARIS):%H:%M}")
    return "\n".join(lignes)

def envoyable_simple(c):
    a = c["action"]
    return a.startswith("Acheter") or a.startswith("Vendre")

def decider_action(c, s):
    capital = s.get("capital", CAPITAL_DEFAUT)
    d, et, v = c["dir"], c["etoiles"], c["verdict"]["verdict"]
    if d < 0:
        return "Vendre (tu détiens ce titre)" if c["sym"] in s.get("positions", {}) else "Éviter / ne pas acheter"
    if c["sym"] in U.NON_TR:
        return "Indicateur seulement"
    if not rentable(capital, c["obj_pct"], c["stop_pct"]):
        return f"Surveiller — non rentable avec {capital:.0f} € (les {2 * FRAIS_ORDRE:.0f} € de frais mangent le gain)"
    if et >= 4 and v == "CONFIRME" and c["tendance"] >= 0:
        return "Acheter"
    if et >= 3 and v != "REJETE" and c["tendance"] >= 0:
        return "Acheter prudemment (petite mise) ou attendre confirmation"
    return "Surveiller de près"

# ═════════════════════════════════════════════════════════════════════════════
# 10. TELEGRAM
# ═════════════════════════════════════════════════════════════════════════════

def telegram(msg, clavier=None):
    morceaux = [msg[i:i + 3900] for i in range(0, len(msg), 3900)] or [""]
    if not TG_TOKEN or not TG_CHAT:
        extra = ""
        if clavier and "inline_keyboard" in clavier:
            extra = "\n[boutons] " + " | ".join(b["text"] for l in clavier["inline_keyboard"] for b in l)
        print("──── (Telegram non configuré) ────\n" + msg + extra + "\n", flush=True)
        return True
    ok = True
    for i, m in enumerate(morceaux):
        corps = {"chat_id": TG_CHAT, "text": m, "disable_web_page_preview": True}
        if clavier and i == len(morceaux) - 1:
            corps["reply_markup"] = clavier
        try:
            r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", timeout=15, json=corps)
            ok &= r.ok
            if not r.ok:
                log("[telegram]", r.status_code, r.text[:200])
        except Exception as e:
            log("[telegram]", e)
            ok = False
    return ok

AIDE = ("📱 Utilise les boutons en bas de l'écran. Pour analyser un titre, tape juste son nom (ex : airbus).\n"
        "Sous chaque alerte : « ✅ J'ai acheté » / « ✅ J'ai vendu » pour que je suive ta position.\n\n"
        "🤖 Commandes (facultatif) :\n"
        "/etat – capital, positions, portefeuille virtuel, marché\n"
        "/analyse NVDA – analyse complète d'un titre (ou nom : /analyse airbus)\n"
        "/achete NVDA 118,50 – tu as acheté (prix en € vu sur TR) : je te dis quand revendre\n"
        "/vendu NVDA – je retire la position\n"
        "/capital 25 – met à jour ton capital\n"
        "/pause · /reprise – coupe / relance les alertes\n"
        "/briefing – briefing marché immédiat\n"
        "/detail NVDA – détails techniques de la dernière alerte\n"
        "/simple · /complet – alertes simples (défaut) ou techniques\n"
        "Réponse sous 5 min, de 6h à minuit (au prochain passage du bot).")

def resoudre_symbole(txt):
    low = txt.strip().lower()
    for sym, (nom, _) in U.COMMOS.items():
        if low == nom.lower() or low == COMMOS_EN.get(sym, ""):
            return sym
    t = txt.strip().upper()
    if t in U.NOMS:
        return t
    for suffixe in ("", "-EUR"):
        if t + suffixe in U.NOMS:
            return t + suffixe
    low = txt.strip().lower()
    for sym, nom in U.NOMS.items():
        if low and low in nom.lower():
            return sym
    return t   # symbole Yahoo saisi tel quel

# ─── Menu et boutons ────────────────────────────────────────────────────────

B_ETAT, B_POS, B_SURV, B_BRIEF, B_ANALYSE, B_REGL = ("📋 État", "💼 Mes positions", "👀 À surveiller",
                                                       "☀️ Briefing", "🔎 Analyser", "⚙️ Réglages")
MENU = {"keyboard": [[{"text": B_ETAT}, {"text": B_POS}], [{"text": B_SURV}, {"text": B_BRIEF}],
                     [{"text": B_ANALYSE}, {"text": B_REGL}]],
        "resize_keyboard": True, "is_persistent": True,
        "input_field_placeholder": "Tape un nom pour l'analyser (ex : airbus)"}

def boutons(*lignes):
    """boutons(("Texte", "action:SYM"), ...) -> clavier sous le message. Une ligne = un tuple ou une liste de tuples."""
    rows = []
    for l in lignes:
        l = [l] if isinstance(l, tuple) else l
        rows.append([{"text": t, "callback_data": d[:64]} for t, d in l])
    return {"inline_keyboard": rows}

def boutons_achat(sym):
    return boutons([("✅ J'ai acheté", f"achat:{sym}"), ("📊 Détails", f"detail:{sym}")])

def boutons_vente(sym):
    return boutons([("✅ J'ai vendu", f"vendu:{sym}"), ("📊 Détails", f"detail:{sym}")])

def envoyer_reglages(s):
    cap = s.get("capital", CAPITAL_DEFAUT)
    simple = s.get("mode_simple", MODE_SIMPLE_DEFAUT)
    telegram(f"⚙️ RÉGLAGES\nCapital : {cap:.0f} € · Mode : {'simple' if simple else 'complet'} · "
             f"Alertes : {'en pause ⏸' if s.get('pause') else 'actives ▶️'}\n\nChoisis ton capital :",
             boutons([(f"{'• ' if cap == v else ''}{v} €", f"cap:{v}") for v in (20, 50, 100)],
                     [(f"{'• ' if cap == v else ''}{v} €", f"cap:{v}") for v in (200, 300, 500)],
                     [("🗣 Mode simple" if not simple else "🔧 Mode complet", "mode:complet" if simple else "mode:simple")],
                     [("▶️ Reprendre les alertes", "pause:0") if s.get("pause") else ("⏸ Mettre en pause", "pause:1")]))

def changer_capital(s, valeur):
    s["capital"] = float(valeur)
    msg = f"💶 Capital : {s['capital']:.0f} €"
    if not s["virtuel"]["pos"]:
        s["virtuel"].update({"cash": s["capital"], "debut_semaine": s["capital"]})
        msg += " (portefeuille virtuel remis au même montant)"
    telegram(msg)

def noter_achat(s, sym, prix=None):
    s.setdefault("positions", {})[sym] = {"prix_eur": prix, "ts": maintenant().isoformat()}
    telegram(f"📌 {nom_tr(sym)} noté{f' (acheté {prix:.2f} €)' if prix else ' au prix actuel'}. "
             f"Je te préviens quand revendre (objectif, seuil de perte ou signal de baisse)."
             + ("" if prix else f"\nSi ton prix d'achat est différent, envoie : /achete {sym} 118,50"))

def noter_vente(s, sym):
    s.setdefault("positions", {}).pop(sym, None)
    telegram(f"✔️ {nom_tr(sym)} retiré de tes positions.")

def envoyer_surveillance(s):
    lignes, _ = lignes_surveillance(s, 24)
    telegram("👀 À SURVEILLER (24 dernières heures)\n\n" + "\n\n".join(lignes) if lignes
             else "👀 Rien de particulier à surveiller pour l'instant.")

def traiter_commande(s, cmd, args):
    if cmd in ("/aide", "/start", "/help", "/menu"):
        telegram(AIDE, MENU)
    elif cmd == "/capital" and args:
        try:
            changer_capital(s, float(args[0].replace(",", ".").replace("€", "")))
        except ValueError:
            telegram("Format : /capital 25")
    elif cmd == "/achete" and args:
        try:
            prix = float(args[1].replace(",", ".").replace("€", "")) if len(args) > 1 else None
        except ValueError:
            prix = None
        noter_achat(s, resoudre_symbole(args[0]), prix)
    elif cmd == "/vendu" and args:
        noter_vente(s, resoudre_symbole(args[0]))
    elif cmd == "/pause":
        s["pause"] = True
        telegram("⏸ Alertes en pause.", boutons(("▶️ Reprendre", "pause:0")))
    elif cmd == "/reprise":
        s["pause"] = False
        telegram("▶️ Alertes relancées.")
    elif cmd == "/analyse" and args:
        s.setdefault("a_analyser", []).append(resoudre_symbole(" ".join(args)))
    elif cmd == "/briefing":
        s["briefing_demande"] = True
    elif cmd == "/etat":
        s["etat_demande"] = True
    elif cmd == "/positions":
        s["positions_demande"] = True
    elif cmd == "/detail" and args:
        sym = resoudre_symbole(args[0])
        telegram(s.get("details", {}).get(sym) or f"Pas d'alerte récente pour {nom_tr(sym)}. Tape son nom pour l'analyser.")
    elif cmd == "/simple":
        s["mode_simple"] = True
        telegram("✅ Mode simple : alertes courtes, uniquement quand il y a quelque chose à faire.")
    elif cmd == "/complet":
        s["mode_simple"] = False
        telegram("✅ Mode complet : toutes les alertes avec les détails techniques.")

def traiter_bouton(s, data):
    action, _, val = data.partition(":")
    if action == "achat":
        noter_achat(s, val)
    elif action == "vendu":
        noter_vente(s, val)
    elif action == "detail":
        traiter_commande(s, "/detail", [val])
    elif action == "cap":
        changer_capital(s, val)
    elif action == "mode":
        traiter_commande(s, "/simple" if val == "simple" else "/complet", [])
    elif action == "pause":
        traiter_commande(s, "/pause" if val == "1" else "/reprise", [])

def commandes_telegram(s):
    if not TG_TOKEN:
        return
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                         params={"offset": s.get("tg_offset", 0) + 1, "timeout": 0}, timeout=15)
        maj = r.json().get("result", []) if r.ok else []
    except Exception:
        return
    for u in maj:
        s["tg_offset"] = u["update_id"]
        cb = u.get("callback_query")
        if cb:                                             # appui sur un bouton sous un message
            if str(cb.get("message", {}).get("chat", {}).get("id")) == TG_CHAT:
                try:
                    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery",
                                  json={"callback_query_id": cb["id"]}, timeout=10)
                except Exception:
                    pass
                traiter_bouton(s, cb.get("data", ""))
            continue
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) != TG_CHAT:
            continue
        txt = (m.get("text") or "").strip()
        if not txt:
            continue
        if txt.startswith("/"):
            cmd, *args = txt.split()
            traiter_commande(s, cmd.lower().split("@")[0], args)
        elif txt == B_ETAT:
            s["etat_demande"] = True
        elif txt == B_POS:
            s["positions_demande"] = True
        elif txt == B_SURV:
            envoyer_surveillance(s)
        elif txt == B_BRIEF:
            s["briefing_demande"] = True
        elif txt == B_ANALYSE:
            telegram("🔎 Tape simplement un nom : une action (airbus, nvidia), une crypto (bitcoin) "
                     "ou une matière première (or, café). Réponse sous 5 min.")
        elif txt == B_REGL:
            envoyer_reglages(s)
        elif len(txt) <= 40:                               # texte libre = analyse de ce titre
            s.setdefault("a_analyser", []).append(resoudre_symbole(txt))

def message_positions(s, ctxs, fx):
    pos = s.get("positions", {})
    if not pos:
        telegram("💼 Aucune position suivie.\nQuand tu achètes suite à une alerte, appuie sur « ✅ J'ai acheté ».")
        return
    lignes, rangs = ["💼 MES POSITIONS", ""], []
    for sym, p in pos.items():
        c = ctxs.get(sym)
        nom = nom_tr(sym)
        if not c or not p.get("prix"):
            lignes.append(f"• {nom} : cours indisponible pour le moment")
        else:
            perf = pct(c["prix"], p["prix"])
            ico = "⚪" if abs(perf) < 0.1 else ("🟢" if perf > 0 else "🔴")
            e_now, e_in = en_eur(sym, c["prix"], fx), en_eur(sym, p["prix"], fx)
            prix_txt = f"{feur(e_in)} → {feur(e_now)}" if marche(sym) != "FUT" else "(suivi en %)"
            lignes.append(f"{ico} {nom} : {perf:+.1f}% {prix_txt}")
            if p.get("obj") and p.get("stop") and marche(sym) != "FUT":
                lignes.append(f"   objectif {feur(en_eur(sym, p['obj'], fx))} · seuil de perte {feur(en_eur(sym, p['stop'], fx))}")
        rangs.append((f"✅ J'ai vendu {nom[:20]}", f"vendu:{sym}"))
    telegram("\n".join(lignes), boutons(*rangs))

# ═════════════════════════════════════════════════════════════════════════════
# 11. ÉTAT (anti-spam, journal, positions, portefeuille virtuel)
# ═════════════════════════════════════════════════════════════════════════════

def charger_etat():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = {}
    for k, v in {"cooldowns": {}, "compteur": {}, "journal": [], "positions": {}, "chauds": [],
                 "capital": CAPITAL_DEFAUT, "briefings": {}}.items():
        s.setdefault(k, v)
    s.setdefault("virtuel", {"cash": s["capital"], "pos": None, "trades": [], "debut_semaine": s["capital"], "semaine": ""})
    return s

def sauver_etat(s):
    s.pop("_llm_scan", None)
    limite = (maintenant() - timedelta(days=35)).isoformat()
    s["journal"] = [j for j in s["journal"] if j["ts"] >= limite]
    s["virtuel"]["trades"] = s["virtuel"]["trades"][-60:]
    auj = datetime.now(PARIS).strftime("%Y-%m-%d")
    s["compteur"] = {k: v for k, v in s["compteur"].items() if k.startswith(auj)}
    s["cooldowns"] = {k: v for k, v in s["cooldowns"].items() if time.time() - v < 86400}
    if len(s.get("details", {})) > 40:
        s["details"] = dict(list(s["details"].items())[-40:])
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, ensure_ascii=False, default=str)

def en_cooldown(s, cle, minutes):
    t = s["cooldowns"].get(cle)
    return t is not None and time.time() - t < minutes * 60

def valeur_virtuelle(s, prix_actuels):
    v = s["virtuel"]
    if not v["pos"]:
        return v["cash"]
    p = prix_actuels.get(v["pos"]["sym"])
    return v["cash"] + (v["pos"]["eur"] * p / v["pos"]["prix"] if p else v["pos"]["eur"])

def gerer_virtuel(s, prix_actuels, signaux_vente):
    """Portefeuille fictif qui suit les meilleurs signaux avec les VRAIS frais TR : mesure objective."""
    v = s["virtuel"]
    sem = datetime.now(PARIS).strftime("%G-S%V")
    if v["semaine"] != sem:
        v["semaine"], v["debut_semaine"] = sem, round(valeur_virtuelle(s, prix_actuels), 2)
    pos = v["pos"]
    if not pos:
        return
    p = prix_actuels.get(pos["sym"])
    if not p:
        return
    raison = None
    if p <= pos["stop"]:
        raison = "stop touché"
    elif p >= pos["obj"]:
        raison = "objectif atteint"
    elif pos["sym"] in signaux_vente:
        raison = "signal de vente"
    else:
        np_ = datetime.now(PARIS)
        if np_.weekday() == 4 and np_.hour * 60 + np_.minute >= 21 * 60 + 45 and marche(pos["sym"]) != "CRYPTO":
            raison = "clôture de fin de semaine"
    if raison:
        valeur = pos["eur"] * p / pos["prix"]
        v["cash"] = round(v["cash"] + valeur - FRAIS_ORDRE, 2)
        res = valeur - FRAIS_ORDRE - (pos["eur"] + FRAIS_ORDRE)
        v["trades"].append({"sym": pos["sym"], "entree": pos["prix"], "sortie": p, "res_eur": round(res, 2),
                            "raison": raison, "ts": maintenant().isoformat()})
        v["pos"] = None
        telegram(f"🧪 Portefeuille virtuel : vente {pos['sym']} ({raison}) — résultat {res:+.2f} € frais inclus. "
                 f"Valeur : {v['cash']:.2f} €")

def acheter_virtuel(s, c):
    v = s["virtuel"]
    if v["pos"] or v["cash"] < FRAIS_ORDRE + 2 or c["sym"] in U.NON_TR:
        return
    if not rentable(v["cash"], c["obj_pct"], c["stop_pct"]):
        return   # avec le capital virtuel actuel, les frais mangeraient le gain
    eur = round(v["cash"] * MISE_PART - FRAIS_ORDRE, 2)
    v["cash"] = round(v["cash"] - eur - FRAIS_ORDRE, 2)
    v["pos"] = {"sym": c["sym"], "prix": c["prix"], "eur": eur, "stop": c["stop"], "obj": c["obj"],
                "ts": maintenant().isoformat()}

# ═════════════════════════════════════════════════════════════════════════════
# 12. SCANNER TOUS MARCHÉS (re-classement horaire de l'univers TR)
# ═════════════════════════════════════════════════════════════════════════════

def maj_chauds(s, d1_all):
    fixes = set(U.IA_INFRA + U.POWER_COOLING + U.SEMIS + U.MATIERES)
    notes = []
    for sym in U.UNIVERS_SCANNER:
        if sym in fixes or not seance_ouverte(marche(sym), avec_attente=False):
            continue
        d = d1_all.get(sym)
        if d is None or len(d) < 30:
            continue
        date_j = datetime.now(SEANCES[marche(sym)][0]).date()
        if d.index[-1].date() != date_j and not FORCE:
            continue
        hist = d.iloc[:-1]
        a = float(atr(hist).iloc[-1]) / float(hist["Close"].iloc[-1]) * 100
        v = pct(float(d["Close"].iloc[-1]), float(hist["Close"].iloc[-1]))
        vr = float(d["Volume"].iloc[-1]) / fraction_seance(marche(sym)) / max(1, hist["Volume"].iloc[-20:].mean())
        hi20, lo20 = hist["High"].iloc[-20:].max(), hist["Low"].iloc[-20:].min()
        cassure = d["Close"].iloc[-1] > hi20 or d["Close"].iloc[-1] < lo20
        if np.isnan(v) or a <= 0:
            continue
        note = abs(v) / a * min(vr, 5) + (1.5 if cassure else 0)
        if vr >= 1.3 and abs(v) >= 0.8 * a:
            notes.append((note, sym, v, vr))
    notes.sort(reverse=True)
    s["chauds"] = [n[1] for n in notes[:NB_CHAUDS]]
    s["chauds_detail"] = [f"{n[1]} {n[2]:+.1f}% vol {n[3]:.1f}×" for n in notes[:NB_CHAUDS]]
    s["chauds_ts"] = time.time()
    log(f"Scanner : {len(notes)} titres actifs, retenus : {s['chauds_detail'][:10]}")

# ═════════════════════════════════════════════════════════════════════════════
# 13. BRIEFINGS & BILAN
# ═════════════════════════════════════════════════════════════════════════════

def ligne_var(noms, donnees):
    parts = []
    for sym, nom in noms.items():
        v = variation_jour(donnees.get(sym))
        if not np.isnan(v):
            parts.append(f"{nom} {v:+.1f}%")
    return " · ".join(parts) if parts else "n/d"

RAISONS_SIMPLES = [("non rentable", "gain trop petit pour ton capital une fois les 2 € de frais payés"),
                   ("Éviter", "signal de baisse : à éviter pour l'instant"),
                   ("Indicateur", "non achetable sur Trade Republic"),
                   ("Surveiller", "signal pas encore assez sûr")]

def ajouter_surveillance(s, c):
    raison = next((r for k, r in RAISONS_SIMPLES if k in c["action"]), "signal pas encore assez sûr")
    expl = (c["verdict"].get("simple") or (expliquer(c["conds"], 1) or [""])[0]).strip()
    nom = U.COMMOS[c["sym"]][0] if c["sym"] in U.COMMOS else U.NOMS.get(c["sym"], c["sym"])
    liste = [x for x in s.setdefault("a_surveiller", []) if x["sym"] != c["sym"]]
    liste.append({"ts": maintenant().isoformat(), "sym": c["sym"], "nom": nom, "dir": c["dir"],
                  "expl": expl, "raison": raison, "vu": False})
    s["a_surveiller"] = liste[-30:]

def lignes_surveillance(s, heures=24, non_vus=False):
    limite = (maintenant() - timedelta(hours=heures)).isoformat()
    items = [x for x in s.get("a_surveiller", []) if x["ts"] >= limite and (not non_vus or not x["vu"])]
    return [f"{'↗' if x['dir'] > 0 else '↘'} {x['nom']} : {x['expl'] or 'mouvement notable'} → {x['raison']}"
            for x in items[-10:]], items

def envoyer_digest(s):
    lignes, items = lignes_surveillance(s, 12, non_vus=True)
    if not lignes:
        return
    cap = s.get("capital", CAPITAL_DEFAUT)
    note = (f"\n\nℹ️ Avec {cap:.0f} €, les 2 € de frais (achat + vente) = {2 * FRAIS_ORDRE / cap * 100:.0f} % de ton "
            f"capital : je n'envoie un 🟢 que si le gain attendu reste positif APRÈS frais." if cap < PETIT_CAPITAL else "")
    telegram("👀 À SURVEILLER (rien à faire pour l'instant)\n\n" + "\n\n".join(lignes)
             + "\n\nSi l'un d'eux devient une vraie occasion, je t'enverrai une alerte 🟢." + note)
    for x in items:
        x["vu"] = True

def briefing(s, type_="matin"):
    macro = telecharger(list(U.MACRO), "5d", "1d")
    asie = telecharger(list(U.ASIE) + list(U.EST), "5d", "1d")
    simple = s.get("mode_simple", MODE_SIMPLE_DEFAUT)
    evts = [e for e in calendrier(s) if e[0].astimezone(PARIS).date() == datetime.now(PARIS).date()]
    evts_txt = "\n".join(f"• {dt.astimezone(PARIS):%H:%M} {pays} – {t}" for dt, pays, t in evts) or "• aucune annonce majeure"
    reg, reg_txt = regime_marche(macro)
    asie_txt = ligne_var(U.ASIE, asie)
    est_txt = ligne_var(U.EST, asie)
    macro_txt = ligne_var(U.MACRO, macro)
    monde = actus_monde()
    synthese = llm([{"role": "system", "content": SYSTEME_ANALYSTE},
                    {"role": "user", "content":
                     f"Rédige le briefing {'du matin (avant ouverture de Trade Republic à 7h30)' if type_ == 'matin' else 'avant ouverture de Wall Street (15h30)'} "
                     f"pour un investisseur centré sur l'IA (puces, électricité, refroidissement, matières premières) "
                     f"avec un petit capital{' qui DÉBUTE complètement : aucun jargon (pas de RSI, risk-on, taux directeur non expliqué...), phrases courtes et concrètes' if simple else ''}. "
                     f"130 mots max, format : 1) Ambiance du marché : confiant / neutre / inquiet + pourquoi en une phrase "
                     f"2) Les 3 nouvelles importantes (monde, économie, entreprises) et ce qu'elles changent "
                     f"3) Effet probable sur les valeurs IA et les matières premières "
                     f"4) À quoi faire attention aujourd'hui. N'utilise QUE ces données :\n"
                     f"Régime : {reg_txt}\nAsie : {asie_txt}\nEurope de l'Est : {est_txt}\nMacro : {macro_txt}\n"
                     f"Agenda : {evts_txt}\nActualités :\n{fmt_actus(monde, 15)}"}], max_tokens=450, s=s)
    titre = "☀️ BRIEFING DU MATIN" if type_ == "matin" else "🇺🇸 BRIEFING AVANT WALL STREET"
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    np_ = datetime.now(PARIS)
    if simple:
        asie_txt = ligne_var({k: U.ASIE[k] for k in ("^N225", "^HSI", "2330.TW", "000660.KS")}, asie)
        macro_txt = ligne_var({k: U.MACRO[k] for k in ("NQ=F", "^GDAXI", "^FCHI", "GC=F", "BZ=F", "BTC-EUR")}, macro)
        msg = (f"{titre} – {jours[np_.weekday()]} {np_:%d/%m %H:%M}\n\n{reg_txt}\n\n"
               f"📊 En bref : {macro_txt}\n🌏 Asie cette nuit : {asie_txt}\n\n"
               f"🗓 Annonces qui peuvent faire bouger les marchés (heure de Paris) :\n{evts_txt}\n"
               f"(je n'envoie aucune alerte 30 min avant / 15 min après)\n\n")
    else:
        msg = (f"{titre} – {jours[np_.weekday()]} {np_:%d/%m %H:%M}\n\nMarché : {reg_txt}\n\n"
               f"🌏 Asie : {asie_txt}\n\n🇪🇺 Est : {est_txt}\n\n📊 Macro : {macro_txt}\n\n"
               f"🗓 Annonces à fort impact (heure de Paris) :\n{evts_txt}\n\n")
    msg += f"🧠 Synthèse :\n{synthese}\n" if synthese else f"📰 À la une :\n{fmt_actus(monde, 8)}\n"
    surv, _ = lignes_surveillance(s, 24)
    if surv:
        msg += "\n👀 À surveiller :\n" + "\n".join(surv[-5:]) + "\n"
    if s.get("chauds_detail") and not simple:
        msg += "\n🔥 Titres les plus actifs (dernier scan) : " + ", ".join(s["chauds_detail"][:8])
    telegram(msg)

def message_etat(s, prix_actuels, reg_txt):
    v = s["virtuel"]
    val = valeur_virtuelle(s, prix_actuels)
    pos = ", ".join(s["positions"]) or "aucune"
    vp = f"{v['pos']['sym']} (entrée {v['pos']['prix']:.4g})" if v["pos"] else "aucune"
    auj = datetime.now(PARIS).strftime("%Y-%m-%d")
    nb = sum(1 for j in s["journal"] if j["ts"][:10] == maintenant().strftime("%Y-%m-%d"))
    telegram(f"📋 ÉTAT – {datetime.now(PARIS):%d/%m %H:%M}\nCapital déclaré : {s['capital']:.2f} €\n"
             f"Tes positions suivies : {pos}\nAlertes aujourd'hui : {nb}{' (EN PAUSE)' if s.get('pause') else ''}\n"
             f"Marché : {reg_txt}\n\n🧪 Portefeuille virtuel : {val:.2f} € (début de semaine {v['debut_semaine']:.2f} €, "
             f"{pct(val, v['debut_semaine']):+.1f}%)\nPosition virtuelle : {vp}\n"
             f"Titres chauds : {', '.join(s.get('chauds', [])[:10]) or 'n/d'}\nAppels IA aujourd'hui : "
             f"{s.get('llm_jour', {}).get(auj, 0)}\nMode : {'simple' if s.get('mode_simple', MODE_SIMPLE_DEFAUT) else 'complet'}"
             + ("\n\n👀 À surveiller :\n" + "\n".join(lignes_surveillance(s, 24)[0][-5:]) if lignes_surveillance(s, 24)[0] else ""))

def bilan_hebdo(s):
    depuis = (maintenant() - timedelta(days=7)).isoformat()
    sig = [j for j in s["journal"] if j["ts"] >= depuis]
    v = s["virtuel"]
    prix = telecharger(sorted({j["sym"] for j in sig} | ({v["pos"]["sym"]} if v["pos"] else set())), "5d", "1d")
    pa = {k: float(d["Close"].iloc[-1]) for k, d in prix.items()}
    res = []
    for j in sig:
        if j["sym"] in pa:
            res.append((pct(pa[j["sym"]], j["prix"]) * j["dir"], j))
    val = valeur_virtuelle(s, pa)
    trades = [t for t in v["trades"] if t["ts"] >= depuis]
    txt = f"📊 BILAN DE LA SEMAINE {v['semaine']}\n\n"
    txt += (f"🧪 Portefeuille virtuel (règles strictes + frais TR réels) :\n{v['debut_semaine']:.2f} € → {val:.2f} € "
            f"({pct(val, v['debut_semaine']):+.1f}%) · {len(trades)} trade(s)\n")
    for t in trades:
        txt += f"  {'✅' if t['res_eur'] > 0 else '❌'} {t['sym']} {t['res_eur']:+.2f} € ({t['raison']})\n"
    if res:
        g = [r for r, _ in res]
        txt += (f"\n📈 {len(res)} signaux envoyés · réussite {sum(x > 0 for x in g) / len(g) * 100:.0f}% · "
                f"moyenne {np.mean(g):+.2f}% (hors frais)\n")
        par = {}
        for r, j in res:
            par.setdefault(j["mod"], []).append(r)
        txt += "Par module : " + ", ".join(f"{m} {np.mean(x):+.1f}% ({len(x)})" for m, x in par.items()) + "\n"
        fort = [r for r, j in res if j["etoiles"] >= 4]
        if fort:
            txt += f"Signaux ★★★★+ : {np.mean(fort):+.2f}% ({len(fort)})\n"
        conf = [r for r, j in res if j.get("verdict") == "CONFIRME"]
        if conf:
            txt += f"Signaux confirmés par l'actu : {np.mean(conf):+.2f}% ({len(conf)})\n"
        txt += "\n" + "\n".join(f"{'✅' if r > 0 else '❌'} {j['sym']} {'ACHAT' if j['dir'] > 0 else 'VENTE'} "
                                f"{'★' * j['etoiles']} {r:+.1f}%" for r, j in res[-25:])
    else:
        txt += "\nAucun signal cette semaine."
    telegram(txt)
    os.makedirs(os.path.join(ICI, "bilans"), exist_ok=True)
    with open(os.path.join(ICI, "bilans", f"{v['semaine']}.md"), "w", encoding="utf-8") as f:
        f.write(txt.replace("\n", "  \n"))

def briefings_programmes(s):
    now = datetime.now(PARIS)
    auj = now.strftime("%Y-%m-%d")
    b = s["briefings"]
    mins = now.hour * 60 + now.minute
    if "--matin" in sys.argv or (now.weekday() < 5 and 7 * 60 + 5 <= mins < 9 * 60 and b.get("matin") != auj):
        b["matin"] = auj
        briefing(s, "matin")
    if "--preus" in sys.argv or (now.weekday() < 5 and 15 * 60 + 10 <= mins < 16 * 60 and b.get("preus") != auj):
        b["preus"] = auj
        briefing(s, "preus")
    if "--recap" in sys.argv or (now.weekday() == 4 and mins >= 22 * 60 + 5 and b.get("recap") != auj):
        b["recap"] = auj
        bilan_hebdo(s)
    if s.pop("briefing_demande", False):
        briefing(s, "matin" if mins < 15 * 60 else "preus")
    for h, m in DIGEST_HEURES:
        cle = f"digest{h}{m:02d}"
        if now.weekday() < 5 and h * 60 + m <= mins < h * 60 + m + 60 and b.get(cle) != auj:
            b[cle] = auj
            envoyer_digest(s)

# ═════════════════════════════════════════════════════════════════════════════
# 14. SCAN PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════

def analyse_a_la_demande(sym, ctx, regime, reg_txt, evts_txt, s, fx):
    if ctx is None:
        telegram(f"❓ {sym} : pas de données récentes (symbole inconnu, marché fermé ou Yahoo indisponible). "
                 f"Pour une action européenne, utilise le symbole Yahoo (ex : AIR.PA, SAP.DE).")
        return
    conds = analyser("scanner", dict(MODULES["scanner"], vol_min=0), ctx)
    d, score = evaluer(conds, ctx, regime)
    d_aff = d or (1 if ctx["tendance"] >= 0 else -1)
    c = candidat("scanner", ctx, conds, d_aff, score, reg_txt, evts_txt)
    s["_llm_scan"] = []
    c["verdict"] = verdict_actus(c, s)
    c["etoiles"] = etoiles(score) if d else 1
    c["action"] = decider_action(c, s) if d else "Pas de signal technique net : attendre"
    complet = formater_alerte(c, s, fx)
    s.setdefault("details", {})[c["sym"]] = complet
    if not s.get("mode_simple", MODE_SIMPLE_DEFAUT):
        telegram("🔎 ANALYSE À LA DEMANDE\n" + complet, boutons_achat(sym) if d > 0 else None)
        return
    nom = nom_tr(sym)
    if d > 0 and c["action"].startswith("Acheter"):
        telegram("🔎 " + formater_simple(c, s, fx), boutons_achat(sym))
        return
    raisons = expliquer(conds) or ["pas de mouvement particulier en ce moment"]
    avis = c["verdict"].get("simple") or c["verdict"].get("avis") or ""
    verdict = ("⏸ PAS MAINTENANT" if d >= 0 else "🔴 PLUTÔT À ÉVITER POUR L'INSTANT")
    telegram(f"🔎 {nom} : {verdict}\n\n" + (f"• {avis}\n" if avis else "")
             + "\n".join(f"• {r[0].upper() + r[1:]}" for r in raisons)
             + f"\n\nAction : {c['action']}.", boutons(("📊 Détails techniques", f"detail:{sym}")))

def candidat(mod, ctx, conds, d, score, reg_txt, evts_txt):
    stop, obj, sp, op = niveaux(ctx, d)
    var_label, var = ("1h", var_minutes(ctx, 60)) if mod not in ("power", "commo") else ("2h", var_minutes(ctx, 120))
    if mod == "matieres":
        var_label, var = "jour", ctx["var_jour"]
    return {"mod": mod, "module_nom": MODULES[mod]["nom"], "sym": ctx["sym"], "dir": d, "score": score,
            "conds": conds, "prix": ctx["prix"], "ts": ctx["ts"], "var": var, "var_label": var_label,
            "var_jour": ctx["var_jour"], "rsi": ctx["rsi"], "vol": vol_rel_horaire(ctx["m5"], 12),
            "tendance": ctx["tendance"],
            "tendance_txt": {1: "haussière ↗ (au-dessus MM50 jour)", -1: "baissière ↘ (sous MM50 jour)", 0: "neutre →"}[ctx["tendance"]],
            "regime_txt": reg_txt, "evts_txt": evts_txt, "stop": stop, "obj": obj, "stop_pct": sp, "obj_pct": op}

def scan():
    s = charger_etat()
    regler_niveaux(s.get("capital", CAPITAL_DEFAUT))
    commandes_telegram(s)
    briefings_programmes(s)

    ouverts = {m for m in ("US", "EU", "UK", "CRYPTO", "FUT") if seance_ouverte(m)}
    besoin = ouverts or s.get("a_analyser") or s.get("etat_demande") or s.get("positions_demande")
    if not besoin:
        log("Aucun marché ouvert (fenêtre d'analyse) — fin.")
        sauver_etat(s)
        return
    log(f"Marchés ouverts : {sorted(ouverts)}")

    macro = telecharger(list(U.MACRO) + U.FX, "5d", "1d")
    regime, reg_txt = regime_marche(macro)
    fx = taux_change(macro)
    evts = calendrier(s)
    evts_auj = [e for e in evts if e[0] > maintenant() and e[0].astimezone(PARIS).date() == datetime.now(PARIS).date()]
    evts_txt = ", ".join(f"{dt.astimezone(PARIS):%H:%M} {p} {t}" for dt, p, t in evts_auj[:5]) or "aucune"
    blackout = None if FORCE else blackout_macro(evts)

    # Scanner horaire de tout l'univers
    actions_ouvertes = ouverts - {"CRYPTO", "FUT"}
    if actions_ouvertes and (time.time() - s.get("chauds_ts", 0) > 3600 or FORCE):
        maj_chauds(s, donnees_jour(U.UNIVERS_SCANNER + U.MATIERES + U.IA_INFRA + U.SEMIS + U.POWER_COOLING, s))
    elif not actions_ouvertes:
        s["chauds"] = []

    # Liste des titres à analyser maintenant
    a_voir = {}
    for mod, cfg in MODULES.items():
        liste = s["chauds"] if cfg["liste"] == "chauds" else cfg["liste"]
        a_voir[mod] = [x for x in liste if marche(x) in ouverts]
    demandes = s.pop("a_analyser", [])
    tous = sorted({x for l in a_voir.values() for x in l} | set(s["positions"]) | set(demandes)
                  | ({s["virtuel"]["pos"]["sym"]} if s["virtuel"]["pos"] else set()) | {"NVDA", "SMCI"})
    m5_all = telecharger(tous, "1mo", "5m")
    d1_all = donnees_jour(tous, s)
    log(f"Données 5 min : {len(m5_all)}/{len(tous)} titres")

    ctxs = {}
    for sym in tous:
        try:
            c = construire_ctx(sym, m5_all, d1_all, tolerer_perime=sym in demandes or sym in s["positions"])
            if c:
                c["_d1_all"], c["_ctx_all"] = d1_all, ctxs
                ctxs[sym] = c
        except Exception as e:
            log(f"  contexte {sym} : {e}")
    prix_actuels = {k: c["prix"] for k, c in ctxs.items()}

    for sym in demandes:
        analyse_a_la_demande(sym, ctxs.get(sym), regime, reg_txt, evts_txt, s, fx)
    if s.pop("etat_demande", False):
        message_etat(s, prix_actuels, reg_txt)

    # Détection des signaux
    candidats, ventes = [], set()
    for mod, cfg in MODULES.items():
        for sym in a_voir[mod]:
            ctx = ctxs.get(sym)
            if not ctx:
                continue
            conds = analyser(mod, cfg, ctx)
            if not conds:
                continue
            d, score = evaluer(conds, ctx, regime)
            log(f"  {mod:8} {sym:9} dir={d:+d} score={score} :: {[t for _, _, t, _ in conds]}")
            if d == 0:
                continue
            if d < 0:
                ventes.add(sym)
            if score < SCORE_MIN:
                continue
            if d < 0 and sym not in s["positions"] and not ALERTER_VENTES_NON_DETENUES:
                continue
            candidats.append(candidat(mod, ctx, conds, d, score, reg_txt, evts_txt))

    # Suivi des positions réelles déclarées
    for sym, pos in s["positions"].items():
        c = ctxs.get(sym)
        if not c:
            continue
        frais_cours = c["age"] <= FRAICHEUR_MAX_MIN
        if not pos.get("prix"):
            taux = (fx or {}).get(devise(sym), np.nan)
            if pos.get("prix_eur") and marche(sym) != "FUT" and taux and not np.isnan(taux):
                pos["prix"] = pos["prix_eur"] / taux      # prix TR en € -> devise de cotation
            else:
                pos["prix"] = c["prix"]
        if not pos.get("stop"):
            stop, obj, _, _ = niveaux(c, 1)
            ratio = pos["prix"] / c["prix"]
            pos["stop"], pos["obj"] = stop * ratio, obj * ratio
        perf = pct(c["prix"], pos["prix"])
        if frais_cours and c["prix"] <= pos["stop"] and not pos.get("alerte_stop"):
            pos["alerte_stop"] = True
            telegram(f"🛑 REVENDS {nom_tr(sym)} MAINTENANT\n{perf:+.1f}% depuis ton achat : c'est le seuil prévu pour "
                     f"limiter la perte.\nSur TR : ouvre ta ligne → Vendre, puis appuie sur « J'ai vendu ».\n"
                     f"(prix {fprix(sym, c['prix'], fx)})", boutons(("✅ J'ai vendu", f"vendu:{sym}")))
        elif frais_cours and c["prix"] >= pos["obj"] and not pos.get("alerte_obj"):
            pos["alerte_obj"] = True
            telegram(f"🎯 OBJECTIF ATTEINT : {nom_tr(sym)} ({perf:+.1f}% depuis ton achat)\n"
                     f"Sur TR : vends tout pour encaisser le gain, puis appuie sur « J'ai vendu ».\n"
                     f"(prix {fprix(sym, c['prix'], fx)})", boutons(("✅ J'ai vendu", f"vendu:{sym}")))

    if s.pop("positions_demande", False):
        message_positions(s, ctxs, fx)

    gerer_virtuel(s, prix_actuels, ventes)

    if s.get("pause"):
        log("En pause : aucune alerte envoyée.")
        sauver_etat(s)
        return
    if blackout:
        log(f"Blackout macro ({blackout}) : pas de nouvelle alerte.")
        if candidats and s.get("blackout_notifie") != blackout:
            s["blackout_notifie"] = blackout
            telegram(f"⏳ Signaux détectés mais mis en attente : annonce macro majeure {blackout}. "
                     f"Trop de volatilité imprévisible autour de ces annonces.")
        sauver_etat(s)
        return

    # Tri, vérification actualités, envoi
    auj = datetime.now(PARIS).strftime("%Y-%m-%d")
    envoyes = sum(v for k, v in s["compteur"].items() if k.startswith(auj + ":total"))
    candidats.sort(key=lambda c: c["score"], reverse=True)
    n_scan = 0
    for c in candidats:
        if n_scan >= MAX_ALERTES_PAR_SCAN or envoyes >= MAX_ALERTES_PAR_JOUR:
            break
        cfg = MODULES[c["mod"]]
        cle_mod, cle_glob = f"{c['mod']}:{c['sym']}", f"global:{c['sym']}:{c['dir']}"
        cle_jour = f"{auj}:{c['mod']}:{c['sym']}"
        if en_cooldown(s, cle_mod, cfg["cooldown"]) or en_cooldown(s, cle_glob, COOLDOWN_GLOBAL_MIN):
            continue
        if cfg.get("max_jour") and s["compteur"].get(cle_jour, 0) >= cfg["max_jour"]:
            continue
        c["verdict"] = verdict_actus(c, s)
        if c["verdict"] is None:
            continue
        v = c["verdict"]["verdict"]
        if v == "REJETE":
            log(f"  {c['sym']} rejeté par l'analyse d'actualité : {c['verdict'].get('actu')}")
            s["cooldowns"][cle_mod] = time.time()
            continue
        c["score"] += 1 if v == "CONFIRME" else (-1 if v == "PRUDENCE" and c["verdict"].get("source") == "ia" else 0)
        if c["score"] < SCORE_MIN:
            s["cooldowns"][cle_mod] = time.time() - max(0, cfg["cooldown"] - 20) * 60   # réessai dans 20 min
            continue
        c["etoiles"] = etoiles(c["score"])
        c["action"] = decider_action(c, s)
        complet = formater_alerte(c, s, fx)
        s.setdefault("details", {})[c["sym"]] = complet
        simple = s.get("mode_simple", MODE_SIMPLE_DEFAUT)
        if simple and not envoyable_simple(c):
            ajouter_surveillance(s, c)          # pas d'action concrète : ira dans le récap "à surveiller"
            s["cooldowns"][cle_mod] = time.time()
            continue
        if telegram(formater_simple(c, s, fx) if simple else complet,
                    boutons_achat(c["sym"]) if c["dir"] > 0 else boutons_vente(c["sym"])):
            n_scan += 1
            envoyes += 1
            now = time.time()
            s["cooldowns"][cle_mod] = s["cooldowns"][cle_glob] = now
            s["compteur"][cle_jour] = s["compteur"].get(cle_jour, 0) + 1
            s["compteur"][f"{auj}:total"] = envoyes
            s["journal"].append({"ts": maintenant().isoformat(), "mod": c["mod"], "sym": c["sym"], "dir": c["dir"],
                                 "prix": round(c["prix"], 6), "etoiles": c["etoiles"], "verdict": v})
            if c["dir"] > 0 and c["etoiles"] >= VIRTUEL_ETOILES_MIN and c["action"].startswith("Acheter"):
                acheter_virtuel(s, c)
    sauver_etat(s)
    log(f"Scan terminé — {n_scan} alerte(s).")

if __name__ == "__main__":
    if "--test" in sys.argv:
        ok = telegram("✅ AI Market Bots v2.2 connectés.\n\n" + AIDE, MENU)
        if TG_TOKEN:
            try:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/setMyCommands", timeout=10, json={"commands": [
                    {"command": "menu", "description": "Afficher les boutons"},
                    {"command": "etat", "description": "Capital, positions, portefeuille virtuel"},
                    {"command": "positions", "description": "Mes positions en cours"},
                    {"command": "briefing", "description": "Briefing marché immédiat"},
                    {"command": "capital", "description": "Changer le capital (ex : /capital 200)"},
                    {"command": "achete", "description": "J'ai acheté (ex : /achete NVDA 118,50)"},
                    {"command": "vendu", "description": "J'ai vendu (ex : /vendu NVDA)"}]})
            except Exception:
                pass
        if LLM_KEY:
            try:
                r = requests.post(f"{LLM_BASE}/chat/completions", timeout=30,
                                  headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"},
                                  json={"model": LLM_MODEL, "messages": [{"role": "user", "content": "Réponds juste : OK"}], "max_tokens": 5})
                if r.ok:
                    telegram(f"🧠 IA d'analyse : connectée ✅ (modèle {LLM_MODEL})")
                else:
                    telegram(f"🧠 IA ERREUR {r.status_code} — base:{LLM_BASE} modèle:{LLM_MODEL}\n{r.text[:600]}")
            except Exception as e:
                telegram(f"🧠 IA EXCEPTION — base:{LLM_BASE} modèle:{LLM_MODEL}\n{e}")
        else:
            telegram("🧠 IA d'analyse : non configurée (analyse des actus par mots-clés seulement).")
        sys.exit(0 if ok else 1)
    scan()
