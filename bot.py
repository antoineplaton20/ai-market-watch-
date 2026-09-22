#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI MARKET WATCH — Système multi-bots de surveillance technique (écosystème IA)
=============================================================================
4 modules : Général (AI Infrastructure) · Power & Cooling · Semiconductors
Momentum · Raw Materials AI. Alertes Telegram + bilan hebdo le vendredi soir.

Principes de fiabilité :
- Données Yahoo Finance via yfinance (gratuit, sans clé API).
- Seules les bougies CLÔTURÉES sont analysées (pas de signal sur une bougie
  en formation qui peut encore s'inverser).
- Volume relatif comparé au MÊME créneau horaire des séances précédentes
  (sinon chaque ouverture déclencherait un faux "volume élevé").
- Variations intraday calculées sur la séance du jour (le gap de la nuit
  n'est pas compté comme un mouvement "en 1h").
- Aucune donnée inventée : un symbole sans données fraîches est ignoré.
- Anti-spam : cooldown par module/symbole + empreinte (un même événement
  n'est jamais envoyé deux fois) + regroupement par symbole.

Tous les réglages sont dans la section CONFIGURATION ci-dessous.
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from zoneinfo import ZoneInfo

# =============================================================================
# CONFIGURATION — modifiable directement depuis GitHub (icône crayon)
# =============================================================================

MODULES = {
    # --- 1. AI Infrastructure Watcher (vue générale 1h / 4h) -----------------
    "general": {
        "actif": True,
        "watchlist": ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "ARM", "SMCI",
                      "DELL", "CEG", "VST", "EQIX", "DLR", "MOD", "FCX", "MP"],
        "cooldown_min": 45,
        "rsi_survente": 32,
        "rsi_surachat": 68,
        "var_1h": 4.5,           # % sur 1h glissante
        "vol_momentum": 1.8,     # × moyenne, pour le momentum
        "vol_croisement": 1.5,   # "volume élevé" pour une cassure de MM20
        "vol_jours": 20,         # moyenne du volume sur N séances (même créneau)
    },
    # --- 2. Power & Cooling Alert ----------------------------------------
    "power": {
        "actif": True,
        "watchlist": ["CEG", "VST", "NRG", "TLN", "EQIX", "DLR", "MOD", "SMCI",
                      "DELL", "VRT"],
        "cooldown_min": 60,
        "var_2h": 3.8,           # % sur 2h glissantes
        "vol_min": 2.0,          # volume obligatoire (× moyenne)
        "vol_jours": 10,
        "rsi_zone": [35, 65],
        "ecart_mm50": 4.0,       # % d'écart prix / MM50 1h
    },
    # --- 3. Semiconductors Momentum --------------------------------------
    "semis": {
        "actif": True,
        "watchlist": ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "ARM", "MRVL"],
        "cooldown_min": 40,
        "vol_breakout": 2.2,
        "vol_min": 1.3,          # filtre anti-bruit
        "var_1h": 5.0,
        "range_bougies": 20,     # range = 20 dernières bougies 1h
        "mm_rapide": 9,          # moyennes mobiles exponentielles (MME)
        "mm_lente": 21,
        "ignorer_avant": "10:00",  # heure de New York (ouverture trop volatile)
        "vol_jours": 20,
    },
    # --- 4. Raw Materials AI ---------------------------------------------
    "raw": {
        "actif": True,
        "watchlist": ["FCX", "MP", "SCCO", "TECK", "RIO", "BHP", "COPX"],
        "max_par_jour": 2,
        "var_jour": 3.5,
        "vol_min": 1.7,          # volume cumulé du jour vs même heure sur 20 j
        "vol_jours": 20,
        "range_jours": 10,
        "correl_avec": ["NVDA", "SMCI"],
        "correl_jours": 20,
        "correl_min": 0.5,
    },
}
# Idées d'ajouts (à coller dans une watchlist) :
# GEV, ETN (équipement électrique) · CCJ (uranium) · ANET (réseau data centers)

AFFICHER_STOP = True       # repère de stop sur les signaux d'achat
MULT_ATR_STOP = 1.5        # stop = prix - 1,5 × ATR(14) 1h
AFFICHER_ACTU = True       # dernier titre d'actualité Yahoo (< 24 h)
FRAICHEUR_MAX_MIN = 35     # données plus vieilles → symbole ignoré
MAX_MESSAGES_PAR_CYCLE = 8 # au-delà : résumé en une ligne (jour de krach...)

# Références de marché (contexte) et secteur de comparaison par symbole
REFERENCES = ["SPY", "SMH", "XLU"]
SECTEUR = {s: "SMH" for s in ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "ARM", "MRVL"]}
SECTEUR.update({s: "XLU" for s in ["CEG", "VST", "NRG", "TLN"]})  # autres → SPY

PROFILS = {
    "NVDA": "GPU IA, leader des accélérateurs data center",
    "AMD": "GPU/CPU data center",
    "AVGO": "puces réseau et ASIC IA sur mesure",
    "TSM": "fondeur des puces IA avancées",
    "ASML": "lithographie EUV, goulot de la production de puces",
    "MU": "mémoire HBM pour GPU IA",
    "ARM": "architecture CPU sous licence",
    "MRVL": "ASIC IA et interconnexions optiques",
    "SMCI": "serveurs IA et refroidissement liquide",
    "DELL": "serveurs IA",
    "CEG": "nucléaire, contrats d'électricité avec les data centers",
    "VST": "production électrique, demande des data centers",
    "NRG": "production électrique, demande des data centers",
    "TLN": "nucléaire/gaz, alimentation directe de data centers",
    "EQIX": "data centers (colocation)",
    "DLR": "data centers",
    "MOD": "gestion thermique des data centers",
    "VRT": "alimentation et refroidissement des data centers",
    "FCX": "cuivre (câblage, réseaux électriques)",
    "MP": "terres rares (aimants permanents)",
    "SCCO": "cuivre",
    "TECK": "cuivre et zinc",
    "RIO": "cuivre, aluminium, minerai de fer",
    "BHP": "cuivre, minerai de fer",
    "COPX": "ETF mineurs de cuivre",
}

