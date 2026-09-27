"""VEILLE — rien ne doit échapper à l'armée, et elle doit réagir vite.

Chaque sentinelle est un petit bot du chef d'orchestre (isolé, relancé, compte rendu) :
- éclair        (2 s)   : mouvement brutal du cours, écart achat/vente MT5 anormal, écart entre sources ;
- niveaux       (10 s)  : pivots du jour, plus haut / bas de la veille et de la semaine, chiffres ronds, sommets et
                          creux récents, Fibonacci : alerte à chaque cassure ;
- tendance      (60 s)  : tendance sur 15 min, 1 h, 4 h, 1 j (moyennes, RSI, ADX) et leur alignement ;
- microstructure (30 s) : contrat perpétuel or Binance (taux de financement, positions ouvertes, ratio acheteurs /
                          vendeurs) et carnet d'ordres PAXG (déséquilibre) ;
- calendrier    (60 s)  : annonces économiques américaines à fort impact (emploi, inflation, Fed…), alerte avant,
                          et aucun nouvel ordre MT5 de 15 min avant à 15 min après ;
- actualités    (5 min) : titres sur l'or (Google Actualités), mots clés critiques signalés ;
- COT CFTC      (6 h)   : positions des gros spéculateurs (« managed money ») sur l'or COMEX, chaque semaine.

Sources publiques et gratuites ; une source indisponible n'arrête jamais les autres.
"""
from __future__ import annotations

import datetime as dt
import html
import time
import xml.etree.ElementTree as ET
from collections import deque

import numpy as np

from . import base, config, donnees, indicateurs as I, telegram

UA = {"User-Agent": "Mozilla/5.0 (armee-or)"}


JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")


def heure_paris(ts, fmt="%a %d %H:%M"):
    """Heure de Paris (l'utilisateur), quel que soit le fuseau du serveur ; jours en français."""
    try:
        from zoneinfo import ZoneInfo
        d, suffixe = dt.datetime.fromtimestamp(ts, ZoneInfo("Europe/Paris")), ""
    except Exception:
        d, suffixe = dt.datetime.fromtimestamp(ts, dt.timezone.utc), " UTC"
    return d.strftime(fmt.replace("%a", JOURS[d.weekday()])) + suffixe


def _get(url, session=None, params=None, timeout=20):
    import requests
    r = (session or requests).get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r


# ============================================================================ éclair
class Eclair:
    """Mémoire des derniers cours (10 min) : alerte si le mouvement dépasse largement la normale."""

    def __init__(self):
        self.prix = deque(maxlen=900)

    def normale(self):
        """Écart-type des variations d'une minute (dernières 24 h de bougies 1 min), en %."""
        for s in (config.SOURCE_PRINCIPALE, *config.SOURCES_DIRECT):
            lignes = donnees.charger_lignes(s, "1m", limite=1440)
            if len(lignes) > 200:
                c = np.array([x[4] for x in lignes])
                return float(np.std(np.diff(np.log(c))) * 100) or None
        return None

    def observer(self, maintenant=None):
        from . import flux
        maintenant = maintenant or time.time()
        d = flux.prix_direct()
        if not d:
            return "aucun cours frais"
        self.prix.append((maintenant, d["prix"]))
        msgs = []
        sigma = base.lire("eclair:sigma")
        if not sigma or maintenant - sigma["ts"] > 3600:
            v = self.normale()
            sigma = {"ts": maintenant, "v": v}
            base.ecrire("eclair:sigma", sigma)
        if sigma.get("v"):
            for minutes in (1, 5):
                anciens = [p for t, p in self.prix if maintenant - t >= minutes * 60 - 3]
                if not anciens:
                    continue
                var = (d["prix"] / anciens[-1] - 1) * 100
                seuil = 5 * sigma["v"] * np.sqrt(minutes)
                if abs(var) > seuil and abs(var) > 0.15:
                    telegram.alerte_rare(f"eclair-{minutes}", f"⚡ Mouvement brutal de l'or : {var:+.2f} % en {minutes} "
                                         f"min ({abs(var) / (sigma['v'] * np.sqrt(minutes)):.0f}× la normale), "
                                         f"{d['prix']:.2f} $.", 600, important=True)
                    msgs.append(f"{var:+.2f} % en {minutes} min")
        m = base.lire("direct:MT5")
        if m and m.get("ask") and maintenant - m.get("ts", 0) < 120:
            ecart = m["ask"] - m["bid"]
            hist = base.lire("eclair:ecarts") or []
            hist = (hist + [ecart])[-300:]
            base.ecrire("eclair:ecarts", hist)
            med = float(np.median(hist))
            if len(hist) > 60 and med > 0 and ecart > 4 * med:
                telegram.alerte_rare("eclair-spread", f"⚠️ Écart achat/vente MT5 anormal : {ecart:.2f} $ "
                                     f"({ecart / med:.0f}× l'habitude). Ordres plus chers en ce moment.", 1800)
                msgs.append(f"écart MT5 {ecart:.2f}")
        return ", ".join(msgs) or f"{d['prix']:.2f} $ calme"


