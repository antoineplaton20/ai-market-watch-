"""GARDIEN : taille des positions, exécution, stop-loss posé CHEZ BINANCE, surveillance.
Aucune IA ici : que des règles fixes. C'est lui qui garde les pertes petites."""
import datetime
import json
import os
import time
import config
import langage as L
import auditeur
import ledger
import paliers
from alertes import alerte, log


def _journal(*args, **kwargs):
    """Le journal d'audit ne doit jamais empêcher une action de PROTECTION (stop, vente)."""
    try:
        ledger.ordre(*args, **kwargs)
    except Exception as e:
        log(f"⚠️ Journal d'audit indisponible ({e})")

FICHIER_ETAT = "etat.json"


# ============================ ÉTAT PERSISTANT ============================
def charger_etat():
    if os.path.exists(FICHIER_ETAT):
        with open(FICHIER_ETAT, encoding="utf-8") as f:
            return json.load(f)
    return {"positions": {}, "quarantaine": {}, "jour": "", "arret_jour": False, "arret_manuel": False}


def sauver_etat(etat):
    tmp = FICHIER_ETAT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(etat, f, indent=2)
    os.replace(tmp, FICHIER_ETAT)


# ================================ OUTILS =================================
def _qte(ex, sym, q):
    return float(ex.amount_to_precision(sym, q))


def _prix(ex, sym, p):
    return float(ex.price_to_precision(sym, p))


def _base_libre(ex, sym):
    base = ex.markets[sym]["base"]
    return float(ex.fetch_balance()["free"].get(base, 0) or 0)


def valeur_positions(ex, etat):
    """Renvoie (valeur actuelle des positions, gain/perte latent). v14 : latent aussi par mode (strict / exploration)."""
    valeur = latent = 0.0
    modes = {"strict": 0.0, "exploration": 0.0}
    for sym, p in etat["positions"].items():
        prix = ex.fetch_ticker(sym)["bid"]
        valeur += p["quantite"] * prix
        l = (prix - p["entree"]) * p["quantite"]
        latent += l
        modes[p.get("mode", "strict")] = modes.get(p.get("mode", "strict"), 0.0) + l
    etat["latent_modes"] = modes
    return valeur, latent


# ============================ RÈGLES DU JOUR =============================
def verifier_jour(ex, etat):
    """Coupe les achats si la perte du jour atteint la limite. Renvoie le capital utilisable."""
    aujourdhui = datetime.date.today().isoformat()
    if etat["jour"] != aujourdhui:
        etat["jour"] = aujourdhui
        etat["arret_jour"] = False
    minuit = datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()
    valeur, latent = valeur_positions(ex, etat)
    etat["latent"] = latent
    base = paliers.capital_autorise(etat)
    # v14 : la limite de perte du jour juge le champion STRICT ; l'exploration (démo) a son propre budget
    modes = etat.get("latent_modes", {})
    pnl_jour = auditeur.pnl_depuis(minuit, "strict") + modes.get("strict", latent)
    etat["pnl_jour"] = pnl_jour
    etat["pnl_jour_exploration"] = auditeur.pnl_depuis(minuit, "exploration") + modes.get("exploration", 0.0)
    limite = -base * config.PERTE_JOUR_MAX_PCT / 100
    if pnl_jour <= limite and not etat["arret_jour"]:
        etat["arret_jour"] = True
        alerte(f"🛑 Perte du jour : {L.dollars(pnl_jour)}. Plus aucun achat jusqu'à demain. "
               "Les achats en cours restent protégés.")
    usdt = float(ex.fetch_balance()["total"].get(config.DEVISE, 0) or 0)
    return min(usdt + valeur, base + auditeur.pnl_depuis(etat.get("palier_depuis", 0.0)))


def peut_acheter(etat):
    return (not etat["arret_manuel"] and not etat["arret_jour"] and not etat.get("disjoncteur")
            and time.time() >= etat.get("pause_jusqua", 0) and etat.get("niveau_risque") != "ARRÊT"
            and not etat.get("donnees_ko") and not etat.get("reseau_ko")
            and sum(1 for p in etat["positions"].values() if p.get("mode", "strict") == "strict") < config.POSITIONS_MAX)


# ============================== EXÉCUTION ================================
def poser_stop(ex, sym, qte, stop):
    """Stop-loss enregistré chez Binance : il se déclenche même si ton PC est éteint."""
    o = ex.create_order(
        sym, "STOP_LOSS_LIMIT", "sell", _qte(ex, sym, qte), _prix(ex, sym, stop * 0.995),
        {"stopPrice": _prix(ex, sym, stop), "timeInForce": "GTC",
         "newClientOrderId": f"eqb{int(time.time() * 1000)}"},       # signature : ordre créé par le bot
    )
    return o["id"]


