"""ÉTATS DE RISQUE GRADUÉS : SÛR (x1) → PRUDENCE (x0,75) → RÉDUCTION (x0,5) → ARRÊT (x0).
La taille des positions baisse progressivement AVANT d'en arriver à l'arrêt. Aucun modèle n'y touche."""
import time
import config
import auditeur
import calibration
import disjoncteur
import paliers
from alertes import alerte

MULTIPLICATEURS = {"SÛR": 1.0, "PRUDENCE": 0.75, "RÉDUCTION": 0.5, "ARRÊT": 0.0}


def _serie_pertes(rs):
    n = 0
    for r in reversed(rs):
        if r >= 0:
            break
        n += 1
    return n


def evaluer(etat, statut_ia=None):
    raisons = []
    if etat.get("disjoncteur"):
        raisons.append("disjoncteur : " + etat["disjoncteur"]["raison"])
    if etat.get("arret_manuel"):
        raisons.append("arrêt manuel (/stop)")
    if etat.get("arret_jour"):
        raisons.append("limite de perte du jour")
    if time.time() < etat.get("pause_jusqua", 0):
        raisons.append("pause après une série de pertes")
    if etat.get("donnees_ko"):
        raisons.append("données ou horloge douteuses")
    if etat.get("reseau_ko"):
        raisons.append("connexion à Binance instable")
    if raisons:
        niveau = "ARRÊT"
    else:
        base = paliers.capital_autorise(etat)
        trades = auditeur.trades_depuis(etat.get("disjoncteur_rearme", 0.0), "strict")
        baisse = disjoncteur.baisse_actuelle([u for _, u in trades],
                                              etat.get("latent_modes", {}).get("strict", etat.get("latent", 0.0)), base)
        perte_jour = max(0.0, -etat.get("pnl_jour", 0.0)) / base
        serie = _serie_pertes([r for r, _ in trades])
        statut_ia = statut_ia or calibration.mesure()["statut"]
        mesures = {"baisse": baisse, "perte_jour": perte_jour, "pertes_suite": serie}
        if any(mesures[k] >= v for k, v in config.RISQUE_REDUCTION.items()):
            niveau = "RÉDUCTION"
        elif any(mesures[k] >= v for k, v in config.RISQUE_PRUDENCE.items()) or statut_ia in ("NON FIABLE", "SURCONFIANT"):
            niveau = "PRUDENCE"
        else:
            niveau = "SÛR"
        if niveau != "SÛR":
            raisons.append(f"le capital a baissé de {baisse:.1%} depuis son plus haut · perte du jour {perte_jour:.1%} · "
                           f"{serie} perte(s) d'affilée · fiabilité de l'IA : {statut_ia}")
    if niveau != etat.get("niveau_risque", "SÛR"):
        icone = {"SÛR": "🟢", "PRUDENCE": "🟡", "RÉDUCTION": "🟠", "ARRÊT": "🔴"}[niveau]
        import langage as L
        alerte(f"{icone} Niveau de risque : {L.NIVEAUX_RISQUE[etat.get('niveau_risque', 'SÛR')]} → "
               f"{L.NIVEAUX_RISQUE[niveau]}" + (f"\nPourquoi : {'; '.join(raisons)}" if raisons else ""),
               important=niveau in ("RÉDUCTION", "ARRÊT"))
    etat["niveau_risque"] = niveau
    return niveau, MULTIPLICATEURS[niveau], raisons
