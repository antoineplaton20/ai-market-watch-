"""EXÉCUTANT METATRADER 5 — l'armée s'entraîne avec de vrais ordres sur ton compte DÉMO.

Trois équipes, chacune avec son numéro magique (ses positions ne se mélangent jamais, ni avec tes ordres manuels) :
- « décisions 4 h » et « décisions 1 j » : exécutent les décisions du chef d'orchestre (seulement quand l'avantage
  attendu dépasse les coûts), taille selon le profil de levier choisi, stop à 3 ATR, fermeture à l'horizon ;
- « entraînement 1 h » : à chaque bougie d'une heure, prend le sens du consensus au lot MINIMUM, même quand
  l'avantage est inférieur aux coûts. Elle sert à mesurer en conditions réelles (écart achat/vente, exécution,
  glissement) ce que valent les pronostics : elle perdra probablement un peu, c'est son rôle de le mesurer.

Garde-fous : aucun ordre si le compte n'est pas un compte démo (vérifié ici ET dans le pont), une seule position
par équipe, « or mt5 fermer » ferme tout et suspend les ordres.
"""
from __future__ import annotations

import math
import time

import numpy as np

from . import base, config, indicateurs as I, mt5, strategie as S, telegram, veille

EQUIPES = {
    "4h": {"magic": 770004, "tf": "4h", "nom": "décisions 4 h", "duree_h": S.UNITES["4h"][0] * S.UNITES["4h"][1]},
    "1d": {"magic": 770024, "tf": "1d", "nom": "décisions 1 j", "duree_h": S.UNITES["1d"][0] * S.UNITES["1d"][1]},
    "entrainement": {"magic": 770001, "tf": "1h", "nom": "entraînement 1 h",
                     "duree_h": S.UNITES["1h"][0] * S.UNITES["1h"][1]},
}
PAR_MAGIC = {e["magic"]: k for k, e in EQUIPES.items()}
MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
STOP_ATR = 3.0


def profil_actif():
    return mt5.nom_profil(base.lire("mt5:profil") or config.MT5_PROFIL) or "pro 1 % risqué"


def entrainement_actif():
    v = base.lire("mt5:entrainement")
    return config.MT5_ENTRAINEMENT if v is None else bool(v)


def _noter(equipe, action, ticket=None, sens=0, volume=0.0, prix=0.0, sl=0.0, ok=True, message=""):
    with base.connexion() as c:
        c.execute("INSERT INTO ordres_mt5(ts, equipe, action, ticket, sens, volume, prix, sl, ok, message) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)", (time.time(), equipe, action, ticket, sens, volume, prix, sl, int(ok),
                                                  str(message)[:300]))


def _atr(tf):
    """ATR 14 sur les bougies FERMÉES du symbole MT5 lui-même."""
    rates = np.array(mt5.appel("bougies", tf=tf, n=120), dtype=float)
    if len(rates) < 30:
        raise mt5.ErreurMT5("pas assez de bougies MT5")
    r = rates[:-1]
    return float(I.atr(r[:, 2], r[:, 3], r[:, 4], 14)[-1])


MARCHE_FERME = 10018                                      # TRADE_RETCODE_MARKET_CLOSED
SILENCE_MARCHE_S = 900                                    # plus aucun cours MT5 depuis 15 min : marché fermé


def marche_ferme():
    """Week-end ou pause quotidienne de l'or : le cours MT5 ne bouge plus (vigie du service flux)."""
    d = base.lire("direct:MT5")
    return bool(d) and time.time() - d.get("ts", 0) > SILENCE_MARCHE_S


def _frais(p, equipe_tf, maintenant_ms):
    """Décision encore fraîche (prise à la clôture de la dernière bougie de l'unité) ?"""
    return p and maintenant_ms - (p["ts"] + MS[equipe_tf]) < min(MS[equipe_tf], 4 * 3_600_000)


def _taux_usd(devise):
    """Valeur d'une unité de la devise du compte en dollars (compte en EUR : cours EURUSD du courtier)."""
    if not devise or devise.upper() == "USD":
        return 1.0
    for symbole, inverse in ((f"{devise}USD", False), (f"USD{devise}", True)):
        try:
            t = mt5.appel("tick", symbole=symbole)
        except mt5.ErreurMT5:
            continue
        milieu = (t["bid"] + t["ask"]) / 2
        if milieu > 0:
            return 1 / milieu if inverse else milieu
    raise mt5.ErreurMT5(f"cours {devise}/USD introuvable pour convertir le capital")