def calculer_ordre(ex, sym, d, capital, multiplicateur=1.0, stop_atr=None):
    """Taille calculée pour que, si le stop est touché, la perte = 1 % du capital (x le modulateur PEUR & AVIDITÉ)."""
    try:
        atr_v = float(d["df"].iloc[-2]["atr"])
        prix = float(ex.fetch_ticker(sym)["ask"])
        stop = prix - (stop_atr or config.STOP_ATR) * atr_v
        if stop <= 0:
            return None
        # Risque réel par unité = distance au stop + frais aller-retour + glissement du stop limite (0,5 %)
        risque_unitaire = (prix - stop) + prix * config.FRAIS_ALLER_RETOUR_PCT / 100 + stop * 0.005
        qte = (capital * config.RISQUE_PAR_TRADE_PCT / 100 * multiplicateur) / risque_unitaire
        qte = min(qte, capital * config.POSITION_MAX_PCT / 100 / prix)
        usdt_libre = float(ex.fetch_balance()["free"].get(config.DEVISE, 0) or 0)
        qte = _qte(ex, sym, min(qte, usdt_libre * 0.98 / prix))
        cout_min = ((ex.markets[sym].get("limits") or {}).get("cost") or {}).get("min") or 5
        if qte * prix < cout_min * 1.2:
            return None
        return {"prix": prix, "quantite": qte, "atr": atr_v, "stop_atr": stop_atr or config.STOP_ATR}
    except Exception as e:
        log(f"{sym} : ordre impossible à calculer ({e})")
        return None


def acheter(ex, sym, ordre, etat, score, votes, genome=None, decision_id=None, mode="strict", risques=None):
    import strategie
    ps = strategie.params_sortie(genome) if genome else {
        "stop_atr": config.STOP_ATR, "secu_r": config.SECURISATION_R, "trailing_atr": config.TRAILING_ATR,
        "objectif_atr": config.OBJECTIF_ATR,
        "horizon_bougies": int(config.DUREE_MAX_H * 60 / config.MINUTES[config.TIMEFRAME_SIGNAL])}
    achat = ex.create_order(sym, "market", "buy", ordre["quantite"])
    _journal(decision_id, sym, "buy", "market", ordre["quantite"], ordre["prix"], achat, "entrée")
    entree = float(achat.get("average") or ordre["prix"])
    recu = float(achat.get("filled") or ordre["quantite"])
    qte = 0.0
    for _ in range(5):                # le solde peut mettre quelques secondes à se mettre à jour
        time.sleep(1)
        qte = min(recu, _base_libre(ex, sym))
        if _qte(ex, sym, qte) * entree >= 5:
            break
    else:
        qte = recu * 0.999            # frais maximum déduits : on protège quand même ce qui a été acheté
        alerte(f"⚠️ {sym} : solde lent à s'afficher, stop posé sur la quantité achetée moins les frais.")
    stop = entree - ordre.get("stop_atr", ps["stop_atr"]) * ordre["atr"]
    objectif = entree + ps["objectif_atr"] * ordre["atr"]
    try:
        id_stop = poser_stop(ex, sym, qte, stop)
        _journal(decision_id, sym, "sell", "stop_loss_limit", qte, stop, {"id": id_stop}, "stop initial")
    except Exception as e:
        alerte(f"⚠️ {sym} : Binance refuse la vente de protection ({e}). Revente immédiate : jamais d'achat sans protection.")
        try:
            ex.create_order(sym, "market", "sell", _qte(ex, sym, qte))
            return
        except Exception as e2:
            # Ni stop ni revente possibles (panne Binance) : la position est suivie quand même,
            # la surveillance réessaie toutes les 20 s et le filet de secours reste actif.
            alerte(f"🚨 {sym} : la revente est refusée aussi ({e2}). Achat suivi SANS protection, le bot réessaie en continu.")
            id_stop = "aucun"
    etat["positions"][sym] = {
        "entree": entree, "quantite": qte, "stop": stop, "stop_initial": stop,
        "objectif": objectif, "atr": ordre["atr"], "id_stop": id_stop, "securise": False,
        "plus_haut": entree, "secu_r": ps["secu_r"], "trailing_atr": ps["trailing_atr"],
        "part_frac": ps.get("part_frac", 0.0), "part_r": ps.get("part_r", 1.0), "qte_initiale": qte,
        "horizon_h": ps["horizon_bougies"] * config.MINUTES[config.TIMEFRAME_SIGNAL] / 60,
        "signal_tf": config.TIMEFRAME_SIGNAL, "entry_tf": config.TIMEFRAME_ENTRY,
        "risk_tf": config.TIMEFRAME_SIGNAL,
        "genome": (genome or {}).get("id", "config"), "decision_id": decision_id,
        "ouvert": time.time(), "votes": {k: v for k, (v, _) in votes.items()},
        "mode": mode, "risques": list(risques or []),
    }
    etat["dernier_achat_ts"] = time.time()
    base = sym.split("/")[0]
    corps = (f"Acheté : {L.dollars(qte * entree)} à {L.prix(entree)} $\n"
             f"🛡 Revente automatique si le prix baisse à {L.prix(stop)} $ ({L.pct((stop / entree - 1) * 100)})\n"
             f"🎯 Objectif : {L.prix(objectif)} $ ({L.pct((objectif / entree - 1) * 100)})\n"
             f"Confiance de l'équipe : {L.pourcent(score)}")
    if mode == "exploration":
        alerte(f"🧪 ACHAT D'ESSAI — {base} (argent fictif)\n{corps}\n"
               f"Pourquoi c'est un essai (le bot prudent ne l'aurait pas fait) :\n{L.puces(risques)}")
    else:
        alerte(f"🟢 ACHAT — {base}\n{corps}")


