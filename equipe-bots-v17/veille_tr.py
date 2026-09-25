"""VEILLE TRADE REPUBLIC — processus séparé du bot Binance (service equipe-bots-tr).

1. Univers : la liste officielle publiée par Trade Republic (PDF public), relue chaque jour.
2. Yahoo Finance : chaque ISIN (actions, ETF) est relié une fois pour toutes à son symbole Yahoo (cache).
3. Tri quotidien : titres liquides (échanges médians en euros) en tendance journalière haussière -> présélection.
4. Toutes les 15 min : filtre 4 unités (4h/1h/15m/5m, bougies fermées) + coûts TR -> signal d'ACHAT Telegram.
5. Suivi de chaque signal : sécurisation, stop suiveur, objectif, stop, retournement -> signaux de VENTE.

AUCUN ordre n'est passé chez Trade Republic : c'est toi qui décides et qui agis dans l'application.
Lancement : python veille_tr.py | test : python veille_tr.py --test | univers : python veille_tr.py --univers [fichier.pdf]
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

if __name__ == "__main__":             # journal séparé (tr.log) : ne se mélange pas avec celui du bot Binance
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | TR | %(message)s",
                        handlers=[RotatingFileHandler("tr.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
                                  logging.StreamHandler()])

import datetime as dt
import json
import os
import time
import traceback

import config
from alertes import alerte, log
from moteurs import tr_univers as U

FICHIER_ETAT = "tr_etat.json"
HISTORIQUE_MAX = 500


# ================================ ÉTAT ==================================
def charger_etat():
    try:
        with open(FICHIER_ETAT, encoding="utf-8") as f:
            etat = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        etat = {}
    for cle, defaut in (("univers", {}), ("correspondance", {}), ("prefiltre", {}), ("analyse", {}),
                        ("jour", {}), ("suivis", {}), ("historique", []), ("pauses", {}), ("yahoo", {})):
        etat.setdefault(cle, defaut)
    return etat


def sauver_etat(etat):
    tmp = FICHIER_ETAT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False)
    os.replace(tmp, FICHIER_ETAT)


def _pct(x):
    return ("+" if x >= 0 else "−") + f"{abs(x):.1f}".replace(".", ",") + " %"


def jour_ouvre(ts=None):
    """Bourses fermées le week-end : Yahoo épargné."""
    return dt.datetime.fromtimestamp(ts or time.time(), dt.timezone.utc).weekday() < 5


def tr_ouvert(ts=None):
    """Trade Republic (LS Exchange) : actions et ETF du lundi au vendredi, 7 h 30 – 23 h, heure de Paris.
    Nouveaux signaux d'achat jusqu'à 22 h 30 seulement, pour laisser le temps de passer l'ordre."""
    from zoneinfo import ZoneInfo
    t = dt.datetime.fromtimestamp(ts or time.time(), ZoneInfo("Europe/Paris"))
    hm = t.hour * 60 + t.minute
    return t.weekday() < 5 and config.TR_OUVERTURE_MIN <= hm < config.TR_FIN_SIGNAUX_MIN