def _ouvrir(cle, sens, compte, pos_avant, entrainement=False):
    eq = EQUIPES[cle]
    specs = mt5.appel("specs")
    tick = mt5.appel("tick")
    prix = tick["ask"] if sens > 0 else tick["bid"]
    atr = _atr(eq["tf"])
    stop = prix - sens * STOP_ATR * atr
    if entrainement:
        lots, explication = specs["volume_min"], f"lot minimum {specs['volume_min']:g} (entraînement)"
        if mt5.appel("marge", sens=sens, volume=lots) > 0.9 * compte["margin_free"]:
            lots, explication = 0.0, "marge insuffisante"
    else:
        marge_lot = mt5.appel("marge", sens=sens, volume=1.0)            # dans la devise du compte
        taux = _taux_usd(compte.get("currency"))                          # capital converti en dollars (XAUUSD)
        lots, explication = mt5.volume(profil_actif(), compte["equity"] * taux, prix, stop, specs, marge_lot * taux,
                                       compte["margin_free"] * taux)
    if lots <= 0:
        _noter(cle, "refus", sens=sens, prix=prix, sl=stop, ok=False, message=explication)
        return f"{eq['nom']} : pas d'ordre ({explication})"
    r = mt5.appel("ouvrir", sens=sens, volume=lots, sl=stop, magic=eq["magic"],
                  commentaire=f"armee-or {cle}")
    _noter(cle, "ouverture", r.get("ordre"), sens, lots, r.get("prix") or prix, stop, r["ok"],
           f"{r['retcode']} {r['commentaire']} · {explication}")
    if not r["ok"] and r["retcode"] == MARCHE_FERME:
        return f"{eq['nom']} : marché fermé, pas d'ordre"
    if not r["ok"]:
        telegram.alerte_rare(f"mt5-refus-{cle}", f"⚠️ MT5 a refusé l'ordre ({eq['nom']}) : {r['retcode']} "
                             f"{r['commentaire']}", 3600, important=True)
        return f"{eq['nom']} : ordre refusé ({r['retcode']} {r['commentaire']})"
    from . import apprentissage                             # mesure du glissement réel (prix demandé / obtenu)
    apprentissage.enregistrer_execution(cle, sens, prix, r.get("prix"), lots)
    suivi = base.lire("mt5:suivi", {}) or {}
    for p in mt5.appel("positions"):
        if p["magic"] == eq["magic"] and str(p["ticket"]) not in suivi and p["ticket"] not in pos_avant:
            suivi[str(p["ticket"])] = {"equipe": cle, "ouverture": time.time(), "fin": time.time() + eq["duree_h"] * 3600,
                                       "sens": sens, "volume": p["volume"], "prix": p["price_open"], "sl": p["sl"]}
    base.ecrire("mt5:suivi", suivi)
    texte = (f"🤖 MT5 démo · {eq['nom']} : {'ACHAT' if sens > 0 else 'VENTE'} {lots:g} lot "
             f"{specs.get('name') or config.MT5_SYMBOLE} ({lots * specs['trade_contract_size']:g} oz) à "
             f"{r.get('prix') or prix:.2f} · stop {stop:.2f} ({STOP_ATR:g} ATR) · fermeture prévue dans "
             f"{eq['duree_h']} h · {explication}")
    if not entrainement:
        telegram.envoyer(texte + f" · profil {profil_actif()}", important=True)
    return texte


def fermer_tout(motif="demande"):
    faits = []
    for p in mt5.appel("positions"):
        r = mt5.appel("fermer", ticket=p["ticket"], commentaire=f"armee-or {motif}"[:25])
        _noter(PAR_MAGIC.get(p["magic"], "?"), "fermeture", p["ticket"], 0, p["volume"], r.get("prix") or 0, 0,
               r["ok"], f"{motif} · {r['retcode']} {r['commentaire']}")
        faits.append(p["ticket"])
    base.ecrire("mt5:suivi", {})
    return faits


def resultats(force=False):
    """Résultats réalisés par équipe depuis le branchement (bénéfice + commissions + swap), mis en cache 5 min."""
    r = base.lire("mt5:resultats")
    if r and not force and time.time() - r["ts"] < 300:
        return r
    depuis = base.lire("mt5:depuis") or time.time()
    out = {k: {"pnl": 0.0, "trades": 0, "gagnants": 0} for k in EQUIPES}
    par_position = {}
    for d in mt5.appel("historique", depuis=depuis):
        k = PAR_MAGIC.get(d["magic"])
        if not k:
            continue
        net = d["profit"] + d["commission"] + d["swap"] + d["fee"]
        out[k]["pnl"] += net
        par_position.setdefault((k, d["position_id"]), [0.0, False])
        par_position[(k, d["position_id"])][0] += net
        if d["entry"] in (1, 3):                                  # sortie de position
            par_position[(k, d["position_id"])][1] = True
    for (k, _), (net, fermee) in par_position.items():
        if fermee:
            out[k]["trades"] += 1
            out[k]["gagnants"] += int(net > 0)
    r = {"ts": time.time(), "equipes": out}
    base.ecrire("mt5:resultats", r)
    return r


