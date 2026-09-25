"""MODE EXPLORATION (v14) — COMPTE DÉMO UNIQUEMENT.

Pourquoi : un bot qui n'achète jamais n'apprend rien. En démo, l'argent est fictif : on laisse l'équipe prendre
volontairement plus de risques pour que des transactions aient lieu, et on MESURE ce que chaque risque rapporte.

Règles :
- verrou : niveau 0 forcé dès que MODE n'est pas demo/testnet (argent réel : jamais d'exploration) ;
- chaque trade d'exploration est marqué, avec la liste des règles qu'il a enfreintes (« risques pris ») ;
- ces résultats nourrissent les notes /10 des bots et des vetos (l'apprentissage) ;
- le disjoncteur, les niveaux de risque et les paliers ne jugent QUE les trades stricts du champion ;
- l'exploration a son propre budget de pertes par jour, ses limites de positions et son coupe-circuit ;
- toujours actifs : stop posé chez Binance, veto VEILLE (piratage, délisting...), données fraîches, liquidité minimale.
"""
import datetime as dt
import time

import config

NIVEAUX = {
    1: {"nom": "prudent", "delta_vote": 0.10, "mtf_min": 3, "espece": True, "couts": "net_positif",
        "vetos_durs": True, "pump": True, "max_positions": 1, "max_jour": 4, "garantie_h": None,
        "score_garantie": None, "perte_jour_pct": 5.0, "analyses_forcees": 0},
    2: {"nom": "normal", "delta_vote": 0.15, "mtf_min": 2, "espece": False, "couts": "ignores",
        "vetos_durs": True, "pump": True, "max_positions": 2, "max_jour": 8, "garantie_h": 4,
        "score_garantie": 0.45, "perte_jour_pct": 10.0, "analyses_forcees": 25},
    3: {"nom": "agressif", "delta_vote": 0.25, "mtf_min": 0, "espece": False, "couts": "ignores",
        "vetos_durs": False, "pump": False, "max_positions": 3, "max_jour": 15, "garantie_h": 1,
        "score_garantie": 0.35, "perte_jour_pct": 20.0, "analyses_forcees": 40},
}
RISQUE_PAR_TRADE_PCT = 0.5          # moitié du risque d'un trade strict : on apprend, on ne parie pas le compte
COUPE_CIRCUIT_DD = 0.40             # capital en baisse de 40 % (tous trades) : exploration coupée
TOUJOURS_BLOQUANTS = {"VEILLE"}     # vraie mauvaise nouvelle (piratage, délisting...) : aucune leçon utile
VETOS_DURS = {"BALEINES_VETO", "CORRELATION", "RECHERCHE_VETO", "CONTRADICTEUR"}
NOMS = {0: "arrêtés", 1: "prudent", 2: "normal", 3: "audacieux"}


def niveau(etat) -> int:
    """Niveau effectif. Hors démo : 0, toujours."""
    if not config.EXPLORATION_AUTORISEE or config.REEL:
        return 0
    n = etat.get("exploration_niveau", config.EXPLORATION_NIVEAU_DEFAUT)
    return n if n in NIVEAUX else 0


def regler(etat, n) -> str:
    import langage as L
    if not config.EXPLORATION_AUTORISEE or config.REEL:
        etat["exploration_niveau"] = 0
        return "⛔ Les essais n'existent qu'en compte DÉMO. Avec de l'argent réel, seul le bot prudent achète."
    if n not in (0, 1, 2, 3):
        return "Écris : /exploration 0 (arrêt) · 1 (prudent) · 2 (normal) · 3 (audacieux)"
    etat["exploration_niveau"] = n
    etat.pop("exploration_coupee", None)
    etat["exploration_depuis"] = time.time()
    if n == 0:
        return "🧪 Essais arrêtés : seul le bot prudent achète."
    p = NIVEAUX[n]
    lignes = [f"🧪 Essais niveau {n} sur 3 ({NOMS[n]}) — argent fictif uniquement.",
              f"• Achète même si l'équipe est moins d'accord qu'habituellement",
              f"• Il suffit que {p['mtf_min']} horizons de temps sur 4 soient à la hausse" if p["mtf_min"] else
              "• Achète même si aucun horizon de temps n'est à la hausse",
              "• Seulement quand la stratégie habituelle voit un signal" if p["espece"] else
              "• Même quand la stratégie habituelle ne voit rien",
              "• Respecte toujours les alertes graves (gros vendeurs, IA, doublons)" if p["vetos_durs"] else
              "• Ignore aussi les alertes graves, sauf les mauvaises nouvelles dans la presse",
              f"• Au maximum {L.pluriel(p['max_positions'], 'essai')} en même temps et {p['max_jour']} par jour",
              f"• Arrêt pour la journée si les essais perdent plus de {p['perte_jour_pct']:.0f} % du capital",
              f"• Chaque essai risque au plus {L.nombre(RISQUE_PAR_TRADE_PCT, 1)} % du capital (moitié d'un achat normal)"]
    if p["garantie_h"]:
        lignes.append(f"• Au moins un achat {L.toutes_les_heures(p['garantie_h'])}, si une crypto obtient au moins "
                      f"{L.pourcent(p['score_garantie'])} de confiance")
    return "\n".join(lignes)


def _aujourdhui():
    return dt.date.today().isoformat()


