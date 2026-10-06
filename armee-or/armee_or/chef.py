"""CHEF D'ORCHESTRE — pilote toute l'armée de l'or, sans jamais s'arrêter.

- Chaque bot a son rythme ; il est lancé, chronométré, isolé (une panne n'arrête jamais les autres) et doit RENDRE
  COMPTE : succès ou erreur, durée, message, tout est enregistré (table « rapports »). Un bot en échec répété est
  relancé avec une attente croissante et signalé sur Telegram.
- Les pronostics sont enregistrés PUIS jugés quand leur horizon arrive : le chef n'écoute que les pronostiqueurs
  qui battent le naïf (poids = compétence récente).
- Décisions : seulement si l'avantage attendu dépasse nettement les coûts (strategie.py). Elles sont exécutées
  sur PAPIER, en parallèle pour chaque profil de levier, avec liquidations simulées.
- Si MetaTrader 5 est branché (compte DÉMO uniquement), l'exécutant passe aussi les décisions en vrais ordres de
  démo, plus une équipe d'entraînement au lot minimum (executant.py). Aucun ordre sur un compte réel.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import traceback

import numpy as np

from . import apprentissage, archive_mt5, base, bibliotheque, chandeliers, config, donnees, executant, flux, indicateurs as I, \
    levier as L, mt5, papier, pronostiqueurs as P, rythme, strategie as S, telegram, veille

_log = logging.getLogger("or.chef")
SOURCE_DECISION = "PAXGUSDT"            # plus long historique (2020→) + flux direct ; XAUUSDT sert de référence de prix
FENETRES = {"1h": 8000, "4h": 4000, "1d": 2500}
MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
PROFILS_DIRECT = ["x1", "x3", "x10", "x20 (max. UE)", "pro 1 % risqué"]


# ============================================================================ les bots
class Bot:
    def __init__(self, nom, famille, periode_s, fonction, fond=False):
        self.nom, self.famille, self.periode, self.fonction = nom, famille, periode_s, fonction
        self.fond = fond                    # travail lent (réseau, gros calcul) : dans son propre fil, sans bloquer
        self.fil = None                     # les bots rapides (sentinelle éclair, exécutant MT5)
        self.prochaine = 0.0
        self.echecs = 0
        self.ok = self.ko = 0
        self.dernier_message = ""
        self.derniere_erreur = None
        self.duree = 0.0

    def lancer(self, chef):
        if not self.fond:
            return self.executer(chef)
        if self.fil is not None and self.fil.is_alive():
            return None                                        # encore au travail : on ne l'empile pas
        import threading
        self.fil = threading.Thread(target=self.executer, args=(chef,), daemon=True, name=f"bot-{self.nom}")
        self.fil.start()
        return None

    def du(self, maintenant):
        return maintenant >= self.prochaine

    def executer(self, chef):
        debut = time.time()
        try:
            msg = self.fonction(chef) or "ok"
            self.ok += 1
            self.echecs = 0
            self.dernier_message = str(msg)[:300]
            self.prochaine = time.time() + self.periode
            succes = True
        except Exception as ex:
            self.ko += 1
            self.echecs += 1
            self.derniere_erreur = f"{type(ex).__name__}: {str(ex)[:200]}"
            self.dernier_message = self.derniere_erreur
            _log.warning("Bot %s en échec : %s", self.nom, traceback.format_exc()[-800:])
            self.prochaine = time.time() + min(3600, self.periode * 2 ** min(self.echecs, 6))
            succes = False
            if self.echecs == 5:
                telegram.alerte_rare(f"bot-{self.nom}", f"⚠️ Le bot « {self.nom} » échoue depuis 5 passages "
                                     f"({self.derniere_erreur}). Il est relancé avec une attente croissante ; les "
                                     "autres continuent.", 6 * 3600)
        self.duree = time.time() - debut
        try:
            with base.connexion() as c:
                c.execute("INSERT INTO rapports(ts, bot, ok, duree, message) VALUES(?,?,?,?,?)",
                          (time.time(), self.nom, int(succes), self.duree, self.dernier_message))
        except Exception:
            pass
        return succes

    def etat(self):
        return {"nom": self.nom, "famille": self.famille, "ok": self.ok, "ko": self.ko, "echecs_suite": self.echecs,
                "dernier_message": self.dernier_message, "duree_s": round(self.duree, 2)}


# ============================================================================ travail de chaque bot
def bot_vigie(chef):
    d = flux.prix_direct()
    if d is None:
        for s in config.SOURCES_DIRECT:                       # le chef tente lui-même un rattrapage REST
            try:
                flux.rattraper(s)
            except Exception:
                pass
        telegram.alerte_rare("flux", "🔴 Aucun cours en direct depuis plus d'une minute (Binance et COMEX). "
                             "Les vigies réessaient sans fin.", 3600, important=True)
        return "aucun cours frais"
    x, p = base.lire("direct:XAUUSDT"), base.lire("direct:PAXGUSDT")
    if x and p and time.time() - x["ts"] < 120 and time.time() - p["ts"] < 120:
        ecart = abs(p["prix"] / x["prix"] - 1) * 100
        base.ecrire("ecart_paxg_xau_pct", ecart)
        if ecart > 1.0:
            telegram.alerte_rare("ecart", f"⚠️ PAXG et XAUUSDT s'écartent de {ecart:.2f} % : cours à vérifier.", 3600)
    return f"{d['prix']:.2f} $ ({d['source']}, retard {retard_txt(d['retard_ms'])})"


def bot_archiviste(chef):
    depuis = int(time.time() * 1000) - 3 * 86_400_000
    for s in config.SOURCES_DIRECT:
        donnees.consolider(s, depuis_ms=depuis)
    if time.time() - (base.lire("comex_maj", 0) or 0) > 86400:
        from .marches_lies import telecharger
        ts, c = telecharger("GC=F", "1d", "1mo")
        if len(c):
            # clôtures seules : suffisant pour les comptes de fond (o = h = l = c)
            donnees.inserer("GC", "1d", [[int(t) * 1000 - int(t) * 1000 % 86_400_000, x, x, x, x, 0.0]
                                         for t, x in zip(ts, c)])
        base.ecrire("comex_maj", time.time())
    return "bougies consolidées"


def bot_marches(chef):
    from .marches_lies import releve
    r = releve()
    base.ecrire("marches", r)
    return f"contexte {r['contexte']:+.2f}, {len(r['marches'])} marchés"


def bot_rythme(chef):
    b = donnees.charger(SOURCE_DECISION, "1h", limite=2000)
    if len(b["c"]) < 600:
        return "historique insuffisant"
    e = rythme.etat(b)
    base.ecrire("rythme", e)
    if e["regime"] == "volatilité extrême":
        telegram.alerte_rare("volatilite", f"🌪 Volatilité extrême sur l'or (ATR {e['atr_pct']:.2f} % par heure) : "
                             "aucune nouvelle position papier, stops plus exposés au glissement.", 6 * 3600, True)
    return f"{e['regime']}, séance {e['seance']}"


def source_stats(tf):
    """Historique le plus long pour mesurer les motifs : XAUUSD du courtier MT5 s'il est plus fourni que PAXG."""
    with base.connexion() as c:
        n = {s: c.execute("SELECT COUNT(*) FROM bougies WHERE source=? AND tf=?", (s, tf)).fetchone()[0]
             for s in (archive_mt5.SOURCE, SOURCE_DECISION)}
    return archive_mt5.SOURCE if n[archive_mt5.SOURCE] > n[SOURCE_DECISION] else SOURCE_DECISION