NOMS_MODULES = {"general": "Général", "power": "Power & Cooling",
                "semis": "Semis Momentum", "raw": "Raw Materials"}

# =============================================================================
# CONSTANTES / OUTILS
# =============================================================================

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
NAN = float("nan")
ETAT_FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
MODE = os.environ.get("MODE", "normal").strip().lower()
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def log(msg):
    print(f"[{datetime.now(UTC):%H:%M:%S}] {msg}", flush=True)


def ok(x):
    return x is not None and pd.notna(x)


def fpct(x):
    return f"{round(x, 1) + 0.0:+.1f}%" if ok(x) else "n/d"


def fprix(x):
    return f"${x:.2f}" if ok(x) else "n/d"


def fx(x):
    return f"{x:.1f}×" if ok(x) else "n/d"


def fn0(x):
    return f"{x:.0f}" if ok(x) else "n/d"


def assez(d, n):
    return d is not None and len(d) >= n


def minutes(idx):
    """Minutes depuis minuit (heure de New York) pour chaque bougie."""
    return np.asarray(idx.hour * 60 + idx.minute)


def hm_vers_minutes(txt):
    h, m = txt.split(":")
    return int(h) * 60 + int(m)


# =============================================================================
# DONNÉES
# =============================================================================

def telecharger(tickers, periode, intervalle, essais=3):
    for i in range(essais):
        try:
            df = yf.download(tickers, period=periode, interval=intervalle,
                             group_by="ticker", auto_adjust=False, prepost=False,
                             threads=True, progress=False)
            if df is not None and not df.empty:
                return df
            log(f"{intervalle} : réponse vide (essai {i + 1})")
        except Exception as e:
            log(f"{intervalle} : erreur essai {i + 1} → {e}")
        time.sleep(5 * (i + 1))
    return None


def extraire(brut, sym, quotidien=False):
    """Isole un symbole d'un téléchargement groupé, index en heure de New York."""
    if brut is None or brut.empty:
        return None
    try:
        cols = brut.columns
        if isinstance(cols, pd.MultiIndex):
            if sym in cols.get_level_values(0):
                d = brut[sym]
            elif sym in cols.get_level_values(1):
                d = brut.xs(sym, axis=1, level=1)
            else:
                return None
        else:
            d = brut
        d = d[["Open", "High", "Low", "Close", "Volume"]].copy()
        d = d.dropna(subset=["Open", "High", "Low", "Close"])
        if d.empty:
            return None
        idx = pd.DatetimeIndex(d.index)
        if idx.tz is None:
            idx = idx.tz_localize(NY if quotidien else UTC)
        d.index = idx.tz_convert(NY)
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d["Volume"] = d["Volume"].fillna(0).astype(float)
        return d
    except Exception as e:
        log(f"{sym} : extraction impossible → {e}")
        return None


def fins_de_bougies(idx, minutes_bougie):
    """Heure de fin de chaque bougie (plafonnée à la clôture de 16h00), en ns UTC."""
    fin = (idx + pd.Timedelta(minutes=minutes_bougie)).as_unit("ns").asi8
    fin_seance = (idx.normalize() + pd.Timedelta(hours=16)).as_unit("ns").asi8
    return np.minimum(fin, fin_seance)


def cloturees(d, minutes_bougie, maintenant):
    """Ne garde que les bougies terminées (+1 min de marge pour Yahoo)."""
    if d is None or d.empty:
        return d
    limite = pd.Timestamp(maintenant - timedelta(minutes=1)).as_unit("ns").value
    return d[fins_de_bougies(d.index, minutes_bougie) <= limite]


def en_4h(h1):
    """Bougies 4h de séance : 9h30-13h30 et 13h30-16h00 (heure de New York)."""
    if h1 is None or h1.empty:
        return None
    second = minutes(h1.index) >= 13 * 60 + 30
    decal = np.where(second, 13.5, 9.5)
    cle = h1.index.normalize() + pd.to_timedelta(decal, unit="h")
    g = h1.groupby(cle)
    out = pd.DataFrame({
        "Open": g["Open"].first(), "High": g["High"].max(), "Low": g["Low"].min(),
        "Close": g["Close"].last(), "Volume": g["Volume"].sum(), "n": g["Close"].count(),
    })
    if len(out):
        attendu = 3 if out.index[-1].hour >= 13 else 4
        if out["n"].iloc[-1] < attendu:   # dernière bougie 4h incomplète → écartée
            out = out.iloc[:-1]
    return out.drop(columns="n")


def cloture_veille(d1, jour):
    if d1 is None or d1.empty:
        return NAN
    passe = d1[d1.index.normalize() < jour]
    return float(passe["Close"].iloc[-1]) if len(passe) else NAN


# =============================================================================
# INDICATEURS
# =============================================================================

def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    perte = (-delta.clip(upper=0)).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    return 100 - 100 / (1 + gain / perte)


def sma(s, n):
    return s.rolling(n, min_periods=n).mean()


def ema(s, n):
    return s.ewm(span=n, min_periods=n, adjust=False).mean()