# ============================================================================ niveaux clés
def calculer_niveaux(j, h4, prix):
    """j : bougies 1 j, h4 : bougies 4 h. -> liste de {nom, prix} triée."""
    niv = []
    if len(j["c"]) >= 6:
        H, L, C = j["h"][-2], j["l"][-2], j["c"][-2]               # dernière journée TERMINÉE
        p = (H + L + C) / 3
        niv += [("pivot", p), ("R1", 2 * p - L), ("S1", 2 * p - H), ("R2", p + H - L), ("S2", p - (H - L)),
                ("plus haut d'hier", H), ("plus bas d'hier", L),
                ("plus haut 5 jours", float(np.max(j["h"][-6:-1]))), ("plus bas 5 jours", float(np.min(j["l"][-6:-1])))]
    if len(j["c"]) >= 65:
        hi, lo = float(np.max(j["h"][-65:-1])), float(np.min(j["l"][-65:-1]))
        for f in (0.382, 0.5, 0.618):
            niv.append((f"Fibonacci {f * 100:.1f} % (3 mois)", hi - f * (hi - lo)))
    if len(h4["c"]) >= 30:                                           # sommets / creux « fractals » récents en 4 h
        h, l = h4["h"][-60:], h4["l"][-60:]
        for i in range(2, len(h) - 2):
            if h[i] == max(h[i - 2:i + 3]):
                niv.append(("sommet 4 h récent", float(h[i])))
            if l[i] == min(l[i - 2:i + 3]):
                niv.append(("creux 4 h récent", float(l[i])))
    rond = 50.0
    niv += [("chiffre rond", np.floor(prix / rond) * rond), ("chiffre rond", np.ceil(prix / rond) * rond)]
    def priorite(nom):                                   # deux niveaux au même prix : on garde le plus parlant
        for i, debut in enumerate(("pivot", "R", "S", "plus", "Fibonacci", "sommet", "creux", "chiffre")):
            if nom.startswith(debut):
                return i
        return 9
    garde = {}
    for nom, v in niv:
        cle = round(float(v), 1)
        if cle not in garde or priorite(nom) < priorite(garde[cle][0]):
            garde[cle] = (nom, float(v))
    fusion = []                                         # niveaux à moins de 0,05 % l'un de l'autre : un seul
    for nom, v in sorted(garde.values(), key=lambda x: x[1]):
        if fusion and v - fusion[-1][1] <= prix * 0.0005:
            if priorite(nom) < priorite(fusion[-1][0]):
                fusion[-1] = (nom, v)
            continue
        fusion.append((nom, v))
    return [{"nom": nom, "prix": v} for nom, v in fusion]


