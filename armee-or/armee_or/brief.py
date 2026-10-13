"""BRIEF DU MATIN — chaque jour de semaine à 8 h (heure de Paris), sur Telegram.

Ce qui s'est passé pendant la nuit (séance asiatique), ce qui arrive aujourd'hui (annonces), où sont les
niveaux à surveiller, ce que font les marchés liés et les taux réels, les titres du moment et l'état de
l'armée. À la demande : /or_brief sur Telegram, « or brief » dans Termius.
"""
from __future__ import annotations

import datetime as dt
import time

from . import base, config, donnees, flux, telegram, veille

HEURE_ENVOI = 8                                              # heure de Paris


def _paris(ts):
    from zoneinfo import ZoneInfo
    return dt.datetime.fromtimestamp(ts, ZoneInfo("Europe/Paris"))


def _marche(ticker):
    for x in (base.lire("marches") or {}).get("marches", []):
        if x["ticker"] == ticker:
            return x
    return None


def nuit(maintenant):
    """Variation depuis 23 h (Paris) la veille : la séance asiatique."""
    p = _paris(maintenant)
    debut = (p - dt.timedelta(days=1)).replace(hour=23, minute=0, second=0, microsecond=0)
    if p.hour >= 23:
        debut = p.replace(hour=23, minute=0, second=0, microsecond=0)
    for s in (config.SOURCE_PRINCIPALE, "PAXGUSDT"):
        b = donnees.charger(s, "1m", depuis_ms=int(debut.timestamp() * 1000))
        if len(b["c"]) >= 30:
            return {"depart": float(b["o"][0]), "dernier": float(b["c"][-1]), "haut": float(b["h"].max()),
                    "bas": float(b["l"].min()), "depuis": debut.timestamp()}
    return None


def texte_brief(maintenant=None):
    m = maintenant or time.time()
    p = _paris(m)
    L = [f"☀️ Brief de l'or · {veille.JOURS[p.weekday()]} {p.day:02d}/{p.month:02d} · {p:%H:%M}"]
    d = flux.prix_direct()
    n = nuit(m)
    if d:
        ligne = f"Or {d['prix']:,.2f} $".replace(",", " ")
        eur = _marche("EURUSD=X")
        if eur and eur.get("dernier"):
            ligne += f" (≈ {d['prix'] / eur['dernier']:,.0f} €/once)".replace(",", " ")
        L.append(ligne)
    if n:
        var = (n["dernier"] / n["depart"] - 1) * 100
        L.append(f"🌙 Nuit (depuis 23 h) : {var:+.2f} % · haut {n['haut']:.2f} · bas {n['bas']:.2f} "
                 f"({n['haut'] - n['bas']:.2f} $ d'amplitude)")
    cal = base.lire("calendrier") or {}
    aujourd_hui = [e for e in cal.get("evenements", []) if _paris(e["ts"]).date() == p.date() and e["ts"] > m - 3600]
    L.append("🗓 Aujourd'hui : " + (" · ".join(
        f"{_paris(e['ts']):%H:%M} {e['titre']} (prév. {e['prevision'] or '?'})" for e in aujourd_hui)
        if aujourd_hui else "aucune annonce américaine à fort impact"))
    if aujourd_hui:
        L.append("   Pas de nouvel ordre MT5 de 15 min avant à 15 min après chaque annonce.")
    niv = base.lire("niveaux")
    if niv and d:
        dessus = [x for x in niv["niveaux"] if x["prix"] > d["prix"]][:2]
        dessous = [x for x in niv["niveaux"] if x["prix"] < d["prix"]][-2:][::-1]
        L.append("📏 À surveiller : " + " · ".join(
            [f"R {x['prix']:.1f} ({x['nom']})" for x in dessus] + [f"S {x['prix']:.1f} ({x['nom']})" for x in dessous]))
    t = base.lire("tendances")
    if t:
        mots = {1: "↑", -1: "↓", 0: "→"}
        L.append("🧭 Tendances : " + " ".join(f"{tf} {mots[v['sens']]}" for tf, v in t["unites"].items() if v)
                 + f" (alignement {t['alignement']:+d}/4)")
    morceaux = []
    for tk, nom in (("DX-Y.NYB", "dollar"), ("^TNX", "taux 10 ans"), ("SI=F", "argent"), ("^VIX", "VIX"),
                    ("^GSPC", "S&P 500")):
        x = _marche(tk)
        if x:
            morceaux.append(f"{nom} {x['var_1j']:+.1f} %")
    tr = base.lire("tresor")
    if tr and tr.get("reel_10a") is not None:
        morceaux.append(f"taux réel 10 ans {tr['reel_10a']:.2f} % ({tr.get('reel_10a_5j', 0):+.2f} pt/5 j)")
    if morceaux:
        L.append("🌍 Hier : " + " · ".join(morceaux))
    c = base.lire("cot")
    if c and m - c.get("ts", 0) < 4 * 86400:
        L.append(f"🏦 Gros spéculateurs (CFTC {c['date']}) : {c['net_pct_oi']:.0f} % des positions, rang 3 ans "
                 f"{c['rang_3_ans'] * 100:.0f} %")
    a = base.lire("actualites")
    if a and a.get("titres"):
        L.append("📰 " + "\n📰 ".join(
            (f"[{', '.join(i['themes'])}] " if i["themes"] else "") + i["titre"] for i in a["titres"][:3]))
    permis = base.lire("mt5:permis") or {}
    etat = base.lire("mt5:etat") or {}
    morceaux = ["permis " + " ".join(f"{tf} {'✅' if (permis.get(tf) or {}).get('ok') else '✖'}"
                                     for tf in ("1h", "4h", "1d"))]
    if config.MT5_ACTIF:
        compte = etat.get("compte")
        morceaux.append(f"MT5 {compte['equity']:.2f} {compte['currency']}" if etat.get("connecte") and compte
                        else "MT5 non connecté")
    nb = len(base.lire("alertes:prix") or [])
    if nb:
        morceaux.append(f"{nb} alerte(s) de prix")
    r = base.lire("risque:etat") or {}
    if r.get("coupe"):
        morceaux.append("⛔ coupe-circuit actif")
    L.append("🤖 Armée : " + " · ".join(morceaux))
    L.append("Écran complet : /or_go · graphique : /or_gp_1h")
    return "\n".join(L)


def bot_brief(maintenant=None):
    """Envoie le brief une fois par jour de semaine, à partir de 8 h (Paris) et jusqu'à midi."""
    m = maintenant or time.time()
    p = _paris(m)
    jour = p.date().isoformat()
    if p.weekday() >= 5:
        return "week-end : pas de brief"
    if base.lire("brief:dernier") == jour:
        return "brief déjà envoyé aujourd'hui"
    if not HEURE_ENVOI <= p.hour < 12:
        return f"prochain brief à {HEURE_ENVOI} h"
    telegram.envoyer(texte_brief(m))
    base.ecrire("brief:dernier", jour)
    return "brief envoyé"
