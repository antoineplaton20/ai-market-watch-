"""Point d'entrée : python lanceur.py (chien de garde) ou python main.py.
v9 : états de risque gradués, approbation humaine, paliers de capital, fraîcheur des données,
journal d'audit, registre immuable, calibration de l'IA, recherche fondamentale, notifications immédiates."""
import datetime as dt
import subprocess
import sys
import time
import ccxt
import config
import approbations
import auditeur
import calibration
import controle_donnees as CD
import disjoncteur
import etat_risque
import ledger
import paliers
import registre
import securite
import strategie as S
import equipe as E
import exploration as X
import langage as L
from exchange import connecter
from alertes import alerte, log, commandes, ignorer_anciennes
from indicateurs import bougies
from reconciliation import reconcilier
from gardien import (charger_etat, sauver_etat, verifier_jour, peut_acheter, surveiller,
                     calculer_ordre, acheter, vendre, vendre_tout, valeur_positions)
from moteurs.cost_engine import estimate as estimate_cost
from moteurs.opportunity_engine import evaluate as evaluate_opportunity


# =============================== TELEGRAM ===============================
def statut(ex, etat):
    _, latent = valeur_positions(ex, etat)
    compte = "DÉMO (argent fictif)" if not config.REEL else "RÉEL"
    lignes = [f"📍 Compte {compte} · les bots regardent le marché toutes les "
              f"{L.UNITES.get(config.TIMEFRAME_SIGNAL, config.TIMEFRAME_SIGNAL)}",
              f"Niveau de risque : {L.NIVEAUX_RISQUE.get(etat.get('niveau_risque', 'SÛR'), '?')} · "
              f"capital autorisé : {paliers.capital_autorise(etat):.0f} $ (palier {etat.get('palier', 0) + 1})",
              f"Achats en cours : {len(etat['positions'])} · gain ou perte pas encore encaissé : {L.dollars(latent, True)}"]
    for sym, p in etat["positions"].items():
        lignes.append(f"• {'🧪 ' if p.get('mode') == 'exploration' else ''}{sym.split('/')[0]} : acheté "
                      f"{L.prix(p['entree'])} $ · protection à {L.prix(p['stop'])} $"
                      + (" 🔒 (plus de perte possible)" if p['securise'] else ""))
    n = X.niveau(etat)
    lignes.append(f"🧪 Essais : niveau {n} ({X.NOMS[n]})"
                  + (f" · {L.pluriel(X.achats_du_jour(etat), 'achat')} d'essai aujourd'hui" if n else "")
                  + (f" · ARRÊTÉS ({etat['exploration_coupee']})" if etat.get("exploration_coupee") else ""))
    lignes.append("🎯 Bot prudent : " + auditeur.rapport("strict"))
    return "\n".join(lignes)


def rapport_journee(etat):
    minuit = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
    trades = auditeur.trades_depuis(minuit)
    analyses, signaux = ledger.decisions_depuis(minuit)
    return (f"🗓 Bilan du {dt.date.today():%d/%m}\n"
            f"Ventes terminées : {len(trades)} · résultat : {L.dollars(sum(u for _, u in trades), True)}\n"
            f"Achats en cours : {len(etat['positions'])}\n"
            f"🎯 Bot prudent : {L.pluriel(signaux, 'signal', 'signaux')} d'achat sur {analyses} cryptos étudiées de près\n"
            f"🧪 Essais : {L.pluriel(X.achats_du_jour(etat), 'achat')} aujourd'hui, "
            f"{L.pluriel(len(auditeur.trades_depuis(minuit, 'exploration')), 'terminé')}\n"
            f"Niveau de risque : {L.NIVEAUX_RISQUE.get(etat.get('niveau_risque', 'SÛR'), '?')}\n"
            f"{calibration.texte()}\n🏆 Stratégie actuelle : {S.decrire(S.champion())}")


def traiter_approbation(etat, ident, accepte):
    demande = approbations.resoudre(ident, accepte)
    if not demande:
        return alerte(f"Demande « {ident} » inconnue ou déjà traitée.")
    if demande["genre"] == "champion":
        alerte(auditeur.promouvoir(demande) if accepte else auditeur.refuser_challenger())
    elif demande["genre"] == "palier":
        if accepte:
            paliers.monter(etat)
        else:
            alerte("Palier refusé : le capital autorisé ne change pas.")