def surveiller_niveaux(source="PAXGUSDT"):
    from . import flux
    d = flux.prix_direct()
    if not d:
        return "aucun cours frais"
    cache = base.lire("niveaux")
    if not cache or time.time() - cache["ts"] > 900:
        j, h4 = donnees.charger(source, "1d", limite=80), donnees.charger(source, "4h", limite=120)
        cache = {"ts": time.time(), "niveaux": calculer_niveaux(j, h4, d["prix"]), "dernier_prix": d["prix"]}
    avant, prix = cache.get("dernier_prix", d["prix"]), d["prix"]
    casses = [n for n in cache["niveaux"] if (avant < n["prix"] <= prix) or (avant > n["prix"] >= prix)]
    for n in casses:
        sens = "à la hausse ⬆️" if prix > avant else "à la baisse ⬇️"
        telegram.alerte_rare(f"niveau-{n['nom']}-{n['prix']:.1f}", f"📏 Cassure {sens} : {n['nom']} ({n['prix']:.2f} $) "
                             f"— or à {prix:.2f} $.", 4 * 3600, important=n["nom"] not in ("chiffre rond",))
    cache["dernier_prix"] = prix
    base.ecrire("niveaux", cache)
    dessus = [n for n in cache["niveaux"] if n["prix"] > prix][:2]
    dessous = [n for n in cache["niveaux"] if n["prix"] < prix][-2:]
    return (f"{len(casses)} cassure(s) · résistance {dessus[0]['prix']:.1f}" if dessus else f"{len(casses)} cassure(s)") \
        + (f" · support {dessous[-1]['prix']:.1f}" if dessous else "")


def texte_niveaux():
    from . import flux
    cache, d = base.lire("niveaux"), flux.prix_direct()
    if not cache or not d:
        return "Niveaux clés : pas encore calculés."
    prix = d["prix"]
    dessus = [n for n in cache["niveaux"] if n["prix"] > prix][:4]
    dessous = [n for n in cache["niveaux"] if n["prix"] < prix][-4:][::-1]
    return "\n".join([f"📏 Niveaux clés (or à {prix:.2f} $)", "Au-dessus : " + " · ".join(
        f"{n['nom']} {n['prix']:.1f}" for n in dessus), "En dessous : " + " · ".join(
        f"{n['nom']} {n['prix']:.1f}" for n in dessous)])


# ============================================================================ tendance multi-unités
def tendance(b):
    c = b["c"]
    if len(c) < 60:
        return None
    e20, e50 = I.ema(c, 20)[-1], I.ema(c, 50)[-1]
    rsi, adx = float(I.rsi(c, 14)[-1]), float(I.adx(b["h"], b["l"], c, 14)[-1])
    sens = 1 if (c[-1] > e20 > e50) else -1 if (c[-1] < e20 < e50) else 0
    return {"sens": sens, "rsi": rsi, "adx": adx, "force": "forte" if adx >= 25 else "faible"}


def surveiller_tendances(source="PAXGUSDT"):
    out = {tf: tendance(donnees.charger(source, tf, limite=300)) for tf in ("15m", "1h", "4h", "1d")}
    sens = [v["sens"] for v in out.values() if v]
    alignement = sum(sens)
    base.ecrire("tendances", {"ts": time.time(), "unites": out, "alignement": alignement})
    if abs(alignement) == 4:
        telegram.alerte_rare(f"alignement-{alignement}", f"🧭 Les 4 unités de temps sont alignées à la "
                             f"{'HAUSSE' if alignement > 0 else 'BAISSE'} (15 min, 1 h, 4 h, 1 j).", 6 * 3600)
    return texte_tendances()


def texte_tendances():
    t = base.lire("tendances")
    if not t:
        return "Tendances : pas encore calculées."
    mots = {1: "hausse", -1: "baisse", 0: "neutre"}
    return "Tendances : " + " · ".join(f"{tf} {mots[v['sens']]} (RSI {v['rsi']:.0f}, {v['force']})"
                                       for tf, v in t["unites"].items() if v) + f" · alignement {t['alignement']:+d}/4"