def atr(d, n=14):
    pc = d["Close"].shift()
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(),
                    (d["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()


def croisement(a, b):
    """+1 si a croise b à la hausse sur la dernière bougie, -1 à la baisse, 0 sinon."""
    if len(a) < 3 or not ok(b.iloc[-1]) or not ok(b.iloc[-2]):
        return 0
    if a.iloc[-2] <= b.iloc[-2] and a.iloc[-1] > b.iloc[-1]:
        return 1
    if a.iloc[-2] >= b.iloc[-2] and a.iloc[-1] < b.iloc[-1]:
        return -1
    return 0


def volume_relatif(d, jours):
    """Volume de la dernière bougie / moyenne du même créneau sur N séances."""
    if not assez(d, 10):
        return NAN
    der = d.index[-1]
    masque = (minutes(d.index) == der.hour * 60 + der.minute) & \
             np.asarray(d.index.normalize() < der.normalize())
    ref = d.loc[masque, "Volume"].tail(jours)
    ref = ref[ref > 0]
    if len(ref) < max(3, jours // 3):
        return NAN
    return float(d["Volume"].iloc[-1] / ref.mean())


def seance_du_jour(m15, heure_min=None):
    jour = m15.index[-1].normalize()
    auj = m15[np.asarray(m15.index.normalize() == jour)]
    if heure_min is not None:
        auj = auj[minutes(auj.index) >= heure_min]
    return auj


def variation_glissante(m15, n, heure_min=None):
    """Variation % sur les n dernières bougies 15 min de la séance du jour."""
    if not assez(m15, 2):
        return NAN
    fen = seance_du_jour(m15, heure_min).tail(n)
    if fen.empty:
        return NAN
    return float((fen["Close"].iloc[-1] / fen["Open"].iloc[0] - 1) * 100)


def volume_fenetre_relatif(m15, n, jours, heure_min=None):
    """Volume des n dernières bougies 15 min du jour / moyenne de la même
    fenêtre horaire sur N séances. n très grand = volume cumulé du jour."""
    if not assez(m15, 10):
        return NAN
    auj = seance_du_jour(m15, heure_min).tail(n)
    if auj.empty:
        return NAN
    t0, t1 = minutes(auj.index)[0], minutes(auj.index)[-1]
    passe = m15[np.asarray(m15.index.normalize() < auj.index[-1].normalize())]
    mp = minutes(passe.index)
    passe = passe[(mp >= t0) & (mp <= t1)]
    if passe.empty:
        return NAN
    sommes = passe.groupby(passe.index.normalize())["Volume"].sum().tail(jours)
    sommes = sommes[sommes > 0]
    if len(sommes) < 3:
        return NAN
    return float(auj["Volume"].sum() / sommes.mean())


def _pivot_recent(S, i, fen, piv, haut):
    for j in range(i - 5, max(i - fen, piv) - 1, -1):
        seg = S[j - piv:j + piv + 1]
        if (haut and S[j] == seg.max()) or (not haut and S[j] == seg.min()):
            return j
    return None


def divergence(d, r, fen=30, piv=3, marge=3.0):
    """Divergence RSI sur la dernière bougie : +1 haussière, -1 baissière."""
    n = len(d)
    if n < fen + 25 or not ok(r.iloc[-1]):
        return 0, ""
    H, L, R = d["High"].to_numpy(), d["Low"].to_numpy(), r.to_numpy()
    i = n - 1
    if H[i] >= H[i - 20:i].max():
        j = _pivot_recent(H, i, fen, piv, haut=True)
        if j is not None and ok(R[j]) and R[j] >= 60 and R[i] < R[j] - marge and H[i] > H[j]:
            return -1, f"nouveau plus haut mais RSI plus faible ({R[i]:.0f} vs {R[j]:.0f})"
    if L[i] <= L[i - 20:i].min():
        j = _pivot_recent(L, i, fen, piv, haut=False)
        if j is not None and ok(R[j]) and R[j] <= 40 and R[i] > R[j] + marge and L[i] < L[j]:
            return 1, f"nouveau plus bas mais RSI plus fort ({R[i]:.0f} vs {R[j]:.0f})"
    return 0, ""


def ligne_stop(h1, prix, sens):
    if not AFFICHER_STOP or sens <= 0 or not assez(h1, 20):
        return None
    a = atr(h1).iloc[-1]
    if not ok(a) or not ok(prix):
        return None
    mult = f"{MULT_ATR_STOP:g}".replace(".", ",")
    return f"Repère stop : {fprix(prix - MULT_ATR_STOP * a)} ({mult}× ATR 1h)"


def ligne_relative(sym, x, D):
    ref = SECTEUR.get(sym, "SPY")
    r = D.get(ref)
    if r is None or not ok(x["var_jour"]) or not ok(r["var_jour"]):
        return ""
    ecart = x["var_jour"] - r["var_jour"]
    txt = f"{'surperforme' if ecart >= 0 else 'sous-performe'} {ref} de {abs(ecart):.1f} pts aujourd'hui"
    if abs(ecart) >= 2:
        txt += " (mouvement spécifique)"
    elif abs(ecart) < 1 and abs(x["var_jour"]) >= 2:
        txt += " (mouvement de secteur)"
    return txt


def derniere_actu(sym):
    """Dernier titre d'actualité Yahoo de moins de 24 h (ou None)."""
    if not AFFICHER_ACTU:
        return None
    try:
        items = yf.Ticker(sym).news or []
    except Exception:
        return None
    limite = datetime.now(UTC) - timedelta(hours=24)
    for it in items[:10]:
        try:
            c = it.get("content") or it
            titre = (c.get("title") or "").strip()
            date = None
            if c.get("pubDate"):
                date = datetime.fromisoformat(str(c["pubDate"]).replace("Z", "+00:00"))
            elif it.get("providerPublishTime"):
                date = datetime.fromtimestamp(int(it["providerPublishTime"]), UTC)
            if titre and date and date >= limite:
                return titre if len(titre) <= 140 else titre[:137] + "…"
        except Exception:
            continue
    return None


def nouveau_signal(module, sym, sens, cle, lignes, prix):
    return {"module": module, "symbole": sym, "direction": sens, "cle": cle,
            "texte": "\n".join(l for l in lignes if l), "prix": prix}


# =============================================================================
# MODULE 1 — AI INFRASTRUCTURE WATCHER
# =============================================================================

def module_general(sym, x, cfg, D):
    h1, h4, m15 = x["h1"], x["h4"], x["m15"]
    if not assez(h1, 60) or not assez(m15, 10):
        return None
    c1 = h1["Close"]
    r1 = rsi(c1).iloc[-1]
    mm20 = sma(c1, 20)
    vol1 = volume_relatif(h1, cfg["vol_jours"])
    var1h = variation_glissante(m15, 4)
    volw = volume_fenetre_relatif(m15, 4, cfg["vol_jours"])

    achat, vente = [], []  # (libellé, déclencheur ?)
    if ok(r1) and r1 < cfg["rsi_survente"]:
        achat.append((f"RSI 1h en survente ({r1:.0f})", True))
    if ok(r1) and r1 > cfg["rsi_surachat"]:
        vente.append((f"RSI 1h en surachat ({r1:.0f})", True))

    r4 = NAN
    if assez(h4, 30):
        c4 = h4["Close"]
        r4 = rsi(c4).iloc[-1]
        if ok(r4) and r4 < cfg["rsi_survente"]:
            achat.append((f"RSI 4h en survente ({r4:.0f})", True))
        if ok(r4) and r4 > cfg["rsi_surachat"]:
            vente.append((f"RSI 4h en surachat ({r4:.0f})", True))
        cr4 = croisement(c4, sma(c4, 20))
        vol4 = volume_relatif(h4, cfg["vol_jours"])
        if cr4 and ok(vol4) and vol4 >= cfg["vol_croisement"]:
            (achat if cr4 > 0 else vente).append(
                (f"cassure de la MM20 4h {'à la hausse' if cr4 > 0 else 'à la baisse'}", True))
        mm50_4 = sma(c4, 50).iloc[-1]
        if ok(mm50_4):
            if c4.iloc[-1] > mm50_4:
                achat.append(("tendance 4h haussière (au-dessus de la MM50)", False))
            else:
                vente.append(("tendance 4h baissière (sous la MM50)", False))

    if ok(var1h) and ok(volw) and volw > cfg["vol_momentum"]:
        if var1h > cfg["var_1h"]:
            achat.append((f"fort momentum haussier ({var1h:+.1f}% en 1h, volume {volw:.1f}×)", True))
        if var1h < -cfg["var_1h"]:
            vente.append((f"fort momentum baissier ({var1h:+.1f}% en 1h, volume {volw:.1f}×)", True))

    cr = croisement(c1, mm20)
    if cr and ok(vol1) and vol1 >= cfg["vol_croisement"]:
        (achat if cr > 0 else vente).append(
            (f"prix croise la MM20 1h {'à la hausse' if cr > 0 else 'à la baisse'} (volume {vol1:.1f}×)", True))

    def valide(conds):
        return len(conds) >= 2 and any(c[1] for c in conds)

    def score(conds):  # déclencheur = 1 point, simple contexte (tendance) = 0,5
        return sum(1 if c[1] else 0.5 for c in conds)

    va, vv = valide(achat), valide(vente)
    if va and vv:
        sa, sv = score(achat), score(vente)
        if sa == sv:
            return None
        va, vv = sa > sv, sv > sa
    if not (va or vv):
        return None
    sens = 1 if va else -1
    conds, opposes = (achat, vente) if va else (vente, achat)

    action = ("Acheter" if sens > 0 else "Vendre") if len(conds) >= 3 else "Surveiller de près"
    raison = " + ".join(c[0] for c in conds)
    raison = raison[0].upper() + raison[1:]
    opp = [c[0] for c in opposes if c[1]]
    if opp:
        action = "Surveiller de près"
        raison += f" — attention, signal opposé : {opp[0]}"

    lignes = [
        f"{'🚀' if sens > 0 else '🔻'} {sym} – Signal {'ACHAT' if sens > 0 else 'VENTE'}",
        f"Prix actuel : {fprix(x['prix'])}",
        f"Variation 1h : {fpct(var1h)}",
        f"RSI : {fn0(r1)} (1h) | {fn0(r4)} (4h)",
        f"Volume : {fx(vol1)} moyenne",
        f"Raison : {raison}.",
        f"Action suggérée : {action}",
        ligne_stop(h1, x["prix"], sens),
    ]
    cle = f"general:{sym}:{sens}:{h1.index[-1].isoformat()}"
    return nouveau_signal("general", sym, sens, cle, lignes, x["prix"])


# =============================================================================
# MODULE 2 — POWER & COOLING ALERT
# =============================================================================

def module_power(sym, x, cfg, D):
    h1, m15 = x["h1"], x["m15"]
    if not assez(h1, 60) or not assez(m15, 10):
        return None
    vol = volume_fenetre_relatif(m15, 8, cfg["vol_jours"])
    if not ok(vol) or vol < cfg["vol_min"]:          # volume obligatoire
        return None
    var2h = variation_glissante(m15, 8)
    c1 = h1["Close"]
    r = rsi(c1)
    rn = r.iloc[-1]
    prec = r.iloc[-4:-1]
    bas, haut = cfg["rsi_zone"]
    mm50 = sma(c1, 50).iloc[-1]
    ecart = (x["prix_clos"] / mm50 - 1) * 100 if ok(mm50) else NAN

    hausse, baisse = [], []
    if ok(var2h) and var2h >= cfg["var_2h"]:
        hausse.append(f"{var2h:+.1f}% en 2h")
    if ok(var2h) and var2h <= -cfg["var_2h"]:
        baisse.append(f"{var2h:+.1f}% en 2h")
    if ok(rn) and rn > haut and (prec <= haut).any():
        hausse.append(f"RSI sort de la zone {bas}-{haut} par le haut ({rn:.0f})")
    if ok(rn) and rn < bas and (prec >= bas).any():
        baisse.append(f"RSI sort de la zone {bas}-{haut} par le bas ({rn:.0f})")
    if ok(ecart) and ecart > cfg["ecart_mm50"]:
        hausse.append(f"prix {ecart:+.1f}% au-dessus de la MM50")
    if ok(ecart) and ecart < -cfg["ecart_mm50"]:
        baisse.append(f"prix {ecart:+.1f}% sous la MM50")

    if len(hausse) >= 2 and len(hausse) > len(baisse):
        sens, conds = 1, hausse
    elif len(baisse) >= 2 and len(baisse) > len(hausse):
        sens, conds = -1, baisse
    else:
        return None

    if len(conds) >= 3:
        typ = "Achat fort" if sens > 0 else "Vente forte"
    else:
        typ = "Momentum haussier" if sens > 0 else "Momentum baissier"

    commentaire = PROFILS.get(sym, "")
    rel = ligne_relative(sym, x, D)
    if rel:
        commentaire = f"{commentaire} — {rel}" if commentaire else rel
    lignes = [
        f"⚡ POWER/COOLING ALERT – {sym}",
        f"Type : {typ}",
        f"Prix : {fprix(x['prix'])}",
        f"Variation 2h : {fpct(var2h)}",
        f"Volume relatif : {fx(vol)}",
        f"Signaux : {' + '.join(conds)}",
        f"Commentaire : {commentaire[:1].upper() + commentaire[1:]}." if commentaire else None,
        ligne_stop(h1, x["prix"], sens) if len(conds) >= 3 else None,
    ]
    cle = f"power:{sym}:{sens}:{h1.index[-1].isoformat()}"
    return nouveau_signal("power", sym, sens, cle, lignes, x["prix"])


# =============================================================================
# MODULE 3 — SEMICONDUCTORS MOMENTUM
# =============================================================================

def module_semis(sym, x, cfg, D):
    h1, h4, m15 = x["h1"], x["h4"], x["m15"]
    if not assez(h1, 60) or not assez(m15, 10):
        return None
    seuil = hm_vers_minutes(cfg["ignorer_avant"])
    if minutes(m15.index)[-1] < seuil:               # filtre d'ouverture
        return None
    c1 = h1["Close"]
    r1s = rsi(c1)
    r1 = r1s.iloc[-1]
    vol1 = volume_relatif(h1, cfg["vol_jours"])
    var1h = variation_glissante(m15, 4, heure_min=seuil)
    volw = volume_fenetre_relatif(m15, 4, cfg["vol_jours"], heure_min=seuil)

    sig = []  # (priorité, type, sens, détail, timeframe, volume)
    n = cfg["range_bougies"]
    if len(h1) > n + 1 and ok(vol1) and vol1 >= cfg["vol_breakout"]:
        haut_r = h1["High"].iloc[-n - 1:-1].max()
        bas_r = h1["Low"].iloc[-n - 1:-1].min()
        if c1.iloc[-1] > haut_r:
            sig.append((1, "Breakout haussier", 1, f"clôture au-dessus du range {n} bougies ({fprix(haut_r)})", "1h", vol1))
        elif c1.iloc[-1] < bas_r:
            sig.append((1, "Breakout baissier", -1, f"clôture sous le range {n} bougies ({fprix(bas_r)})", "1h", vol1))
    if ok(vol1) and vol1 >= cfg["vol_min"]:
        ds, dd = divergence(h1, r1s)
        if ds:
            sig.append((2, f"Divergence {'haussière' if ds > 0 else 'baissière'}", ds, dd, "1h", vol1))
        cr = croisement(ema(c1, cfg["mm_rapide"]), ema(c1, cfg["mm_lente"]))
        if cr:
            sig.append((3, f"Croisement {'haussier' if cr > 0 else 'baissier'}", cr,
                        f"MME{cfg['mm_rapide']} {'au-dessus' if cr > 0 else 'sous'} la MME{cfg['mm_lente']}", "1h", vol1))
    if ok(var1h) and abs(var1h) >= cfg["var_1h"] and ok(volw) and volw >= cfg["vol_min"]:
        s = 1 if var1h > 0 else -1
        sig.append((4, f"Momentum {'haussier' if s > 0 else 'baissier'}", s,
                    f"{var1h:+.1f}% en 1h", "15 min (1h glissante)", volw))
    if not sig:
        return None

    sig.sort(key=lambda s: s[0])
    _, typ, sens, detail, tf, vol_aff = sig[0]
    confirm = [s[1] for s in sig[1:] if s[2] == sens]
    contra = [s[1] for s in sig[1:] if s[2] != sens]

    t4 = 0
    if assez(h4, 25):
        c4 = h4["Close"]
        e4 = ema(c4, 21)
        if ok(e4.iloc[-1]) and ok(e4.iloc[-2]):
            if c4.iloc[-1] > e4.iloc[-1] and e4.iloc[-1] > e4.iloc[-2]:
                t4 = 1
            elif c4.iloc[-1] < e4.iloc[-1] and e4.iloc[-1] < e4.iloc[-2]:
                t4 = -1
    tendance = {1: "haussière", -1: "baissière", 0: "neutre"}[t4]

    if typ.startswith("Divergence") or contra or t4 != sens:
        suggestion = "Attendre confirmation"
    else:
        suggestion = "Acheter" if sens > 0 else "Vendre"

    lignes = [
        f"🔥 SEMI MOMENTUM – {sym}",
        f"Signal : {typ}",
        f"Détail : {detail}",
        f"Timeframe : {tf}",
        f"Prix : {fprix(x['prix'])}",
        f"RSI 1h : {fn0(r1)}",
        f"Volume : {fx(vol_aff)}",
        f"Tendance 4h : {tendance}",
        f"Confirmations : {', '.join(confirm)}" if confirm else None,
        f"⚠️ Signal opposé : {', '.join(contra)}" if contra else None,
        f"Suggestion : {suggestion}",
        ligne_stop(h1, x["prix"], sens) if suggestion == "Acheter" else None,
    ]
    cle = f"semis:{sym}:{typ}:{h1.index[-1].isoformat()}"
    return nouveau_signal("semis", sym, sens, cle, lignes, x["prix"])


# =============================================================================
# MODULE 4 — RAW MATERIALS AI
# =============================================================================

def module_raw(sym, x, cfg, D):
    d1, m15 = x["d1"], x["m15"]
    if not assez(d1, cfg["range_jours"] + 5) or not assez(m15, 10):
        return None
    jour = x["jour"]
    passe = d1[np.asarray(d1.index.normalize() < jour)]
    if len(passe) < cfg["range_jours"] + 2:
        return None
    prix = x["prix_clos"]
    var_j = x["var_jour"]
    volc = volume_fenetre_relatif(m15, 10_000, cfg["vol_jours"])
    rng = passe.tail(cfg["range_jours"])
    haut, bas = rng["High"].max(), rng["Low"].min()

    hausse, baisse = [], []  # (code, libellé)
    if ok(var_j) and var_j >= cfg["var_jour"]:
        hausse.append(("var", f"{var_j:+.1f}% sur la journée"))
    if ok(var_j) and var_j <= -cfg["var_jour"]:
        baisse.append(("var", f"{var_j:+.1f}% sur la journée"))
    if prix > haut:
        hausse.append(("range", f"sortie par le haut du range {cfg['range_jours']} j ({fprix(haut)})"))
    if prix < bas:
        baisse.append(("range", f"sortie par le bas du range {cfg['range_jours']} j ({fprix(bas)})"))
    if hausse and not baisse:
        sens, conds = 1, hausse
    elif baisse and not hausse:
        sens, conds = -1, baisse
    else:
        return None

    if ok(volc) and volc >= cfg["vol_min"]:
        conds.append(("vol", f"volume inhabituel ({volc:.1f}×)"))

    # Corrélation avec NVDA / SMCI (rendements journaliers sur 20 séances)
    meilleur = None
    rend = passe["Close"].pct_change()
    for ref in cfg["correl_avec"]:
        rx = D.get(ref)
        if rx is None or rx["d1"] is None:
            continue
        rr = rx["d1"][np.asarray(rx["d1"].index.normalize() < jour)]["Close"].pct_change()
        j = pd.concat([rend, rr], axis=1, join="inner").dropna().tail(cfg["correl_jours"])
        if len(j) < 10:
            continue
        corr = float(j.iloc[:, 0].corr(j.iloc[:, 1]))
        if ok(corr) and (meilleur is None or corr > meilleur[1]):
            meilleur = (ref, corr, rx["var_jour"])
    contexte_corr = ""
    if meilleur:
        ref, corr, vref = meilleur
        contexte_corr = f"corrél. 20 j avec {ref} : {corr:.2f} ({ref} {fpct(vref)} auj.)"
        if corr >= cfg["correl_min"] and ok(vref) and vref * sens >= 1.0:
            conds.append(("corr", f"mouvement aligné sur {ref}"))

    if len(conds) < 2:
        return None

    profil = PROFILS.get(sym, "")
    contexte = " · ".join(t for t in [profil[:1].upper() + profil[1:] if profil else "",
                                      contexte_corr, ligne_relative(sym, x, D)] if t)
    lignes = [
        f"🪨 RAW MATERIALS AI – {sym}",
        f"Mouvement : {'Hausse forte' if sens > 0 else 'Baisse forte'}",
        f"Prix : {fprix(x['prix'])}",
        f"Variation jour : {fpct(var_j)}",
        f"Volume : {fx(volc)} (cumul du jour vs même heure)",
        f"Signaux : {' + '.join(c[1] for c in conds)}",
        f"Contexte : {contexte}" if contexte else None,
    ]
    codes = "|".join(sorted(c[0] for c in conds))
    cle = f"raw:{sym}:{jour.date().isoformat()}:{sens}:{codes}"
    return nouveau_signal("raw", sym, sens, cle, lignes, x["prix"])


MODULES_FN = {"general": module_general, "power": module_power,
              "semis": module_semis, "raw": module_raw}


# =============================================================================
# ÉTAT (cooldowns, empreintes, journal) — sauvegardé dans state.json
# =============================================================================

def charger_etat():
    base = {"cooldowns": {}, "empreintes": {}, "compteurs": {}, "journal": [],
            "dernier_bilan": "", "derniere_erreur": ""}
    try:
        with open(ETAT_FICHIER, encoding="utf-8") as f:
            base.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"state.json illisible, remis à zéro → {e}")
    return base


def sauvegarder_etat(etat):
    with open(ETAT_FICHIER, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=1, sort_keys=True)


def nettoyer_etat(etat, maintenant):
    def recent(v, jours):
        try:
            return maintenant - datetime.fromisoformat(v) < timedelta(days=jours)
        except Exception:
            return False
    etat["empreintes"] = {k: v for k, v in etat["empreintes"].items() if recent(v, 3)}
    etat["cooldowns"] = {k: v for k, v in etat["cooldowns"].items() if recent(v, 1)}
    auj = maintenant.date().isoformat()
    etat["compteurs"] = {k: v for k, v in etat["compteurs"].items() if k.endswith(auj)}
    etat["journal"] = [j for j in etat["journal"] if recent(j.get("t", ""), 21)]


def autorise(etat, s, maintenant):
    if s["cle"] in etat["empreintes"]:
        return False
    cfg = MODULES[s["module"]]
    if s["module"] == "raw":
        k = f"raw:{s['symbole']}:{maintenant.date().isoformat()}"
        return etat["compteurs"].get(k, 0) < cfg["max_par_jour"]
    der = etat["cooldowns"].get(f"{s['module']}:{s['symbole']}")
    return not der or maintenant - datetime.fromisoformat(der) >= timedelta(minutes=cfg["cooldown_min"])


def enregistrer(etat, s, maintenant):
    iso = maintenant.isoformat(timespec="seconds")
    etat["empreintes"][s["cle"]] = iso
    etat["cooldowns"][f"{s['module']}:{s['symbole']}"] = iso
    if s["module"] == "raw":
        k = f"raw:{s['symbole']}:{maintenant.date().isoformat()}"
        etat["compteurs"][k] = etat["compteurs"].get(k, 0) + 1
    if s["direction"] and ok(s["prix"]):
        etat["journal"].append({"t": iso, "m": s["module"], "s": s["symbole"],
                                "d": s["direction"], "p": round(float(s["prix"]), 4)})


# =============================================================================
# TELEGRAM
# =============================================================================

def envoyer(texte):
    if not TOKEN or not CHAT_ID:
        log("Secrets Telegram absents — message affiché ici :\n" + texte)
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for i in range(3):
        try:
            r = requests.post(url, data={"chat_id": CHAT_ID, "text": texte,
                                         "disable_web_page_preview": "true"}, timeout=15)
            if r.ok:
                return True
            log(f"Telegram {r.status_code} : {r.text[:200]}")
            if r.status_code == 429:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 3)))
                continue
            if r.status_code in (400, 401, 403, 404):
                return False   # token / chat_id incorrect : inutile d'insister
        except Exception as e:
            log(f"Telegram erreur : {e}")
        time.sleep(2 * (i + 1))
    return False