def achats_du_jour(etat) -> int:
    j = etat.get("exploration_jour") or {}
    return j.get("n", 0) if j.get("date") == _aujourdhui() else 0


def noter_achat(etat):
    j = etat.get("exploration_jour") or {}
    if j.get("date") != _aujourdhui():
        j = {"date": _aujourdhui(), "n": 0}
    j["n"] += 1
    etat["exploration_jour"] = j


def positions_exploration(etat) -> int:
    return sum(1 for p in etat["positions"].values() if p.get("mode") == "exploration")


def peut_explorer(etat, n, base, pnl_jour_exploration) -> tuple:
    """(autorisé, raison). Indépendant du disjoncteur strict : c'est justement l'exploration qui apprend."""
    if not n:
        return False, "désactivée"
    p = NIVEAUX[n]
    for cle, raison in (("arret_manuel", "arrêt manuel (/stop)"), ("donnees_ko", "données douteuses"),
                        ("reseau_ko", "réseau instable"), ("exploration_coupee", "coupe-circuit d'exploration")):
        if etat.get(cle):
            return False, raison
    if positions_exploration(etat) >= p["max_positions"]:
        return False, f"{p['max_positions']} position(s) d'exploration déjà ouverte(s)"
    if achats_du_jour(etat) >= p["max_jour"]:
        return False, f"{p['max_jour']} achats d'exploration aujourd'hui"
    if pnl_jour_exploration <= -base * p["perte_jour_pct"] / 100:
        return False, f"budget de perte du jour atteint ({pnl_jour_exploration:.2f} USDT)"
    return True, ""


def garantie_due(etat, n) -> bool:
    h = NIVEAUX.get(n, {}).get("garantie_h")
    return bool(h) and time.time() - etat.get("dernier_achat_ts", time.time()) >= h * 3600


def evaluer(res, champ, n, opportunite=None, garantie=False, seuil_pump=None):
    """Décide si un candidat analysé peut être acheté EN EXPLORATION.
    res : sortie de main.analyser ; opportunite : fonction sans argument -> porte v11 (appelée seulement si utile).
    Renvoie (ok, risques_pris) : risques_pris = règles strictes enfreintes, enregistrées avec le trade."""
    p = NIVEAUX[n]
    vetos = set(res.get("vetos", [])) - {"OPPORTUNITE_VETO"}
    if vetos & TOUJOURS_BLOQUANTS:
        return False, sorted(vetos & TOUJOURS_BLOQUANTS)
    durs = vetos & VETOS_DURS
    if durs and p["vetos_durs"]:
        return False, sorted(durs)
    F = res.get("F") or {}
    # « Risque pris » = règle qui aurait VRAIMENT bloqué le champion : ses vetos souples activés par son génome
    # (contexte compris : calendrier, météo, peur/avidité) + tout veto dur ou de l'IA.
    import strategie as S
    souples = {v for v in S.VETOS if champ.get(f"veto_{v}") and F.get(f"veto_{v}")}
    risques = sorted(souples | (vetos - set(S.VETOS)))
    seuil_pump = config.HAUSSE_24H_MAX_PCT if seuil_pump is None else seuil_pump
    if F.get("hausse_24h", 0) > seuil_pump:
        if p["pump"]:
            return False, ["PUMP"]
        risques.append("PUMP")
    score = float(res.get("decisions", {}).get("champion", (False, 0.0))[1])
    nb_mtf = sum(bool(v) for v in (res.get("mtf_checks") or {}).values())
    if garantie:
        if not p["garantie_h"] or score < p["score_garantie"]:
            return False, []
        risques.append("GARANTIE")
    else:
        if score < champ["seuil_vote"] - p["delta_vote"]:
            return False, []
        if p["espece"] and not res.get("espece_ok"):
            return False, []
        if nb_mtf < p["mtf_min"]:
            return False, []
    if score < champ["seuil_vote"]:
        risques.append("VOTE_FAIBLE")
    if not res.get("espece_ok"):
        risques.append("HORS_ESPECE")
    if nb_mtf < 4:
        risques.append(f"MTF_{nb_mtf}/4")
    if opportunite is not None:
        opp = opportunite()
        if opp is not None and not opp.allowed:
            if p["couts"] == "net_positif" and opp.net_potential_pct < 0 and not garantie:
                return False, []
            risques.append("COUTS")
    return True, sorted(set(risques))


def verifier_coupe_circuit(etat, base):
    """Coupe-circuit de l'exploration : capital en baisse de 40 % depuis son lancement (tous trades confondus)."""
    import auditeur
    import disjoncteur
    from alertes import alerte
    if not niveau(etat) or etat.get("exploration_coupee"):
        return
    trades = auditeur.trades_depuis(etat.get("exploration_depuis", 0.0))
    dd = disjoncteur.pire_baisse([u for _, u in trades], etat.get("latent", 0.0), base)
    if dd >= COUPE_CIRCUIT_DD:
        etat["exploration_coupee"] = f"baisse de {dd:.0%} du capital"
        alerte(f"🧪🛑 Essais arrêtés : le capital a baissé de {dd:.0%} depuis leur lancement. Le bot prudent continue. "
               f"Regarde ce qu'ils ont appris avec /exploration, puis relance avec /exploration 1, 2 ou 3.")