def bot_eclair(chef):
    if not hasattr(chef, "eclair"):
        chef.eclair = veille.Eclair()
    return chef.eclair.observer()


def bot_niveaux(chef):
    return veille.surveiller_niveaux(SOURCE_DECISION)


def bot_tendances(chef):
    return veille.surveiller_tendances(SOURCE_DECISION)


def bot_microstructure(chef):
    return veille.surveiller_microstructure()


def bot_calendrier(chef):
    return veille.surveiller_calendrier()


def bot_actualites(chef):
    return veille.surveiller_actualites()


def bot_cot(chef):
    return veille.surveiller_cot()


def bot_archive_veille(chef):
    n = apprentissage.archiver_veille()
    apprentissage.releve_memoire()                            # compteurs de la base, une fois par heure
    return f"{n} observations archivées"


def bot_rattrapage(chef):
    dernier = (base.lire("apprentissage:rattrapage") or {}).get("ts", 0)
    if time.time() - dernier < 20 * 3600:                      # une fois par jour, même après un redémarrage
        return "historique déjà à jour aujourd'hui"
    bilan, erreurs = apprentissage.rattraper_historique()
    return f"{sum(bilan.values())} observations rattrapées" + (f" · indisponibles : {', '.join(erreurs)}" if erreurs else "")


def bot_examen(chef):
    dernier = (base.lire("apprentissage:examen") or {}).get("ts", 0)
    rattrapage = (base.lire("apprentissage:rattrapage") or {}).get("ts", 0)
    if not rattrapage or (time.time() - dernier < 20 * 3600 and dernier > rattrapage):
        return "examen à jour" if rattrapage else "en attente du rattrapage de l'historique"
    barres = {tf: donnees.charger(SOURCE_DECISION, tf, limite=FENETRES[tf]) for tf in ("1h", "4h", "1d")}
    resultats, seuil = apprentissage.examiner(barres)
    admis = [f"{n} ({tf})" for tf, r in resultats.items() for n, x in r.items() if x.get("admis")]
    anciens = set(base.lire("apprentissage:admis_precedents") or [])
    nouveaux = [a for a in admis if a not in anciens]
    if nouveaux:
        telegram.envoyer("🎓 Nouveaux signaux admis dans les décisions (ils battent le naïf, test de Diebold-Mariano "
                         f"z ≥ {seuil:.2f}, sur les deux moitiés de l'historique) : " + ", ".join(nouveaux))
    base.ecrire("apprentissage:admis_precedents", admis)
    return f"{sum(len(r) for r in resultats.values())} candidats examinés · admis : {', '.join(admis) or 'aucun'}"


def bot_frais(chef):
    deals = None
    if config.MT5_ACTIF:
        try:
            deals = mt5.appel("historique", depuis=base.lire("mt5:depuis") or time.time() - 30 * 86400)
        except mt5.ErreurMT5:
            deals = None
    m = apprentissage.mesurer_couts(deals)
    c = apprentissage.appliquer_couts()
    return ("frais réels " + (f"{c['aller_retour'] * 100:.4f} % aller-retour ({c['executions']} exécutions)" if c
                              else f"pas encore assez d'exécutions ({m.get('executions', 0)})"))


