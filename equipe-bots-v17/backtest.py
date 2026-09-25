"""BACKTESTEUR v3 : note chaque bot sur 10 sur plusieurs années, AVANT de risquer un euro.

  python backtest.py                     2 ans, 25 paires, unité de config.py
  python backtest.py --jours 1095        3 ans d'historique
  python backtest.py --unite 4h          trades de plusieurs jours (swing)
  python backtest.py --comparer          compare 15 min / 1 h / 4 h et recommande la meilleure unité

Sources (gratuites, mises en cache dans archives/) : data.binance.vision (bougies, funding, positions),
DefiLlama (stablecoins), alternative.me (peur & avidité), Yahoo Finance (Nasdaq, dollar).

Trois garde-fous contre les illusions :
1. Aucune donnée future : chaque information est datée au moment où elle était réellement connue.
2. Stabilité : l'historique est coupé en périodes. Un bot n'est « fiable » que s'il tient sur CHACUNE.
3. Hors échantillon : les poids sont appris sur les premières périodes, puis l'équipe est jugée
   sur la dernière, qu'elle n'a jamais vue. C'est CE chiffre qui compte."""
import argparse
import datetime as dt
import json
import ccxt
import numpy as np
import pandas as pd
import config
import historique as H
from indicateurs import ema, rsi, atr
from simulation import simuler_sortie, note_sur_10