def traiter_commandes(ex, etat):
    for c in commandes():
        morceaux = c.split()
        cmd, arg = morceaux[0], (morceaux[1] if len(morceaux) > 1 else None)
        if cmd == "/stop":
            etat["arret_manuel"] = True
            alerte("⏸ Achats arrêtés. Les achats en cours restent protégés. Pour reprendre : /reprise")
        elif cmd == "/reprise":
            etat["arret_manuel"] = False
            alerte("▶️ Les achats reprennent.")
        elif cmd == "/vendre_tout":
            etat["arret_manuel"] = True
            alerte("🚨 Je revends tout et j'arrête les achats. Pour reprendre ensuite : /reprise")
            vendre_tout(ex, etat)
        elif cmd == "/statut":
            alerte(statut(ex, etat), important=False)
        elif cmd == "/notes":
            alerte(auditeur.bulletin(), important=False)
        elif cmd == "/evolution":
            alerte(auditeur.etat_evolution(), important=False)
        elif cmd == "/rearmer":
            disjoncteur.rearmer(etat)
        elif cmd == "/rapport":
            alerte(rapport_journee(etat), important=False)
        elif cmd == "/calibration":
            alerte(calibration.texte(), important=False)
        elif cmd == "/journal":
            lignes = [f"{dt.datetime.fromtimestamp(ts):%d/%m %H:%M} {sym} {role} score {sc:.0%} "
                      f"{'SIGNAL' if sig else ''} {issue or ''}" for ts, sym, role, sc, sig, v, issue
                      in ledger.dernieres_decisions()]
            alerte("🧾 Dernières décisions :\n" + ("\n".join(lignes) or "aucune"), important=False)
        elif cmd == "/attente":
            att = approbations.en_attente()
            alerte("🙋 Approbations en attente :\n" + ("\n".join(f"• {k} : {v['texte'][:120]}" for k, v in att.items())
                                                     or "aucune"), important=False)
        elif cmd in ("/approuver", "/refuser") and arg:
            traiter_approbation(etat, arg, cmd == "/approuver")
        elif cmd == "/exploration":
            if arg is None:
                n = X.niveau(etat)
                alerte(f"🧪 Essais : niveau {n} ({X.NOMS[n]})"
                       + (f" — ARRÊTÉS : {etat['exploration_coupee']}" if etat.get("exploration_coupee") else "")
                       + f"\n{auditeur.bilan_exploration()}\n"
                       "Changer : /exploration 0 (arrêt) · 1 (prudent) · 2 (normal) · 3 (audacieux)", important=False)
            else:
                try:
                    alerte(X.regler(etat, int(arg)))
                except ValueError:
                    alerte("Écris : /exploration 0 (arrêt) · 1 (prudent) · 2 (normal) · 3 (audacieux)")
        elif cmd == "/univers":
            alerte(E.texte_univers(), important=False)
        elif cmd == "/tr":
            import veille_tr
            alerte(veille_tr.texte_statut(), important=False)
        elif cmd == "/renseignement":                     # armée de renseignement (service equipe-bots-renseignement)
            try:
                import lecture_renseignement as LR
                alerte(LR.texte_statut(), important=False)
            except Exception as e:
                alerte(f"🛰 Renseignement : état illisible ({e}). Termius : bots renseignement-journal", important=False)
        elif cmd in ("/marches", "/briefing", "/note"):     # veille marchés mondiaux (service equipe-bots-marches)
            try:
                import veille_marches as VM
                if cmd == "/marches":
                    alerte(VM.texte_statut(), important=False)
                elif cmd == "/briefing":
                    e = VM.charger_etat()
                    alerte(VM.texte_briefing(e["briefing"], complet=True) + "\n\n" + VM.texte_reperes(e["reperes"]),
                           important=False)
                elif len(morceaux) > 1:
                    alerte(VM.demander_note(" ".join(morceaux[1:])), important=False)
                else:
                    alerte("Écris : /note LVMH (ou un ticker comme MC.PA, un ISIN, ou bitcoin)", important=False)
            except Exception as e:
                alerte(f"🌍 Veille marchés : état illisible ({e}). Dans Termius : bots marches-journal", important=False)
        elif cmd == "/v17":                                  # moteur V17 (service séparé equipe-bots-v17)
            try:
                from v17_ops import rapport as R17
                alerte(R17.commande_telegram(arg), important=False)
            except Exception as e:
                alerte(f"🧪 v17 : état illisible ({e}). Dans Termius : bots v17-etat", important=False)
        elif cmd == "/registre":
            ok, n, msg = registre.verifier()
            alerte(f"📚 Registre de recherche : {'✅' if ok else '❌'} {msg}", important=not ok)
        elif cmd == "/sante":
            dj = etat.get("disjoncteur")
            alerte(f"🩺 Santé du bot\n"
                   f"Niveau de risque : {L.NIVEAUX_RISQUE.get(etat.get('niveau_risque', 'SÛR'), '?')}\n"
                   f"Sécurité générale : {'⛔ DÉCLENCHÉE — ' + dj['raison'] + ' (/rearmer pour relancer)' if dj else '✅ active'}\n"
                   f"Prix reçus : {'⚠️ ' + etat['donnees_ko'] if etat.get('donnees_ko') else '✅ normaux'} · "
                   f"connexion Binance : {'⚠️ instable' if etat.get('reseau_ko') else '✅ ok'}\n"
                   f"Dernière sauvegarde : {etat.get('derniere_sauvegarde', 'aucune')}", important=False)