def alerte_erreur(etat, maintenant, msg):
    """Prévient qu'il y a un problème, au maximum une fois toutes les 3 h."""
    der = etat.get("derniere_erreur")
    try:
        if der and maintenant - datetime.fromisoformat(der) < timedelta(hours=3):
            return False
    except Exception:
        pass
    txt = f"⚠️ AI MARKET WATCH — {msg}\n🕒 {maintenant.astimezone(UTC):%H:%M} UTC"
    if envoyer(txt):
        etat["derniere_erreur"] = maintenant.isoformat(timespec="seconds")
        return True
    return False


# =============================================================================
# ASSEMBLAGE DES MESSAGES
# =============================================================================

def pied_de_message(D, maintenant):
    marche = " · ".join(f"{r} {fpct(D[r]['var_jour'])}" for r in ("SPY", "SMH") if r in D)
    return f"🕒 Analyse : {maintenant.astimezone(UTC):%H:%M} UTC" + (f" · {marche}" if marche else "")


def fusionner(signaux, pied, avec_actu=True):
    """Un message par symbole ; signale la convergence ou la contradiction."""
    groupes = {}
    for s in signaux:
        groupes.setdefault(s["symbole"], []).append(s)
    sortie = []
    for sym, g in groupes.items():
        sens = {s["direction"] for s in g if s["direction"]}
        blocs = "\n\n".join(s["texte"] for s in g)
        if len(g) > 1:
            if len(sens) > 1:
                entete = f"⚠️ {sym} — signaux CONTRADICTOIRES entre modules : prudence"
            else:
                entete = f"📌 {sym} — {len(g)} modules convergent ({'haussier' if 1 in sens else 'baissier'})"
            blocs = entete + "\n\n" + blocs
        actu = derniere_actu(sym) if avec_actu else None
        txt = blocs + (f"\n📰 {actu}" if actu else "") + f"\n{pied}"
        score = len(g) * 10 - (5 if len(sens) > 1 else 0)
        sortie.append((score, sym, txt, g))
    sortie.sort(key=lambda t: -t[0])
    return sortie


