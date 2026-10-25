"""ÉQUIPE VIDÉO — la méthode des deux vidéos du propriétaire (2,02 $ -> 218 697 $ en 74 min ; 9,88 $ -> 129 861 $ en
51 min, sur XAUUSDm), rejouée à l'identique sur un DEUXIÈME compte DÉMO à fort levier (service armee-or-mt5-video,
port 18778). Jamais sur le compte de l'armée : autre compte, autre pont, autre numéro magique (770077).

La méthode, telle qu'elle apparaît image par image dans les vidéos :
- un panier de positions identiques dans le même sens (ici : le sens de la dernière bougie 1 min close) ;
- tout le panier est fermé dès qu'il gagne quelques dollars par once ;
- AUCUN stop : une perte reste ouverte jusqu'à ce qu'elle revienne… ou que le courtier coupe le compte ;
- la mise repart à la hausse après chaque gain, presque toute la marge engagée.

Rejouée avec CES règles (fonction simuler) sur l'or réel, bougies 1 min de janvier à septembre 2026 : 167 040
loteries (un départ toutes les 10 min, 2,02 $ ou 9,88 $, gain pris à 1, 2 ou 3 $ par once). Le résultat des vidéos est
atteint 4 fois (1 sur 42 000), 99,98 % des loteries sont ruinées en moins de 24 h. L'équipe sert à le VOIR sur un vrai
compte démo : chaque loterie (un départ jusqu'à sa ruine) est comptée. Argent fictif seulement : le pont refuse tout
ordre en réel.
"""
from __future__ import annotations

import logging
import math
import time

from . import base, config, mt5, telegram

_log = logging.getLogger("or.video")

MAGIQUE = 770077
CLE = "video:etat"
N_POSITIONS = int(config.nombre("OR_VIDEO_POSITIONS", 8))       # les vidéos : 7 à 10 positions identiques
EXPO = config.nombre("OR_VIDEO_EXPO", 0.25)                      # $ gagnés ou perdus par $ de mouvement, / équité
GAIN_PAR_ONCE = config.nombre("OR_VIDEO_GAIN", 1.0)             # panier fermé dès +1 $ par once (les vidéos : 1 à 3 $)
MARGE_MAX = 0.95                                                 # part de la marge libre engagée (vidéos : ~100 %)
MARCHE_FERME = 10018
PALIERS = (10, 100, 1_000, 10_000, 100_000)
VIDEOS = (("vidéo 1", 2.02, 218_697.79, 74), ("vidéo 2", 9.88, 129_861.08, 51))
REJEU = ("Rejouée sur 9 mois d'or réel (1 min, 2026) : 167 040 loteries, résultat des vidéos atteint 4 fois "
         "(1 sur 42 000), 99,98 % ruinées en moins de 24 h.")


def _n(x, decimales=0):
    """Nombre à la française pour Telegram : 218 697 et non 218,697."""
    return f"{x:,.{decimales}f}".replace(",", " ")


def appel(op, **parametres):
    """Toujours le pont du 2e compte : l'équipe vidéo ne parle jamais au pont de l'armée."""
    return mt5.appel(op, port=config.VIDEO_PORT, **parametres)


def lire():
    return base.lire(CLE) or {}


def ecrire(e):
    base.ecrire(CLE, e)


def actif():
    v = base.lire("video:actif")
    return True if v is None else bool(v)


def gain_par_once():
    v = base.lire("video:gain")
    return float(v) if v else GAIN_PAR_ONCE


# ============================================================================ règles (direct ET rejeu historique)
def taille_panier(equite, marge_libre, marge_lot_min, specs, n=N_POSITIONS, expo=EXPO):
    """-> (positions, lots par position) ; (0, 0.0) si même une position au lot minimum est impossible.
    Lots totaux visés : expo × équité / taille du contrat (au moins le lot minimum, comme dans les vidéos),
    plafonnés par la marge libre."""
    pas = specs.get("volume_step") or 0.01
    mini = specs.get("volume_min") or 0.01
    contrat = specs.get("trade_contract_size") or 100.0
    possible = (math.floor(MARGE_MAX * marge_libre / marge_lot_min + 1e-9) * mini
                if marge_lot_min and marge_lot_min > 0 else float("inf"))
    total = min(max(expo * equite / contrat, mini), possible)
    if total < mini - 1e-9:
        return 0, 0.0
    n = max(1, min(n, int(total / mini + 1e-9)))
    lots = max(mini, math.floor(total / n / pas + 1e-9) * pas)
    return n, round(min(lots, specs.get("volume_max") or lots), 8)