def _heure(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M") if ts else "jamais"


def yahoo_en_pause(etat):
    return etat["yahoo"].get("pause_jusqu", 0) > time.time()


def mettre_en_pause(etat, raison):
    etat["yahoo"]["pause_jusqu"] = time.time() + config.TR_PAUSE_YAHOO_MIN * 60
    etat["yahoo"]["raison"] = raison[:120]
    log(f"Yahoo indisponible ({raison}) : pause {config.TR_PAUSE_YAHOO_MIN} min.")
    if time.time() - etat["yahoo"].get("derniere_alerte", 0) > 6 * 3600:
        etat["yahoo"]["derniere_alerte"] = time.time()
        alerte(f"⏸ Veille Trade Republic : Yahoo (la source des prix) ne répond plus pour l'instant. "
               f"Pause de {config.TR_PAUSE_YAHOO_MIN} min puis reprise toute seule. Rien à faire.", important=False)


# ============================== 1. UNIVERS ===============================
def etape_univers(etat, force=False, pdf=None):
    u = etat["univers"]
    existe = os.path.exists(config.UNIVERS_TR_FICHIER)
    delai = config.TR_UNIVERS_MAJ_H * 3600 if existe else 1800        # sans univers : nouvel essai toutes les 30 min
    if not force and not pdf and time.time() - u.get("tentative", 0) < delai:
        return u
    res = U.mettre_a_jour(pdf_local=pdf)
    u["tentative"] = time.time()
    if res["ok"]:
        nouveau = res["n"] != u.get("n")
        u.update({k: res[k] for k in ("ok", "ts", "n", "source", "par_type")})
        u.pop("erreur", None)
        log(f"Univers officiel TR : {res['n']} titres ({res['source']}) {res['par_type']}")
        if nouveau:
            alerte(f"🇪🇺 Univers Trade Republic à jour : {res['n']} titres "
                   f"({', '.join(f'{k} {v}' for k, v in sorted(res['par_type'].items()))}).", important=False)
    else:
        u["erreur"] = res["erreur"]
        log(f"Univers officiel TR non mis à jour : {res['erreur']}")
        if not os.path.exists(config.UNIVERS_TR_FICHIER) and time.time() - u.get("alerte_ts", 0) > 86400:
            u["alerte_ts"] = time.time()
            alerte(f"⚠️ Veille TR : liste officielle Trade Republic introuvable ({res['erreur'][:200]}).\n"
                   "Solution : télécharge le PDF « liste d'actions et ETF disponibles » sur le site Trade Republic, "
                   "envoie-le sur le serveur (SFTP) puis : bots tr-univers /root/NOM.pdf")
    return u


# ========================== 2. CORRESPONDANCE ============================
def etape_correspondance(etat, univers, cache, budget_s):
    from moteurs import tr_yahoo as Y
    try:
        r = Y.cartographier(univers, cache, budget_s)
    finally:
        Y.sauver_cache(cache)
    suivables = [i for i in univers if i["kind"] in ("stock", "etf")]
    etat["correspondance"] = {"ts": time.time(), "suivables": len(suivables),
                              "reconnus": sum(1 for i in suivables if (cache.get(i["isin"]) or {}).get("ticker")),
                              "restants": r["restants"]}
    if r["faits"]:
        log(f"Yahoo : {r['faits']} ISIN cherchés, {r['trouves']} reconnus, {r['restants']} restants")
    return r


def instruments_suivables(univers, cache):
    """ticker Yahoo -> {isin, nom, ticker, devise, kind}"""
    res = {}
    for i in univers:
        e = cache.get(i["isin"]) or {}
        if e.get("ticker") and e["ticker"] not in res:
            res[e["ticker"]] = {"isin": i["isin"], "nom": i["nom"] or e.get("nom") or i["isin"],
                                "ticker": e["ticker"], "devise": e.get("devise"), "kind": i["kind"]}
    return res


# ============================ 3. TRI QUOTIDIEN ============================
def etape_prefiltre(etat, instruments, budget_s, telecharger=None):
    """Évalue en journalier les titres pas encore vus aujourd'hui (reprise possible), puis recalcule la sélection."""
    from moteurs import tr_yahoo as Y
    from moteurs import tr_analyse as A
    telecharger = telecharger or Y.telecharger
    p = etat["prefiltre"]
    aujourdhui = dt.date.today().isoformat()
    if p.get("date") != aujourdhui:
        ancienne = p.get("selection") or []           # gardée tant que le tri du jour n'est pas terminé
        p.clear()
        p.update({"date": aujourdhui, "res": {}, "selection": ancienne})
    if p.get("taux_date") != aujourdhui:
        p["taux"] = Y.taux_de_change({x["devise"] for x in instruments.values()})
        p["taux_date"] = aujourdhui
    a_faire = [t for t in instruments if t not in p["res"]]
    debut, maintenant_ms = time.time(), time.time() * 1000
    for k in range(0, len(a_faire), 50):
        if time.time() - debut > budget_s:
            break
        paquet = a_faire[k:k + 50]
        cours = telecharger(paquet, "6mo", "1d")
        for t in paquet:
            r = A.journalier(cours.get(t), p["taux"].get(instruments[t]["devise"] or ""), maintenant_ms)
            p["res"][t] = r or {"ok": False}
    restants = sum(1 for t in instruments if t not in p["res"])
    nouvelle = selection(p["res"], instruments)
    if not restants or len(nouvelle) >= len(p.get("selection") or []):
        p["selection"] = nouvelle
    p["evalues"] = len(p["res"])
    p["restants"] = restants
    p["ts"] = time.time()
    return restants


def selection(resultats, instruments):
    bons = [(t, r) for t, r in resultats.items()
            if r.get("ok") and r["haussier"] and r["liq"] >= config.TR_VOLUME_MIN_EUR and r["age_j"] <= 6
            and t in instruments]
    bons.sort(key=lambda x: -x[1]["liq"])
    return [{**instruments[t], "liq": r["liq"]} for t, r in bons[:config.TR_PRESELECTION]]


# ========================== 4-5. INTRADAY =================================
def texte_signal(pos, a):
    from moteurs import tr_analyse as A
    heure = dt.datetime.fromtimestamp(a["fin_bougie_ms"] / 1000).strftime("%H:%M")
    stop, obj, secu = ((pos['stop'] / pos['entree'] - 1) * 100, (pos['objectif'] / pos['entree'] - 1) * 100,
                       pos['r'] / pos['entree'] * 100)
    return (f"🟢 IDÉE D'ACHAT — Trade Republic (c'est toi qui passes l'ordre)\n"
            f"{pos['nom']}\nCode ISIN à chercher dans l'app : {pos['isin']}\n"
            f"Prix sur Yahoo : {A.prix_lisible(pos['entree'])} {pos.get('devise') or ''} à {heure}\n"
            f"✅ À la hausse sur les 4 horizons de temps (4 h, 1 h, 15 min, 5 min)\n"
            f"🛡 Après l'achat, place un ordre stop à {_pct(stop)} sous ton prix d'achat (vente de protection)\n"
            f"🎯 Objectif : revendre vers {_pct(obj)}\n"
            f"🔒 Dès {_pct(secu)} de gain, remonte ton ordre stop à ton prix d'achat : tu ne pourras plus perdre\n"
            f"Frais Trade Republic (1 € à l'achat + 1 € à la vente) pour {config.TR_MONTANT_ORDRE_EUR:.0f} € : "
            f"{pos['cout_pct']:.2f} % → gain espéré après frais ≈ {_pct(pos['net_pct'])}\n"
            "⚠️ Ces idées n'ont pas encore fait leurs preuves : suis leur bilan avec /tr. "
            "Le prix Trade Republic en € n'est pas le même que sur Yahoo : raisonne en %.")


def texte_cloture(c):
    titres = {"stop": "🔴 VENDS — le prix a touché ton seuil de protection",
              "objectif": "🟢 VENDS — objectif atteint",
              "retournement": "⚠️ Vente conseillée — la tendance repart à la baisse",
              "duree": f"⌛ Fin du suivi après {config.TR_SUIVI_JOURS} jours — à toi de décider"}
    return (f"{titres[c['raison']]} (Trade Republic)\n{c['nom']} · ISIN {c['isin']}\n"
            f"Depuis l'idée d'achat : {_pct(c['brut_pct'])} avant frais, {_pct(c['net_pct'])} après frais")


def etape_intraday(etat, instruments, memoire, telecharger=None, maintenant=None):
    from moteurs import tr_yahoo as Y
    from moteurs import tr_analyse as A
    telecharger = telecharger or Y.telecharger
    maintenant = maintenant or time.time()
    sel = {x["ticker"]: x for x in etat["prefiltre"].get("selection", [])}
    suivis = etat["suivis"]
    tickers = list(dict.fromkeys(list(sel) + [p["ticker"] for p in suivis.values()]))
    etat["analyse"] = {"ts": maintenant, "n": len(tickers), "a_jour": 0, "signaux": 0}
    if not tickers:
        return
    if maintenant - memoire.get("h1_ts", 0) > 55 * 60 or any(t not in memoire.get("h1_demandes", ()) for t in tickers):
        memoire["h1"] = telecharger(tickers, "60d", "1h")         # bougies 1 h : une fois par heure suffit
        memoire["h1_ts"], memoire["h1_demandes"] = maintenant, set(tickers)
    cours5 = telecharger(tickers, "5d", "5m")
    lectures = {t: A.analyser_titre(cours5.get(t), memoire["h1"].get(t), maintenant * 1000) for t in tickers}
    etat["analyse"]["a_jour"] = sum(1 for a in lectures.values() if a.get("ok") and a["donnees_ok"])

    # 5. Suivi des signaux déjà envoyés (VENTE)
    for isin, pos in list(suivis.items()):
        a = lectures.get(pos["ticker"])
        evts, cloture = A.suivre(pos, a, maintenant)
        if a and a.get("ok"):
            pos["dernier_prix"] = a["prix"]
        ferme = "" if tr_ouvert(maintenant) else "\n🕗 Trade Republic est fermé : à faire dès l'ouverture (7 h 30)."
        for _, texte, important in evts:
            alerte(f"🇪🇺 {pos['nom']} : {texte}{ferme}", important=important)
        if cloture:
            alerte(texte_cloture(cloture) + ferme)
            etat["historique"] = (etat["historique"] + [cloture])[-HISTORIQUE_MAX:]
            etat["pauses"][isin] = maintenant
            del suivis[isin]

    # 4. Nouveaux signaux (ACHAT)
    jour = etat["jour"]
    if jour.get("date") != dt.date.today().isoformat():
        jour.clear()
        jour.update({"date": dt.date.today().isoformat(), "signaux": 0})
    candidats = []
    if not tr_ouvert(maintenant):
        lectures_achat = {}                           # TR fermé : aucun signal d'achat inexécutable
        log("Trade Republic fermé : pas de nouveau signal d'achat (suivi des signaux en cours maintenu).")
    else:
        lectures_achat = lectures
    for t, a in lectures_achat.items():
        info = sel.get(t)
        if not info or not a.get("ok") or info["isin"] in suivis:
            continue
        if maintenant - etat["pauses"].get(info["isin"], 0) < config.TR_PAUSE_TITRE_H * 3600:
            continue
        opp = A.opportunite(a)
        if opp.allowed:
            candidats.append((opp.net_potential_pct, t, a, opp))
    candidats.sort(key=lambda x: -x[0])
    place = max(0, config.TR_SIGNAUX_MAX_JOUR - jour["signaux"])
    for _, t, a, opp in candidats[:place]:
        info = sel[t]
        pos = A.nouvelle_position({k: info[k] for k in ("isin", "nom", "ticker", "devise")}, a, opp, maintenant)
        suivis[info["isin"]] = pos
        jour["signaux"] += 1
        etat["analyse"]["signaux"] += 1
        alerte(texte_signal(pos, a))
    if len(candidats) > place:
        log(f"{len(candidats) - place} signal(s) TR non envoyé(s) : limite de {config.TR_SIGNAUX_MAX_JOUR} par jour")
    etat["pauses"] = {k: v for k, v in etat["pauses"].items() if maintenant - v < config.TR_PAUSE_TITRE_H * 3600}


# ================================ STATUT (/tr) =============================
def texte_statut(etat=None):
    etat = etat or charger_etat()
    u, c, p, a = etat["univers"], etat["correspondance"], etat["prefiltre"], etat["analyse"]
    lignes = ["🇪🇺 Veille Trade Republic (idées que tu passes toi-même, aucun ordre automatique)"]
    if u.get("n"):
        lignes.append(f"Titres disponibles chez Trade Republic : {u['n']} (liste officielle du {_heure(u.get('ts'))})")
    else:
        n = len(U.lire())
        lignes.append(f"Titres suivis : {n}" if n else "Liste officielle : pas encore chargée")
    if u.get("erreur"):
        lignes.append("⚠️ La dernière lecture de la liste officielle a échoué : l'ancienne liste est gardée.")
    if c.get("suivables"):
        lignes.append(f"Retrouvés sur Yahoo (source des prix) : {c['reconnus']} sur {c['suivables']}"
                      + (f" — recherche en cours, encore {c['restants']}" if c.get("restants") else ""))
    lignes.append(f"Surveillés de près aujourd'hui : {len(p.get('selection', []))} titres (les plus échangés "
                  f"et en hausse, parmi {p.get('evalues', 0)} étudiés)")
    if a.get("ts"):
        lignes.append(f"Dernier passage : {_heure(a['ts'])}"
                      + (" (bourses fermées)" if a["n"] and not a["a_jour"] else ""))
    lignes.append(f"Idées d'achat aujourd'hui : "
                  f"{etat['jour'].get('signaux', 0) if etat['jour'].get('date') == dt.date.today().isoformat() else 0}"
                  f" sur {config.TR_SIGNAUX_MAX_JOUR} maximum")
    if etat["suivis"]:
        lignes.append(f"Idées en cours de suivi ({len(etat['suivis'])}) :")
        for pos in etat["suivis"].values():
            ecart = (pos.get("dernier_prix", pos["entree"]) / pos["entree"] - 1) * 100
            lignes.append(f"• {pos['nom'][:30]} : {_pct(ecart)} depuis l'idée · protection à "
                          f"{_pct((pos['stop'] / pos['entree'] - 1) * 100)}" + (" 🔒" if pos["securise"] else ""))
    h = etat["historique"]
    if h:
        gagnants = sum(1 for x in h if x["net_pct"] > 0)
        moyenne = sum(x["net_pct"] for x in h) / len(h)
        lignes.append(f"Bilan des idées terminées : {len(h)} · {gagnants / len(h) * 100:.0f} % gagnantes · en moyenne "
                      f"{_pct(moyenne)} après frais (pour {etat.get('montant', config.TR_MONTANT_ORDRE_EUR):.0f} € par ordre)")
    else:
        lignes.append("Bilan des idées terminées : aucune pour l'instant")
    lignes.append("Trade Republic est " + ("ouvert ✅" if tr_ouvert() else "fermé (lundi-vendredi 7 h 30 – 23 h)"))
    if yahoo_en_pause(etat):
        lignes.append(f"⏸ Yahoo ne répond pas : reprise vers {_heure(etat['yahoo']['pause_jusqu'])}")
    return "\n".join(lignes)


# ================================ BOUCLE ==================================
def un_tour(etat, memoire):
    from moteurs import tr_yahoo as Y
    etat["montant"] = config.TR_MONTANT_ORDRE_EUR            # lu par /tr (processus du bot Binance)
    etape_univers(etat)
    univers = U.lire()
    if yahoo_en_pause(etat) or not univers:
        return
    cache = Y.charger_cache()
    instruments = instruments_suivables(univers, cache)
    intervalle = config.TR_INTERVALLE_MIN * 60
    try:
        if jour_ouvre() and time.time() >= etat["analyse"].get("ts", 0) + intervalle and \
                (etat["prefiltre"].get("selection") or etat["suivis"]):
            etape_intraday(etat, instruments, memoire)
            sauver_etat(etat)
        prochaine = etat["analyse"].get("ts", 0) + intervalle
        if prochaine <= time.time():                 # rien à analyser pour l'instant : tout le temps au travail de fond
            prochaine = time.time() + intervalle
        budget = min(config.TR_BUDGET_LOT_S, prochaine - time.time() - 10)
        if budget > 20 and any(True for _ in Y.a_chercher(univers, cache, time.time())):
            fin = time.time() + budget
            etape_correspondance(etat, univers, cache, budget)
            instruments = instruments_suivables(univers, cache)
            budget = fin - time.time()
        if budget > 20 and Y.verifier_devises(cache, min(budget, 60)):     # corrige les devises déjà en cache
            Y.sauver_cache(cache)
            instruments = instruments_suivables(univers, cache)
            budget = prochaine - time.time() - 10
        if budget > 20:
            etape_prefiltre(etat, instruments, budget)
    except Y.LimiteYahoo as e:
        mettre_en_pause(etat, str(e))


def boucle():
    if not config.TR_ACTIF:
        log("Veille TR désactivée (TR_ACTIF=0).")
        return 0
    alerte("🇪🇺 Veille Trade Republic démarrée : elle surveille les actions et ETF de Trade Republic et t'envoie des "
           "idées d'achat et de vente, que tu passes toi-même dans l'app. Bilan : /tr", important=False)
    memoire, derniere_erreur = {}, 0.0
    while True:
        etat = charger_etat()
        try:
            un_tour(etat, memoire)
        except Exception as e:
            log("Erreur veille TR : " + traceback.format_exc()[-1500:])
            if time.time() - derniere_erreur > 3600:
                derniere_erreur = time.time()
                alerte(f"⚠️ Veille TR : erreur ({type(e).__name__}: {str(e)[:150]}). Elle continue ; détail : bots tr-journal",
                       important=False)
        sauver_etat(etat)
        time.sleep(20)


# ================================ TEST ====================================
def mode_test():
    """Diagnostic en direct depuis le serveur (bots tr-test) : aucune alerte Telegram, aucun signal."""
    from moteurs import tr_yahoo as Y
    from moteurs import tr_analyse as A
    ok = True
    print("1) Liste officielle Trade Republic...")
    res = U.mettre_a_jour()
    if res["ok"]:
        print(f"   ✔ {res['n']} titres lus ({res['source']}) : {res['par_type']}")
    else:
        existant = len(U.lire())
        print(f"   ✖ {res['erreur']}" + (f"\n   (univers existant conservé : {existant} titres)" if existant else ""))
        ok = ok and bool(existant)
    print("2) Yahoo Finance : recherche par ISIN...")
    essais = [("US67066G1040", "stock", "NVIDIA"), ("DE0007164600", "stock", "SAP"), ("IE00B4L5Y983", "etf", "iShares MSCI World")]
    tickers = []
    for isin, genre, nom in essais:
        try:
            r = Y.chercher_isin(isin, genre)
            print(f"   {'✔' if r else '✖'} {nom} ({isin}) -> {r['ticker'] + ' ' + str(r['devise']) if r else 'introuvable'}")
            if r:
                tickers.append(r["ticker"])
        except Exception as e:
            ok = False
            print(f"   ✖ {nom} : {type(e).__name__} {str(e)[:120]}")
        time.sleep(1)
    if tickers:
        print("3) Cours 1 h et 5 min + filtre 4 unités...")
        try:
            h1, m5 = Y.telecharger(tickers, "60d", "1h"), Y.telecharger(tickers, "5d", "5m")
            for t in tickers:
                a = A.analyser_titre(m5.get(t), h1.get(t))
                if a["ok"]:
                    opp = A.opportunite(a)
                    print(f"   ✔ {t} : {len(m5[t])} bougies 5 min, dernière close il y a {a['age_min']:.0f} min "
                          f"({'à jour' if a['donnees_ok'] else 'bourse fermée ou différée'}) | "
                          + " ".join(f"{k}{'✅' if v else '❌'}" for k, v in a["checks"].items())
                          + f" | coût {opp.cost_pct:.2f} %, net {opp.net_potential_pct:+.2f} % -> "
                          + ("SIGNAL" if opp.allowed else "pas de signal"))
                else:
                    print(f"   ✖ {t} : {a['raison']}")
        except Exception as e:
            ok = False
            print(f"   ✖ téléchargement : {type(e).__name__} {str(e)[:150]}")
    else:
        ok = False
    print("\n✅ Veille TR opérationnelle." if ok else "\n❌ Problème ci-dessus : envoie une capture à Claude.")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(mode_test())
    if "--univers" in sys.argv:
        i = sys.argv.index("--univers")
        pdf = sys.argv[i + 1] if len(sys.argv) > i + 1 else None
        e = charger_etat()
        u = etape_univers(e, force=True, pdf=pdf)
        sauver_etat(e)
        print(f"✔ Univers : {u['n']} titres ({u.get('source')}) {u.get('par_type')}" if not u.get("erreur")
              else f"✖ {u['erreur']}")
        sys.exit(0 if not u.get("erreur") else 1)
    try:
        sys.exit(boucle())
    except KeyboardInterrupt:
        log("Veille TR arrêtée.")