# =============================== ANALYSE ================================
def ajuster(g, poids_audit):
    g2 = dict(g)
    for v in S.VOTANTS:
        g2[f"poids_{v}"] = g[f"poids_{v}"] * poids_audit.get(v, 1.0)
    return g2


def analyser(ex, sym, d, etat, cache_h1, poids_audit, contexte, genomes, cache_mtf=None, capital=None, forcer=False):
    if sym in etat["positions"] or etat["quarantaine"].get(sym, 0) > time.time():
        return None
    try:
        mtf = E.multi_timeframe(ex, sym, cache_mtf)
    except Exception as e:
        log(f"  {sym} : MTF indisponible ({e})")
        return None
    mtf_checks = {"4h": bool(mtf[config.TIMEFRAME_REGIME].closed["c"] > mtf[config.TIMEFRAME_REGIME].closed["ema50"] and mtf[config.TIMEFRAME_REGIME].closed["ema20"] > mtf[config.TIMEFRAME_REGIME].closed["ema50"]),
                  "1h": bool(mtf[config.TIMEFRAME_TREND].closed["c"] > mtf[config.TIMEFRAME_TREND].closed["ema50"] and mtf[config.TIMEFRAME_TREND].closed["ema20"] > mtf[config.TIMEFRAME_TREND].closed["ema50"]),
                  "15m": bool(mtf[config.TIMEFRAME_SIGNAL].closed["c"] > mtf[config.TIMEFRAME_SIGNAL].closed["ema50"] and mtf[config.TIMEFRAME_SIGNAL].closed["ema20"] > mtf[config.TIMEFRAME_SIGNAL].closed["ema50"]),
                  "5m": bool(mtf[config.TIMEFRAME_ENTRY].closed["c"] > mtf[config.TIMEFRAME_ENTRY].closed["ema50"] and mtf[config.TIMEFRAME_ENTRY].closed["ema20"] > mtf[config.TIMEFRAME_ENTRY].closed["ema50"])}
    if config.TIMEFRAME_TREND == "1h":
        cache_h1.setdefault(sym, mtf["1h"].df)         # la corrélation réutilise les bougies 1 h déjà chargées
    votes = {"TENDANCE": E.tech_tendance(d), "MOMENTUM": E.tech_momentum(d)}
    # MULTI_UNITES garde la définition du backtest (sup1/sup2) : les génomes sont entraînés dessus.
    # La porte MTF 4/4 de la v11 reste appliquée à part, avant tout achat (moteur d'opportunité).
    v_mu, r_mu = E.multi_unites(ex, sym, cache_h1, d, mtf)
    votes["MULTI_UNITES"] = (v_mu, f"{r_mu} | MTF {sum(mtf_checks.values())}/4 favorables")
    F0 = S.caracteristiques_live(d, votes, [], contexte)
    actifs = {}
    for role, g in genomes.items():
        if not bool(S.condition_espece(g, F0, config.UNITE_BOUGIE)):
            continue
        if g["espece"] == "MOMENTUM" and E.leader(votes, {}) < config.PRE_SCORE_MIN:
            continue
        actifs[role] = g
    force = False
    if not actifs:
        # v14 : l'EXPLORATION (démo) peut analyser une paire où aucune espèce ne se déclenche,
        # seulement si les votants techniques sont déjà plutôt favorables (évite des appels inutiles)
        if not forcer or E.leader(votes, {}) < config.PRE_SCORE_MIN:
            return None
        actifs, force = {"champion": genomes["champion"]}, True

    vetos, avis_vetos = [], {}
    for nom, (ok, r) in (("ANTI_HYPE", E.anti_hype(d)), ("RECHERCHE", E.recherche(d["base"]))):
        avis_vetos[nom] = r
        if not ok:
            vetos.append("ANTI_HYPE" if nom == "ANTI_HYPE" else "RECHERCHE_VETO")
    ok, v, r = E.derives(d["base"])
    votes["DERIVES"] = (v, r)
    if not ok:
        vetos.append("DERIVES_VETO")
    trades = E.lire_trades(ex, sym)
    votes["CARNET"] = E.carnet(d, trades)
    ok, v, r = E.baleines(trades)
    votes["BALEINES"] = (v, r)
    if not ok:
        vetos.append("BALEINES_VETO")
    ok, r = E.correlation(ex, sym, etat, cache_h1)
    avis_vetos["CORRELATION"] = r
    if not ok:
        vetos.append("CORRELATION")
    ok, r = E.actualite(d["base"])
    avis_vetos["VEILLE"] = r
    if not ok:
        vetos.append("VEILLE")
    votes["DEVELOPPEURS"] = E.developpeurs(d["base"])
    for nom, fonction in (("LIQUIDITE", E.liquidite), ("MACRO", E.macro), ("MARCHES_MONDIAUX", E.marches_mondiaux),
                          ("POSITIONNEMENT", lambda: E.positionnement(d["base"]))):
        ok, v, r = fonction()
        votes[nom] = (v, r)
        if not ok:
            vetos.append(f"{nom}_VETO")
    ok, r = E.attention()
    avis_vetos["ATTENTION"] = r
    if not ok:
        vetos.append("ATTENTION_VETO")
    F = S.caracteristiques_live(d, votes, vetos, contexte, E.flux_seul(trades))

    # Vetos que l'évolution ne peut jamais désactiver
    durs = [x for x in ("BALEINES_VETO", "CORRELATION", "VEILLE", "RECHERCHE_VETO") if x in vetos]
    decisions = {}
    for role, g in actifs.items():
        sig, score = S.decider(ajuster(g, poids_audit), F, config.UNITE_BOUGIE)
        decisions[role] = (bool(sig) and not durs, float(score))
    brutes = dict(decisions)

    # ESCALADE : l'IA relit la décision. Elle peut seulement dire NON ; muette = attente, jamais de trade.
    ia = {}
    if decisions.get("champion", (False,))[0]:
        avis = {k: r for k, (_, r) in votes.items()}
        avis.update(avis_vetos)
        v, r = E.contradicteur(sym, d, avis, contexte.get("sentiment"))
        ia = dict(E.DERNIER_CONTRADICTEUR)
        if v is not None:
            votes["CONTRADICTEUR"] = (v, r)
            if v == 0.0:
                vetos.append("CONTRADICTEUR")
                decisions["champion"] = (False, decisions["champion"][1])
        elif config.ANTHROPIC_API_KEY and config.IA_OBLIGATOIRE_SI_CLE:
            vetos.append("IA_INDISPONIBLE")
            decisions["champion"] = (False, decisions["champion"][1])
    espece_ok = bool(S.condition_espece(genomes["champion"], F, config.UNITE_BOUGIE))
    return {"votes": votes, "vetos": vetos, "decisions": decisions, "brutes": brutes, "F": F, "ia": ia, "mtf": mtf,
            "mtf_checks": mtf_checks, "force": force, "espece_ok": espece_ok}