# ============================================================================ microstructure Binance
def microstructure(session=None):
    out = {"ts": time.time()}
    try:
        p = _get("https://fapi.binance.com/fapi/v1/premiumIndex", session, {"symbol": "XAUUSDT"}).json()
        out["financement_pct"] = float(p["lastFundingRate"]) * 100
        out["prime_pct"] = (float(p["markPrice"]) / float(p["indexPrice"]) - 1) * 100
        oi = _get("https://fapi.binance.com/futures/data/openInterestHist", session,
                  {"symbol": "XAUUSDT", "period": "5m", "limit": 13}).json()
        if len(oi) >= 2:
            out["positions_ouvertes"] = float(oi[-1]["sumOpenInterestValue"])
            out["positions_ouvertes_1h_pct"] = (float(oi[-1]["sumOpenInterest"]) / float(oi[0]["sumOpenInterest"]) - 1) * 100
        ls = _get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", session,
                  {"symbol": "XAUUSDT", "period": "5m", "limit": 1}).json()
        if ls:
            out["acheteurs_pct"] = float(ls[-1]["longAccount"]) * 100
    except Exception as ex:
        out["erreur_perpetuel"] = f"{type(ex).__name__}"
    try:
        carnet = _get("https://api.binance.com/api/v3/depth", session, {"symbol": "PAXGUSDT", "limit": 100}).json()
        bids = np.array(carnet["bids"], dtype=float)
        asks = np.array(carnet["asks"], dtype=float)
        mid = (bids[0, 0] + asks[0, 0]) / 2
        vb = bids[bids[:, 0] >= mid * 0.998, 1].sum()
        va = asks[asks[:, 0] <= mid * 1.002, 1].sum()
        out["desequilibre_pct"] = float((vb - va) / (vb + va) * 100) if vb + va else 0.0
    except Exception as ex:
        out["erreur_carnet"] = f"{type(ex).__name__}"
    return out


def surveiller_microstructure(session=None):
    m = microstructure(session)
    base.ecrire("microstructure", m)
    if abs(m.get("financement_pct", 0)) >= 0.05:
        telegram.alerte_rare("financement", f"💸 Taux de financement du perpétuel or extrême : {m['financement_pct']:+.3f} % "
                             "(les positions à levier d'un côté paient cher : retournement possible).", 8 * 3600)
    if abs(m.get("positions_ouvertes_1h_pct", 0)) >= 10:
        telegram.alerte_rare("oi", f"📊 Positions ouvertes sur le perpétuel or : {m['positions_ouvertes_1h_pct']:+.1f} % "
                             "en 1 h (afflux ou fuite massive de capitaux à levier).", 3600)
    if abs(m.get("desequilibre_pct", 0)) >= 60:
        telegram.alerte_rare("carnet", f"📚 Carnet d'ordres PAXG très déséquilibré : {m['desequilibre_pct']:+.0f} % "
                             f"({'acheteurs' if m['desequilibre_pct'] > 0 else 'vendeurs'} dominants près du prix).", 3600)
    return texte_microstructure(m)


def texte_microstructure(m=None):
    m = m or base.lire("microstructure")
    if not m:
        return "Microstructure : pas encore relevée."
    morceaux = []
    if "financement_pct" in m:
        morceaux.append(f"financement {m['financement_pct']:+.4f} %")
    if "positions_ouvertes_1h_pct" in m:
        morceaux.append(f"positions ouvertes {m['positions_ouvertes_1h_pct']:+.1f} %/1 h")
    if "acheteurs_pct" in m:
        morceaux.append(f"comptes acheteurs {m['acheteurs_pct']:.0f} %")
    if "desequilibre_pct" in m:
        morceaux.append(f"carnet PAXG {m['desequilibre_pct']:+.0f} %")
    return "Microstructure : " + (" · ".join(morceaux) if morceaux else "sources Binance indisponibles")


# ============================================================================ calendrier économique
CALENDRIER = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
MARGE_ANNONCE_S = 15 * 60