# Décisions de la Fed et inflation US (UTC) pour noter CALENDRIER. Sources : Fed, BLS.
MACRO_PASSE = [
    "2024-01-31 19:00", "2024-03-20 18:00", "2024-05-01 18:00", "2024-06-12 18:00", "2024-07-31 18:00",
    "2024-09-18 18:00", "2024-11-07 19:00", "2024-12-18 19:00",
    "2025-01-29 19:00", "2025-03-19 18:00", "2025-05-07 18:00", "2025-06-18 18:00", "2025-07-30 18:00",
    "2025-09-17 18:00", "2025-10-29 18:00", "2025-12-10 19:00",
    "2026-01-13 13:30", "2026-01-28 19:00", "2026-02-13 13:30", "2026-03-11 12:30", "2026-03-18 18:00",
    "2026-04-10 12:30", "2026-04-29 18:00", "2026-05-12 12:30", "2026-06-10 12:30", "2026-06-17 18:00",
    "2026-07-14 12:30", "2026-07-29 18:00", "2026-08-12 12:30", "2026-09-11 12:30", "2026-09-16 18:00",
]
MACRO_MS = np.array([int(dt.datetime.strptime(m, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
                         .timestamp() * 1000) for m in MACRO_PASSE])
REGLE = {"1h": "1h", "4h": "4h", "1d": "1D", "1w": "7D"}


# =============================== PRÉPARATION ===============================
def regime(df15, unite):
    """Tendance d'une unité supérieure, visible uniquement une fois la bougie FERMÉE."""
    x = df15.set_index(pd.to_datetime(df15["t"], unit="ms"))
    h = x.resample(REGLE[unite], label="left", closed="left").agg({"c": "last"}).dropna()
    e20, e50 = ema(h["c"], 20), ema(h["c"], 50)
    return pd.DataFrame({"t_ferme": H.en_ms(h.index + pd.Timedelta(REGLE[unite])),
                         "haussier": ((h["c"] > e50) & (e20 > e50)).astype(float).values})


def asof(df, autre, cle_autre, colonnes):
    if autre is None or autre.empty:
        for c in colonnes:
            df[c] = np.nan
        return df
    a = autre.rename(columns={cle_autre: "_k"}).sort_values("_k")
    a["_k"] = a["_k"].astype("int64")
    return pd.merge_asof(df.sort_values("t_ferme"), a[["_k"] + colonnes], left_on="t_ferme", right_on="_k",
                         direction="backward").drop(columns="_k")


def preparer(df15, unite, externes, base):
    minutes = config.MINUTES[unite]
    df = H.regrouper(df15, minutes).copy()
    df["ema20"], df["ema50"], df["rsi"], df["atr"] = ema(df["c"], 20), ema(df["c"], 50), rsi(df["c"]), atr(df)
    df["vol_moy"] = df["v"].rolling(20).mean()
    df["t_ferme"] = df["t"] + minutes * 60000
    sup1, sup2 = config.UNITES_SUP[unite]
    df = asof(df, regime(df15, sup1).rename(columns={"haussier": "sup1"}), "t_ferme", ["sup1"])
    df = asof(df, regime(df15, sup2).rename(columns={"haussier": "sup2"}), "t_ferme", ["sup2"])
    df = asof(df, externes["btc"].rename(columns={"haussier": "btc_ok"}), "t_ferme", ["btc_ok"])
    df = asof(df, externes["fundings"].get(base), "t_f", ["funding"])
    pos = externes["positions"].get(base)
    df = asof(df, pos, "t_m", ["oi", "ls_foule", "ls_gros"])
    if pos is not None and not pos.empty:          # open interest il y a 3 h, pour mesurer son évolution
        p3 = pos[["t_m", "oi"]].rename(columns={"oi": "oi_3h"}).copy()
        p3["t_m"] = p3["t_m"] + 3 * 3600 * 1000
        df = asof(df, p3, "t_m", ["oi_3h"])
    else:
        df["oi_3h"] = np.nan
    df = asof(df, externes["fng"], "t_g", ["fng"])
    df = asof(df, externes["stables"], "t_l", ["liq_7j"])
    df = asof(df, externes["macro"], "t_x", ["nasdaq_ok", "dxy_stress"])
    df = asof(df, externes.get("monde"), "t_w", ["spx_ok", "vix_stress"])
    df = asof(df, externes.get("attention"), "t_a", ["attention"])
    return df.sort_values("t").reset_index(drop=True)


# ========================= DÉCISIONS DES BOTS =========================
def _ok(x):
    return x == x                                    # faux si NaN (donnée absente)


def decisions(A, i, par_jour):
    part = A["v_achat"][i] / A["v"][i] if A["v"][i] > 0 else 0.5
    c, e20, e50 = A["c"][i], A["ema20"][i], A["ema50"][i]
    oi, oi3, foule, gros = A["oi"][i], A["oi_3h"][i], A["ls_foule"][i], A["ls_gros"][i]
    liq, nq, dxy = A["liq_7j"][i], A["nasdaq_ok"][i], A["dxy_stress"][i]
    evol_oi = oi / oi3 if _ok(oi) and _ok(oi3) and oi3 > 0 else np.nan
    votes = {
        "TENDANCE": 1.0 if c > e20 > e50 else 0.0,
        "MOMENTUM": 1.0 if (50 <= A["rsi"][i] <= 68 and A["v"][i] > A["vol_moy"][i]) else 0.0,
        "MULTI_UNITES": ((A["sup1"][i] == 1) + (A["sup2"][i] == 1)) / 2,
        "CARNET": 1.0 if part >= 0.55 else (0.5 if part >= 0.50 else 0.0),
        "DERIVES": None if not _ok(evol_oi) else (1.0 if evol_oi >= config.OI_HAUSSE_MIN else 0.5 if evol_oi >= 0.99 else 0.2),
        "LIQUIDITE": None if not _ok(liq) else (1.0 if liq > config.LIQUIDITE_ENTREE_PCT else 0.5),
        "MACRO": None if not (_ok(nq) and _ok(dxy)) else (int(nq == 1) + int(dxy != 1)) / 2,
        "POSITIONNEMENT": None if not (_ok(foule) and _ok(gros)) else
                          (1.0 if gros > foule * 1.05 else 0.5 if gros > foule * 0.95 else 0.2),
        "MARCHES_MONDIAUX": None if not _ok(A["spx_ok"][i]) else (1.0 if A["spx_ok"][i] == 1 else 0.3),
    }
    hausse_4b = (c / A["c"][i - 4] - 1) * 100
    atr_pct = A["atr"][i] / c * 100
    fng = A["fng"][i]
    vetos = {
        "RISK_ATR": not (config.ATR_MIN_PCT <= atr_pct <= config.ATR_MAX_PCT * config.echelle(U)),
        "METEO": A["btc_ok"][i] != 1,
        "ANTI_HYPE": bool((A["vol_moy"][i] > 0 and A["v"][i] > config.HYPE_VOLUME_X * A["vol_moy"][i])
                          or hausse_4b > config.HYPE_HAUSSE_1H_PCT * config.echelle(U)),
        "DERIVES_VETO": bool(_ok(A["funding"][i]) and A["funding"][i] > config.FUNDING_MAX),
        "PEUR_AVIDITE": bool(_ok(fng) and (fng >= config.AVIDITE_FORTE or fng <= config.PEUR_EXTREME)),
        "CALENDRIER": bool(np.any(np.abs(MACRO_MS - A["t_ferme"][i]) <= config.CALENDRIER_MARGE_H * 3600000)),
        "LIQUIDITE_VETO": bool(_ok(liq) and liq < config.LIQUIDITE_SORTIE_PCT),
        "MACRO_VETO": bool(_ok(nq) and _ok(dxy) and nq != 1 and dxy == 1),
        "POSITIONNEMENT_VETO": bool(_ok(foule) and foule > config.POS_FOULE_MAX),
        "MARCHES_MONDIAUX_VETO": bool(A["vix_stress"][i] == 1),
        "ATTENTION_VETO": bool(_ok(A["attention"][i]) and A["attention"][i] > config.ATTENTION_PIC_X),
    }
    return votes, vetos


def candidats(sym, df, unite):
    A = {k: df[k].to_numpy(dtype=float) for k in df.columns}
    par_jour = 1440 // config.MINUTES[unite]
    horizon = int(config.HORIZON_H[unite] * 60 / config.MINUTES[unite])
    res, i, fin = [], max(200, par_jour + 5), len(df) - 2
    while i < fin:
        c = A["c"][i]
        if abs(c / A["ema20"][i] - 1) * 100 > config.ECART_EMA20_MAX_PCT * config.echelle(unite) \
                or (c / A["c"][i - par_jour] - 1) * 100 > config.HAUSSE_24H_MAX_PCT:
            i += 1
            continue
        votes, vetos = decisions(A, i, par_jour)
        entree = A["o"][i + 1] * (1 + config.GLISSEMENT_PCT / 100)
        j = slice(i + 1, i + 1 + horizon + 1)
        bougies = list(zip(A["o"][j], A["h"][j], A["l"][j], A["c"][j]))
        r, pnl, raison, n = simuler_sortie(bougies, entree, A["atr"][i], horizon)
        res.append({"paire": sym, "t": int(A["t"][i + 1]), "t_sortie": int(A["t"][min(i + n, len(df) - 1)]),
                    "r": r, "pnl_pct": pnl, "raison": raison, "votes": votes, "vetos": vetos})
        i += n + 1
    return res


# ================================ NOTATION ================================
def noter(trades):
    notes = {}
    if not trades:
        return notes
    for bot in trades[0]["votes"]:
        oui = [t["r"] for t in trades if t["votes"][bot] is not None and t["votes"][bot] >= 0.5]
        non = [t["r"] for t in trades if t["votes"][bot] is not None and t["votes"][bot] < 0.5]
        if len(oui) >= 5 and len(non) >= 5:
            notes[bot] = {"note": note_sur_10(np.mean(oui) - np.mean(non)), "n": len(oui) + len(non),
                          "E_oui": float(np.mean(oui)), "E_non": float(np.mean(non))}
    for bot in trades[0]["vetos"]:
        bloques = [t["r"] for t in trades if t["vetos"][bot]]
        passes = [t["r"] for t in trades if not t["vetos"][bot]]
        if len(bloques) >= 5 and passes:
            notes[bot] = {"note": note_sur_10(np.mean(passes) - np.mean(bloques)), "n": len(bloques),
                          "E_autorises": float(np.mean(passes)), "E_bloques": float(np.mean(bloques))}
    return notes


def decouper(trades, k):
    if not trades or k < 1:
        return []
    trades = sorted(trades, key=lambda t: t["t"])
    bornes = np.linspace(trades[0]["t"], trades[-1]["t"] + 1, k + 1)
    return [[t for t in trades if bornes[p] <= t["t"] < bornes[p + 1]] for p in range(k)]


def bulletin_stable(periodes):
    """Note par période, puis note retenue : plafonnée à 7,9 si le bot flanche sur une période."""
    par_periode = [noter(p) for p in periodes]
    tout = noter([t for p in periodes for t in p])
    res = {}
    for bot, v in tout.items():
        serie = [round(float(n[bot]["note"]), 1) for n in par_periode if bot in n]
        stable = len(serie) >= 2 and min(serie) >= config.NOTE_COUPURE
        moyenne = float(np.mean(serie)) if serie else v["note"]
        res[bot] = {**{k: round(float(x), 3) for k, x in v.items() if k != "n"}, "n": int(v["n"]),
                    "par_periode": serie, "stable": bool(stable),
                    "note_retenue": round(moyenne if stable else min(moyenne, config.NOTE_FIABLE - 0.1), 1)}
    return res


def poids(bulletin):
    return {b: (1.5 if v["note_retenue"] >= config.NOTE_FIABLE else 0.0 if v["note_retenue"] < config.NOTE_COUPURE else 1.0)
            for b, v in bulletin.items() if v["n"] >= config.ECHANTILLON_MIN and "E_oui" in v}


def selection(trades, w):
    choisis = []
    for t in trades:
        if any(t["vetos"].values()):
            continue
        exprimes = {b: v for b, v in t["votes"].items() if v is not None}
        total = sum(w.get(b, 1.0) for b in exprimes)
        if len(exprimes) >= config.VOTANTS_MIN and total > 0 and \
                sum(w.get(b, 1.0) * v for b, v in exprimes.items()) / total >= config.SEUIL_VOTE:
            choisis.append(t)
    return choisis


def portefeuille(trades):
    """Realized equity at exit time; never finance a trade with a future gain.

    This summary lacks intratrade marks: its drawdown is realized-only.
    """
    import heapq
    capital, pic, pire = 1.0, 1.0, 0.0
    ouvertes, retenus = [], []

    def solder(jusqua):
        nonlocal capital, pic, pire
        while ouvertes and ouvertes[0][0] <= jusqua:
            _, _, pnl = heapq.heappop(ouvertes)
            capital += pnl
            pic = max(pic, capital)
            pire = min(pire, capital / pic - 1)

    for index, t in enumerate(sorted(trades, key=lambda x: x["t"])):
        solder(t["t"])
        if len(ouvertes) >= config.POSITIONS_MAX or capital <= 0:
            continue
        if t["t_sortie"] < t["t"]:
            raise ValueError('sortie antérieure à entrée')
        risque_pct = abs(t["pnl_pct"] / t["r"]) if t["r"] else 1.0
        fraction = min(config.RISQUE_PAR_TRADE_PCT / 100,
                       config.POSITION_MAX_PCT / 100 * risque_pct / 100)
        # Freeze sizing at entry using only already realized capital.
        heapq.heappush(ouvertes, (t["t_sortie"], index, capital * fraction * t["r"]))
        retenus.append(t)
    solder(float('inf'))
    return capital, pire, retenus


def resume(nom, res, jours):
    capital, pire, trades = res
    if not trades:
        return f"{nom} : aucun trade", None
    rs = np.array([t["r"] for t in trades])
    gains, pertes = rs[rs > 0].sum(), -rs[rs < 0].sum()
    e = float(rs.mean())
    return (f"{nom} : {len(trades)} trades ({len(trades) / (jours / 30):.1f}/mois) | gagnants {np.mean(rs > 0):.0%}"
            f" | espérance {e:+.3f} R | profit factor {gains / pertes if pertes else float('inf'):.2f}"
            f" | capital {(capital - 1) * 100:+.1f} % | baisse réalisée (hors pertes latentes) {pire * 100:.1f} %"), e


# ================================== MAIN ==================================
def charger(jours, nb_paires, univers="actuel"):
    ex = ccxt.binance({"enableRateLimit": True})
    ex.load_markets()
    tickers = ex.fetch_tickers()
    paires = [s for s, t in sorted(tickers.items(), key=lambda kv: -(kv[1].get("quoteVolume") or 0))
              if s.endswith("/USDT") and s not in config.EXCLUS and ex.markets.get(s, {}).get("spot")
              and ex.markets[s].get("active")][:nb_paires]
    if univers == "complet":
        # Univers complet : les 5 plus grosses + un tirage au sort (renouvelé chaque semaine) parmi TOUTES
        # les paires ayant existé, y compris celles retirées de Binance après un effondrement.
        import random
        tout = [p for p in H.toutes_les_paires() if p not in paires[:5]]
        semaine = dt.date.today().isocalendar()
        tirage = random.Random(semaine[0] * 100 + semaine[1]).sample(tout, min(len(tout), max(0, nb_paires - 5)))
        paires = paires[:5] + tirage
        print(f"Univers complet : {len(tout) + 5} paires connues, tirage de la semaine : {', '.join(tirage[:8])}...")
    print(f"Téléchargement : {jours} jours, {len(paires)} paires (mis en cache, plus rapide ensuite)...")
    btc15 = H.bougies_15m("BTC/USDT", jours + 30)
    externes = {"btc": regime(btc15, "1h"), "btc15": btc15, "fng": H.peur_avidite(), "stables": H.stablecoins(),
                "macro": H.macro(jours), "monde": H.marches_mondiaux(jours), "attention": H.attention(jours),
                "fundings": {}, "positions": {}}
    for nom in ("fng", "stables", "macro", "monde", "attention"):
        print(f"  {nom} : {'OK' if externes[nom] is not None else 'indisponible (bot noté en direct seulement)'}")
    donnees15 = {}
    for n, sym in enumerate(paires, 1):
        base = sym.split("/")[0]
        df15 = H.bougies_15m(sym, jours)
        if df15 is None or len(df15) < 2000:
            print(f"  [{n}/{len(paires)}] {sym} : historique insuffisant, ignorée")
            continue
        donnees15[sym] = df15
        externes["fundings"][base] = H.fundings(base, jours)
        externes["positions"][base] = H.positions(base, min(jours, config.METRICS_JOURS_MAX))
        q = H.QUALITE.get(sym, {})
        print(f"  [{n}/{len(paires)}] {sym} : {len(df15)} bougies 15 min"
              + (f" ({q['retirees']} aberrantes retirées, {q['trous_plus_1h']} trous)" if q.get("retirees") or q.get("trous_plus_1h") else ""))
    return donnees15, externes


def regime_marche(btc15, debut_ms, fin_ms):
    """Ce que BTC a fait sur une période : variation, plus haut, pire baisse -> hausse / baisse / les deux."""
    if btc15 is None or len(btc15) == 0:
        return None
    x = btc15[(btc15["t"] >= debut_ms) & (btc15["t"] <= fin_ms)]["c"].astype(float).to_numpy()
    if len(x) < 10:
        return None
    pic = np.maximum.accumulate(x)                  # plus haut atteint AVANT chaque instant
    creux = np.minimum.accumulate(x)                # plus bas atteint AVANT chaque instant
    baisse = float((x / pic - 1).min() * 100)       # pire chute depuis un sommet
    hausse = float((x / creux - 1).max() * 100)     # plus forte montée depuis un creux
    regimes = ([f"hausse {hausse:+.0f} %"] if hausse >= 20 else []) + ([f"baisse {baisse:.0f} %"] if baisse <= -20 else [])
    return {"variation": float((x[-1] / x[0] - 1) * 100), "pire_baisse": baisse, "plus_forte_hausse": hausse,
            "texte": " et ".join(regimes) if regimes else "marché sans grande tendance",
            "deux_regimes": hausse >= 20 and baisse <= -20}


def walk_forward(periodes):
    """Porte 3 : pour chaque période k >= 1, l'équipe apprend sur les périodes AVANT k (trades soldés avant),
    puis est jugée sur la période k. Renvoie [(début ms, fin ms, R des trades choisis)]."""
    fenetres = []
    for k in range(1, len(periodes)):
        test = periodes[k]
        if not test:
            continue
        debut = min(t["t"] for t in test)
        app = [t for p in periodes[:k] for t in p if t["t_sortie"] < debut]
        if len(app) < 50:
            continue
        w = poids(bulletin_stable(decouper(app, max(1, k))))
        rs = [t["r"] for t in selection(test, w)]
        fenetres.append((debut, max(t["t"] for t in test), rs))
    return fenetres


def analyser(unite, donnees15, externes, jours):
    global U
    U = unite
    tous = []
    for sym, df15 in donnees15.items():
        tous += candidats(sym, preparer(df15, unite, externes, sym.split("/")[0]), unite)
    if len(tous) < 200:
        return None
    periodes = decouper(tous, config.BACKTEST_PERIODES)
    bulletin = bulletin_stable(periodes)
    test = periodes[-1]
    if not test:
        return None
    debut_test = min(t["t"] for t in test)
    apprentissage = [t for p in periodes[:-1] for t in p if t["t_sortie"] < debut_test]
    w_app = poids(bulletin_stable(decouper(apprentissage, config.BACKTEST_PERIODES - 1)))
    jours_test = jours / config.BACKTEST_PERIODES
    ligne_sans, _ = resume("Sans filtre", portefeuille(tous), jours)
    ligne_hors, e_hors = resume("ÉQUIPE HORS ÉCHANTILLON (dernière période, jamais vue)",
                                portefeuille(selection(test, w_app)), jours_test)
    ligne_dans, _ = resume("Équipe sur tout l'historique (optimiste)", portefeuille(selection(tous, poids(bulletin))), jours)
    # Porte 3 : walk-forward sur toutes les périodes (et plus seulement la dernière)
    fen = walk_forward(periodes)
    rs_wf = np.array([r for *_, rs in fen for r in rs], dtype=float)
    e_fen = [float(np.mean(rs)) if len(rs) >= 5 else None for *_, rs in fen]
    btc15 = externes.get("btc15")
    lignes_wf = []
    for (d, f, rs), e in zip(fen, e_fen):
        reg = regime_marche(btc15, d, f)
        lignes_wf.append(f"  fenêtre {dt.datetime.fromtimestamp(d / 1000, dt.timezone.utc):%Y-%m-%d} → "
                         f"{dt.datetime.fromtimestamp(f / 1000, dt.timezone.utc):%Y-%m-%d} : {len(rs)} trades, "
                         f"espérance {'n/a' if e is None else f'{e:+.3f} R'}"
                         + (f" | BTC {reg['variation']:+.0f} % ({reg['texte']})" if reg else ""))
    tout_reg = regime_marche(btc15, min(t["t"] for t in tous), max(t["t"] for t in tous))
    return {"bulletin": bulletin, "lignes": [ligne_sans, ligne_dans, ligne_hors], "e_hors": e_hors, "n": len(tous),
            "rs_wf": rs_wf, "e_fenetres": e_fen, "lignes_wf": lignes_wf, "regime": tout_reg}


def portes(r, variance_sharpes=0.0, nb_essais=1):
    """Porte 2 (Sharpe dégonflé) + porte 3 (walk-forward). La porte 1 (aucune fuite) est vérifiée par les tests."""
    import surapprentissage as SA
    rs = r["rs_wf"]
    valides = [e for e in r["e_fenetres"] if e is not None]
    e_wf = float(rs.mean()) if len(rs) else None
    dsr = SA.sharpe_degonfle(rs, variance_sharpes, nb_essais) if len(rs) >= 10 else 0.0
    wf_ok = e_wf is not None and e_wf > 0.05 and len(valides) >= 2 and sum(e > 0 for e in valides) >= len(valides) - 1
    return {"e_wf": e_wf, "dsr": dsr, "wf_ok": wf_ok, "dsr_ok": dsr >= config.BACKTEST_DSR_MIN,
            "ok": wf_ok and dsr >= config.BACKTEST_DSR_MIN}


def rapport(unite, r, jours):
    L = [f"=== UNITÉ {unite} | {jours} jours | {r['n']} trades simulés | frais {config.FRAIS_ALLER_RETOUR_PCT} % + glissement ===",
         "BULLETIN (/10)  5 = hasard | 8 = +0,3 R par trade | note retenue plafonnée à 7,9 si instable",
         f"{'bot':<20}{'retenue':>8}  {'par période':<26}{'cas':>7}  état"]
    for bot, v in sorted(r["bulletin"].items(), key=lambda kv: -kv[1]["note_retenue"]):
        if v["n"] < config.ECHANTILLON_MIN:
            etat = "échantillon trop petit"
        elif v["note_retenue"] >= config.NOTE_FIABLE:
            etat = "FIABLE ✅"
        elif v["note_retenue"] >= config.NOTE_COUPURE:
            etat = "en observation" + ("" if v["stable"] else " (instable)")
        else:
            etat = "coupé ⛔" if "E_oui" in v else "veto à revoir ⚠️"
        L.append(f"{bot:<20}{v['note_retenue']:>8}  {str(v['par_periode']):<26}{v['n']:>7}  {etat}")
    L += [""] + r["lignes"]
    reg = r.get("regime")
    if reg:
        L.append(f"Régimes de marché dans l'échantillon (BTC) : {reg['texte']} (variation {reg['variation']:+.0f} %)"
                 + ("" if reg["deux_regimes"] else " ⚠️ PAS de hausse ET de baisse : conclusion fragile"))
    L += ["WALK-FORWARD (apprend sur le passé, jugé sur la période suivante, fenêtre après fenêtre) :"] + r["lignes_wf"]
    g = r.get("portes") or portes(r)
    e_txt = "n/a" if g["e_wf"] is None else f"{g['e_wf']:+.3f} R"
    L.append(f"PORTES : walk-forward {'✅' if g['wf_ok'] else '❌'} (espérance {e_txt}) | "
             f"Sharpe dégonflé {g['dsr']:.0%} {'✅' if g['dsr_ok'] else '❌'} (exigé {config.BACKTEST_DSR_MIN:.0%}) | "
             "aucune fuite de données : vérifié par les tests (bots verifier)")
    L.append("VERDICT : " + ("les portes sont franchies → démo prolongée autorisée, jamais de réel sans ta décision."
                             if g["ok"] else "portes NON franchies → PAS de réel avec cette unité."))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jours", type=int, default=730)
    ap.add_argument("--paires", type=int, default=25)
    ap.add_argument("--unite", default=config.UNITE_BOUGIE, choices=list(config.MINUTES))
    ap.add_argument("--comparer", action="store_true")
    ap.add_argument("--univers", default=config.BACKTEST_UNIVERS, choices=["complet", "actuel"],
                    help="complet = paires disparues incluses (sans biais du survivant)")
    a = ap.parse_args()
    donnees15, externes = charger(a.jours, a.paires, a.univers)
    unites = list(config.MINUTES) if a.comparer else [a.unite]
    synthese = []
    for u in unites:
        print(f"\nAnalyse en {u}...")
        r = analyser(u, donnees15, externes, a.jours)
        if r is None:
            print(f"{u} : pas assez de trades pour conclure.")
            continue
        texte = rapport(u, r, a.jours)
        print(texte)
        with open(f"backtest_rapport_{u}.txt", "w", encoding="utf-8") as f:
            f.write(texte)
        with open(f"notes_backtest_{u}.json", "w", encoding="utf-8") as f:
            json.dump(r["bulletin"], f, indent=2, ensure_ascii=False)
        synthese.append((u, r))
    if len(synthese) > 1:
        # Porte 2 : on a comparé plusieurs unités -> le Sharpe exigé monte avec le nombre d'essais
        import surapprentissage as SA
        sharpes = [SA.sharpe(r["rs_wf"]) for _, r in synthese]
        var = SA.variance_robuste([s for s in sharpes if s is not None])
        print("\n=== COMPARAISON HORS ÉCHANTILLON ===")
        valides = []
        for u, r in synthese:
            g = portes(r, var, len(synthese))
            print(f"  {u:>4} : walk-forward {'n/a' if g['e_wf'] is None else round(g['e_wf'], 3)} R par trade | "
                  f"Sharpe dégonflé ({len(synthese)} essais) {g['dsr']:.0%} | {'portes franchies' if g['ok'] else 'refusée'}")
            if g["ok"]:
                valides.append((u, g["e_wf"]))
        if valides:
            meilleure = max(valides, key=lambda x: x[1])[0]
            print(f"→ Recommandation : mettre UNITE_BOUGIE = \"{meilleure}\" dans config.py")
        else:
            print("→ Aucune unité n'a d'avantage prouvé : on ajuste les réglages, pas de réel.")
    print("\nFichiers : backtest_rapport_<unité>.txt, notes_backtest_<unité>.json (lu par l'AUDITEUR)")


U = config.UNITE_BOUGIE
if __name__ == "__main__":
    main()
