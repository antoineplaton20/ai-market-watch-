"""TERMINAL DE L'OR — un écran par code court, comme sur un terminal financier professionnel, dans Termius.

  or go              écran de lancement EN DIRECT (rafraîchi toutes les 2 s ; Ctrl+C pour quitter)
  or gp [15m|1h|4h|1d]   graphique du cours (1 h par défaut)
  or gip             intraday minute par minute
  or eco             agenda des annonces américaines à fort impact
  or top             actualités de l'or
  or wei             marchés liés : dernier, variation 1 j et 5 j, corrélation 60 j
  or corr            corrélations avec l'or sur 60 jours, de la plus forte à la plus faible
  or rv              valeur relative or / argent sur 10 ans
  or niv             niveaux clés : échelle des résistances et supports
  or cot             positions des gros spéculateurs (CFTC)
  or des             fiche de l'instrument : courtier, contrat, écart mesuré, séances
  or risk            compte, positions, permis de trader, réglages
  or codes           liste des codes

Tout est lu dans la base de l'armée (aucun appel réseau, sauf la fiche MT5 qui interroge le pont local) :
l'écran s'affiche instantanément, même si internet est lent.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import sys
import textwrap
import time

import numpy as np

from . import base, config, donnees, flux, indicateurs as I, veille

# ============================================================================ couleurs : ambre sur fond noir
AMBRE, TITRE, VERT, ROUGE, GRIS, BLANC = "38;5;214", "1;30;48;5;214", "38;5;77", "38;5;203", "38;5;245", "1;97"
_COULEUR = None                                   # None : automatique (écran Termius oui, fichier ou Telegram non)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _couleur():
    if _COULEUR is not None:
        return _COULEUR
    return os.getenv("NO_COLOR") is None and sys.stdout.isatty()


def _c(code, texte):
    return f"\033[{code}m{texte}\033[0m" if _couleur() else str(texte)


def visible(texte):
    return len(_ANSI.sub("", texte))


def largeur():
    return max(36, min(120, shutil.get_terminal_size((80, 24)).columns))


def _coupe(texte, w):
    return texte if len(texte) <= w else texte[:max(1, w - 1)] + "…"


def _n(x, d=2):
    return f"{x:,.{d}f}".replace(",", " ")


def bandeau(titre, w, droite=""):
    if len(titre) + len(droite) + 4 > w:                       # écran étroit : le titre d'abord
        droite = ""
    return _c(TITRE, (" " + _coupe(titre, w - len(droite) - 3)).ljust(w - len(droite) - 1) + droite + " ")


def section(nom, w):
    return _c(AMBRE, ("─ " + nom + " ").ljust(w, "─"))


def _var(v, fmt="{:+.2f}", suffixe=" %"):
    if v is None or not np.isfinite(v):
        return _c(GRIS, "—")
    return _c(VERT if v > 0 else ROUGE if v < 0 else GRIS, fmt.format(v) + suffixe)


def _fleche(sens):
    return {1: _c(VERT, "▲"), -1: _c(ROUGE, "▼")}.get(sens, _c(GRIS, "■"))


def _a_la_ligne(elements, w, prefixe=""):
    """Assemble des morceaux (déjà colorés) séparés par « · » sans dépasser la largeur visible."""
    lignes, courante = [], prefixe
    for e in elements:
        if visible(e) > w - len(prefixe):                     # morceau trop long à lui seul : coupé, sans couleur
            e = _coupe(_ANSI.sub("", e), w - len(prefixe))
        sep = "" if visible(courante) <= len(prefixe) else " · "
        if visible(courante) + len(sep) + visible(e) > w and visible(courante) > len(prefixe):
            lignes.append(courante)
            courante, sep = " " * len(prefixe), ""
        courante += sep + e
    if visible(courante.strip()):
        lignes.append(courante)
    return lignes


def _heure(ts, fmt="%a %d %H:%M"):
    return veille.heure_paris(ts, fmt)


# ============================================================================ marché : séances et ouverture
def _zone(nom):
    from zoneinfo import ZoneInfo
    return ZoneInfo(nom)


SEANCES = (("Asie", "Asia/Tokyo", 9, 18), ("Londres", "Europe/London", 8, 17), ("New York", "America/New_York", 8, 17))


def seances(maintenant=None):
    m = maintenant or time.time()
    out = []
    for nom, zone, h1, h2 in SEANCES:
        t = dt.datetime.fromtimestamp(m, _zone(zone))
        out.append((nom, t.weekday() < 5 and h1 <= t.hour < h2))
    return out


def marche_ouvert(maintenant=None):
    """Or au comptant / CFD : du dimanche 18 h au vendredi 17 h (heure de New York), pause quotidienne 17 h - 18 h."""
    t = dt.datetime.fromtimestamp(maintenant or time.time(), _zone("America/New_York"))
    if t.weekday() == 5 or (t.weekday() == 6 and t.hour < 18) or (t.weekday() == 4 and t.hour >= 17):
        return False, "FERMÉ (week-end)"
    if t.hour == 17:
        return False, "PAUSE quotidienne"
    return True, "OUVERT"


# ============================================================================ données
DUREE_TF = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
NOMS_SOURCES = {"MT5": "courtier MT5", "XAUUSDT": "Binance XAUUSDT", "PAXGUSDT": "Binance PAXG"}


def serie(tf, n, maintenant=None):
    """Bougies les plus fiables disponibles : celles du courtier MT5 si elles sont à jour, sinon Binance."""
    m = maintenant or time.time()
    for s in ("MT5", config.SOURCE_PRINCIPALE, "PAXGUSDT"):
        if s == "MT5" and tf == "1m":
            continue
        b = donnees.charger(s, tf, limite=n)
        if len(b["c"]) >= min(n, 30) and m - b["ts"][-1] / 1000 < 3 * DUREE_TF[tf] + 3 * 86400:
            return s, b
    return None, None


def cours(maintenant=None):
    m = maintenant or time.time()
    d = flux.prix_direct()
    if not d:
        return None
    out = {"prix": d["prix"], "source": d.get("source") or d["cle"], "retard_ms": d.get("retard_ms", 0)}
    t5 = base.lire("direct:MT5")
    if t5 and m - t5.get("ts", 0) < 900 and t5.get("bid"):
        out["bid"], out["ask"] = t5["bid"], t5["ask"]
    minuit = int(m // 86400 * 86400 * 1000)
    for s in (config.SOURCE_PRINCIPALE, "PAXGUSDT"):
        b = donnees.charger(s, "1m", depuis_ms=minuit)
        if len(b["o"]):
            out["ouverture"] = float(b["o"][0])
            out["var"] = out["prix"] - out["ouverture"]
            out["var_pct"] = out["var"] / out["ouverture"] * 100
            out["haut"], out["bas"] = float(b["h"].max()), float(b["l"].min())
            break
    eur = _marche("EURUSD=X")
    if eur and eur.get("dernier"):
        out["prix_eur"] = out["prix"] / eur["dernier"]
    return out


def _marche(ticker):
    for x in (base.lire("marches") or {}).get("marches", []):
        if x["ticker"] == ticker:
            return x
    return None


# ============================================================================ graphique en caractères
BLOCS = " ▁▂▃▄▅▆▇█"


def graphique(valeurs, w, hauteur=8, decimales=2):
    """Graphique en aires : une colonne par période, 8 nuances par ligne, échelle de prix à droite."""
    v = np.asarray(valeurs, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < 2:
        return [_c(GRIS, "(pas encore assez de données pour tracer)")]
    bas, haut = float(v.min()), float(v.max())                         # extrêmes de toute la période
    largeur_etiq = max(len(_n(haut, decimales)), len(_n(bas, decimales))) + 1
    wg = max(10, w - largeur_etiq)
    if len(v) > wg:
        v = np.array([p[-1] for p in np.array_split(v, wg)])           # dernière valeur de chaque tranche
    if haut - bas < 1e-12:
        haut = bas + 1.0
    niv = np.round((v - bas) / (haut - bas) * (hauteur * 8 - 1)).astype(int) + 1
    lignes = []
    for r in range(hauteur - 1, -1, -1):
        rang = "".join(BLOCS[min(8, max(0, k - r * 8))] for k in niv)
        etiq = _n(haut, decimales) if r == hauteur - 1 else _n(bas, decimales) if r == 0 else \
            _n((haut + bas) / 2, decimales) if r == hauteur // 2 else ""
        lignes.append(_c(AMBRE, rang.ljust(wg)) + " " + _c(GRIS, etiq))
    return lignes


def axe_temps(ts_debut_ms, ts_fin_ms, w, fmt="%d/%m %H:%M"):
    g, d = _heure(ts_debut_ms / 1000, fmt), _heure(ts_fin_ms / 1000, fmt)
    return _c(GRIS, g + " " * max(1, w - len(g) - len(d)) + d)


# ============================================================================ écrans
CODES = [("go", "écran de lancement en direct"), ("gp", "graphique : or gp 15m | 1h | 4h | 1d"),
         ("gip", "intraday minute par minute"), ("eco", "agenda des annonces"), ("top", "actualités"),
         ("wei", "marchés liés"), ("corr", "corrélations avec l'or"), ("rv", "valeur relative or / argent"),
         ("niv", "niveaux clés"), ("cot", "positions des gros spéculateurs"), ("des", "fiche de l'instrument"),
         ("risk", "compte, positions, permis"), ("codes", "cette liste")]


def _pied(w):
    return _c(GRIS, _coupe("CODES " + " ".join(c.upper() for c, _ in CODES[:-1]), w))


def ecran_go(w=None, maintenant=None):
    w, m = w or largeur(), maintenant or time.time()
    L = [bandeau("TERMINAL OR  XAU/USD", w, _heure(m, "%a %d %H:%M:%S" if w >= 50 else "%H:%M:%S"))]
    c = cours(m)
    if c:
        sens = 0 if "var" not in c else (1 if c["var"] > 0 else -1 if c["var"] < 0 else 0)
        ligne = _c(BLANC, _n(c["prix"]) + " $") + " " + _fleche(sens)
        if "var" in c:
            ligne += " " + _var(c["var"], suffixe=" $") + " (" + _var(c["var_pct"]) + ")"
        L += _a_la_ligne([ligne] + ([_c(GRIS, f"≈ {_n(c['prix_eur'], 0)} €/once")] if "prix_eur" in c else []), w)
        details = []
        if "bid" in c:
            details += [f"MT5 {_n(c['bid'])} / {_n(c['ask'])}", f"écart {c['ask'] - c['bid']:.2f} $"]
        if "haut" in c:
            details.append(f"jour haut {_n(c['haut'])} bas {_n(c['bas'])}")
        details += [_coupe(c["source"], w), f"retard {c['retard_ms'] / 1000:.1f} s"]
        L += [_c(GRIS, x) for x in _a_la_ligne(details, w)]
    else:
        L.append(_c(ROUGE, "Aucun cours frais : les vigies se reconnectent."))
    ouvert, etat = marche_ouvert(m)
    L += _a_la_ligne([_c(VERT if ouvert else ROUGE, f"Marché {etat}")] + [
        (_c(VERT, "●") if o else _c(GRIS, "○")) + " " + nom for nom, o in seances(m)], w)
    src, b = serie("15m", 2 * w, m)
    if b is not None:
        L.append(section(f"24 H · 15 MIN · {NOMS_SOURCES.get(src, src)}", w))
        L += graphique(b["c"][-96:], w, 5)
    niv = base.lire("niveaux")
    if niv and c:
        dessus = [n for n in niv["niveaux"] if n["prix"] > c["prix"]][:2]
        dessous = [n for n in niv["niveaux"] if n["prix"] < c["prix"]][-2:][::-1]
        morceaux = [_c(ROUGE, "R ") + f"{_n(n['prix'], 1)} {(n['prix'] / c['prix'] - 1) * 100:+.2f} % {n['nom']}"
                    for n in dessus] + [_c(VERT, "S ") + f"{_n(n['prix'], 1)} "
                                        f"{(n['prix'] / c['prix'] - 1) * 100:+.2f} % {n['nom']}" for n in dessous]
        L.append(section("NIVEAUX", w))
        L += _a_la_ligne(morceaux, w)
    t = base.lire("tendances")
    if t:
        L.append(section("TENDANCES", w))
        u = t["unites"]
        morceaux = [f"{tf} {_fleche(v['sens'])}" for tf, v in u.items() if v]
        if u.get("1h"):
            morceaux.append(f"RSI 1 h {u['1h']['rsi']:.0f}")
        morceaux.append(f"alignement {t['alignement']:+d}/4")
        L += _a_la_ligne(morceaux, w)
    mk = base.lire("marches")
    if mk:
        L.append(section("MARCHÉS", w))
        morceaux = []
        for tk, nom, d in (("DX-Y.NYB", "DXY", 2), ("^TNX", "US10A", 2), ("SI=F", "ARGENT", 2), ("^VIX", "VIX", 1),
                           ("^GSPC", "S&P", 0), ("EURUSD=X", "EUR/USD", 4), ("BTC-USD", "BTC", 0)):
            x = _marche(tk)
            if x:
                morceaux.append(f"{nom} {_n(x['dernier'], d)} {_var(x['var_1j'], '{:+.1f}')}")
        if mk.get("ratio_or_argent"):
            morceaux.append(f"OR/ARG {mk['ratio_or_argent']:.1f}")
        tr = base.lire("tresor") or {}
        if tr.get("reel_10a") is not None:
            morceaux.append(f"TAUX RÉEL 10A {tr['reel_10a']:.2f} " + _var(tr.get("reel_10a_5j"), "{:+.2f}", " pt/5j"))
        L += _a_la_ligne(morceaux, w)
    ms = base.lire("microstructure")
    if ms:
        morceaux = []
        if "financement_pct" in ms:
            morceaux.append(f"financement {ms['financement_pct']:+.4f} %")
        if "acheteurs_pct" in ms:
            morceaux.append(f"acheteurs {ms['acheteurs_pct']:.0f} %")
        if "desequilibre_pct" in ms:
            morceaux.append(f"carnet {_var(ms['desequilibre_pct'], '{:+.0f}')}")
        if "positions_ouvertes_1h_pct" in ms:
            morceaux.append(f"pos. ouvertes 1 h {_var(ms['positions_ouvertes_1h_pct'], '{:+.1f}')}")
        if morceaux:
            L.append(section("FLUX BINANCE", w))
            L += _a_la_ligne(morceaux, w)
    cal = base.lire("calendrier")
    if cal:
        groupes = []                                            # annonces à la même heure : un seul horaire
        for e in (e for e in cal["evenements"] if e["ts"] > m - 900):
            if groupes and groupes[-1][0] == e["ts"]:
                groupes[-1][1].append(e)
            elif len(groupes) < 3:
                groupes.append((e["ts"], [e]))
        a_venir = groupes
        L.append(section("AGENDA (Paris)", w))
        for ts, evts in groupes:
            reste = ts - m
            quand = "EN COURS" if reste <= 0 else f"dans {int(reste // 3600)} h {int(reste % 3600 // 60):02d}"
            L += _a_la_ligne([_c(AMBRE, _heure(ts, "%a %H:%M")), _c(ROUGE if 0 < reste <= 1800 else GRIS, quand)]
                             + [_coupe(f"{e['titre']} (prév. {e['prevision'] or '?'})", w) for e in evts], w)
        if not a_venir:
            L.append(_c(GRIS, "aucune annonce à fort impact d'ici la fin de semaine"))
    ac = base.lire("actualites")
    if ac and ac.get("titres"):
        L.append(section("ACTUALITÉS", w))
        L += [_coupe("• " + i["titre"], w) for i in ac["titres"][:3]]
    L.append(section("ARMÉE", w))
    L += _a_la_ligne(_etat_armee(), w)
    L.append(_pied(w))
    return "\n".join(L)


def _etat_armee():
    morceaux = []
    permis = base.lire("mt5:permis")
    if permis:
        from .executant import permis_exige
        morceaux.append("permis " + " ".join(f"{tf} {'✔' if (permis.get(tf) or {}).get('ok') else '✖'}"
                                             for tf in ("1h", "4h", "1d"))
                        + ("" if permis_exige() else _c(AMBRE, " (non exigés : bots actifs)")))
    e = base.lire("mt5:etat") or {}
    compte = e.get("compte")
    if config.MT5_ACTIF:
        if e.get("connecte") and compte:
            morceaux.append(f"MT5 {'démo' if compte.get('demo') else 'RÉEL'} {_n(compte['equity'])} {compte['currency']}")
        else:
            morceaux.append(_c(ROUGE, "MT5 non connecté"))
    if base.lire("mt5:agressif"):
        morceaux.append(_c(ROUGE, "MODE AGRESSIF"))
    morceaux.append(f"{len(base.lire('mt5:suivi', {}) or {})} position(s)")
    if base.lire("pause") or base.lire("mt5:pause"):
        morceaux.append(_c(ROUGE, "EN PAUSE"))
    ch = base.lire("chef")
    if ch:
        bots = ch.get("bots", [])
        sains = sum(1 for b in bots if not b.get("echecs_suite"))
        age = time.time() - ch.get("ts", 0)
        morceaux.append(_c(VERT if sains == len(bots) and age < 60 else ROUGE, f"bots {sains}/{len(bots)} sains"))
    return morceaux


def ecran_gp(tf="1h", w=None, maintenant=None):
    tf = {"1j": "1d", "15": "15m", "60": "1h", "4": "4h", "d": "1d"}.get(tf, tf)
    if tf not in DUREE_TF or tf == "1m":
        tf = "1h"
    w = w or largeur()
    src, b = serie(tf, max(60, w - 10), maintenant)
    L = [bandeau(f"GP  XAU/USD  {tf}", w, NOMS_SOURCES.get(src, src or "?"))]
    if b is None:
        return "\n".join(L + [_c(GRIS, "Pas encore de bougies pour cette unité.")])
    L += graphique(b["c"], w, 12)
    L.append(axe_temps(b["ts"][0], b["ts"][-1], w))
    atr, rsi = I.atr(b["h"], b["l"], b["c"], 14)[-1], I.rsi(b["c"], 14)[-1]
    var = (b["c"][-1] / b["c"][0] - 1) * 100
    L += _a_la_ligne([f"dernier {_n(b['c'][-1])}", f"haut {_n(b['h'].max())}", f"bas {_n(b['l'].min())}",
                      f"sur la période {_var(var)}", f"ATR 14 {atr:.2f} $", f"RSI 14 {rsi:.0f}",
                      f"{len(b['c'])} bougies"], w)
    L.append(_pied(w))
    return "\n".join(L)


def ecran_gip(w=None, maintenant=None):
    w = w or largeur()
    _, b = serie("1m", min(480, 3 * w), maintenant)
    L = [bandeau("GIP  XAU/USD  intraday 1 min", w, _heure(maintenant or time.time(), "%H:%M"))]
    if b is None:
        return "\n".join(L + [_c(GRIS, "Pas de bougies minute récentes.")])
    L += graphique(b["c"], w, 12)
    L.append(axe_temps(b["ts"][0], b["ts"][-1], w, "%H:%M"))
    r = np.diff(np.log(b["c"]))
    L += _a_la_ligne([f"dernier {_n(b['c'][-1])}", f"haut {_n(b['h'].max())}", f"bas {_n(b['l'].min())}",
                      f"variation {_var((b['c'][-1] / b['c'][0] - 1) * 100)}",
                      f"volatilité minute {np.std(r) * 100:.3f} %" if len(r) > 2 else "volatilité —"], w)
    L.append(_pied(w))
    return "\n".join(L)


def ecran_eco(w=None, maintenant=None):
    w, m = w or largeur(), maintenant or time.time()
    L = [bandeau("ECO  annonces américaines à fort impact", w, "heure de Paris")]
    cal = base.lire("calendrier")
    if not cal:
        return "\n".join(L + [_c(GRIS, "Agenda pas encore chargé.")])
    for e in cal["evenements"]:
        reste = e["ts"] - m
        passe = reste < -3600
        quand = "passé" if reste < 0 else f"dans {int(reste // 86400)} j {int(reste % 86400 // 3600)} h" if reste > 86400 \
            else f"dans {int(reste // 3600)} h {int(reste % 3600 // 60):02d}"
        tete = f"{_heure(e['ts'], '%a %d %H:%M')}  {quand}"
        corps = f"   {e['titre']} · prév. {e['prevision'] or '?'} · préc. {e['precedent'] or '?'}"
        alerte = 0 <= reste <= 1800
        L.append(_c(GRIS if passe else ROUGE if alerte else BLANC, _coupe(tete, w)))
        L.append(_c(GRIS, _coupe(corps, w)) if passe else _coupe(corps, w))
    L.append(_c(GRIS, _coupe("Aucun nouvel ordre MT5 de 15 min avant à 15 min après chaque annonce.", w)))
    L.append(_pied(w))
    return "\n".join(L)


def ecran_top(w=None, n=12):
    w = w or largeur()
    L = [bandeau("TOP  actualités de l'or", w, "Google Actualités")]
    a = base.lire("actualites")
    if not a:
        return "\n".join(L + [_c(GRIS, "Actualités pas encore relevées.")])
    for k, i in enumerate(a["titres"][:n], 1):
        tag = ("[" + ", ".join(i["themes"]) + "] ") if i["themes"] else ""
        lignes = textwrap.wrap(tag + i["titre"], w - 4) or [""]
        L.append(_c(AMBRE, f"{k:>2} ") + (_c(ROUGE, tag) + lignes[0][len(tag):] if tag and lignes[0].startswith(tag)
                                           else lignes[0]))
        L += ["   " + x for x in lignes[1:]]
    L.append(_pied(w))
    return "\n".join(L)


def ecran_wei(w=None):
    w = w or largeur()
    L = [bandeau("WEI  marchés liés à l'or", w, "Yahoo, différé")]
    mk = base.lire("marches")
    if not mk:
        return "\n".join(L + [_c(GRIS, "Marchés liés pas encore relevés.")])
    if w < 56:                                                # téléphone : deux lignes par marché
        for x in mk["marches"]:
            L.append(_c(AMBRE, _coupe(x["nom"], w)))
            corr = "—" if x["correlation_60j"] is None else f"{x['correlation_60j']:+.2f}"
            L += _a_la_ligne([_n(x["dernier"]), "1 j " + _var(x["var_1j"]), "5 j " + _var(x["var_5j"]),
                              f"corr {corr}"], w, "  ")
        L.append(_c(GRIS, _coupe(f"Contexte pour l'or : {mk['contexte']:+.2f} sur ±1", w)))
        L += _tresor(w)
        L.append(_pied(w))
        return "\n".join(L)
    wn = max(10, w - 38)
    L.append(_c(GRIS, "MARCHÉ".ljust(wn) + "   DERNIER    1 J %    5 J %  CORR"))
    for x in mk["marches"]:
        corr = "  —  " if x["correlation_60j"] is None else f"{x['correlation_60j']:+.2f}"
        L.append(_coupe(x["nom"], wn).ljust(wn) + f"{_n(x['dernier'], 2):>10} " + " " * max(0, 8 - len(
            f"{x['var_1j']:+.2f}")) + _var(x["var_1j"], suffixe="") + " " + " " * max(0, 8 - len(
                f"{x['var_5j']:+.2f}")) + _var(x["var_5j"], suffixe="") + f"  {corr}")
    L.append(_c(GRIS, _coupe(f"Contexte pour l'or (dollar, taux, argent…) : {mk['contexte']:+.2f} sur ±1", w)))
    L += _tresor(w)
    L.append(_pied(w))
    return "\n".join(L)


def _tresor(w):
    from . import tresor
    t = base.lire("tresor") or {}
    if t.get("reel_10a") is None:
        return []
    L = [section(f"TRÉSOR US · officiel · {t.get('date')}", w)]
    for nom, lib in tresor.NOMS.items():
        if t.get(nom) is not None:
            L += _a_la_ligne([f"{lib} {t[nom]:.2f} %", "5 séances " + _var(t.get(f"{nom}_5j"), "{:+.2f}", " pt")], w)
    L.append(_c(GRIS, _coupe("Taux réel en hausse : en général défavorable à l'or (il ne rapporte rien).", w)))
    return L


def ecran_corr(w=None):
    w = w or largeur()
    L = [bandeau("CORR  corrélation avec l'or, 60 jours", w)]
    mk = base.lire("marches")
    lignes = [x for x in (mk or {}).get("marches", []) if x["correlation_60j"] is not None]
    if not lignes:
        return "\n".join(L + [_c(GRIS, "Pas encore assez de données.")])
    wn, wb = max(10, w // 3), max(5, w - max(10, w // 3) - 8)
    for x in sorted(lignes, key=lambda x: -abs(x["correlation_60j"])):
        k = x["correlation_60j"]
        L.append(_coupe(x["nom"], wn).ljust(wn) + " " + _var(k, "{:+.2f}", "") + " " +
                 _c(VERT if k > 0 else ROUGE, "█" * int(round(abs(k) * wb))))
    L.append(_c(GRIS, _coupe("+1 : bougent ensemble · −1 : en sens inverse · recalculée chaque jour", w)))
    L.append(_pied(w))
    return "\n".join(L)


def ecran_rv(w=None):
    from . import apprentissage
    w = w or largeur()
    L = [bandeau("RV  valeur relative or / argent", w, "onces d'argent pour 1 once d'or")]
    t1, v1 = apprentissage.serie("yahoo:or_comex:1d")
    t2, v2 = apprentissage.serie("yahoo:argent:1d")
    commun, i1, i2 = np.intersect1d(t1, t2, return_indices=True) if len(t1) and len(t2) else ([], [], [])
    mk = base.lire("marches") or {}
    actuel = mk.get("ratio_or_argent")
    if len(commun) < 250:
        return "\n".join(L + [f"Ratio actuel : {actuel:.1f}" if actuel else "Ratio pas encore disponible.",
                              *[_c(GRIS, x) for x in textwrap.wrap(
                                  "Historique de 10 ans en cours de rattrapage (une fois par jour).", w)]])
    r = v1[i1] / v2[i2]
    actuel = actuel or float(r[-1])
    rang = float((r < actuel).mean() * 100)
    z = (actuel - r.mean()) / r.std()
    L += graphique(r[-min(len(r), 2 * w):], w, 8, 1)
    L.append(axe_temps(commun[-min(len(r), 2 * w)] * 1000, commun[-1] * 1000, w, "%m/%Y"))
    L += _a_la_ligne([f"actuel {actuel:.1f}", f"moyenne {r.mean():.1f}", f"min {r.min():.1f}", f"max {r.max():.1f}",
                      f"rang {rang:.0f} % de l'historique", f"écart à la moyenne {z:+.1f} σ"], w)
    lecture = ("l'argent est historiquement BON MARCHÉ face à l'or" if rang >= 80 else
               "l'argent est historiquement CHER face à l'or" if rang <= 20 else "zone habituelle")
    L.append(_c(AMBRE, _coupe(f"Lecture : {lecture}. Ce n'est pas un signal : rien ne dit quand le ratio revient.", w)))
    L.append(_pied(w))
    return "\n".join(L)


def ecran_niv(w=None):
    w = w or largeur()
    L = [bandeau("NIV  niveaux clés", w, "1 j et 4 h")]
    niv, d = base.lire("niveaux"), flux.prix_direct()
    if not niv or not d:
        return "\n".join(L + [_c(GRIS, "Niveaux pas encore calculés.")])
    prix = d["prix"]
    dessus = [n for n in niv["niveaux"] if n["prix"] > prix][:5][::-1]
    dessous = [n for n in niv["niveaux"] if n["prix"] < prix][-5:][::-1]
    def ligne(n):
        ecart = f"{n['prix'] - prix:+8.2f} $  " if w >= 56 else ""
        return _coupe(f"{_n(n['prix'], 2):>9} {ecart}{(n['prix'] / prix - 1) * 100:+.2f} %  {n['nom']}", w - 2)
    L += [_c(ROUGE, "R ") + ligne(n) for n in dessus]
    L.append(_c(BLANC, f"▶ {_n(prix, 2):>9} cours actuel"))
    L += [_c(VERT, "S ") + ligne(n) for n in dessous]
    L.append(_pied(w))
    return "\n".join(L)


def ecran_cot(w=None):
    w = w or largeur()
    L = [bandeau("COT  gros spéculateurs sur l'or", w, "CFTC, hebdomadaire")]
    c = base.lire("cot")
    if not c:
        return "\n".join(L + [_c(GRIS, "Rapport pas encore relevé.")])
    L += _a_la_ligne([f"rapport du {c['date']}", f"position nette {_n(c['net'], 0)} contrats",
                      f"{c['net_pct_oi']:.0f} % des positions", f"semaine {_var(c['variation'], '{:+,.0f}', '')}"], w)
    wb = max(10, w - 14)
    k = int(round(c["rang_3_ans"] * (wb - 1)))
    L.append("rang 3 ans " + _c(GRIS, "[") + _c(AMBRE, "─" * k + "●" + "─" * (wb - 1 - k)) + _c(GRIS, "]"))
    L.append(_c(GRIS, _coupe("0 % : jamais aussi vendeurs en 3 ans · 100 % : jamais aussi acheteurs", w)))
    L.append(_pied(w))
    return "\n".join(L)


def ecran_des(w=None, maintenant=None):
    w, m = w or largeur(), maintenant or time.time()
    L = [bandeau("DES  fiche de l'instrument", w, "XAU/USD")]
    e = base.lire("mt5:etat") or {}
    compte = e.get("compte") or {}
    morceaux = [f"symbole courtier {e.get('symbole') or config.MT5_SYMBOLE}"]
    if compte:
        morceaux += [f"serveur {compte.get('server')}", f"levier du compte 1:{compte.get('leverage')}",
                     f"devise {compte.get('currency')}", "compte " + ("DÉMO" if compte.get("demo") else "RÉEL")]
    if config.MT5_ACTIF:
        try:
            from . import mt5
            s = mt5.appel("specs", delai=3)
            morceaux += [f"contrat {s['trade_contract_size']:g} oz par lot",
                         f"lot min {s['volume_min']:g} (= {s['volume_min'] * s['trade_contract_size']:g} oz)",
                         f"pas {s['volume_step']:g}", f"{s['digits']} décimales"]
        except Exception:
            morceaux.append(_c(GRIS, "pont MT5 indisponible : contrat non lu"))
    L.append(section("COURTIER", w))
    L += _a_la_ligne(morceaux, w)
    couts, d = base.lire("apprentissage:couts") or {}, flux.prix_direct()
    L.append(section("FRAIS MESURÉS", w))
    if couts.get("ecart") and d:
        L += _a_la_ligne([f"écart médian {couts['ecart'] * 100:.4f} % ≈ {couts['ecart'] * d['prix']:.2f} $/once",
                          f"glissement {couts.get('glissement', 0) * 100:+.4f} %",
                          f"commission {couts.get('commission', 0) * 100:.4f} %",
                          f"{couts.get('executions', 0)} exécutions"], w)
    else:
        L.append(_c(GRIS, "pas encore mesurés"))
    L.append(section("HORAIRES (Paris)", w))
    jour = dt.datetime.fromtimestamp(m, _zone("Europe/Paris")).date()
    for nom, zone, h1, h2 in SEANCES:
        debut = dt.datetime.combine(jour, dt.time(h1), _zone(zone)).timestamp()
        fin = dt.datetime.combine(jour, dt.time(h2), _zone(zone)).timestamp()
        L.append(f"{nom:<9} {_heure(debut, '%H:%M')} - {_heure(fin, '%H:%M')}")
    ouvert, etat = marche_ouvert(m)
    L.append(_coupe("Or : du dimanche 18 h au vendredi 17 h (New York), pause 17 h - 18 h · maintenant ", w - 14)
             + _c(VERT if ouvert else ROUGE, etat))
    L.append(section("SOURCES", w))
    L += _a_la_ligne(["Binance XAUUSDT et PAXG en direct", "courtier MT5", "COMEX (Yahoo)", "21 marchés liés",
                      "CFTC", "agenda Forex Factory", "Google Actualités"], w)
    L.append(_pied(w))
    return "\n".join(L)


def ecran_risk(w=None):
    from . import executant
    w = w or largeur()
    L = [bandeau("RISK  compte, positions, permis", w, "MT5")]
    for ligne in executant.rapport_mt5().split("\n"):
        L += textwrap.wrap(ligne, w) or [""]
    if base.lire("pause") or base.lire("mt5:pause"):
        L.append(_c(ROUGE, "Nouvelles positions EN PAUSE"))
    L.append(_pied(w))
    return "\n".join(L)


def ecran_codes(w=None):
    w = w or largeur()
    L = [bandeau("CODES  terminal de l'or", w, "dans Termius : or <code>")]
    L += [_c(AMBRE, f"{c.upper():<6}") + _coupe(d, w - 6) for c, d in CODES]
    L.append(_c(GRIS, _coupe("Exemples : or go · or gp 4h · or eco · or rv", w)))
    return "\n".join(L)


ECRANS = {"go": ecran_go, "gp": ecran_gp, "gip": ecran_gip, "eco": ecran_eco, "top": ecran_top, "wei": ecran_wei,
          "corr": ecran_corr, "rv": ecran_rv, "niv": ecran_niv, "cot": ecran_cot, "des": ecran_des,
          "risk": ecran_risk, "codes": ecran_codes}


def _ajuster(texte, w):
    """Filet de sécurité : aucune ligne plus large que l'écran (repliée, couleur retirée si besoin)."""
    out = []
    for ligne in texte.split("\n"):
        if visible(ligne) <= w:
            out.append(ligne)
        else:
            out += textwrap.wrap(_ANSI.sub("", ligne), w) or [""]
    return "\n".join(out)


def rendu(code, *args, w=None, couleur=None):
    """Texte d'un écran ; couleur=False pour Telegram ou un fichier."""
    global _COULEUR
    avant, _COULEUR = _COULEUR, couleur
    w = w or largeur()
    try:
        fn = ECRANS.get(code.lower(), ecran_codes)
        return _ajuster(fn(*args, w=w) if code.lower() == "gp" else fn(w=w), w)
    finally:
        _COULEUR = avant


def main(argv):
    code = (argv[0] if argv else "go").lower()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if code not in ECRANS:
        print(rendu("codes"))
        return 1
    if code == "go" and "--une-fois" not in argv and sys.stdout.isatty():
        try:
            while True:
                sortie = rendu("go")
                sys.stdout.write("\033[H\033[2J" + sortie + "\n" + _c(GRIS, "Ctrl+C pour quitter") + "\n")
                sys.stdout.flush()
                time.sleep(2)
        except KeyboardInterrupt:
            print()
            return 0
    print(rendu(code, *args))
    return 0