def cloturer(etat, sym, sortie, raison):
    p = etat["positions"].pop(sym)
    pnl_pct, pnl_usdt = auditeur.enregistrer(sym, p, sortie, raison)
    if pnl_pct < 0:
        etat["quarantaine"][sym] = time.time() + config.QUARANTAINE_H * 3600
    icone = "✅" if pnl_pct > 0 else "🔻"
    explo = " (essai 🧪)" if p.get("mode") == "exploration" else ""
    alerte(f"{icone} VENTE — {sym.split('/')[0]}{explo} : {'gagné' if pnl_usdt > 0 else 'perdu'} "
           f"{L.dollars(abs(pnl_usdt))} ({L.pct(pnl_pct)}, frais compris)\n"
           f"Revendu à {L.prix(sortie)} $ · raison : {L.raison_vente(raison)}")
    if p.get("decision_id"):
        try:
            ledger.issue(p["decision_id"], f"clôturée ({raison}) {pnl_pct:+.2f} %")
        except Exception:
            pass


def vendre(ex, sym, etat, raison):
    p = etat["positions"][sym]
    try:
        o = ex.fetch_order(p["id_stop"], sym)
        if o["status"] == "closed":  # le stop a déjà vendu entre-temps
            cloturer(etat, sym, float(o.get("average") or o.get("price") or p["stop"]), "stop-loss")
            return
        ex.cancel_order(p["id_stop"], sym)
        deja = float(o.get("filled") or 0)
        if deja > 0:                 # stop exécuté en partie : cette partie est comptée à son vrai prix
            px = float(o.get("average") or p["stop"])
            p["gain_partiel_usdt"] = p.get("gain_partiel_usdt", 0.0) + (px - p["entree"]) * deja
            p["quantite"] = max(0.0, p["quantite"] - deja)
    except Exception:
        pass
    time.sleep(1)
    vendu, montant = 0.0, 0.0
    for essai in range(3):           # un ordre au marché peut n'être exécuté qu'en partie : on termine la vente
        try:
            reste = min(p["quantite"] - vendu, _base_libre(ex, sym))
            q = _qte(ex, sym, reste)
            if q <= 0 or q * float(ex.fetch_ticker(sym)["bid"]) < 5:
                break
            voulu = float(ex.fetch_ticker(sym)["bid"])
            o = ex.create_order(sym, "market", "sell", q)
            _journal(p.get("decision_id"), sym, "sell", "market", q, voulu, o, raison)
            fait = float(o.get("filled") if o.get("filled") is not None else q)
            vendu += fait
            montant += fait * float(o.get("average") or ex.fetch_ticker(sym)["bid"])
            if fait >= q * 0.999:
                break
            time.sleep(1)
        except Exception as e:
            if vendu == 0:
                alerte(f"❌ Vente {sym} échouée ({e}). Vérifie sur Binance !")
                return
            break
    if vendu == 0:
        alerte(f"❌ Vente {sym} : rien n'a pu être vendu. Vérifie sur Binance !")
        return
    if vendu < p["quantite"] * 0.98:
        alerte(f"⚠️ {sym} : vente incomplète ({vendu:.6g} sur {p['quantite']:.6g}), le reste est à vérifier sur Binance.")
    cloturer(etat, sym, montant / vendu, raison)


def vendre_tout(ex, etat):
    for sym in list(etat["positions"]):
        vendre(ex, sym, etat, "vente manuelle")