# ================================ CYCLE =================================
def controle_marche(ex, etat):
    """Règle dure : si les données de référence (BTC) sont périmées, on ne prend aucun nouveau risque."""
    try:
        frais = CD.bougies_fraiches(bougies(ex, "BTC/USDT", config.UNITE_BOUGIE, 5), config.UNITE_BOUGIE)
    except Exception:
        frais = False
    raison = None if frais else "bougies BTC périmées ou illisibles"
    if etat.get("horloge_ko"):
        raison = etat["horloge_ko"]
    if raison != etat.get("donnees_ko"):
        alerte(f"⚠️ Les prix reçus semblent anormaux ({raison}) : aucun nouvel achat en attendant."
               if raison else "✅ Les prix reçus sont de nouveau normaux.")
    etat["donnees_ko"] = raison
    return raison is None


def sortie_anticipee(ex, etat):
    """Positions ouvertes : une vraie mauvaise nouvelle (piratage, délisting...) déclenche une vente immédiate."""
    for sym in list(etat["positions"]):
        ok, r = E.actualite(ex.markets[sym]["base"])
        if ok:
            continue
        if r.startswith("alerte presse"):
            alerte(f"🚨 VENTE IMMÉDIATE — {sym.split('/')[0]} : mauvaise nouvelle dans la presse.\n{r}")
            vendre(ex, sym, etat, "sortie anticipée : mauvaise nouvelle")
        elif not etat.get("notif_veille", {}).get(sym):
            etat.setdefault("notif_veille", {})[sym] = time.time()
            alerte(f"⚠️ {sym.split('/')[0]} (déjà acheté) : {r}. La protection reste en place, à surveiller.")


def notifier_bloque(etat, sym, score, vetos, raisons):
    if not config.NOTIF_SIGNAUX_BLOQUES:
        return
    derniers = etat.setdefault("notif_bloques", {})
    if time.time() - derniers.get(sym, 0) < config.NOTIF_BLOQUE_DELAI_H * 3600:
        return
    derniers[sym] = time.time()
    alerte(f"✋ {sym.split('/')[0]} : l'équipe voulait acheter (confiance {L.pourcent(score)}) mais s'est retenue.\n"
           f"Pourquoi :\n{L.puces(vetos)}" + (f"\n{raisons}" if raisons else ""))