def bot_journal(chef):
    dernier = base.lire("journal:dernier")
    if dernier is None:                                       # premier journal un jour après l'installation
        base.ecrire("journal:dernier", time.time() - 6 * 86400)
        return "premier journal dans 24 h"
    if time.time() - dernier < 7 * 86400:
        return "prochain journal dans " + f"{(dernier + 7 * 86400 - time.time()) / 86400:.1f} j"
    telegram.envoyer(apprentissage.journal())
    base.ecrire("journal:dernier", time.time())
    return "journal envoyé"


def bot_archive_mt5(chef):
    if not config.MT5_ACTIF:
        return "MT5 non configuré"
    inst = executant.etat_installation()
    if inst and not inst.startswith(("installation réussie", "installé")):
        return f"MT5 pas encore installé ({inst})"
    return archive_mt5.archiver()


def bot_chandeliers(chef):
    msgs = []
    for tf in ("1h", "4h", "1d"):
        b = donnees.charger(SOURCE_DECISION, tf, limite=FENETRES[tf])
        if len(b["c"]) < 200:
            continue
        cle_stats = f"stats_chandeliers:{tf}"
        stats = base.lire(cle_stats)
        if not stats or time.time() - stats.get("_ts", 0) > 86400:
            source = source_stats(tf)
            stats = chandeliers.statistiques(donnees.charger(source, tf), S.UNITES[tf][0])
            stats["_ts"], stats["_source"] = time.time(), source
            base.ecrire(cle_stats, stats)
        derniers = chandeliers.derniers_motifs(b, stats)
        dernier_ts = int(b["ts"][-1])
        if base.lire(f"chandeliers_vu:{tf}") != dernier_ts:
            base.ecrire(f"chandeliers_vu:{tf}", dernier_ts)
            base.ecrire(f"chandeliers:{tf}", {"ts": dernier_ts, "motifs": derniers})
            fiables = [m for m in derniers if m["fiable"]]
            if fiables and tf in ("4h", "1d"):
                telegram.envoyer("🕯 " + tf + " : " + " ; ".join(
                    f"{m['motif'].replace('_', ' ')} (sur l'or : {m['reussite'] * 100:.0f} % dans le sens "
                    f"annoncé, n={m['n']})" for m in fiables))
        msgs.append(f"{tf}: {len(derniers)} motif(s)")
    return ", ".join(msgs)


def _decision_enregistree(tf, ts):
    with base.connexion() as c:
        r = c.execute("SELECT sens FROM decisions WHERE ts=? AND details LIKE ?", (int(ts), f'%"unite": "{tf}"%')).fetchone()
    return int(r["sens"]) if r else 0


def _resoudre(tf, b):
    """Juge les pronostics arrivés à échéance avec les bougies fermées disponibles."""
    prix = dict(zip(b["ts"].tolist(), b["c"].tolist()))
    with base.connexion() as c:
        ouverts = c.execute("SELECT id, cible_ts, p_hausse, prix_ref FROM pronostics WHERE issue IS NULL AND "
                            "horizon=? AND cible_ts<=?", (MS[tf], int(b["ts"][-1]))).fetchall()
        for r in ouverts:
            if r["cible_ts"] in prix:
                issue = int(prix[r["cible_ts"]] > r["prix_ref"])
                c.execute("UPDATE pronostics SET issue=?, brier=? WHERE id=?",
                          (issue, (r["p_hausse"] - issue) ** 2, r["id"]))