def bilan_panier(positions):
    """-> (lots, gain ou perte flottant, swaps compris)."""
    return (sum(p["volume"] for p in positions),
            sum((p.get("profit") or 0.0) + (p.get("swap") or 0.0) for p in positions))


def a_fermer(positions, specs, gain=None):
    """Panier fermé dès +gain $ par once sur l'ensemble des lots ; jamais à perte (aucun stop, comme les vidéos)."""
    lots, profit = bilan_panier(positions)
    return lots > 0 and profit >= (gain or gain_par_once()) * lots * (specs.get("trade_contract_size") or 100.0)


def sens_du_moment(bougies):
    """Sens de la dernière bougie 1 min CLOSE (la dernière reçue est encore en cours)."""
    if len(bougies) < 2:
        return 1
    _, o, _, _, c, *_ = bougies[-2]
    return 1 if c >= o else -1


def seuil_ruine(loterie):
    return max(1.0, 0.05 * loterie["depart"])


# ============================================================================ le bot (toutes les secondes)
def specs_du_compte(e, maintenant):
    s = e.get("specs")
    if not s or maintenant - e.get("specs_ts", 0) > 3600:
        s = appel("specs")
        e["specs"], e["specs_ts"] = s, maintenant
    return s


def nouvelle_loterie(e, equite, devise, maintenant):
    lot = {"n": len(e.get("loteries", [])) + 1, "depart": equite, "ts": maintenant, "pic": equite, "paniers": 0,
           "palier": 1}
    e["loterie"], e["attente"] = lot, None
    telegram.envoyer(f"🎰 Équipe vidéo : loterie n°{lot['n']}, départ avec {equite:.2f} {devise}. Méthode des vidéos : "
                     f"panier sans stop, fermé dès +{gain_par_once():g} $ par once, mise relancée à chaque gain. "
                     f"Les vidéos montrent ×13 000 et ×108 000. {REJEU}")
    return lot


def ruine(e, lot, equite, devise, maintenant):
    e.setdefault("loteries", []).append({**lot, "fin": maintenant, "equite_fin": equite, "issue": "ruinée"})
    e["loteries"] = e["loteries"][-100:]
    e["loterie"], e["attente"], e["panier"] = None, equite, None
    e["ruines"] = e.get("ruines", 0) + 1
    telegram.envoyer(f"💥 Équipe vidéo : loterie n°{lot['n']} RUINÉE après {(maintenant - lot['ts']) / 60:.0f} min. "
                     f"Départ {lot['depart']:.2f} {devise}, record {lot['pic']:.2f} (×{lot['pic'] / lot['depart']:.1f}), "
                     f"{lot['paniers']} paniers gagnés avant la ruine.\nPour rejouer : remets le solde du compte démo "
                     "(espace du courtier > compte démo > solde, par exemple 10 $) ; l'équipe repart seule.", True)


def annoncer_palier(lot, equite, devise, maintenant):
    mult = equite / lot["depart"]
    atteints = [p for p in PALIERS if mult >= p > lot.get("palier", 1)]
    if atteints:
        lot["palier"] = atteints[-1]
        telegram.envoyer(f"🚀 Équipe vidéo, loterie n°{lot['n']} : ×{_n(atteints[-1])} ({lot['depart']:.2f} → "
                         f"{_n(equite, 2)} {devise}) en {(maintenant - lot['ts']) / 60:.0f} min, {lot['paniers']} paniers "
                         "gagnés." + (" Résultat des vidéos atteint." if mult >= 13_000 else ""), True)


def refus(e, r, maintenant):
    """Ordre refusé : nouvel essai dans 5 min si le marché est fermé, 30 s sinon (jamais une rafale par seconde)."""
    ferme = r.get("retcode") == MARCHE_FERME
    e["reessai"] = maintenant + (300 if ferme else 30)
    if ferme:
        return "marché fermé : nouvel essai dans 5 min"
    telegram.alerte_rare("video-refus", f"⚠️ Équipe vidéo : ordre refusé par le courtier ({r.get('retcode')} "
                         f"{r.get('commentaire') or r.get('erreur') or ''}). Nouvel essai toutes les 30 s.", 3600)
    return f"ordre refusé ({r.get('retcode')}) : nouvel essai dans 30 s"