# ============================= SURVEILLANCE ==============================
def surveiller(ex, etat):
    for sym in list(etat["positions"]):
        p = etat["positions"][sym]

        # 0. Position sans stop (panne au moment de l'achat) : on réessaie, sinon on vend
        if p["id_stop"] == "aucun":
            try:
                p["id_stop"] = poser_stop(ex, sym, p["quantite"], p["stop"])
                alerte(f"✅ {sym} : la vente de protection est enfin en place.")
            except Exception:
                vendre(ex, sym, etat, "stop toujours impossible, sortie par sécurité")
                continue

        # 1. Le stop chez Binance a-t-il déjà vendu ?
        try:
            o = ex.fetch_order(p["id_stop"], sym)
        except Exception as e:
            log(f"{sym} : statut du stop illisible ({e})")
            o = None
        if o and o["status"] == "closed":
            cloturer(etat, sym, float(o.get("average") or o.get("price") or p["stop"]), "stop-loss")
            continue
        if o and o["status"] in ("canceled", "expired", "rejected"):
            try:
                p["id_stop"] = poser_stop(ex, sym, p["quantite"], p["stop"])
                log(f"{sym} : stop disparu, reposé")
            except Exception:
                vendre(ex, sym, etat, "stop perdu, sortie par sécurité")
                continue

        prix = float(ex.fetch_ticker(sym)["bid"])
        un_r = p["entree"] - p["stop_initial"]
        p["plus_haut"] = max(p.get("plus_haut", p["entree"]), prix)

        # 2. Sécurisation puis TRAILING : le stop ne fait que monter
        cible = p["stop"]
        if not p["securise"] and p["plus_haut"] >= p["entree"] + p.get("secu_r", config.SECURISATION_R) * un_r:
            cible = p["entree"] * (1 + config.SECURISATION_MARGE_PCT / 100)   # même niveau qu'en backtest
        if p["securise"] or cible > p["stop"]:
            cible = max(cible, p["plus_haut"] - p.get("trailing_atr", config.TRAILING_ATR) * p["atr"])
        if cible > p["stop"] + (0 if not p["securise"] else config.TRAILING_PAS_ATR * p["atr"]) and cible < prix:
            try:
                ex.cancel_order(p["id_stop"], sym)
                p["id_stop"] = poser_stop(ex, sym, p["quantite"], cible)
                _journal(p.get("decision_id"), sym, "sell", "stop_loss_limit", p["quantite"], cible,
                         {"id": p["id_stop"]}, "stop remonté")
                premier = not p["securise"]
                p["stop"], p["securise"] = cible, True
                if premier:
                    alerte(f"🔒 {sym.split('/')[0]} : cet achat ne peut plus faire perdre d'argent — le seuil de "
                           f"protection est remonté au-dessus du prix d'achat.")
                else:
                    alerte(f"↗️ {sym.split('/')[0]} : seuil de protection remonté à {L.prix(cible)} $ "
                           f"(gain déjà protégé : {L.pct((cible / p['entree'] - 1) * 100)})", important=False)
            except Exception as e:
                vendre(ex, sym, etat, f"déplacement du stop impossible ({e})")
                continue

        # 3. Prise de bénéfices partielle (si le gène du champion la prévoit)
        pf, pr = p.get("part_frac", 0.0), p.get("part_r", 1.0)
        if pf > 0.05 and not p.get("partiel") and prix >= p["entree"] + pr * un_r:
            p["partiel"] = True
            qte_vente = _qte(ex, sym, p["quantite"] * pf)
            if qte_vente * prix >= 6 and (p["quantite"] - qte_vente) * prix >= 6:
                try:
                    ex.cancel_order(p["id_stop"], sym)
                    o = ex.create_order(sym, "market", "sell", qte_vente)
                    _journal(p.get("decision_id"), sym, "sell", "market", qte_vente, prix, o, "prise partielle")
                    px = float(o.get("average") or prix)
                    p["gain_partiel_usdt"] = p.get("gain_partiel_usdt", 0.0) + (px - p["entree"]) * qte_vente
                    time.sleep(1)
                    p["quantite"] = min(p["quantite"] - qte_vente, _base_libre(ex, sym))
                    p["id_stop"] = poser_stop(ex, sym, p["quantite"], p["stop"])
                    alerte(f"💰 {sym.split('/')[0]} : {pf:.0%} revendus à {L.prix(px)} $ "
                           f"({L.pct((px / p['entree'] - 1) * 100)}). Le reste continue, avec un seuil de protection "
                           f"qui monte avec le prix.")
                except Exception as e:
                    vendre(ex, sym, etat, f"prise partielle impossible ({e})")
                    continue

        # 4. Sorties
        if prix >= p["objectif"]:
            vendre(ex, sym, etat, "objectif atteint")
        elif prix <= p["stop"] * 0.99:
            vendre(ex, sym, etat, "filet de secours")  # si le stop Binance n'a pas été exécuté
        elif time.time() - p["ouvert"] > p.get("horizon_h", config.DUREE_MAX_H) * 3600:
            vendre(ex, sym, etat, "trop long sans résultat")