def charger_calendrier(session=None):
    evts = []
    for e in _get(CALENDRIER, session).json():
        if e.get("country") != "USD" or e.get("impact") != "High":
            continue
        try:
            ts = dt.datetime.fromisoformat(e["date"]).timestamp()
        except (KeyError, ValueError):
            continue
        evts.append({"titre": e.get("title", ""), "ts": ts, "prevision": e.get("forecast") or "",
                     "precedent": e.get("previous") or ""})
    evts.sort(key=lambda e: e["ts"])
    base.ecrire("calendrier", {"ts": time.time(), "evenements": evts})
    return evts


def evenement_proche(maintenant=None, marge=MARGE_ANNONCE_S):
    """Annonce à fort impact dans la fenêtre [-marge, +marge] autour de maintenant (None sinon)."""
    maintenant = maintenant or time.time()
    cal = base.lire("calendrier") or {}
    for e in cal.get("evenements", []):
        if abs(e["ts"] - maintenant) <= marge:
            return e
    return None


def surveiller_calendrier(session=None, maintenant=None):
    maintenant = maintenant or time.time()
    cal = base.lire("calendrier")
    if not cal or maintenant - cal["ts"] > 1800:
        charger_calendrier(session)
        cal = base.lire("calendrier")
    for e in cal["evenements"]:
        reste = e["ts"] - maintenant
        heure = heure_paris(e["ts"], "%a %H:%M")
        for avance in (1800, 300):
            if 0 < reste <= avance:
                telegram.alerte_rare(f"annonce-{e['ts']}-{e['titre']}-{avance}", f"🗓 Dans {int(reste // 60)} min ({heure}, "
                                     f"heure de Paris) : {e['titre']} (États-Unis, fort impact) · prévision "
                                     f"{e['prevision'] or '?'} · précédent {e['precedent'] or '?'}. Aucun nouvel ordre MT5 "
                                     "de 15 min avant à 15 min après.", 3 * 3600, important=True)
    proche = evenement_proche(maintenant)
    a_venir = [e for e in cal["evenements"] if e["ts"] > maintenant]
    return (f"annonce en cours : {proche['titre']}" if proche else "") or \
        (f"prochaine : {a_venir[0]['titre']} dans {(a_venir[0]['ts'] - maintenant) / 3600:.1f} h" if a_venir
         else "aucune annonce à fort impact cette semaine")


def texte_calendrier(n=6):
    cal = base.lire("calendrier")
    if not cal:
        return "Calendrier : pas encore chargé."
    a_venir = [e for e in cal["evenements"] if e["ts"] > time.time() - 3600][:n]
    return "🗓 Annonces américaines à fort impact :\n" + ("\n".join(
        f"• {heure_paris(e['ts'])} (Paris) · {e['titre']} · prévision "
        f"{e['prevision'] or '?'} · précédent {e['precedent'] or '?'}" for e in a_venir) or "aucune cette semaine")


# ============================================================================ actualités
FLUX_ACTUS = "https://news.google.com/rss/search"
MOTS_CRITIQUES = {
    "Fed / taux": ("fed ", "federal reserve", "powell", "rate cut", "rate hike", "fomc", "interest rate"),
    "inflation": ("inflation", "cpi", "pce"),
    "géopolitique": ("war", "attack", "missile", "sanction", "invasion", "conflict", "strike"),
    "banques centrales": ("central bank", "pboc", "reserves", "buying gold", "gold purchases"),
    "record": ("record high", "all-time high", "all time high", "plunge", "crash", "soars", "tumbles"),
}