def porte_v11(ex, sym, d, res, champ, capital, etat, entree, atr_v):
    """PORTE v11 : toutes les unités doivent confirmer + coûts nets acceptables."""
    ticker = ex.fetch_ticker(sym)
    bid, ask = float(ticker.get("bid") or entree), float(ticker.get("ask") or entree)
    spread_pct = max(0.0, (ask - bid) / max(ask, 1e-12) * 100)
    spread_ok = spread_pct <= config.SPREAD_MAX_PCT
    liquidity_ok = min(d["carnet"]["achat"], d["carnet"]["vente"]) >= config.PROFONDEUR_MIN_USDT
    params = S.params_sortie(champ)
    gross_potential = abs(float(params.get("objectif_atr", config.OBJECTIF_ATR)) * atr_v / max(ask, 1e-12) * 100)
    cost = estimate_cost(config.PLATEFORME_EXECUTION, max(float(capital or config.CAPITAL_MAX_USDT) * config.POSITION_MAX_PCT / 100, 1.0),
                         spread_pct=spread_pct, slippage_pct=config.GLISSEMENT_PCT, entry_role="taker")
    return evaluate_opportunity("BUY", res["mtf_checks"], not bool(res["vetos"]),
                                data_ok=not bool(etat.get("donnees_ko")), liquidity_ok=liquidity_ok,
                                spread_ok=spread_ok, cost=cost, gross_potential_pct=gross_potential,
                                min_net_pct=config.OPPORTUNITE_MIN_NET_PCT,
                                safety_margin_pct=config.OPPORTUNITE_MARGE_SECURITE_PCT)