def bot_mt5(chef):
    if not config.MT5_ACTIF:
        return "MT5 non configuré"
    if not base.lire("mt5:depuis"):
        base.ecrire("mt5:depuis", time.time())
    inst = etat_installation()
    if inst and not inst.startswith(("installation réussie", "installé")):
        return f"MT5 pas encore installé ({inst})"          # pas d'alerte à répétition : /or_mt5 donne l'état
    try:
        etat = mt5.appel("etat", delai=150)
    except mt5.ErreurMT5 as ex:
        telegram.alerte_rare("mt5-pont", f"🔴 MT5 : {ex}. Le service se relance seul ; or mt5 pour le détail.",
                             6 * 3600)
        raise
    base.ecrire("mt5:etat", {**etat, "ts": time.time()})
    compte = etat.get("compte")
    if not etat["connecte"] or not compte:
        telegram.alerte_rare("mt5-connexion", f"🔴 MT5 non connecté : {etat.get('erreur') or 'en attente du serveur'}. "
                             "Nouvel essai automatique.", 3600)
        return f"MT5 non connecté ({etat.get('erreur')})"
    if not compte["demo"]:
        telegram.alerte_rare("mt5-reel", "⛔ Le compte MT5 connecté n'est PAS un compte démo : l'armée ne passe AUCUN "
                             "ordre. Règle un compte démo avec « or mt5 compte ».", 6 * 3600, important=True)
        return "compte réel détecté : aucun ordre"

    # 1) suivi des positions : fermeture à l'horizon, positions disparues (stop touché ou fermeture manuelle)
    positions = {p["ticket"]: p for p in mt5.appel("positions")}
    suivi = base.lire("mt5:suivi", {}) or {}
    msgs = []
    for t, p in positions.items():
        if str(t) not in suivi:
            cle = PAR_MAGIC.get(p["magic"], "entrainement")
            suivi[str(t)] = {"equipe": cle, "ouverture": time.time(),
                             "fin": time.time() + EQUIPES[cle]["duree_h"] * 3600, "sens": 1 if p["type"] == 0 else -1,
                             "volume": p["volume"], "prix": p["price_open"], "sl": p["sl"]}
    for t, s in list(suivi.items()):
        if int(t) not in positions:
            _noter(s["equipe"], "sortie", int(t), s["sens"], s["volume"], 0, s["sl"], True, "stop touché ou fermée à la main")
            suivi.pop(t)
            msgs.append(f"{EQUIPES[s['equipe']]['nom']} : position {t} sortie (stop ou manuel)")
        elif time.time() >= s["fin"]:
            r = mt5.appel("fermer", ticket=int(t), commentaire=f"armee-or fin {s['equipe']}")
            _noter(s["equipe"], "fermeture", int(t), s["sens"], s["volume"], r.get("prix") or 0, s["sl"], r["ok"],
                   f"horizon atteint · {r['retcode']} {r['commentaire']}")
            if r["ok"]:
                suivi.pop(t)
                p = positions[int(t)]
                gain = p["profit"] + p["swap"]
                msgs.append(f"{EQUIPES[s['equipe']]['nom']} : fermée à l'horizon ({gain:+.2f} {compte['currency']})")
                if s["equipe"] != "entrainement":
                    telegram.envoyer(f"🤖 MT5 démo · {EQUIPES[s['equipe']]['nom']} : position fermée à l'horizon, "
                                     f"{gain:+.2f} {compte['currency']}.")
    base.ecrire("mt5:suivi", suivi)

    # 2) nouvelles positions
    if chef.pause or base.lire("mt5:pause"):
        return "; ".join(msgs + ["ordres en pause"])
    annonce = veille.evenement_proche()
    if annonce:                                           # annonce économique majeure : ni avant ni pendant la secousse
        return "; ".join(msgs + [f"annonce « {annonce['titre']} » : aucun nouvel ordre de 15 min avant à 15 min après"])
    if not (etat.get("terminal") or {}).get("trade_allowed") or not compte.get("trade_allowed", True):
        telegram.alerte_rare("mt5-algo", "⚠️ MT5 refuse les ordres automatiques (trading algorithmique désactivé, ou "
                             "mot de passe INVESTISSEUR = lecture seule). Donne le mot de passe principal : « or mt5 "
                             "compte », puis « or redemarrer ».", 6 * 3600, important=True)
        return "; ".join(msgs + ["trading algorithmique non autorisé par le terminal"])
    if marche_ferme():
        return "; ".join(msgs + ["marché de l'or fermé (week-end ou pause) : aucun nouvel ordre"])
    maintenant_ms = time.time() * 1000
    ouvertes = {s["equipe"] for s in suivi.values()}
    for cle in ("4h", "1d"):
        p = base.lire(f"prono:{cle}")
        if not p or not p["sens"] or not _frais(p, cle, maintenant_ms) or base.lire(f"mt5:fait:{cle}") == p["ts"]:
            continue
        base.ecrire(f"mt5:fait:{cle}", p["ts"])                     # une décision = un ordre au plus
        if cle in ouvertes:
            msgs.append(f"{EQUIPES[cle]['nom']} : position déjà ouverte, décision ignorée")
            continue
        msgs.append(_ouvrir(cle, int(p["sens"]), compte, set(positions)))
    if entrainement_actif() and "entrainement" not in ouvertes:
        p = base.lire("prono:1h")
        if p and _frais(p, "1h", maintenant_ms) and base.lire("mt5:fait:entrainement") != p["ts"] and p["p"] != 0.5:
            base.ecrire("mt5:fait:entrainement", p["ts"])
            msgs.append(_ouvrir("entrainement", 1 if p["p"] > 0.5 else -1, compte, set(positions), entrainement=True))
    return "; ".join(msgs) or f"{len(positions)} position(s), équité {compte['equity']:.2f} {compte['currency']}"