def bot_pronostiqueurs(chef):
    msgs = []
    apprentissage.appliquer_couts()                            # frais réels MT5 appris (sinon estimation fixe)
    for tf in ("1h", "4h", "1d"):
        b = donnees.charger(SOURCE_DECISION, tf, limite=FENETRES[tf])
        h, hb = S.UNITES[tf]
        if len(b["c"]) < P.MIN_CALIB + 100:
            msgs.append(f"{tf}: historique insuffisant")
            continue
        dernier_ts = int(b["ts"][-1])
        _resoudre(tf, b)
        if base.lire(f"prono_vu:{tf}") == dernier_ts:
            continue
        probas, naif, y = P.tout_calculer(b, h)
        probas.update(apprentissage.probas_admis(b, tf, h, y))  # signaux de veille ADMIS à l'examen d'entrée
        cons, poids_hist = P.consensus(probas, naif, y, h)
        dec = S.decisions(cons, b, tf)
        sens = int(dec[-1])
        mv = S.mouvement_habituel(b["c"], h)[-1]
        cible = dernier_ts + h * MS[tf]
        prix_ref = float(b["c"][-1])
        with base.connexion() as c:
            for nom, serie in {**probas, "consensus": cons, "naif": naif}.items():
                if not np.isnan(serie[-1]):
                    c.execute("INSERT INTO pronostics(ts, bot, horizon, p_hausse, prix_ref, cible_ts) VALUES(?,?,?,?,?,?)",
                              (dernier_ts, f"{tf}:{nom}", MS[tf], float(serie[-1]), prix_ref, cible))
            details = {"unite": tf, "p": float(cons[-1]), "naif": float(naif[-1]) if not np.isnan(naif[-1]) else None,
                       "poids": poids_hist[-1][1] if poids_hist else {}, "mouvement_habituel": float(mv),
                       "couts": S.couts(h, hb), "prix": prix_ref}
            c.execute("INSERT INTO decisions(ts, p_consensus, sens, details) VALUES(?,?,?,?)",
                      (dernier_ts, float(cons[-1]), sens, json.dumps(details)))
        base.ecrire(f"prono:{tf}", {"ts": dernier_ts, "p": float(cons[-1]), "sens": sens,
                                    "pronostiqueurs": {k: float(v[-1]) for k, v in probas.items() if not np.isnan(v[-1])},
                                    **details})
        base.ecrire(f"prono_vu:{tf}", dernier_ts)
        _papier(tf, b, dec)
        if sens and not chef.pause:
            atr = float(I.atr(b["h"], b["l"], b["c"], 14)[-1])
            ex = L.excursion_defavorable(donnees.charger(SOURCE_DECISION, "1h", limite=20000), 24)
            f20 = L.fiche(config.CAPITAL_PAPIER, prix_ref, atr, sens, max(cons[-1], 1 - cons[-1]), "x20 (max. UE)",
                          stop_atr=papier.REGLES["stop_atr"], rr=1.0, heures=h * hb, excursions=ex)
            telegram.envoyer(
                f"📡 Signal {'ACHAT' if sens > 0 else 'VENTE'} or ({tf}, horizon {h * hb} h) · probabilité "
                f"{max(cons[-1], 1 - cons[-1]) * 100:.1f} % · avantage attendu {abs(2 * cons[-1] - 1) * mv * 100:.3f} % "
                f"contre coûts {S.couts(h, hb) * 100:.3f} %.\nÀ x20 : perte au stop {f20['perte_si_stop_pct_capital']:.1f} % "
                f"du capital, liquidation à {f20['liquidation']:.2f} $ ({f20['distance_liquidation_pct']:.1f} %). "
                "PAPIER uniquement : aucun ordre.", important=True)
        msgs.append(f"{tf}: p={cons[-1]:.3f} {'ACHAT' if sens > 0 else 'VENTE' if sens < 0 else 'rien'}")
    return ", ".join(msgs) or "rien de neuf"


def _papier(tf, b, dec):
    """Avance les comptes papier de l'unité sur les bougies nouvelles, avec les décisions ENREGISTRÉES."""
    cle = f"papier:{tf}"
    etat = base.lire(cle)
    if not etat:
        etat = {"dernier_ts": int(b["ts"][-1]), "depuis": int(b["ts"][-1]),
                "comptes": {p: papier.compte_neuf(config.CAPITAL_PAPIER) for p in PROFILS_DIRECT}}
        base.ecrire(cle, etat)
        return
    atr = I.atr(b["h"], b["l"], b["c"], 14)
    regles = {**papier.REGLES, "duree": S.UNITES[tf][0]}
    nouveaux = []
    for i in range(1, len(b["ts"])):
        if b["ts"][i] <= etat["dernier_ts"]:
            continue
        sens = _decision_enregistree(tf, b["ts"][i - 1])
        for p, compte in etat["comptes"].items():
            trades = []
            papier.pas(compte, p, i, b, atr, sens, trades, regles)
            nouveaux += [(p, t) for t in trades]
        etat["dernier_ts"] = int(b["ts"][i])
    if nouveaux:
        with base.connexion() as c:
            for p, t in nouveaux:
                c.execute("INSERT INTO trades(profil, sens, entree_ts, prix_entree, notionnel, levier, stop, objectif, "
                          "liquidation, sortie_ts, prix_sortie, motif, pnl, frais, financement, capital_apres) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (f"{tf}:{p}", t["sens"], t["entree_ts"], t["entree"], t["notionnel"], t["levier"], t["stop"],
                           t["objectif"], t["liquidation"], t["sortie_ts"], t["prix_sortie"], t["motif"], t["pnl"],
                           0.0, 0.0, t["capital_apres"]))
                if t["motif"] == "liquidation":
                    telegram.envoyer(f"💥 Compte papier {p} ({tf}) LIQUIDÉ : c'est ce qui arriverait à un vrai "
                                     "compte avec ce levier.", important=True)
    base.ecrire(cle, etat)


