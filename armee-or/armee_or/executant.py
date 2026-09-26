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

import time

import numpy as np

from . import base, config, indicateurs as I, mt5, strategie as S, telegram

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


def _frais(p, equipe_tf, maintenant_ms):
    """Décision encore fraîche (prise à la clôture de la dernière bougie de l'unité) ?"""
    return p and maintenant_ms - (p["ts"] + MS[equipe_tf]) < min(MS[equipe_tf], 4 * 3_600_000)


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
        marge_lot = mt5.appel("marge", sens=sens, volume=1.0)
        lots, explication = mt5.volume(profil_actif(), compte["equity"], prix, stop, specs, marge_lot,
                                       compte["margin_free"])
    if lots <= 0:
        _noter(cle, "refus", sens=sens, prix=prix, sl=stop, ok=False, message=explication)
        return f"{eq['nom']} : pas d'ordre ({explication})"
    r = mt5.appel("ouvrir", sens=sens, volume=lots, sl=stop, magic=eq["magic"],
                  commentaire=f"armee-or {cle}")
    _noter(cle, "ouverture", r.get("ordre"), sens, lots, r.get("prix") or prix, stop, r["ok"],
           f"{r['retcode']} {r['commentaire']} · {explication}")
    if not r["ok"]:
        telegram.alerte_rare(f"mt5-refus-{cle}", f"⚠️ MT5 a refusé l'ordre ({eq['nom']}) : {r['retcode']} "
                             f"{r['commentaire']}", 3600, important=True)
        return f"{eq['nom']} : ordre refusé ({r['retcode']} {r['commentaire']})"
    suivi = base.lire("mt5:suivi", {}) or {}
    for p in mt5.appel("positions"):
        if p["magic"] == eq["magic"] and str(p["ticket"]) not in suivi and p["ticket"] not in pos_avant:
            suivi[str(p["ticket"])] = {"equipe": cle, "ouverture": time.time(), "fin": time.time() + eq["duree_h"] * 3600,
                                       "sens": sens, "volume": p["volume"], "prix": p["price_open"], "sl": p["sl"]}
    base.ecrire("mt5:suivi", suivi)
    texte = (f"🤖 MT5 démo · {eq['nom']} : {'ACHAT' if sens > 0 else 'VENTE'} {lots:g} lot {config.MT5_SYMBOLE} à "
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
    try:
        etat = mt5.appel("etat", delai=150)
    except mt5.ErreurMT5 as ex:
        telegram.alerte_rare("mt5-pont", f"🔴 MT5 : {ex}. Le service se relance seul ; or mt5 pour le détail.", 3600)
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
    if not (etat.get("terminal") or {}).get("trade_allowed") or not compte.get("trade_allowed", True):
        telegram.alerte_rare("mt5-algo", "⚠️ MT5 refuse les ordres automatiques (trading algorithmique désactivé, ou "
                             "mot de passe INVESTISSEUR = lecture seule). Donne le mot de passe principal : « or mt5 "
                             "compte », puis « or redemarrer ».", 6 * 3600, important=True)
        return "; ".join(msgs + ["trading algorithmique non autorisé par le terminal"])
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


def rapport_mt5():
    if not config.MT5_ACTIF:
        return "MT5 non branché (installation : bash /home/bots/armee-or/installer_mt5.sh)."
    e = base.lire("mt5:etat")
    if not e or not e.get("compte"):
        return "MT5 : pas encore connecté" + (f" ({e.get('erreur')})" if e and e.get("erreur") else "") + "."
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
