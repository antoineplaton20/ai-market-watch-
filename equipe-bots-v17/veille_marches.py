"""VEILLE MARCHÉS MONDIAUX — processus séparé (service equipe-bots-marches). AUCUN ordre n'est passé.

1. Toutes les 4 h : lecture de la presse mondiale (une vingtaine de sources : banques centrales, FMI, presse éco
   française et internationale, Wall Street, énergie, défense, devises, crypto), classée en 14 thèmes
   (géopolitique, économie, taux, Wall Street, Europe/CAC 40, industrie, énergie, alimentation, métaux, devises,
   défense, tech/IA, crypto, avis des banques). Synthèse par l'IA si une clé Anthropic est configurée,
   sinon lecture simplifiée par mots-clés. Repères : CAC 40, Euro Stoxx 50, S&P 500, Nasdaq, or, pétrole, devises.
2. Chaque jour : note de 0 à 5 (5 = meilleure option) de tes titres, de ta liste, des principales cryptos et des
   titres Trade Republic retenus par la veille TR — avec le moment d'acheter, d'attendre ou de vendre.
3. Telegram : rapport quotidien, alerte si un titre que tu détiens passe à « vendre », alerte si un titre atteint 5/5.
   Commandes : /marches · /briefing · /note NOM (ou ticker, ou ISIN).

Lancement : python veille_marches.py | test : python veille_marches.py --test | une note : --note LVMH
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

if __name__ == "__main__":             # journal séparé (marches.log)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | MARCHES | %(message)s",
                        handlers=[RotatingFileHandler("marches.log", maxBytes=5_000_000, backupCount=3,
                                                      encoding="utf-8"), logging.StreamHandler()])

import datetime as dt
import json
import os
import re
import time
import traceback

import config
import lecture_renseignement as LR
from alertes import alerte, log
from moteurs import notation as N
from moteurs import sources_marches as S

FICHIER_ETAT = "marches_etat.json"
FICHIER_DEMANDES = "marches_demandes.txt"
PAUSE_YAHOO_S = 1800

SECTEURS = ["Technology", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy",
            "Financial Services", "Healthcare", "Industrials", "Basic Materials", "Real Estate", "Utilities",
            "Crypto", "ETF / indices"]
SECTEURS_FR = {"Technology": "tech", "Communication Services": "télécoms/médias", "Consumer Cyclical": "consommation",
               "Consumer Defensive": "alimentation/conso de base", "Energy": "énergie", "Financial Services": "banques",
               "Healthcare": "santé", "Industrials": "industrie/défense", "Basic Materials": "matériaux",
               "Real Estate": "immobilier", "Utilities": "services publics", "Crypto": "crypto",
               "ETF / indices": "indices/ETF"}
# Sans IA : quels thèmes de presse pèsent sur quels secteurs
THEME_SECTEURS = {"energie": ["Energy", "Utilities"], "alimentaire": ["Consumer Defensive"],
                  "industrie": ["Industrials", "Basic Materials"], "tech": ["Technology", "Communication Services"],
                  "banques_centrales": ["Financial Services", "Real Estate"], "defense": ["Industrials"],
                  "crypto": ["Crypto"], "matieres": ["Basic Materials"], "economie": ["Consumer Cyclical"],
                  "wall_street": ["ETF / indices"], "europe": ["ETF / indices"]}
GRANDES_VALEURS = ["MC.PA", "TTE.PA", "AIR.PA", "SU.PA", "OR.PA", "SAN.PA", "AI.PA", "BNP.PA", "SAF.PA", "HO.PA",
                   "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "IWDA.AS", "CW8.PA"]
CRYPTOS_NOMS = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL", "RIPPLE": "XRP", "CARDANO": "ADA",
                "DOGECOIN": "DOGE", "CHAINLINK": "LINK", "POLKADOT": "DOT", "LITECOIN": "LTC", "AVALANCHE": "AVAX"}
NOMS_REPERES = {"^FCHI": "CAC 40", "^STOXX50E": "Euro Stoxx 50", "^GSPC": "S&P 500", "^IXIC": "Nasdaq",
                "GC=F": "Or", "BZ=F": "Pétrole Brent", "EURUSD=X": "EUR/USD", "EURGBP=X": "EUR/GBP",
                "EURCHF=X": "EUR/CHF", "EURJPY=X": "EUR/JPY"}

PROMPT_BRIEFING = """Tu es l'analyste macro d'un investisseur particulier français (Trade Republic : actions, ETF, crypto).
Voici les titres de presse des dernières 48 h, classés par thème (source entre crochets) :
{blocs}