# =============================================================================
# BILAN HEBDOMADAIRE (vendredi après la clôture)
# =============================================================================

def cle_semaine(dt):
    a, s, _ = dt.isocalendar()
    return f"{a}-S{s:02d}"


def bilan_hebdo(etat, b1d, maintenant):
    cle = cle_semaine(maintenant)
    journal = [j for j in etat["journal"]
               if cle_semaine(datetime.fromisoformat(j["t"])) == cle]
    tete = f"📊 BILAN HEBDO {cle}"
    if not journal:
        return f"{tete}\nAucun signal envoyé cette semaine."
    derniers = {}
    res = []
    for j in journal:
        if j["s"] not in derniers:
            d = extraire(b1d, j["s"], quotidien=True)
            derniers[j["s"]] = float(d["Close"].iloc[-1]) if assez(d, 1) else NAN
        px = derniers[j["s"]]
        if ok(px) and j["p"]:
            res.append({**j, "perf": (px / j["p"] - 1) * 100 * j["d"]})
    if not res:
        return f"{tete}\nDonnées de clôture indisponibles pour évaluer les signaux."

    def stats(lst):
        g = sum(1 for r in lst if r["perf"] > 0)
        n = len(lst)
        return (f"{n} signa{'ux' if n > 1 else 'l'} · {g / n * 100:.0f}% gagnants · "
                f"moy. {fpct(float(np.mean([r['perf'] for r in lst])))}")

    lignes = [tete, "Perf. théorique : prix du signal → clôture de vendredi",
              "(achat gagnant si hausse · vente gagnante si baisse)", ""]
    for m, nom in NOMS_MODULES.items():
        lst = [r for r in res if r["m"] == m]
        if lst:
            lignes.append(f"{nom} : {stats(lst)}")
    lignes += ["", f"TOTAL : {stats(res)}"]
    tri = sorted(res, key=lambda r: -r["perf"])

    def fmt(r):
        jr = JOURS[datetime.fromisoformat(r["t"]).weekday()]
        return f"{r['s']} {fpct(r['perf'])} ({NOMS_MODULES[r['m']]}, {'achat' if r['d'] > 0 else 'vente'}, {jr})"
    lignes.append("🏆 Meilleurs : " + " | ".join(fmt(r) for r in tri[:3]))
    if len(tri) > 3:
        lignes.append("💀 Pires : " + " | ".join(fmt(r) for r in tri[::-1][:3]))
    return "\n".join(lignes)