def bot_fond(chef):
    """Comptes de fond (sans levier) : « garder l'or » et « tendance 10 mois », suivis depuis l'installation."""
    g = donnees.charger("GC", "1d")
    if len(g["c"]) < 300:
        return "COMEX insuffisant"
    mois = np.array([dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m") for t in g["ts"]])
    fin = np.r_[mois[1:] != mois[:-1], True]
    fins = g["c"][fin][:-1]                                   # mois terminés seulement
    tendance = bool(fins[-1] > fins[-10:].mean()) if len(fins) >= 10 else None
    d = flux.prix_direct()
    prix = d["prix"] if d else float(g["c"][-1])
    fond = base.lire("fond")
    if not fond:
        fond = {"depuis": time.time(), "prix_depart": prix, "garder": config.CAPITAL_PAPIER,
                "tendance": config.CAPITAL_PAPIER, "tendance_investi": tendance, "prix_dernier": prix}
    ratio = prix / fond["prix_dernier"]
    fond["garder"] *= ratio
    if fond.get("tendance_investi"):
        fond["tendance"] *= ratio
    if tendance is not None and tendance != fond.get("tendance_investi"):
        fond["tendance"] *= 1 - 0.002                         # coût d'un changement de position
        telegram.envoyer(f"🧭 Règle de fond (10 mois) : l'or passe {'AU-DESSUS' if tendance else 'SOUS'} sa moyenne de "
                         f"10 mois -> {'investi' if tendance else 'hors marché'} (compte papier).", important=True)
    fond.update({"tendance_investi": tendance, "prix_dernier": prix, "maj": time.time()})
    base.ecrire("fond", fond)
    return f"garder {fond['garder']:.0f} ; tendance {fond['tendance']:.0f} ({'investi' if tendance else 'hors marché'})"


def bilan_historique(chemin=None):
    """Tout l'historique, sans regarder le futur : compétence de chaque pronostiqueur (2 moitiés), consensus,
    comptes papier par profil de levier, comparaison avec « garder l'or »."""
    out = {"ts": time.time(), "unites": {}}
    for tf in ("1h", "4h", "1d"):
        b = donnees.charger(SOURCE_DECISION, tf, chemin=chemin)
        h, _ = S.UNITES[tf]
        if len(b["c"]) < P.MIN_CALIB + 200:
            continue
        probas, naif, y = P.tout_calculer(b, h)
        cons, _ = P.consensus(probas, naif, y, h)
        dec = S.decisions(cons, b, tf)
        n = len(y)
        comp = {k: [round(P.competence(v, naif, y, 0, n // 2)[0] * 100, 3), round(P.competence(v, naif, y, n // 2, n)[0] * 100, 3)]
                for k, v in {**probas, "consensus": cons}.items()}
        comptes, _, _ = papier.backtest(b, dec, I.atr(b["h"], b["l"], b["c"], 14), config.CAPITAL_PAPIER,
                                        regles={**papier.REGLES, "duree": h})
        out["unites"][tf] = {
            "bougies": n, "debut": int(b["ts"][0]), "fin": int(b["ts"][-1]), "competences_pct": comp,
            "decisions": int((dec != 0).sum()), "garder_or_x": float(b["c"][-1] / b["c"][0]),
            "comptes": {p: {k: c[k] for k in ("capital", "baisse_max", "trades", "gagnants", "liquidations", "ruine")}
                        for p, c in comptes.items()}}
    base.ecrire("bilan_historique", out, chemin)
    return out


def bot_bilan(chef):
    out = bilan_historique()
    return "bilan : " + ", ".join(f"{tf} {u['decisions']} décisions" for tf, u in out["unites"].items())


def bot_commandes(chef):
    faites = []
    fichier = config.RACINE / "runtime" / "commandes.txt"
    cmds = telegram.commandes()
    if fichier.exists():
        try:
            cmds += [x.strip() for x in fichier.read_text().splitlines() if x.strip()]
            fichier.unlink()
        except OSError:
            pass
    for c in cmds:
        if c in ("/or_pause", "pause"):
            chef.pause = True
            base.ecrire("pause", True)
            telegram.envoyer("⏸ Nouvelles positions papier en pause. L'analyse continue.")
        elif c in ("/or_reprise", "reprise"):
            chef.pause = False
            base.ecrire("pause", False)
            telegram.envoyer("▶️ Positions papier reprises.")
        elif c in ("/or", "/or_rapport", "rapport"):
            telegram.envoyer(rapport(chef))
        elif c in ("/or_levier", "levier"):
            telegram.envoyer(rapport_levier())
        elif c in ("/or_bilan", "bilan"):
            telegram.envoyer(rapport_bilan())
        elif c in ("/or_bibliotheque", "bibliotheque"):
            telegram.envoyer("📚 Bibliothèque de l'armée\n" + bibliotheque.texte())
        elif c in ("/or_veille", "veille"):
            telegram.envoyer(veille.texte_veille())
        elif c in ("/or_apprentissage", "apprentissage"):
            telegram.envoyer(apprentissage.journal())
        elif c in ("/or_verif", "verif"):
            telegram.envoyer(apprentissage.texte_memoire())
            telegram.envoyer(executant.rapport_trades())
        elif c in ("/or_calendrier", "calendrier"):
            telegram.envoyer(veille.texte_calendrier(10))
        elif c in ("/or_niveaux", "niveaux"):
            telegram.envoyer(veille.texte_niveaux())
        elif c in ("/or_actus", "actus"):
            telegram.envoyer(veille.texte_actualites(10))
        elif c in ("/or_bougies", "bougies"):
            telegram.envoyer(rapport_bougies("4h") + "\n\n" + rapport_bougies("1d", nb=6))
        elif c in ("/or_mt5", "mt5"):
            telegram.envoyer("🤖 " + executant.rapport_mt5())
        elif c in ("/or_mt5_fermer", "mt5_fermer"):
            base.ecrire("mt5:pause", True)
            try:
                n = len(executant.fermer_tout("fermeture demandée"))
                telegram.envoyer(f"🛑 MT5 : {n} position(s) de l'armée fermée(s), ordres suspendus (or mt5 reprendre).",
                                 important=True)
            except mt5.ErreurMT5 as ex:
                telegram.envoyer(f"🛑 MT5 : ordres suspendus, mais fermeture impossible pour l'instant ({ex}).", True)
        elif c in ("/or_mt5_ecran", "mt5_ecran"):
            photo = config.RACINE / "runtime" / "ecran_pont.png"
            if not (photo.exists() and time.time() - photo.stat().st_mtime < 600
                    and telegram.envoyer_photo(str(photo), "Écran du terminal MT5 sur le serveur "
                                               f"(il y a {int(time.time() - photo.stat().st_mtime)} s)")):
                telegram.envoyer("📷 Pas de photo récente du terminal MT5 : le service armee-or-mt5 ne tourne pas "
                                 "encore (installation : « or mt5 installer »).")
        elif c in ("/or_mt5_reprendre", "mt5_reprendre"):
            base.ecrire("mt5:pause", False)
            telegram.envoyer("▶️ MT5 : ordres automatiques repris.")
        elif c in ("/or_mt5_profil", "mt5_profil"):
            telegram.envoyer(f"⚖️ Profil actuel : {executant.profil_actif()}. Touche pour changer :\n"
                             "/or_profil_pro (1 % du capital risqué, recommandé)\n/or_profil_x1  /or_profil_x3  "
                             "/or_profil_x5\n/or_profil_x10  /or_profil_x20 (max. UE)  /or_profil_x50 (max. Binance)\n"
                             "Sur l'historique : ruine fréquente à partir de x10.")
        elif c.startswith(("mt5_profil ", "/or_mt5_profil ", "/or_profil_")):
            nom = mt5.nom_profil(c.replace("/or_profil_", " ").split(" ", 1)[1])
            if nom:
                base.ecrire("mt5:profil", nom)
            telegram.envoyer(f"⚖️ MT5 : profil des décisions = {nom}." if nom else
                             "Profil inconnu (x1, x3, x5, x10, x20, x50 ou pro).")
        elif c == "/or_entrainement":
            telegram.envoyer(f"🏋️ Entraînement {'actif' if executant.entrainement_actif() else 'arrêté'}. Touche : "
                             "/or_entrainement_on  ou  /or_entrainement_off")
        elif c in ("mt5_entrainement on", "mt5_entrainement off", "/or_entrainement_on", "/or_entrainement_off"):
            base.ecrire("mt5:entrainement", c.endswith("on"))
            telegram.envoyer(f"🏋️ MT5 : équipe d'entraînement {'active' if c.endswith('on') else 'arrêtée'}.")
        elif c in ("/or_maj", "maj"):
            telegram.envoyer(demander_maj())
        elif c in ("/or_journal", "journal"):
            telegram.envoyer(fin_du_journal())
        elif c in ("/or_aide", "/start", "aide"):
            telegram.envoyer("🟡 Commandes (touche-les) :\n" + "\n".join(f"/{n} — {d}" for n, d in telegram.MENU))
        faites.append(c)
    return ("commandes : " + ", ".join(faites)) if faites else "aucune commande"


UNITE_MAJ = "/etc/systemd/system/armee-or-maj.path"             # installée par installer_or.sh (service root)


def demander_maj():
    """Mise à jour sans terminal : un service root surveille ce fichier et lance « or maj » (code publié sur
    GitHub uniquement, rien n'est lu dans le fichier)."""
    import os
    if not os.path.exists(UNITE_MAJ):
        return ("⚠️ Mise à jour depuis Telegram pas encore installée : une dernière fois « or maj » dans un terminal "
                "(Termius gratuit ou console Hetzner). Ensuite, /or_maj suffira.")
    drapeau = config.RACINE / "runtime" / "demande_maj"
    if drapeau.exists():
        return "⏳ Mise à jour déjà demandée : le résultat arrive ici."
    drapeau.parent.mkdir(parents=True, exist_ok=True)
    drapeau.touch()
    return ("🔄 Mise à jour demandée : téléchargement de la dernière version, tests, redémarrage de l'armée (5 à 15 "
            "min). Le résultat arrive ici. Les positions MT5 restent en place, stops compris.")


def fin_du_journal(n=25):
    try:
        with open(config.JOURNAL, encoding="utf-8", errors="replace") as f:
            lignes = f.readlines()[-n:]
    except OSError:
        return "Journal vide."
    texte = "".join(f"{l[11:19]} {l.split(' | ', 1)[1]}" if " | " in l else l for l in lignes)   # heure seule
    return "📜 Fin du journal de l'armée\n" + texte[-3500:]


def bot_rapporteur(chef):
    telegram.envoyer(rapport(chef))
    return "rapport envoyé"


# ============================================================================ rapports
def retard_txt(ms):
    s = ms / 1000
    if s < 1:
        return f"{ms:.0f} ms"
    if s < 120:
        return f"{s:.0f} s"
    if s < 7200:
        return f"{s / 60:.0f} min"
    return f"{s / 3600:.0f} h (marché fermé ?)"


def rapport(chef=None):
    d = flux.prix_direct()
    lignes = ["Rapport de l'armée de l'or"]
    lignes.append(f"Cours : {d['prix']:.2f} $ · {d['source']} · retard {retard_txt(d['retard_ms'])}" if d
                  else "Cours : aucun flux frais (les vigies réessaient)")
    r = base.lire("rythme")
    if r:
        lignes.append(f"Rythme : {r['regime']} · séance {r['seance']} · ATR 1 h {r['atr_pct']:.2f} % · série {r['serie']:+d}")
    m = base.lire("marches")
    if m:
        top = {x["ticker"]: x for x in m["marches"]}
        dx, tx = top.get("DX-Y.NYB"), top.get("^TNX")
        lignes.append(f"Contexte (dollar, taux, argent…) : {m['contexte']:+.2f}"
                      + (f" · dollar {dx['var_5j']:+.1f} % sur 5 j" if dx else "")
                      + (f" · taux 10 ans {tx['var_5j']:+.1f} %" if tx else ""))
    for tf in ("1h", "4h", "1d"):
        p = base.lire(f"prono:{tf}")
        if p:
            lignes.append(f"Pronostic {tf} : hausse {p['p'] * 100:.1f} % (naïf {(p['naif'] or 0.5) * 100:.1f} %) -> "
                          + ("ACHAT" if p["sens"] > 0 else "VENTE" if p["sens"] < 0 else "aucune action (avantage < coûts)"))
    lignes.append(veille.texte_tendances())
    ev = [e for e in (base.lire("calendrier") or {}).get("evenements", []) if e["ts"] > time.time()]
    if ev:
        lignes.append(f"Prochaine annonce à fort impact : {ev[0]['titre']} ({veille.heure_paris(ev[0]['ts'])}, Paris)")
    for tf in ("1h", "4h", "1d"):
        e = base.lire(f"papier:{tf}")
        if e:
            lignes.append(f"Papier {tf} : " + " · ".join(
                f"{p} {c['capital']:.0f}$" + (" 💥" if c["ruine"] else "") for p, c in e["comptes"].items()))
    f = base.lire("fond")
    if f:
        lignes.append(f"Fond : garder l'or {f['garder']:.0f}$ · tendance 10 mois {f['tendance']:.0f}$ "
                      f"({'investi' if f.get('tendance_investi') else 'hors marché'})")
    if chef:
        ko = [b.nom for b in chef.bots if b.echecs]
        lignes.append(f"Armée : {len(chef.bots) - len(ko)}/{len(chef.bots)} bots en forme"
                      + (f" · en difficulté : {', '.join(ko)}" if ko else "") + (" · ⏸ PAUSE" if chef.pause else ""))
    if config.MT5_ACTIF:
        lignes.append(executant.rapport_mt5())
        lignes.append(archive_mt5.resume())
        lignes.append("Papier : simulé. MT5 : ordres réels sur compte DÉMO uniquement.")
    else:
        lignes.append("Tout est simulé sur papier : aucun ordre réel.")
    return "\n".join(lignes)


def rapport_levier():
    b = donnees.charger(SOURCE_DECISION, "1h", limite=20000)
    if len(b["c"]) < 500:
        return "Historique insuffisant."
    atr = float(I.atr(b["h"], b["l"], b["c"], 14)[-1])
    ex = L.excursion_defavorable(b, 24)
    lignes = [f"⚖️ Levier sur l'or (achat à {b['c'][-1]:.2f} $, stop {papier.REGLES['stop_atr']} ATR, 1 000 $ de capital)"]
    for p in L.PROFILS:
        f = L.fiche(1000, float(b["c"][-1]), atr, 1, 0.5, p, stop_atr=papier.REGLES["stop_atr"], rr=1.0, excursions=ex)
        lignes.append(f"• {p} : notionnel {f['notionnel']:.0f} $, liquidation à {f['liquidation']:.0f} $ "
                      f"({f['distance_liquidation_pct']:.1f} %), perte au stop {f['perte_si_stop_pct_capital']:.1f} % "
                      f"du capital, liquidation atteinte dans {f['proba_liquidation_historique'] * 100:.1f} % des 24 h passées"
                      + (" ⚠ liquidation AVANT le stop" if f["liquidation_avant_stop"] else ""))
    lignes.append("Rappel : la majorité des particuliers perdent de l'argent avec le levier (AMF, 2014).")
    return "\n".join(lignes)


def rapport_bougies(tf="4h", nb=12):
    """Les motifs de chandeliers mesurés sur l'or : les plus marqués d'abord, et le seuil de fiabilité exigé."""
    st = base.lire(f"stats_chandeliers:{tf}")
    if not st:
        return "Statistiques des chandeliers pas encore calculées (quelques minutes après le démarrage)."
    motifs = {k: v for k, v in st.items() if not k.startswith("_")}
    exige = chandeliers.seuil_z(len(motifs))
    source = {"MT5": "XAUUSD du courtier MT5", "PAXGUSDT": "PAXG Binance"}.get(st.get("_source"), st.get("_source") or "PAXG")
    lignes = [f"🕯 {len(motifs)} motifs de chandeliers mesurés sur l'or ({tf}, {source}) · fiable si |z| ≥ {exige:.2f} "
              "et au moins 30 cas (correction pour 40 tests à la fois)"]
    classes = sorted(motifs.items(), key=lambda kv: -abs(kv[1].get("z") or 0))
    for nom, v in classes[:nb]:
        if not v.get("n"):
            continue
        marque = "✅" if v["n"] >= 30 and abs(v["z"]) >= exige else "·"
        lignes.append(f"{marque} {nom.replace('_', ' ')} : {v['reussite'] * 100:.0f} % dans le sens annoncé "
                      f"(sans signal : {v['base'] * 100:.0f} %) · n={v['n']} · z={v['z']:+.1f}")
    fiables = [n for n, v in motifs.items() if (v.get("n") or 0) >= 30 and abs(v.get("z") or 0) >= exige]
    lignes.append(f"Motifs fiables : {', '.join(f.replace('_', ' ') for f in fiables) if fiables else 'aucun pour l’instant'}. "
                  f"Jamais vus sur cet historique : {sum(1 for v in motifs.values() if not v.get('n'))}.")
    return "\n".join(lignes)


def rapport_bilan():
    bh = base.lire("bilan_historique")
    if not bh:
        return "Bilan historique pas encore calculé."
    lignes = ["📜 Bilan sur tout l'historique (sans regarder le futur, frais compris)"]
    for tf, u in bh["unites"].items():
        d0 = dt.datetime.fromtimestamp(u["debut"] / 1000, dt.timezone.utc).strftime("%m/%Y")
        lignes.append(f"— {tf} ({d0} → aujourd'hui, garder l'or : ×{u['garder_or_x']:.2f}) : {u['decisions']} décisions")
        c = u["competences_pct"]["consensus"]
        lignes.append(f"  consensus : {c[0]:+.2f} % puis {c[1]:+.2f} % de mieux que le naïf (1re / 2e moitié)")
        lignes.append("  " + " · ".join(f"{p} {v['capital']:.0f}$" + (" 💥ruiné" if v["ruine"] else "")
                                        for p, v in u["comptes"].items()))
    return "\n".join(lignes)


# ============================================================================ boucle
class Chef:
    def __init__(self):
        self.pause = bool(base.lire("pause", False))
        self.bots = [
            Bot("Vigie du cours", "vigie", 10, bot_vigie, fond=True),
            Bot("Sentinelle éclair", "vigie", 2, bot_eclair),
            Bot("Niveaux clés", "analyste", 10, bot_niveaux),
            Bot("Tendance multi-unités", "analyste", 60, bot_tendances, fond=True),
            Bot("Microstructure Binance", "vigie", 30, bot_microstructure, fond=True),
            Bot("Calendrier économique", "vigie", 60, bot_calendrier, fond=True),
            Bot("Actualités", "vigie", 300, bot_actualites, fond=True),
            Bot("COT CFTC", "vigie", 6 * 3600, bot_cot, fond=True),
            Bot("Archiviste de la veille", "apprentissage", 60, bot_archive_veille, fond=True),
            Bot("Rattrapage de l'historique", "apprentissage", 3600, bot_rattrapage, fond=True),
            Bot("Examinateur des signaux", "apprentissage", 1800, bot_examen, fond=True),
            Bot("Mesure des frais réels", "apprentissage", 3600, bot_frais, fond=True),
            Bot("Journal d'apprentissage", "apprentissage", 3600, bot_journal, fond=True),
            Bot("Archiviste", "archiviste", 20, bot_archiviste, fond=True),
            Bot("Vigie des marchés liés", "vigie", 900, bot_marches, fond=True),
            Bot("Analyste du rythme", "analyste", 300, bot_rythme),
            Bot("Analyste des chandeliers", "analyste", 10, bot_chandeliers, fond=True),
            Bot("Pronostiqueurs + décision", "pronostic", 10, bot_pronostiqueurs, fond=True),
            Bot("Stratège de fond", "strategie", 3600, bot_fond, fond=True),
            Bot("Bilan historique", "archiviste", 7 * 86400, bot_bilan, fond=True),
            Bot("Exécutant MT5 (démo)", "execution", 5, executant.bot_mt5),
            Bot("Archiviste MT5", "archiviste", 3600, bot_archive_mt5, fond=True),
            Bot("Commandes", "chef", 3, bot_commandes, fond=True),
            Bot("Rapporteur", "chef", config.RAPPORT_HEURES * 3600, bot_rapporteur, fond=True),
        ]
        self.bots[-1].prochaine = time.time() + 300           # premier rapport après 5 min

    def tour(self):
        for bot in self.bots:
            if bot.du(time.time()):
                bot.lancer(self)
        base.ecrire("chef", {"ts": time.time(), "pause": self.pause, "bots": [b.etat() for b in self.bots]})

    def attendre(self, delai=600):
        """Attend la fin des bots qui travaillent dans leur propre fil (tests, arrêt propre)."""
        fin = time.time() + delai
        for b in self.bots:
            if b.fil is not None:
                b.fil.join(max(0.0, fin - time.time()))


def premier_demarrage():
    if not base.lire("historique_importe"):
        _log.info("Import de l'historique livré (1833→, COMEX 2000→, Binance 2020→)...")
        donnees.importer_tout()
    if not base.lire("bilan_historique"):
        bilan_historique()


def main():
    from .systemd import dormir, notifier
    premier_demarrage()
    telegram.installer_menu()
    chef = Chef()
    notifier("READY=1")
    telegram.envoyer(f"🎼 Chef d'orchestre en poste : {len(chef.bots)} bots de l'armée de l'or au travail. "
                     "Rapport toutes les " f"{config.RAPPORT_HEURES:g} h. "
                     + ("Ordres automatiques sur ton compte MT5 DÉMO (aucun compte réel), comptes papier en parallèle."
                        if config.MT5_ACTIF else "Tout est simulé sur papier."))
    while True:
        try:
            chef.tour()
        except Exception:
            _log.exception("Tour du chef en erreur (il continue)")
        dormir(1)