def cycle_achat(ex, etat, capital, mult_risque):
    if not controle_marche(ex, etat):
        return
    sortie_anticipee(ex, etat)
    n = X.niveau(etat)
    base = paliers.capital_autorise(etat)
    strict_ok = peut_acheter(etat)
    explo_ok, explo_raison = X.peut_explorer(etat, n, base, etat.get("pnl_jour_exploration", 0.0))
    if not strict_ok and not explo_ok:
        return
    genomes = {"champion": S.champion()}
    ch = S.challenger()
    if ch:
        genomes["challenger"] = ch
    ok_cal, r_cal = E.calendrier()
    ok_met, r_met = E.meteo_marche(ex)
    multiplicateur, r_fng, sentiment = E.peur_avidite()
    contexte = {"veto_CALENDRIER": not ok_cal, "veto_METEO": not ok_met, "sentiment": sentiment,
                "veto_PEUR_AVIDITE": sentiment is not None and (sentiment >= config.AVIDITE_FORTE or sentiment <= config.PEUR_EXTREME)}
    log(f"📅 {r_cal} | ☁️ {r_met} | 🌡 {r_fng} | risque {etat.get('niveau_risque', 'SÛR')} x{mult_risque:.2f}"
        f" | exploration {n} ({'active' if explo_ok else explo_raison})")
    if all(any(g[f"veto_{v}"] and contexte[f"veto_{v}"] for v in ("CALENDRIER", "METEO", "PEUR_AVIDITE"))
           for g in genomes.values()):
        strict_ok = False
        log("Aucun génome n'autorise d'achat dans ce contexte : champion en attente"
            + (" (l'exploration continue)." if explo_ok else ", scan annulé."))
        if not explo_ok:
            return

    # v14 : entretien pendant les longs scans (toutes les paires) + durée maximale d'un scan
    debut_scan = time.time()
    duree_max = config.MINUTES[config.TIMEFRAME_SIGNAL] * 60 * config.SCAN_DUREE_MAX_FRAC
    dernier_entretien = [time.time()]

    def entretien():
        if time.time() - dernier_entretien[0] < config.INTERVALLE_BOUCLE_S:
            return
        dernier_entretien[0] = time.time()
        try:
            traiter_commandes(ex, etat)
            surveiller(ex, etat)
            securite.battement(f"scan en cours, {len(etat['positions'])} positions")
            sauver_etat(etat)
        except Exception as e:
            log(f"Entretien pendant le scan : {e}")

    candidats = E.scout(ex, n)
    decalage = etat.get("scan_reprise", 0) % len(candidats) if candidats else 0
    candidats = candidats[decalage:] + candidats[:decalage]      # reprise là où un scan interrompu s'est arrêté
    etat["scan_reprise"] = 0
    survivants, explorables = [], 0
    for i, c in enumerate(candidats):
        entretien()
        if time.time() - debut_scan > duree_max:
            etat["scan_reprise"] = (decalage + i) % max(len(candidats), 1)
            log(f"Scan interrompu après {i} paires (durée max) : reprise à la prochaine bougie.")
            break
        try:
            garde, _, d = E.filtre(ex, c, n)
        except Exception:
            continue
        if garde:
            survivants.append((c["symbole"], d, True))
        elif d and d.get("explorable"):
            survivants.append((c["symbole"], d, False))
            explorables += 1
    log(f"SCOUT {len(candidats)} paires → FILTRE {len(survivants) - explorables} strictes"
        + (f" + {explorables} explorables" if explorables else "")
        + f" | champion {genomes['champion']['espece']}" + (f", challenger {ch['espece']}" if ch else ""))

    poids_audit = auditeur.poids()
    cache_h1, cache_mtf, finalistes, reserve = {}, {}, [], []
    champ = genomes["champion"]
    forcees = X.NIVEAUX[n]["analyses_forcees"] if explo_ok else 0
    for sym, d, stricte in survivants:
        entretien()
        if time.time() - debut_scan > duree_max:
            log("Analyse interrompue (durée max du scan) : reprise à la prochaine bougie.")
            break
        try:
            res = analyser(ex, sym, d, etat, cache_h1, poids_audit, contexte, genomes, cache_mtf, capital,
                           forcer=forcees > 0)
        except Exception as e:
            log(f"  {sym} : analyse interrompue ({e})")
            continue
        if not res:
            continue
        der = d["df"].iloc[-2]
        entree, atr_v = float(der["c"]), float(der["atr"])
        if res.get("force"):
            forcees -= 1
        if explo_ok:
            reserve.append({"sym": sym, "d": d, "res": res, "entree": entree, "atr": atr_v})
        if res.get("force") or not stricte or not strict_ok:
            continue                                  # candidat d'exploration seulement : pas de décision stricte
        for role, (sig, score) in res["brutes"].items():
            if sig:
                ps = S.params_sortie(genomes[role])
                ps["stop_atr"] = float(S.distance_stop(genomes[role], res["F"]))
                auditeur.ombre(role, genomes[role]["id"], sym, entree, atr_v, ps)
        sig, score = res["decisions"].get("champion", (False, 0.0))
        brut = res["brutes"].get("champion", (False, 0.0))[0]
        candidat = brut or (res["vetos"] and score >= champ["seuil_vote"])
        if not candidat:
            continue
        # Journal d'audit AVANT toute action : sans trace écrite, pas de trade
        try:
            etat_marche = {"F": res["F"], "votes": {k: v for k, (v, _) in res["votes"].items()}, "vetos": res["vetos"]}
            did = ledger.decision(sym, "champion", champ, etat_marche, score, sig, res["vetos"],
                                  etat.get("niveau_risque", "SÛR"))
        except Exception as e:
            alerte(f"⚠️ {sym} : journal d'audit indisponible ({e}) → pas de trade.")
            continue
        if res["ia"]:
            ps = S.params_sortie(champ)
            ps["stop_atr"] = float(S.distance_stop(champ, res["F"]))
            calibration.enregistrer(did, sym, res["ia"]["verdict"], res["ia"]["confiance"], entree, atr_v, ps)
        if sig:
            opp = porte_v11(ex, sym, d, res, champ, capital, etat, entree, atr_v)
            res["opportunity"] = opp.to_dict()
            if opp.allowed:
                finalistes.append((score, sym, d, res["votes"], float(S.distance_stop(champ, res["F"])), did))
            else:
                res["vetos"].append("OPPORTUNITE_VETO")
                ledger.issue(did, "bloqué v11 : " + ", ".join(opp.reasons))
                notifier_bloque(etat, sym, score, res["vetos"], "coût/net/MTF : " + ", ".join(opp.reasons))
        else:
            if score >= config.PRE_SCORE_MIN:
                auditeur.fantome(sym, entree, atr_v, res["vetos"])
            raisons = "; ".join(r for k, (_, r) in res["votes"].items() if k == "CONTRADICTEUR")
            notifier_bloque(etat, sym, score, res["vetos"], raisons)
            ledger.issue(did, "bloqué : " + ", ".join(res["vetos"]))

    finalistes.sort(key=lambda x: x[0], reverse=True)
    for score, sym, d, votes, dist, did in finalistes:
        if not peut_acheter(etat):
            alerte(f"⏭ {sym.split('/')[0]} : bon signal (confiance {L.pourcent(score)}) mais pas d'achat : "
                   f"déjà {config.POSITIONS_MAX} achats en cours, c'est le maximum.")
            ledger.issue(did, "non exécuté : limite de positions")
            continue
        ordre = calculer_ordre(ex, sym, d, capital, multiplicateur * mult_risque, dist)
        if not ordre:
            alerte(f"⏭ {sym.split('/')[0]} : bon signal (confiance {L.pourcent(score)}) mais pas d'achat : "
                   f"le montant serait sous le minimum accepté par Binance.",
                   important=False)
            ledger.issue(did, "non exécuté : montant trop faible")
            continue
        acheter(ex, sym, ordre, etat, score, votes, champ, decision_id=did)
        ledger.issue(did, "achat exécuté" if sym in etat["positions"] else "achat échoué")
        sauver_etat(etat)

    if explo_ok and reserve:
        cycle_exploration(ex, etat, capital, reserve, champ, n)