# =============================================================================
# PROGRAMME PRINCIPAL
# =============================================================================

def tous_les_symboles():
    syms = list(REFERENCES)
    for cfg in MODULES.values():
        syms += cfg["watchlist"]
    syms += MODULES["raw"].get("correl_avec", [])
    return sorted(set(syms))


def preparer(syms, b15, b60, b1d, maintenant):
    D = {}
    for s in syms:
        m15_brut = extraire(b15, s)
        if m15_brut is None:
            continue
        m15 = cloturees(m15_brut, 15, maintenant)
        if m15 is None or m15.empty:
            continue
        h1 = cloturees(extraire(b60, s), 60, maintenant)
        d1 = extraire(b1d, s, quotidien=True)
        jour = m15.index[-1].normalize()
        veille = cloture_veille(d1, jour)
        prix_clos = float(m15["Close"].iloc[-1])
        D[s] = {
            "m15": m15, "h1": h1, "h4": en_4h(h1), "d1": d1, "jour": jour,
            "fin": pd.Timestamp(int(fins_de_bougies(m15.index[-1:], 15)[0]), unit="ns", tz="UTC"),
            "prix": float(m15_brut["Close"].iloc[-1]),   # dernière cotation connue
            "prix_clos": prix_clos,                       # base des calculs
            "veille": veille,
            "var_jour": (prix_clos / veille - 1) * 100 if ok(veille) and veille else NAN,
        }
    return D