def bot_video(chef=None, maintenant=None):
    if not config.VIDEO_ACTIF:
        return "équipe vidéo non configurée (or video installer)"
    m = maintenant or time.time()
    try:
        etat = appel("etat", delai=60)
    except mt5.ErreurMT5 as ex:
        telegram.alerte_rare("video-pont", f"🔴 Équipe vidéo : {ex}. Le service se relance seul ; /or_video pour l'état.",
                             6 * 3600)
        raise
    base.ecrire("video:compte", {**etat, "ts": m})
    compte = etat.get("compte")
    if not etat.get("connecte") or not compte:
        telegram.alerte_rare("video-connexion", "🔴 Équipe vidéo : 2e compte démo non connecté ("
                             f"{etat.get('erreur') or 'en attente du serveur'}). « or video journal » pour le détail.",
                             6 * 3600)
        return "2e compte non connecté"
    if not compte.get("demo"):
        telegram.alerte_rare("video-reel", "⛔ Le 2e compte n'est PAS un compte démo : l'équipe vidéo ne passe aucun "
                             "ordre. Règle un compte démo avec « or video compte ».", 6 * 3600, important=True)
        return "compte réel : aucun ordre"
    e = lire()
    equite, devise = float(compte["equity"]), compte.get("currency") or "$"
    specs = specs_du_compte(e, m)
    positions = [p for p in appel("positions") if p.get("magic") == MAGIQUE]
    lot = e.get("loterie")

    if positions:                                                   # 1) un panier tourne : fermé seulement en gain
        _, profit = bilan_panier(positions)
        if not a_fermer(positions, specs):
            return f"panier ouvert ({len(positions)} positions) : {profit:+.2f}"
        if m < e.get("reessai", 0):
            return "panier gagnant, fermeture en attente (marché fermé ou refus)"
        resultats = [appel("fermer", ticket=p["ticket"], commentaire="armee-or video gain") for p in positions]
        fermes = sum(bool(r.get("ok")) for r in resultats)
        if fermes < len(positions):
            raison = refus(e, next(r for r in resultats if not r.get("ok")), m)
            ecrire(e)
            return raison
        if fermes == len(positions):
            e["panier"] = None
            e["paniers"] = e.get("paniers", 0) + 1
            e["gains"] = e.get("gains", 0.0) + profit
            if lot:
                lot["paniers"] += 1
                lot["pic"] = max(lot["pic"], equite)
                annoncer_palier(lot, equite, devise, m)
        ecrire(e)
        return f"panier fermé en gain : {profit:+.2f} ({fermes}/{len(positions)})"

    e["panier"] = None                                              # disparu sans nous : coupé par le courtier
    if lot and equite < seuil_ruine(lot):                           # 2) compte vidé : la loterie est perdue
        ruine(e, lot, equite, devise, m)
        ecrire(e)
        return "loterie ruinée"
    if not lot:                                                     # 3) nouvelle loterie dès que le solde est remis
        if equite < max(1.0, (e.get("attente") or 0.0) + 1.0):
            ecrire(e)
            return "en attente : remets le solde du compte démo pour rejouer"
        lot = nouvelle_loterie(e, equite, devise, m)
    if not actif() or getattr(chef, "pause", False):
        ecrire(e)
        return "nouveaux paniers en pause"

    if m < e.get("reessai", 0):
        ecrire(e)
        return "ordres en attente (marché fermé ou refus)"
    bougies = appel("bougies", tf="1m", n=3)                       # 4) nouveau panier, mise relancée
    sens = sens_du_moment(bougies)
    marge_lot = appel("marge", sens=sens, volume=specs["volume_min"])
    n, lots = taille_panier(equite, float(compte.get("margin_free") or equite), marge_lot, specs)
    if n == 0:
        ruine(e, lot, equite, devise, m)
        ecrire(e)
        return "marge insuffisante : loterie ruinée"
    ouverts, raison = 0, ""
    for _ in range(n):
        r = appel("ouvrir", sens=sens, volume=lots, sl=0.0, magic=MAGIQUE, commentaire="armee-or video")
        if not r.get("ok"):
            _log.warning("ordre vidéo refusé : %s %s", r.get("retcode"), r.get("commentaire"))
            raison = refus(e, r, m)
            break
        ouverts += 1
    if ouverts:
        e["panier"] = {"sens": sens, "ts": m, "n": ouverts, "lots": lots}
    ecrire(e)
    if not ouverts:
        return raison
    return f"panier : {ouverts} × {lots:g} lot {'ACHAT' if sens > 0 else 'VENTE'}"