def cycle_exploration(ex, etat, capital, reserve, champ, n):
    """v14 — COMPTE DÉMO : achète des candidats que le champion strict refuse, en notant les risques pris."""
    base = paliers.capital_autorise(etat)

    def opportunite(it):
        if "opp" not in it:
            try:
                it["opp"] = porte_v11(ex, it["sym"], it["d"], it["res"], champ, capital, etat, it["entree"], it["atr"])
            except Exception:
                it["opp"] = None
        return it["opp"]

    def score(it):
        return float(it["res"]["decisions"].get("champion", (False, 0.0))[1])

    choix = []
    for it in reserve:
        if it["sym"] in etat["positions"]:
            continue
        ok, risques = X.evaluer(it["res"], champ, n, opportunite=lambda it=it: opportunite(it))
        if ok:
            choix.append((score(it), it, risques))
    if not choix and X.garantie_due(etat, n):
        for it in sorted(reserve, key=score, reverse=True):
            if it["sym"] in etat["positions"]:
                continue
            ok, risques = X.evaluer(it["res"], champ, n, opportunite=lambda it=it: opportunite(it), garantie=True)
            if ok:
                choix = [(score(it), it, risques)]
                log(f"🧪 Garantie d'activité : aucun achat depuis {X.NIVEAUX[n]['garantie_h']} h → meilleur candidat {it['sym']}")
                break
    choix.sort(key=lambda x: x[0], reverse=True)
    for sc, it, risques in choix:
        ok, raison = X.peut_explorer(etat, n, base, etat.get("pnl_jour_exploration", 0.0))
        if not ok:
            log(f"🧪 Exploration arrêtée pour ce cycle : {raison}")
            break
        sym, d, res = it["sym"], it["d"], it["res"]
        if sym in etat["positions"]:
            continue
        try:
            etat_marche = {"F": res["F"], "votes": {k: v for k, (v, _) in res["votes"].items()},
                           "vetos": res["vetos"], "risques": risques}
            did = ledger.decision(sym, "exploration", champ, etat_marche, sc, True, res["vetos"],
                                  f"exploration {n}")
        except Exception as e:
            alerte(f"⚠️ {sym} : journal d'audit indisponible ({e}) → pas de trade.")
            continue
        dist = float(S.distance_stop(champ, res["F"]))
        ordre = calculer_ordre(ex, sym, d, capital, X.RISQUE_PAR_TRADE_PCT / config.RISQUE_PAR_TRADE_PCT, dist)
        if not ordre:
            ledger.issue(did, "exploration non exécutée : montant sous le minimum Binance")
            continue
        acheter(ex, sym, ordre, etat, sc, res["votes"], champ, decision_id=did, mode="exploration", risques=risques)
        if sym in etat["positions"]:
            X.noter_achat(etat)
            ledger.issue(did, "achat d'exploration exécuté ; risques pris : " + (", ".join(risques) or "aucun"))
        else:
            ledger.issue(did, "achat d'exploration échoué")
        sauver_etat(etat)