def analyser(D, symboles_ok):
    signaux = []
    for nom, cfg in MODULES.items():
        if not cfg.get("actif", True):
            continue
        for s in cfg["watchlist"]:
            if s not in symboles_ok:
                continue
            try:
                sig = MODULES_FN[nom](s, D[s], cfg, D)
                if sig:
                    signaux.append(sig)
            except Exception as e:
                log(f"{nom}/{s} : erreur → {e}")
    return signaux


def main(maintenant=None):
    maintenant = maintenant or datetime.now(NY)
    test = MODE == "test"
    etat = charger_etat()
    nettoyer_etat(etat, maintenant)
    avant = json.dumps(etat, sort_keys=True)

    t = maintenant.hour * 60 + maintenant.minute
    en_seance = maintenant.weekday() < 5 and 9 * 60 + 45 <= t <= 16 * 60 + 30
    bilan_du = (not test and maintenant.weekday() == 4 and t >= 16 * 60 + 5
                and etat.get("dernier_bilan") != cle_semaine(maintenant))
    if not (test or en_seance or bilan_du):
        log("Hors séance US : rien à faire.")
        return

    syms = tous_les_symboles()
    b1d = telecharger(syms, "6mo", "1d")

    try:
        if bilan_du and b1d is not None:
            if envoyer(bilan_hebdo(etat, b1d, maintenant)):
                etat["dernier_bilan"] = cle_semaine(maintenant)

        if not (test or en_seance):
            return

        b15 = telecharger(syms, "1mo", "15m")
        b60 = telecharger(syms, "3mo", "60m")
        if b15 is None or b60 is None:
            if test:
                envoyer("🧪 TEST — Yahoo Finance ne répond pas. Réessaie dans quelques minutes.")
            else:
                alerte_erreur(etat, maintenant, "Yahoo Finance ne répond pas : aucune analyse sur ce cycle.")
            return

        D = preparer(syms, b15, b60, b1d, maintenant)
        spy = D.get("SPY")
        if not test and (spy is None or spy["jour"].date() != maintenant.date()):
            log("Marché fermé aujourd'hui (jour férié) : rien à faire.")
            return

        limite = timedelta(minutes=FRAICHEUR_MAX_MIN)
        frais = {s for s, x in D.items() if test or maintenant - x["fin"] <= limite}
        surveilles = set(syms) - set(REFERENCES)
        manquants = sorted(surveilles - frais)
        if manquants:
            log(f"Données absentes ou périmées : {', '.join(manquants)}")
        if not test and len(manquants) > len(surveilles) / 2:
            alerte_erreur(etat, maintenant, f"données Yahoo en retard ou absentes pour "
                                            f"{len(manquants)}/{len(surveilles)} symboles.")

        pied = pied_de_message(D, maintenant)
        signaux = analyser(D, frais)
        log(f"{len(signaux)} signal(s) détecté(s) avant filtres anti-spam.")

        if test:
            der = max((x["fin"] for x in D.values()), default=None)
            der_txt = f"{der.tz_convert(UTC):%d/%m %H:%M} UTC" if der is not None else "n/d"
            diag = [
                "🧪 TEST AI MARKET WATCH",
                f"Données reçues : {len(surveilles & set(D))}/{len(surveilles)} symboles",
                f"Dernière bougie 15 min clôturée : {der_txt}",
                f"Manquants : {', '.join(manquants)}" if manquants else "Manquants : aucun",
                f"Signaux sur les dernières données : {len(signaux)}",
                "(aperçus ci-dessous · cooldowns ignorés · rien n'est enregistré)" if signaux
                else "Aucun signal actuellement : c'est normal, les règles sont sélectives.",
            ]
            envoyer("\n".join(diag))
            for _, _, txt, _ in fusionner(signaux, pied)[:3]:
                envoyer("🧪 APERÇU TEST\n" + txt)
            return

        retenus = [s for s in signaux if autorise(etat, s, maintenant)]
        messages = fusionner(retenus, pied)
        a_envoyer = messages[:MAX_MESSAGES_PAR_CYCLE]
        reste = messages[MAX_MESSAGES_PAR_CYCLE:]
        for _, _, txt, groupe in a_envoyer:
            if envoyer(txt):
                for s in groupe:
                    enregistrer(etat, s, maintenant)
        if reste:
            resume = ", ".join(f"{sym} ({'↑' if g[0]['direction'] > 0 else '↓'})" for _, sym, _, g in reste)
            if envoyer(f"➕ {len(reste)} autres signaux ce cycle : {resume}\n{pied}"):
                for _, _, _, groupe in reste:
                    for s in groupe:
                        enregistrer(etat, s, maintenant)
        log(f"{len(a_envoyer) + (1 if reste else 0)} message(s) envoyé(s).")
    finally:
        if not test and json.dumps(etat, sort_keys=True) != avant:
            sauvegarder_etat(etat)
            log("state.json mis à jour.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("ERREUR FATALE :\n" + traceback.format_exc())
        try:
            e = charger_etat()
            if alerte_erreur(e, datetime.now(NY), "erreur interne du bot (voir l'onglet Actions sur GitHub)."):
                sauvegarder_etat(e)
        except Exception:
            pass
        sys.exit(0)