def etat_installation():
    """Dernier état écrit par installer_mt5.sh (« échec|étape », « ok|connecté »…), lisible depuis Telegram."""
    try:
        statut, _, detail = (config.RACINE / "runtime" / "installation_mt5.txt").read_text().strip().partition("|")
    except OSError:
        return None
    return {"échec": f"installation arrêtée à l'étape « {detail} »", "en cours": f"installation en cours ({detail})",
            "installé": "installé, connexion en attente", "ok": "installation réussie"}.get(statut, statut)


def analyser_trades(deals, taille_contrat=100.0, ecart=None, taux=1.0):
    """Positions fermées de l'armée, dans l'ordre du temps : résultat net décomposé en mouvement du marché,
    écart achat/vente (estimé avec l'écart médian mesuré) et frais (commission, nuit), devise du compte."""
    pos = {}
    for d in deals:
        k = PAR_MAGIC.get(d["magic"])
        if not k:
            continue
        p = pos.setdefault(d["position_id"], {"equipe": k, "brut": 0.0, "frais": 0.0, "notionnel": 0.0, "t": 0,
                                              "ferme": False})
        p["brut"] += d["profit"]
        p["frais"] += d["commission"] + d["swap"] + d["fee"]
        if d["entry"] == 0:
            p["notionnel"] = d["volume"] * taille_contrat * d["price"]
        elif d["entry"] in (1, 3):
            p["ferme"], p["t"] = True, max(p["t"], d["time"])
    fermees = sorted((p for p in pos.values() if p["ferme"]), key=lambda p: p["t"])
    for p in fermees:
        p["ecart"] = (ecart or 0.0) * p["notionnel"] / (taux or 1.0)    # payé à l'aller-retour, déjà dans « brut »
        p["mouvement"] = p["brut"] + p["ecart"]
        p["net"] = p["brut"] + p["frais"]
    return fermees