def nouvelle_bougie(etat):
    """Le scan part ~10 s après la clôture de chaque bougie : signal le plus tôt possible, sans doublon."""
    tranche = int((time.time() - 10) // (config.MINUTES[config.TIMEFRAME_SIGNAL] * 60))
    if tranche != etat.get("derniere_tranche"):
        etat["derniere_tranche"] = tranche
        return True
    return False


def evolution_auto(etat):
    if not config.EVO_AUTO:
        return
    maintenant = dt.datetime.now()
    if maintenant.hour != config.EVO_HEURE or time.time() - etat.get("derniere_evolution", 0) < 20 * 3600:
        return
    etat["derniere_evolution"] = time.time()
    hebdo = maintenant.weekday() == config.EVO_JOUR
    subprocess.Popen([sys.executable, "evolution.py"] + ([] if hebdo else ["--quotidien"]),
                     stdout=open("evolution_console.log", "w"), stderr=subprocess.STDOUT)
    if hebdo:
        subprocess.Popen([sys.executable, "recherche.py"], stdout=open("recherche_console.log", "w"),
                         stderr=subprocess.STDOUT)
    alerte("🧬 " + ("Grande évolution + recherche fondamentale hebdomadaires" if hebdo else "Entraînement quotidien")
           + " lancé(s) en arrière-plan.", important=False)


def rapport_auto(etat):
    aujourdhui = dt.date.today().isoformat()
    if dt.datetime.now().hour >= config.RAPPORT_QUOTIDIEN_HEURE and etat.get("dernier_rapport") != aujourdhui:
        etat["dernier_rapport"] = aujourdhui
        alerte(rapport_journee(etat), important=False)


def taches_horaires(ex, etat):
    ok, ecart = CD.horloge(ex)
    etat["horloge_ko"] = None if ok else (f"horloge décalée de {ecart / 1000:.1f} s" if ecart else "heure Binance illisible")
    reconcilier(ex, etat)
    auditeur.resoudre_fantomes(ex)
    auditeur.resoudre_ombres(ex)
    calibration.resoudre(ex)
    message = auditeur.duel()
    if message:
        alerte(message)
    paliers.proposer(etat)


def main():
    if not securite.prendre_verrou():
        log("⛔ Un autre bot tourne déjà dans ce dossier : arrêt (deux bots = ordres en double).")
        sys.exit(3)
    demarrage = time.time()
    ex = connecter()
    etat = charger_etat()
    etat.setdefault("palier_depuis", time.time())
    ignorer_anciennes()
    securite.battement("démarrage")
    reconcilier(ex, etat, au_demarrage=True)
    sauver_etat(etat)
    if config.REEL:
        alerte(f"⚠️ ARGENT RÉEL : le bot peut engager au maximum {paliers.capital_autorise(etat):.0f} $ (palier {etat.get('palier', 0) + 1}).")
    alerte(f"🤖 Bots v17 démarrés — compte {'DÉMO (argent fictif)' if not config.REEL else 'RÉEL'}, "
           f"ils regardent le marché toutes les {L.UNITES.get(config.TIMEFRAME_SIGNAL, config.TIMEFRAME_SIGNAL)}.\n"
           "Le plus utile : /statut (où on en est) · /rapport (bilan du jour) · /exploration (bilan des essais) · "
           "/tr (Trade Republic) · /v17 (moteur v17) · /marches (monde, notes 0-5) · /note NOM · /renseignement · "
           "/stop (arrêter les achats) · /reprise · /vendre_tout\n"
           "Pour aller plus loin : /notes /sante /journal /univers /evolution /calibration /attente /registre /rearmer")
    etat.setdefault("dernier_achat_ts", time.time())
    etat.setdefault("exploration_depuis", time.time())
    n = X.niveau(etat)
    if n:
        alerte(f"🧪 Mode ESSAIS actif (argent fictif) — niveau {n} sur 3 ({X.NOMS[n]}). Les bots achètent aussi quand "
               "ce n'est pas parfait, pour apprendre de vrais résultats. Chaque achat d'essai est marqué 🧪. "
               "Bilan : /exploration", important=False)
    dernier_horaire = 0.0
    while True:
        try:
            traiter_commandes(ex, etat)
            capital = verifier_jour(ex, etat)
            surveiller(ex, etat)
            disjoncteur.verifier(etat, etat.get("latent_modes", {}).get("strict", etat.get("latent", 0.0)))
            X.verifier_coupe_circuit(etat, paliers.capital_autorise(etat))
            niveau, mult_risque, _ = etat_risque.evaluer(etat)
            if time.time() - dernier_horaire >= 3600:
                dernier_horaire = time.time()
                taches_horaires(ex, etat)
            if nouvelle_bougie(etat):
                cycle_achat(ex, etat, capital, mult_risque)
            evolution_auto(etat)
            rapport_auto(etat)
            securite.message_vivant(etat, capital, demarrage)
            securite.sauvegarde_quotidienne(etat)
            if etat.get("reseau_ko"):
                etat["reseau_ko"] = False
                alerte("✅ La connexion à Binance est revenue.")
            etat["echecs_reseau"] = 0
            sauver_etat(etat)
            securite.battement(f"{len(etat['positions'])} positions, risque {niveau}")
        except ccxt.NetworkError as e:
            etat["echecs_reseau"] = etat.get("echecs_reseau", 0) + 1
            log(f"Réseau instable ({e}), essai {etat['echecs_reseau']}")
            if etat["echecs_reseau"] >= config.ECHECS_RESEAU_MAX and not etat.get("reseau_ko"):
                etat["reseau_ko"] = True
                alerte("🔴 La connexion à Binance est instable : aucun nouvel achat en attendant. "
                       "Les achats en cours restent protégés chez Binance.")
            time.sleep(30)
        except Exception as e:
            alerte(f"❗ Erreur : {e}")
            time.sleep(60)
        time.sleep(config.INTERVALLE_BOUCLE_S)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Arrêt manuel. Les stops restent actifs chez Binance.")
