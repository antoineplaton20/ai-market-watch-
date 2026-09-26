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

from . import base, bibliotheque, chandeliers, config, donnees, executant, flux, indicateurs as I, levier as L, \
    mt5, papier, pronostiqueurs as P, rythme, strategie as S, telegram

_log = logging.getLogger("or.chef")
SOURCE_DECISION = "PAXGUSDT"            # plus long historique (2020→) + flux direct ; XAUUSDT sert de référence de prix
FENETRES = {"1h": 8000, "4h": 4000, "1d": 2500}
MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
PROFILS_DIRECT = ["x1", "x3", "x10", "x20 (max. UE)", "pro 1 % risqué"]


# ============================================================================ les bots
class Bot:
    def __init__(self, nom, famille, periode_s, fonction):
        self.nom, self.famille, self.periode, self.fonction = nom, famille, periode_s, fonction
        self.prochaine = 0.0
        self.echecs = 0
        self.ok = self.ko = 0
        self.dernier_message = ""
        self.derniere_erreur = None
        self.duree = 0.0

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


def bot_chandeliers(chef):
    msgs = []
    for tf in ("1h", "4h", "1d"):
        b = donnees.charger(SOURCE_DECISION, tf, limite=FENETRES[tf])
        if len(b["c"]) < 200:
            continue
        cle_stats = f"stats_chandeliers:{tf}"
        stats = base.lire(cle_stats)
        if not stats or time.time() - stats.get("_ts", 0) > 86400:
            stats = chandeliers.statistiques(donnees.charger(SOURCE_DECISION, tf), S.UNITES[tf][0])
            stats["_ts"] = time.time()
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
    mois = np.array([dt.datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m") for t in g["ts"]])
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
        elif c in ("/or_mt5_reprendre", "mt5_reprendre"):
            base.ecrire("mt5:pause", False)
            telegram.envoyer("▶️ MT5 : ordres automatiques repris.")
        elif c.startswith("mt5_profil ") or c.startswith("/or_mt5_profil "):
            nom = mt5.nom_profil(c.split(" ", 1)[1])
            if nom:
                base.ecrire("mt5:profil", nom)
            telegram.envoyer(f"⚖️ MT5 : profil des décisions = {nom}." if nom else
                             "Profil inconnu (x1, x3, x5, x10, x20, x50 ou pro).")
        elif c in ("mt5_entrainement on", "mt5_entrainement off"):
            base.ecrire("mt5:entrainement", c.endswith("on"))
            telegram.envoyer(f"🏋️ MT5 : équipe d'entraînement {'active' if c.endswith('on') else 'arrêtée'}.")
        faites.append(c)
    return ("commandes : " + ", ".join(faites)) if faites else "aucune commande"


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


def rapport_bilan():
    bh = base.lire("bilan_historique")
    if not bh:
        return "Bilan historique pas encore calculé."
    lignes = ["📜 Bilan sur tout l'historique (sans regarder le futur, frais compris)"]
    for tf, u in bh["unites"].items():
        d0 = dt.datetime.utcfromtimestamp(u["debut"] / 1000).strftime("%m/%Y")
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
            Bot("Vigie du cours", "vigie", 30, bot_vigie),
            Bot("Archiviste", "archiviste", 60, bot_archiviste),
            Bot("Vigie des marchés liés", "vigie", 900, bot_marches),
            Bot("Analyste du rythme", "analyste", 300, bot_rythme),
            Bot("Analyste des chandeliers", "analyste", 60, bot_chandeliers),
            Bot("Pronostiqueurs + décision", "pronostic", 60, bot_pronostiqueurs),
            Bot("Stratège de fond", "strategie", 3600, bot_fond),
            Bot("Bilan historique", "archiviste", 7 * 86400, bot_bilan),
            Bot("Exécutant MT5 (démo)", "execution", 20, executant.bot_mt5),
            Bot("Commandes", "chef", 10, bot_commandes),
            Bot("Rapporteur", "chef", config.RAPPORT_HEURES * 3600, bot_rapporteur),
        ]
        self.bots[-1].prochaine = time.time() + 300           # premier rapport après 5 min

    def tour(self):
        for bot in self.bots:
            if bot.du(time.time()):
                bot.executer(self)
        base.ecrire("chef", {"ts": time.time(), "pause": self.pause, "bots": [b.etat() for b in self.bots]})


def premier_demarrage():
    if not base.lire("historique_importe"):
        _log.info("Import de l'historique livré (1833→, COMEX 2000→, Binance 2020→)...")
        donnees.importer_tout()
    if not base.lire("bilan_historique"):
        bilan_historique()


def main():
    from .systemd import dormir, notifier
    premier_demarrage()
    chef = Chef()
    notifier("READY=1")
    telegram.envoyer(f"🎼 Chef d'orchestre en poste : {len(chef.bots)} bots de l'armée de l'or au travail. "
                     "Rapport toutes les " f"{config.RAPPORT_HEURES:g} h. Tout est simulé sur papier.")
    while True:
        try:
            chef.tour()
        except Exception:
            _log.exception("Tour du chef en erreur (il continue)")
        dormir(5)