# ============================================================================ pilotage
def fermer_tout():
    positions = [p for p in appel("positions") if p.get("magic") == MAGIQUE]
    ok = sum(bool(appel("fermer", ticket=p["ticket"], commentaire="armee-or video stop").get("ok")) for p in positions)
    e = lire()
    e["panier"] = None
    ecrire(e)
    base.ecrire("video:actif", False)
    return (f"🛑 Équipe vidéo : {ok}/{len(positions)} positions fermées, nouveaux paniers arrêtés "
            "(/or_video_on pour reprendre).")


def commande(c):
    """Commandes Telegram (/or_video…) et Termius (video_on, video_gain 2…). -> texte de réponse."""
    c = c.replace("/or_", "").strip()
    if c in ("video_on",):
        base.ecrire("video:actif", True)
        return "▶️ Équipe vidéo : nouveaux paniers autorisés."
    if c in ("video_off",):
        base.ecrire("video:actif", False)
        return "⏸ Équipe vidéo : plus de nouveau panier ; celui en cours se ferme à son gain (/or_video_fermer : tout de suite)."
    if c in ("video_fermer",):
        return fermer_tout()
    if c.startswith(("video_gain_", "video_gain ")):
        v = c[len("video_gain_"):].strip().replace(",", ".")
        try:
            g = float(v)
        except ValueError:
            g = 0.0
        if not 0.1 <= g <= 50:
            return "Gain inconnu : /or_video_gain_1, /or_video_gain_2 ou /or_video_gain_3 ($ par once)."
        base.ecrire("video:gain", g)
        return f"✅ Équipe vidéo : chaque panier se ferme dès +{g:g} $ par once."
    return texte_video()


def texte_video(maintenant=None):
    m = maintenant or time.time()
    if not config.VIDEO_ACTIF:
        return ("🎰 Équipe vidéo non branchée. Crée un compte DÉMO à fort levier chez un courtier (petit solde, 2 à "
                "10 $), puis dans Termius : « or video installer » (login, mot de passe, serveur).\n" + REJEU)
    c = (base.lire("video:compte") or {}).get("compte") or {}
    e = lire()
    lignes = ["🎰 Équipe vidéo — 2e compte DÉMO, méthode des deux vidéos"
              + ("" if actif() else " (nouveaux paniers en pause)")]
    if c:
        lignes.append(f"Compte …{str(c.get('login'))[-3:]} · {c.get('server')} · levier 1:{c.get('leverage')} · "
                      f"solde {c.get('balance', 0):.2f} · équité {c.get('equity', 0):.2f} {c.get('currency', '')}")
    p = e.get("panier")
    lignes.append(f"Panier : {p['n']} × {p['lots']:g} lot {'ACHAT' if p['sens'] > 0 else 'VENTE'}, ouvert il y a "
                  f"{(m - p['ts']) / 60:.0f} min" if p else "Panier : aucun")
    lot = e.get("loterie")
    if lot:
        lignes.append(f"Loterie n°{lot['n']} depuis {(m - lot['ts']) / 60:.0f} min : départ {lot['depart']:.2f}, "
                      f"record {lot['pic']:.2f} (×{lot['pic'] / lot['depart']:.1f}), {lot['paniers']} paniers gagnés")
    finies = e.get("loteries", [])
    if finies:
        meilleur = max(finies, key=lambda x: x["pic"] / x["depart"])
        lignes.append(f"Loteries terminées : {len(finies)} ({e.get('ruines', 0)} ruinées) · meilleure ×"
                      f"{_n(meilleur['pic'] / meilleur['depart'], 1)} · paniers gagnés au total {e.get('paniers', 0)}")
    lignes.append("Vidéos : " + " · ".join(f"×{_n(fin / dep)} en {minutes} min" for _, dep, fin, minutes in VIDEOS)
                  + f". {REJEU}")
    lignes.append(f"Réglages : {N_POSITIONS} positions par panier, fermeture dès +{gain_par_once():g} $ par once, "
                  f"exposition {EXPO:g}, aucun stop · /or_video_gain_2 · /or_video_off · /or_video_fermer")
    return "\n".join(lignes)