Évalue l'effet probable de ces informations sur les marchés dans les prochaines semaines. Sois factuel : n'invente
aucun événement absent des titres, et dis « incertain » quand les titres se contredisent.
Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour :
{{"climat": entier de -2 (très négatif) à 2 (très positif),
 "resume": "3 phrases maximum, en français simple",
 "themes": {{"<clé de thème>": {{"tendance": entier de -2 à 2, "fait_cle": "une phrase"}}}},
 "secteurs": {{"<secteur>": entier de -2 à 2}},
 "risques": ["3 risques maximum"],
 "opportunites": ["3 pistes maximum"]}}
Clés de thème autorisées : {themes}
Secteurs autorisés : {secteurs}"""

PROMPT_TON = """Voici les titres de presse des 7 derniers jours sur {nom} ({ticker}) :
{titres}
Quel est l'effet probable de ces nouvelles sur le cours dans les prochaines semaines ?
Réponds UNIQUEMENT avec un objet JSON valide : {{"ton": entier de -2 (très négatif) à 2 (très positif), "raison": "une phrase en français"}}"""


# ================================== ÉTAT ==================================
def charger_etat(fichier=FICHIER_ETAT):
    try:
        with open(fichier, encoding="utf-8") as f:
            etat = json.load(f)
    except Exception:                    # absent, illisible ou abîmé : on repart d'un état neuf, la veille continue
        etat = {}
    if not isinstance(etat, dict):
        etat = {}
    for cle, defaut in (("briefing", {}), ("notes", {}), ("reperes", {}), ("alertes", {}), ("pause_jusqua", 0)):
        etat.setdefault(cle, defaut)
    return etat


def sauver_etat(etat, fichier=FICHIER_ETAT):
    tmp = fichier + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, default=str)
    os.replace(tmp, fichier)


def _entier(x, bas=-2, haut=2):
    try:
        return max(bas, min(haut, int(round(float(x)))))
    except (TypeError, ValueError):
        return None


def _heure(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M") if ts else "jamais"


# ================================== YAHOO =================================
class LimiteYahoo(Exception):
    pass


class Yahoo:
    """Cours, fiche société (consensus des analystes, fondamentaux) et actualités, via yfinance."""

    def __init__(self):
        import yfinance as yf
        self.yf = yf

    @staticmethod
    def _garde(e):
        from moteurs.tr_yahoo import _est_limite
        if _est_limite(f"{type(e).__name__} {e}"):
            raise LimiteYahoo(str(e)[:150])

    def historique(self, ticker, periode="1y"):
        try:
            return self.yf.Ticker(ticker).history(period=periode, interval="1d", auto_adjust=False)
        except Exception as e:
            self._garde(e)
            return None

    def info(self, ticker):
        try:
            return self.yf.Ticker(ticker).info or {}
        except Exception as e:
            self._garde(e)
            return {}

    def news(self, ticker):
        try:
            return self.yf.Ticker(ticker).news or []
        except Exception as e:
            self._garde(e)
            return []


def _ia(modele, prompt, max_tokens):
    from equipe import ia_json
    return ia_json(modele, prompt, max_tokens)


# ================================= BRIEFING ===============================
def faire_briefing(articles, etat_sources, ia=None):
    ia = ia or (_ia if config.ANTHROPIC_API_KEY else None)
    groupes = S.par_theme(articles, n=10)
    titres_cles = {t: [f"{a['titre']} [{a['source']}]" for a in groupes[t][:3]] for t in S.THEMES}
    ok = sum(1 for v in etat_sources.values() if v.startswith("ok"))
    base = {"ts": time.time(), "n_titres": len(articles), "sources_ok": ok, "sources_total": len(etat_sources),
            "sources_ko": [k for k, v in etat_sources.items() if not v.startswith("ok")],
            "titres_cles": titres_cles, "n_par_theme": {t: len(groupes[t]) for t in S.THEMES}}
    j = None
    if ia and articles:
        blocs = "\n".join(f"## {t}\n" + "\n".join(f"- {a['titre']} [{a['source']}]" for a in groupes[t])
                          for t in S.THEMES if groupes[t])
        j = ia(config.MODELE_IA_MARCHES, PROMPT_BRIEFING.format(
            blocs=blocs, themes=", ".join(S.THEMES), secteurs=", ".join(SECTEURS)), 1800)
    if isinstance(j, dict) and _entier(j.get("climat")) is not None:
        themes = {}
        for t, v in (j.get("themes") or {}).items():
            if t in S.THEMES and isinstance(v, dict) and _entier(v.get("tendance")) is not None:
                themes[t] = {"tendance": _entier(v["tendance"]), "fait_cle": str(v.get("fait_cle", ""))[:200]}
        secteurs = {s: _entier(v) for s, v in (j.get("secteurs") or {}).items()
                    if s in SECTEURS and _entier(v) is not None}
        return {**base, "ia": True, "climat": _entier(j["climat"]), "resume": str(j.get("resume", ""))[:600],
                "themes": themes, "secteurs": secteurs,
                "risques": [str(x)[:200] for x in (j.get("risques") or [])][:3],
                "opportunites": [str(x)[:200] for x in (j.get("opportunites") or [])][:3]}
    # --- Secours sans IA : ton des titres par mots-clés
    themes = {}
    for t in S.THEMES:
        ton = N.sentiment_lexical([a["titre"] for a in groupes[t]])
        if ton is not None:
            themes[t] = {"tendance": _entier(ton), "fait_cle": groupes[t][0]["titre"][:200]}
    tons = [v["tendance"] for v in themes.values()]
    climat = _entier(sum(tons) / len(tons)) if tons else 0
    secteurs = {}
    for t, liste in THEME_SECTEURS.items():
        if t in themes:
            for s in liste:
                secteurs.setdefault(s, []).append(themes[t]["tendance"])
    secteurs = {s: _entier(sum(v) / len(v)) for s, v in secteurs.items()}
    negatifs = [a["titre"] for a in articles if (N.sentiment_lexical([a["titre"]]) or 0) < 0][:3]
    return {**base, "ia": False, "climat": climat, "themes": themes, "secteurs": secteurs,
            "resume": "Lecture simplifiée par mots-clés (pas de clé Anthropic) : le ton des titres, pas leur sens fin.",
            "risques": negatifs, "opportunites": []}


def reperes(yahoo):
    """Indices, or, pétrole et devises : dernier cours, variation sur 1 jour et 5 jours."""
    res = {}
    for t in config.MARCHES_INDICES + config.MARCHES_DEVISES:
        df = yahoo.historique(t, "1mo")
        if df is None or len(df) < 6:
            continue
        c = df["Close"].astype(float)
        res[t] = {"nom": NOMS_REPERES.get(t, t), "cours": float(c.iloc[-1]),
                  "j1": float(c.iloc[-1] / c.iloc[-2] - 1) * 100, "j5": float(c.iloc[-1] / c.iloc[-6] - 1) * 100}
    return res


# ================================= NOTATION ===============================
def est_crypto(ticker):
    return bool(re.fullmatch(r"[A-Z0-9]{2,10}-(EUR|USD|USDT)", ticker or ""))


def secteur_de(ticker, info):
    if est_crypto(ticker):
        return "Crypto"
    if (info.get("quoteType") or "").upper() in ("ETF", "MUTUALFUND", "INDEX"):
        return "ETF / indices"
    return info.get("sector") or "ETF / indices"


def ton_presse(nom, ticker, titres, ia=None):
    if not titres:
        return None, "aucune actualité récente"
    ia = ia or (_ia if config.ANTHROPIC_API_KEY else None)
    if ia:
        j = ia(config.MODELE_IA_VEILLE, PROMPT_TON.format(nom=nom, ticker=ticker,
                                                          titres="\n".join(f"- {t}" for t in titres[:15])), 200)
        if isinstance(j, dict) and _entier(j.get("ton")) is not None:
            return _entier(j["ton"]), str(j.get("raison", ""))[:200]
    ton = N.sentiment_lexical(titres)
    return ton, f"{len(titres)} titre{'s' if len(titres) > 1 else ''} (lecture par mots-clés)"


def noter_titre(ticker, nom, detenu, etat, yahoo, articles=None, ia=None):
    df = yahoo.historique(ticker)
    if df is None or len(df) < 60:
        return None
    info = {} if est_crypto(ticker) else yahoo.info(ticker)
    if not nom or nom.upper() == ticker.upper():
        nom = info.get("longName") or info.get("shortName") or nom or ticker
    actus = S.actus_yahoo(yahoo.news(ticker)) + S.mentionnant(articles or [], nom, ticker)
    titres = list(dict.fromkeys(a["titre"] for a in sorted(actus, key=lambda a: -a["ts"])))
    ton, raison_ton = ton_presse(nom, ticker, titres, ia)
    secteur = secteur_de(ticker, info)
    b = etat.get("briefing") or {}
    impact = (b.get("secteurs") or {}).get(secteur, b.get("climat"))
    sa, ss = LR.signal(LR.cle_actif(ticker)), LR.signal(f"secteur:{secteur}")     # armée de renseignement
    if sa and sa["confiance"] >= 0.3 and sa["n"] >= 3:
        ton = sa["valeur"] if ton is None else (ton + sa["valeur"]) / 2
        raison_ton += f" · renseignement : {sa['n']} infos, ton {sa['valeur']:+.1f}"
    if ss and ss["confiance"] >= 0.3:
        impact = ss["valeur"] if impact is None else (impact + ss["valeur"]) / 2
    r = N.noter(df, info, ton, impact, detenu)
    if r is None:
        return None
    return {"ticker": ticker, "nom": nom, "devise": info.get("currency") or ("EUR" if ticker.endswith("-EUR") else ""),
            "secteur": secteur, "detenu": detenu, "ts": time.time(), "note": r["note"], "avis": r["avis"],
            "raisons": r["raisons"], "action": r["action"], "urgence": r["urgence"], "texte": r["texte"],
            "stop": r["stop"], "objectif": r["objectif"], "cours": r["indicateurs"]["close"],
            "rsi": r["indicateurs"]["rsi"], "perf_3m": r["indicateurs"]["perf_3m"],
            "titres": titres[:3], "ton_raison": raison_ton, "bougies": r.get("bougies", [])}


# ============================== RÉSOLUTION DES NOMS =======================
def _instruments_tr():
    try:
        from moteurs import tr_univers as U
        from moteurs import tr_yahoo as Y
        cache = Y.charger_cache()
        res = {}
        for i in U.lire():
            e = cache.get(i["isin"]) or {}
            if e.get("ticker"):
                res[e["ticker"]] = {"isin": i["isin"], "nom": i["nom"] or e.get("nom") or e["ticker"]}
        return res
    except Exception:
        return {}


def resoudre(texte, reseau=True):
    """« LVMH », « MC.PA », « FR0000121014 », « bitcoin » -> (ticker Yahoo, nom) ; None si introuvable."""
    brut = (texte or "").strip()
    t = brut.upper()
    if not t:
        return None
    if t in CRYPTOS_NOMS:
        t = CRYPTOS_NOMS[t]
    bases = {c.split("-")[0]: c for c in config.MARCHES_CRYPTOS}
    if t in bases:
        return bases[t], t
    instruments = _instruments_tr()
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", t):                          # ISIN
        for tick, i in instruments.items():
            if i["isin"] == t:
                return tick, i["nom"]
        if reseau:
            try:
                from moteurs import tr_yahoo as Y
                r = Y.chercher_isin(t)
                if r:
                    return r["ticker"], r.get("nom") or t
            except Exception:
                return None
        return None
    if t in instruments:
        return t, instruments[t]["nom"]
    trouves = [(tick, i["nom"]) for tick, i in instruments.items() if i["nom"] and t in i["nom"].upper()]
    if trouves:
        return sorted(trouves, key=lambda x: len(x[1]))[0]
    if re.fullmatch(r"[\^A-Z0-9.=\-]{1,15}", t):                               # ticker Yahoo tel quel
        return t, t
    return None


def candidats(etat):
    """Ordre de priorité : ce que tu détiens, ta liste, les cryptos, puis les titres retenus par la veille TR."""
    vus, res = set(), []

    def ajouter(ticker, nom, detenu):
        if ticker and ticker not in vus:
            vus.add(ticker)
            res.append((ticker, nom, detenu))
    for x in config.MARCHES_PORTEFEUILLE:
        r = resoudre(x, reseau=False) or (x.upper(), x)
        ajouter(r[0], r[1], True)
    for x in config.MARCHES_SUIVIS:
        r = resoudre(x, reseau=False) or (x.upper(), x)
        ajouter(r[0], r[1], False)
    for c in config.MARCHES_CRYPTOS:
        ajouter(c, c.split("-")[0], False)
    selection = []
    try:
        with open("tr_etat.json", encoding="utf-8") as f:
            selection = (json.load(f).get("prefiltre") or {}).get("selection") or []
    except (OSError, ValueError):
        pass
    for i in selection[:config.MARCHES_NOTES_MAX]:
        ajouter(i.get("ticker"), i.get("nom"), False)
    if not selection:                                   # veille TR pas encore prête : grandes valeurs dispo chez TR
        for t in GRANDES_VALEURS:
            ajouter(t, None, False)
    return res


# ================================= TEXTES =================================
NOMS_AVIS = {"technique": "graphique", "analystes": "analystes", "fondamentaux": "comptes",
             "actualite": "presse", "contexte": "contexte mondial"}
TON = {-2: "très négatif", -1: "négatif", 0: "neutre", 1: "positif", 2: "très positif"}
FLECHE = {-2: "🔴", -1: "🟠", 0: "⚪", 1: "🟢", 2: "🟢🟢"}


def texte_fiche(f):
    if not f:
        return "Pas de note disponible."
    avis = " · ".join(f"{NOMS_AVIS.get(k, k)} {N.fr(round(v, 1))}" for k, v in f["avis"].items() if v is not None)
    lignes = [f"{N.etoiles(f['note'])} {N.fr(f['note'])}/5 — {f['nom']} ({f['ticker']}) : {N.libelle(f['note'])}",
              f"👉 {f['action']} : {f['texte']}",
              f"Cours {f['cours']:.4g} {f.get('devise', '')} · 3 mois {f['perf_3m']:+.0f} % · RSI {f['rsi']:.0f}"
              if f.get("perf_3m") is not None else f"Cours {f['cours']:.4g} {f.get('devise', '')}",
              f"Détail (sur 5) : {avis}"]
    if f.get("raisons"):
        lignes.append("Pourquoi : " + " ; ".join(f["raisons"][:5]))
    if f.get("bougies"):
        lignes.append("Bougie d'hier : " + " ; ".join(f["bougies"]))
    lignes.append(f"Presse : {f.get('ton_raison', '')}")
    for t in f.get("titres", [])[:2]:
        lignes.append(f"  • {t[:140]}")
    lignes.append(f"Note du {_heure(f['ts'])} · indicatif, ce n'est pas un conseil en investissement.")
    return "\n".join(lignes)


def texte_reperes(rep):
    if not rep:
        return ""
    return "📈 Repères : " + " · ".join(f"{v['nom']} {v['j1']:+.1f} % (5 j {v['j5']:+.1f} %)" for v in rep.values())


def texte_briefing(b, complet=False):
    if not b:
        return "🌍 Pas encore de lecture de la presse (première lecture dans quelques minutes)."
    lignes = [f"🌍 Climat mondial : {FLECHE.get(b['climat'], '')} {TON.get(b['climat'], '?')} "
              f"({b['n_titres']} titres, {b['sources_ok']}/{b['sources_total']} sources, {_heure(b['ts'])}"
              f"{', synthèse IA' if b.get('ia') else ', sans IA'})", b.get("resume", "")]
    themes = b.get("themes") or {}
    if complet:
        for t, nom in S.THEMES.items():
            if t in themes:
                lignes.append(f"{nom} {FLECHE.get(themes[t]['tendance'], '')} {themes[t]['fait_cle']}")
        if b.get("secteurs"):
            lignes.append("Secteurs : " + " · ".join(f"{SECTEURS_FR.get(s, s)} {FLECHE.get(v, '')}"
                                                     for s, v in sorted(b["secteurs"].items(), key=lambda x: -x[1])))
    if b.get("risques"):
        lignes.append("⚠️ Risques : " + " | ".join(b["risques"]))
    if b.get("opportunites"):
        lignes.append("💡 Pistes : " + " | ".join(b["opportunites"]))
    return "\n".join(x for x in lignes if x)


def texte_top(etat, n=10):
    notes = [f for f in etat["notes"].values() if not f.get("detenu")]
    notes.sort(key=lambda f: (-f["note"], f["action"] != "ACHETER"))
    if not notes:
        return "⭐ Notes : en cours de calcul."
    return "⭐ Meilleures notes du jour :\n" + "\n".join(
        f"{N.fr(f['note'])}/5 {f['nom'][:28]} ({f['ticker']}) → {f['action']}" for f in notes[:n])


def texte_portefeuille(etat):
    detenus = [f for f in etat["notes"].values() if f.get("detenu")]
    if not detenus:
        return "💼 Portefeuille : non renseigné (Termius : bots marches-portefeuille MC.PA,AAPL,BTC)"
    return "💼 Tes titres :\n" + "\n".join(
        f"{'🚨' if f['urgence'] else '•'} {f['nom'][:28]} {N.fr(f['note'])}/5 → {f['action']}" for f in detenus)


def texte_statut(etat=None):
    etat = etat or charger_etat()
    blocs = [texte_briefing(etat["briefing"]), texte_reperes(etat["reperes"]), texte_top(etat, 5),
             texte_portefeuille(etat), "Plus : /briefing · /note NOM · rien n'est acheté automatiquement."]
    return "\n\n".join(b for b in blocs if b)


def demander_note(texte):
    """Appelé par le bot principal pour /note : réponse immédiate si la note est fraîche, sinon mise en file."""
    etat = charger_etat()
    r = resoudre(texte, reseau=False)
    if r and r[0] in etat["notes"] and time.time() - etat["notes"][r[0]]["ts"] < config.MARCHES_NOTES_VALIDITE_H * 3600:
        return texte_fiche(etat["notes"][r[0]])
    with open(FICHIER_DEMANDES, "a", encoding="utf-8") as f:
        f.write(texte.strip() + "\n")
    return f"🔎 Analyse de « {texte.strip()} » lancée : la note arrive ici dans 1 à 2 minutes."


# ================================== BOUCLE ================================
def _lire_demandes():
    if not os.path.exists(FICHIER_DEMANDES):
        return []
    tmp = FICHIER_DEMANDES + ".en_cours"
    os.replace(FICHIER_DEMANDES, tmp)
    with open(tmp, encoding="utf-8") as f:
        demandes = [x.strip() for x in f if x.strip()]
    os.remove(tmp)
    return list(dict.fromkeys(demandes))[:10]


def un_tour(etat, yahoo, ia=None, lire_flux=None, maintenant=None):
    maintenant = maintenant or time.time()
    if maintenant < etat.get("pause_jusqua", 0):
        return
    articles = None
    # 1. Presse mondiale et repères
    if maintenant - (etat["briefing"].get("ts") or 0) >= config.MARCHES_BRIEFING_H * 3600:
        articles = LR.articles(48) if (lire_flux is None and LR.frais()) else []
        if articles:                                   # l'armée de renseignement a déjà tout lu : on s'en sert
            sources = {src: "ok" for src in {a["source"] for a in articles}}
        else:
            articles, sources = S.collecter(lire=lire_flux, pause_s=0 if lire_flux else 0.3)
        avant = etat["briefing"].get("climat")
        etat["briefing"] = faire_briefing(articles, sources, ia)
        etat["reperes"] = reperes(yahoo)
        etat["_titres"] = [{"titre": a["titre"], "ts": a["ts"]} for a in articles[:400]]
        log(f"Presse lue : {len(articles)} titres, {etat['briefing']['sources_ok']}/"
            f"{etat['briefing']['sources_total']} sources, climat {etat['briefing']['climat']}")
        if etat["briefing"]["climat"] <= -2 and (avant is None or avant > -2):
            alerte("🔴 Climat mondial très négatif\n" + texte_briefing(etat["briefing"]))
    articles = articles or etat.get("_titres") or []
    # 2. Demandes /note
    for d in _lire_demandes():
        r = resoudre(d)
        f = noter_titre(r[0], r[1], r[0] in {c[0] for c in candidats(etat) if c[2]}, etat, yahoo, articles, ia) \
            if r else None
        if f:
            etat["notes"][f["ticker"]] = f
        alerte(texte_fiche(f) if f else f"❓ « {d} » introuvable ou sans cours sur Yahoo. Essaie le ticker "
                                          "(ex. MC.PA) ou l'ISIN.", important=False)
    # 3. Notes du jour (quelques titres par tour)
    faits = 0
    jour = dt.date.today().isoformat()
    for ticker, nom, detenu in candidats(etat):
        if faits >= config.MARCHES_PAR_TOUR:
            break
        ancienne = etat["notes"].get(ticker)
        if ancienne and maintenant - ancienne["ts"] < config.MARCHES_NOTES_VALIDITE_H * 3600 \
                and ancienne.get("detenu") == detenu:
            continue
        faits += 1
        f = noter_titre(ticker, nom, detenu, etat, yahoo, articles, ia)
        if not f:
            continue
        etat["notes"][ticker] = f
        if detenu and f["urgence"] and not (ancienne and ancienne.get("urgence")):
            alerte(f"🚨 Un de tes titres passe à « {f['action']} »\n{texte_fiche(f)}")
        elif not detenu and f["note"] >= 5 and f["action"] == "ACHETER" \
                and not (ancienne and ancienne["note"] >= 5):
            n = etat["alertes"].get(jour, 0)
            if n < config.MARCHES_ALERTES_JOUR:
                etat["alertes"] = {jour: n + 1}
                alerte(f"🌟 Note 5/5\n{texte_fiche(f)}")
    # 4. Rapport quotidien
    heure = dt.datetime.fromtimestamp(maintenant).hour
    if heure >= config.MARCHES_RAPPORT_HEURE and etat.get("rapport_date") != jour and etat["briefing"] \
            and len(etat["notes"]) >= min(10, len(candidats(etat))):
        etat["rapport_date"] = jour
        alerte("🗞 Rapport marchés du jour\n\n" + texte_statut(etat), important=False)
    # ménage : notes de plus de 7 jours
    etat["notes"] = {t: f for t, f in etat["notes"].items() if maintenant - f["ts"] < 7 * 86400}


def boucle():
    if not config.MARCHES_ACTIF:
        log("Veille marchés désactivée (MARCHES_ACTIF=0).")
        return 0
    alerte("🌍 Veille marchés démarrée : presse mondiale toutes les "
           f"{config.MARCHES_BRIEFING_H:g} h, notes de 0 à 5 et moments d'achat / de vente (aucun ordre passé). "
           f"Rapport chaque jour vers {config.MARCHES_RAPPORT_HEURE} h. Commandes : /marches /briefing /note NOM",
           important=False)
    yahoo, derniere_erreur = Yahoo(), 0.0
    while True:
        etat = charger_etat()
        try:
            un_tour(etat, yahoo)
        except LimiteYahoo as e:
            etat["pause_jusqua"] = time.time() + PAUSE_YAHOO_S
            log(f"Yahoo limite les requêtes ({e}) : pause de {PAUSE_YAHOO_S // 60} min")
        except Exception as e:
            log("Erreur veille marchés : " + traceback.format_exc()[-1500:])
            if time.time() - derniere_erreur > 3600:
                derniere_erreur = time.time()
                alerte(f"⚠️ Veille marchés : erreur ({type(e).__name__}: {str(e)[:150]}). Elle continue ; "
                       "détail : bots marches-journal", important=False)
        try:
            sauver_etat(etat)
        except Exception:                                  # disque plein... : la veille continue quand même
            log("Sauvegarde de l'état impossible : " + traceback.format_exc()[-800:])
        time.sleep(60)


# ================================== TEST ==================================
def mode_test(yahoo=None, lire_flux=None):
    """Diagnostic depuis le serveur (bots marches-test) : aucune alerte Telegram."""
    import alertes
    alertes._ACTIF = False
    ok = True
    print("1) Presse mondiale (flux RSS publics)...")
    articles, sources = S.collecter(lire=lire_flux, pause_s=0 if lire_flux else 0.2)
    for nom, e in sources.items():
        print(f"   {'✔' if e.startswith('ok') else '✖'} {nom} : {e}")
    n_ok = sum(1 for e in sources.values() if e.startswith("ok"))
    print(f"   → {n_ok}/{len(sources)} sources lisibles, {len(articles)} titres de moins de 48 h")
    ok = ok and n_ok >= len(sources) // 2
    b = faire_briefing(articles, sources)
    print("   " + texte_briefing(b, complet=True).replace("\n", "\n   "))
    print(f"2) Synthèse IA : {'clé Anthropic présente' if config.ANTHROPIC_API_KEY else 'pas de clé (lecture par mots-clés)'}")
    print("3) Yahoo Finance : notes d'essai...")
    yahoo = yahoo or Yahoo()
    etat = {"briefing": b, "notes": {}}
    for t, nom in (("MC.PA", "LVMH"), ("AAPL", "Apple"), ("BTC-EUR", "Bitcoin")):
        try:
            f = noter_titre(t, nom, False, etat, yahoo, articles)
            print(("   " + texte_fiche(f).replace("\n", "\n   ")) if f else f"   ✖ {t} : pas de cours")
            ok = ok and f is not None
        except Exception as e:
            ok = False
            print(f"   ✖ {t} : {type(e).__name__} {str(e)[:150]}")
        time.sleep(1)
    print("\n✅ Veille marchés opérationnelle." if ok else "\n❌ Problème ci-dessus : envoie une capture à Claude.")
    return 0 if ok else 1


def mode_note(texte, yahoo=None):
    import alertes
    alertes._ACTIF = False
    r = resoudre(texte)
    if not r:
        print(f"✖ « {texte} » introuvable. Essaie le ticker Yahoo (ex. MC.PA) ou l'ISIN.")
        return 1
    etat = charger_etat()
    f = noter_titre(r[0], r[1], texte.upper() in [x.upper() for x in config.MARCHES_PORTEFEUILLE], etat,
                    yahoo or Yahoo(), etat.get("_titres"))
    print(texte_fiche(f) if f else f"✖ Pas de cours pour {r[0]} sur Yahoo.")
    return 0 if f else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(mode_test())
    if "--note" in sys.argv:
        i = sys.argv.index("--note")
        sys.exit(mode_note(" ".join(sys.argv[i + 1:])))
    try:
        sys.exit(boucle())
    except KeyboardInterrupt:
        log("Veille marchés arrêtée.")
