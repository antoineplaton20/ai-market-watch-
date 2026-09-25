"""CAPITAL PAR PALIERS : le bot ne peut jamais augmenter seul l'argent qu'il engage.
Monter d'un palier = proposition + TON approbation. Descendre (après un coup dur) = automatique."""
import time
import config
import approbations
import auditeur
from alertes import alerte


def capital_autorise(etat):
    i = min(etat.get("palier", 0), len(config.PALIERS_CAPITAL) - 1)
    return float(min(config.CAPITAL_MAX_USDT, config.PALIERS_CAPITAL[i]))


def proposer(etat):
    i = etat.get("palier", 0)
    if i >= len(config.PALIERS_CAPITAL) - 1 or etat.get("disjoncteur") or etat.get("niveau_risque", "SÛR") != "SÛR":
        return False
    if min(config.CAPITAL_MAX_USDT, config.PALIERS_CAPITAL[i + 1]) <= capital_autorise(etat):
        return False              # le plafond absolu CAPITAL_MAX_USDT (.env) est déjà atteint
    depuis = etat.get("palier_depuis", time.time())
    trades = auditeur.trades_depuis(depuis, "strict")
    if (time.time() - depuis) / 86400 < config.PALIER_JOURS_MIN or len(trades) < config.PALIER_TRADES_MIN:
        return False
    e = sum(r for r, _ in trades) / len(trades)
    if e <= 0:
        return False
    return approbations.demander(
        "palier", f"palier-{i + 1}",
        f"Passer du palier {i + 1} ({capital_autorise(etat):.0f} USDT) au palier {i + 2} "
        f"({min(config.CAPITAL_MAX_USDT, config.PALIERS_CAPITAL[i + 1]):.0f} USDT) ?\n{len(trades)} trades depuis le dernier palier, "
        f"espérance {e:+.2f} R, aucun disjoncteur.")


def monter(etat):
    etat["palier"] = min(etat.get("palier", 0) + 1, len(config.PALIERS_CAPITAL) - 1)
    etat["palier_depuis"] = time.time()
    alerte(f"📈 Palier {etat['palier'] + 1} accepté : le bot peut maintenant engager jusqu'à {capital_autorise(etat):.0f} $.")


def descendre(etat, raison):
    if etat.get("palier", 0) > 0:
        etat["palier"] -= 1
        etat["palier_depuis"] = time.time()
        alerte(f"📉 Retour automatique au palier {etat['palier'] + 1} (maximum engagé : {capital_autorise(etat):.0f} $) : {raison}")