# ============================================================================ rejeu sur l'historique (mêmes règles)
def levier_offshore(equite):
    """Levier dynamique type courtier offshore (approximatif) : « illimité » sous 1 000 $, puis dégressif."""
    for plafond, levier in ((1_000, 1e9), (5_000, 2000), (30_000, 1000), (100_000, 500)):
        if equite < plafond:
            return levier
    return 200


def simuler(o, h, l, c, debut, capital, cible, gain=GAIN_PAR_ONCE, ecart=0.25, duree_max=24 * 60,
            specs=None, expo=EXPO):
    """Une loterie sur des bougies 1 min (prix de l'or, $ par once). -> (issue, équité au record, paniers gagnés).
    Le pire d'abord dans chaque bougie (prudent) ; le compte saute quand l'équité touche zéro (stop-out à 0 %)."""
    specs = specs or {"volume_min": 0.01, "volume_step": 0.01, "volume_max": 200.0, "trade_contract_size": 100.0}
    contrat = specs["trade_contract_size"]
    equite, i, gagnes = capital, debut, 0
    fin = min(len(o), debut + duree_max)
    while i < fin:
        p = o[i]
        sens = 1 if c[i - 1] >= o[i - 1] else -1
        n, lots = taille_panier(equite, equite, specs["volume_min"] * contrat * p / levier_offshore(equite), specs,
                                expo=expo)
        if n == 0:
            return "ruine", equite, gagnes
        v = n * lots * contrat
        seuil_gain = p + sens * (ecart + gain)
        seuil_zero = p + sens * ecart - sens * equite / v
        while i < fin:
            pire, mieux = (l[i], h[i]) if sens > 0 else (h[i], l[i])
            if (pire - seuil_zero) * sens <= 0:
                return "ruine", equite, gagnes
            i += 1
            if (mieux - seuil_gain) * sens >= 0:
                equite += v * gain
                gagnes += 1
                break
        if equite >= cible:
            return "cible", equite, gagnes
    return "temps", equite, gagnes


def rejouer(bougies, capital=9.88, cible=129_861.08, pas=10, **options):
    """Une loterie toutes les `pas` bougies 1 min. -> résumé (nombre de départs, cibles, multiplicateurs, ruines)."""
    import numpy as np
    _, o, h, l, c = (np.array([b[k] for b in bougies], dtype=float) for k in range(5))
    res = [simuler(o, h, l, c, d, capital, cible, **options) for d in range(1, len(o) - 60, pas)]
    if not res:
        return {"departs": 0}
    mult = np.array([r[1] / capital for r in res])
    return {"departs": len(res), "cibles": sum(r[0] == "cible" for r in res),
            "ruines": sum(r[0] == "ruine" for r in res), "x10": float(np.mean(mult >= 10)),
            "x100": float(np.mean(mult >= 100)), "meilleur": float(mult.max()),
            "paniers_mediane": float(np.median([r[2] for r in res]))}


def texte_rejeu(r, capital, cible):
    if not r.get("departs"):
        return "Pas assez de bougies 1 min pour rejouer."
    return (f"Rejeu de la méthode des vidéos ({capital:g} $ → objectif {_n(cible)} $) : {_n(r['departs'])} départs, "
            f"objectif atteint {r['cibles']} fois (1 sur {_n(r['departs'] / r['cibles']) if r['cibles'] else '∞'}), ×10 dans {r['x10'] * 100:.1f} % des départs, ×100 dans "
            f"{r['x100'] * 100:.2f} %, meilleur départ ×{_n(r['meilleur'])}, ruinés {_n(r['ruines'])} sur "
            f"{_n(r['departs'])}, paniers gagnés avant la ruine (médiane) {r['paniers_mediane']:.0f}.")