def texte_trades(fermees, devise=""):
    if not fermees:
        return "🔎 Trades MT5 : aucune position fermée pour l'instant."
    lignes = ["🔎 Diagnostic des trades MT5 (positions fermées de l'armée)"]
    for k, eq in EQUIPES.items():
        t = [p for p in fermees if p["equipe"] == k]
        if t:
            g = sum(p["net"] > 0 for p in t)
            lignes.append(f"• {eq['nom']} : {len(t)} trades · {g} gagnants ({100 * g / len(t):.0f} %) · net "
                          f"{sum(p['net'] for p in t):+.2f} {devise} ({sum(p['net'] for p in t) / len(t):+.2f} par trade)")
    n = len(fermees)
    if n >= 4:
        m = n // 2
        lignes.append(f"Évolution : 1re moitié ({m} trades) {sum(p['net'] for p in fermees[:m]):+.2f} · 2e moitié "
                      f"({n - m} trades) {sum(p['net'] for p in fermees[m:]):+.2f} {devise}")
    mouv, ecart, frais = (sum(p[c] for p in fermees) for c in ("mouvement", "ecart", "frais"))
    lignes.append(f"D'où vient le résultat : mouvement du marché dans le sens choisi {mouv:+.2f} · écart achat/vente "
                  f"≈ {-ecart:+.2f} · commissions et nuits {frais:+.2f} = net {mouv - ecart + frais:+.2f} {devise}")
    bons = sum(p["mouvement"] > 0 for p in fermees)
    z = (bons - n / 2) / math.sqrt(n / 4)
    lignes.append(f"Bon sens (avant frais) : {bons}/{n} ({100 * bons / n:.0f} %) · écart au pile ou face : z = {z:+.2f}"
                  f" · avec {n} trades, seul un taux hors de 50 ± {100 / math.sqrt(n):.0f} % se distingue du hasard")
    if abs(z) < 2:
        verdict = ("aucune preuve d'avantage ni de désavantage : les séries gagnantes puis perdantes sont compatibles "
                   "avec le hasard")
        if mouv - ecart + frais < 0:
            verdict += "; ce qui est sûr, ce sont les frais, payés à chaque trade"
    elif z > 0:
        verdict = "le sens choisi est juste plus souvent que le hasard (à confirmer sur plus de trades)"
    else:
        verdict = "le sens choisi est faux plus souvent que le hasard : les pronostics sont à revoir"
    lignes.append("Verdict : " + verdict + ".")
    lignes.append("Ce que l'armée en apprend : les frais réels (écart, glissement, commissions, nuits) remplacent "
                  "l'estimation dans la règle « avantage > 1,5 × coûts ». Le gain ou la perte d'un trade ne change PAS "
                  "les poids : ils suivent les pronostics jugés à chaque bougie, bien plus nombreux (voir /or_apprentissage).")
    return "\n".join(lignes)


def rapport_trades():
    if not config.MT5_ACTIF:
        return "🔎 Trades MT5 : MT5 non branché."
    try:
        deals = mt5.appel("historique", depuis=base.lire("mt5:depuis") or time.time() - 30 * 86400)
        specs = mt5.appel("specs")
    except mt5.ErreurMT5 as ex:
        return f"🔎 Trades MT5 : pont injoignable ({ex})."
    compte = (base.lire("mt5:etat") or {}).get("compte") or {}
    try:
        taux = _taux_usd(compte.get("currency"))
    except mt5.ErreurMT5:
        taux = 1.0
    ecart = (base.lire("apprentissage:couts") or {}).get("ecart")
    fermees = analyser_trades(deals, specs["trade_contract_size"], ecart, taux)
    return texte_trades(fermees, compte.get("currency") or "")


def rapport_mt5():
    inst = etat_installation()
    if not config.MT5_ACTIF:
        return ("MT5 non branché" + (f" · {inst}" if inst else "") + ". Dans Termius : « or mt5 installer » "
                "(identifiants demandés en premier ; le résultat arrive ici).")
    e = base.lire("mt5:etat")
    if not e or not e.get("compte"):
        return ("MT5 : pas encore connecté" + (f" ({e.get('erreur')})" if e and e.get("erreur") else "")
                + (f" · {inst}" if inst and not inst.startswith("installation réussie") else "") + ".")
    c = e["compte"]
    lignes = [f"MT5 {'DÉMO' if c['demo'] else 'RÉEL (aucun ordre)'} · compte …{str(c['login'])[-3:]} · solde "
              f"{c['balance']:.2f} · équité {c['equity']:.2f} {c['currency']} · levier du compte 1:{c['leverage']}"
              + (" · ⏸ ordres en pause" if base.lire("mt5:pause") else "")]
    lignes.append(f"Profil des décisions : {profil_actif()} · entraînement {'actif' if entrainement_actif() else 'arrêté'}")
    for t, s in (base.lire("mt5:suivi", {}) or {}).items():
        reste = max(0, s["fin"] - time.time()) / 3600
        lignes.append(f"• {EQUIPES[s['equipe']]['nom']} : {'ACHAT' if s['sens'] > 0 else 'VENTE'} {s['volume']:g} lot à "
                      f"{s['prix']:.2f}, stop {s['sl']:.2f}, fin dans {reste:.1f} h")
    try:
        r = resultats()
    except mt5.ErreurMT5:
        r = base.lire("mt5:resultats")
    if r:
        lignes.append("Résultats réalisés : " + " · ".join(
            f"{EQUIPES[k]['nom']} {v['pnl']:+.2f} ({v['trades']} trades, {v['gagnants']} gagnants)"
            for k, v in r["equipes"].items()))
    return "\n".join(lignes)