def actualites(session=None, requete="gold price OR XAUUSD OR \"gold prices\""):
    r = _get(FLUX_ACTUS, session, {"q": requete, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    items, titres_vus = [], set()
    for it in ET.fromstring(r.content).findall(".//item")[:40]:
        titre = html.unescape(it.findtext("title") or "")
        sans_source = titre.rsplit(" - ", 1)[0].strip().lower()      # même article repris par plusieurs sites
        if sans_source in titres_vus:
            continue
        titres_vus.add(sans_source)
        bas = f" {titre.lower()} "
        themes = [th for th, mots in MOTS_CRITIQUES.items() if any(m in bas for m in mots)]
        items.append({"titre": titre, "lien": it.findtext("link") or "", "date": it.findtext("pubDate") or "",
                      "themes": themes})
    return items


def surveiller_actualites(session=None):
    items = actualites(session)
    vus = set(base.lire("actus:vues") or [])
    nouveaux = [i for i in items if i["lien"] not in vus]
    base.ecrire("actus:vues", list(vus | {i["lien"] for i in items})[-500:])
    base.ecrire("actualites", {"ts": time.time(), "titres": items[:15]})
    critiques = [i for i in nouveaux if i["themes"]] if vus else []            # 1er passage : pas de rafale
    if critiques:
        telegram.alerte_rare("actus", "📰 Actualités de l'or à surveiller :\n" + "\n".join(
            f"• [{', '.join(i['themes'])}] {i['titre']}" for i in critiques[:5]), 1800)
    return f"{len(nouveaux)} nouveaux titres, {len(critiques)} critiques"


def texte_actualites(n=8):
    a = base.lire("actualites")
    if not a:
        return "Actualités : pas encore relevées."
    return "📰 Derniers titres sur l'or :\n" + "\n".join(
        f"• {'[' + ', '.join(i['themes']) + '] ' if i['themes'] else ''}{i['titre']}" for i in a["titres"][:n])


# ============================================================================ COT (CFTC)
COT = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
CODE_OR = "088691"                                                      # GOLD - COMMODITY EXCHANGE INC.


def cot(session=None, semaines=160):
    rows = _get(COT, session, {"cftc_contract_market_code": CODE_OR, "$order": "report_date_as_yyyy_mm_dd DESC",
                               "$limit": semaines}).json()
    rows = sorted(rows, key=lambda r: r["report_date_as_yyyy_mm_dd"])
    net = np.array([float(r["m_money_positions_long_all"]) - float(r["m_money_positions_short_all"]) for r in rows])
    oi = float(rows[-1]["open_interest_all"])
    rang = float((net[:-1] < net[-1]).mean()) if len(net) > 1 else 0.5
    return {"ts": time.time(), "date": rows[-1]["report_date_as_yyyy_mm_dd"][:10], "net": float(net[-1]),
            "net_pct_oi": float(net[-1] / oi * 100) if oi else 0.0, "rang_3_ans": rang,
            "variation": float(net[-1] - net[-2]) if len(net) > 1 else 0.0}


def surveiller_cot(session=None):
    c = cot(session)
    ancien = base.lire("cot")
    base.ecrire("cot", c)
    if (not ancien or ancien.get("date") != c["date"]) and (c["rang_3_ans"] >= 0.95 or c["rang_3_ans"] <= 0.05):
        telegram.envoyer(f"🏦 COT (CFTC, {c['date']}) : les gros spéculateurs sont à un EXTRÊME de 3 ans "
                         f"({'acheteurs' if c['rang_3_ans'] >= 0.95 else 'vendeurs'}) sur l'or : position nette "
                         f"{c['net']:,.0f} contrats ({c['net_pct_oi']:.0f} % des positions). Souvent signe d'essoufflement.")
    return texte_cot(c)


def texte_cot(c=None):
    c = c or base.lire("cot")
    if not c:
        return "COT : pas encore relevé."
    return (f"COT CFTC ({c['date']}) : gros spéculateurs nets {c['net']:+,.0f} contrats ({c['net_pct_oi']:.0f} % des "
            f"positions) · {c['variation']:+,.0f} sur la semaine · rang sur 3 ans {c['rang_3_ans'] * 100:.0f} %")


def texte_veille():
    from . import marches_lies  # noqa: F401  (le ratio or/argent est relevé par la vigie des marchés liés)
    m = base.lire("marches") or {}
    lignes = ["🛰 Veille de l'armée de l'or", texte_tendances(), texte_niveaux(), texte_microstructure(), texte_cot()]
    if m.get("ratio_or_argent"):
        lignes.append(f"Ratio or / argent : {m['ratio_or_argent']:.1f}")
    lignes += [texte_calendrier(3), texte_actualites(5)]
    return "\n".join(lignes)
