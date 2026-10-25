"""GESTIONNAIRE DE RISQUE CENTRAL — les freins de l'armée, au-dessus de toutes les équipes.

Deux limites, mesurées sur l'ÉQUITÉ du compte MT5 (positions ouvertes comprises) :
- perte du jour : si l'équité recule de plus de OR_RISQUE_PERTE_JOUR_PCT (1 % par défaut) depuis minuit (Paris),
  toutes les positions de l'armée sont fermées et plus aucun ordre n'est passé jusqu'au lendemain ;
- baisse depuis le sommet : si l'équité recule de plus de OR_RISQUE_BAISSE_MAX_PCT (5 % par défaut) depuis son plus
  haut, COUPE-CIRCUIT : tout est fermé et rien ne repart sans ton feu vert (/or_risque_reprendre).

Un changement de compte MT5 remet les compteurs à zéro. Tes ordres manuels ne sont jamais touchés.
"""
from __future__ import annotations

import time
import math

from . import base, config

PERTE_JOUR_PCT = config.nombre("OR_RISQUE_PERTE_JOUR_PCT", 1.0)
BAISSE_MAX_PCT = config.nombre("OR_RISQUE_BAISSE_MAX_PCT", 5.0)
AGRESSIF_PERTE_JOUR_PCT, AGRESSIF_BAISSE_MAX_PCT = 3.0, 10.0       # mode agressif : freins plus lâches
CLE = "risque:etat"


def limites():
    """-> (perte du jour max, baisse max depuis le sommet), en %."""
    if base.lire("mt5:agressif"):
        return AGRESSIF_PERTE_JOUR_PCT, AGRESSIF_BAISSE_MAX_PCT
    return PERTE_JOUR_PCT, BAISSE_MAX_PCT


def _jour(ts):
    from .brief import _paris
    return _paris(ts).date().isoformat()


def controler(compte, maintenant=None):
    """Met à jour l'état du risque. -> (état, nouvel_evenement) ; nouvel_evenement : None, « jour » ou « coupe »."""
    m = maintenant or time.time()
    equite, login, jour = float(compte["equity"]), compte.get("login"), _jour(m)
    if not math.isfinite(equite) or equite < 0:
        raise ValueError("équité invalide : risque non mesurable")
    e = base.lire(CLE) or {}
    if e.get("login") != login:                                    # nouveau compte : nouveaux compteurs
        e = {"login": login, "pic": equite, "coupe": False}
    if e.get("jour") != jour:
        e.update(jour=jour, equite_debut_jour=equite)
        e.pop("arret_jour", None)
    e["pic"] = max(e.get("pic", equite), equite)
    e["equite"] = equite
    e["perte_jour_pct"] = (equite / e["equite_debut_jour"] - 1) * 100 if e["equite_debut_jour"] else 0.0
    e["baisse_pct"] = (equite / e["pic"] - 1) * 100 if e["pic"] else 0.0
    evenement = None
    perte_jour_max, baisse_max = limites()
    if not e.get("coupe") and e["baisse_pct"] <= -baisse_max:
        e.update(coupe=True, ts_coupe=m, raison=f"baisse de {e['baisse_pct']:.2f} % depuis le sommet "
                                                f"({e['pic']:.2f})")
        evenement = "coupe"
    elif not e.get("coupe") and e.get("arret_jour") != jour and e["perte_jour_pct"] <= -perte_jour_max:
        e.update(arret_jour=jour, raison=f"perte du jour de {e['perte_jour_pct']:.2f} %")
        evenement = "jour"
    e["ts"] = m
    base.ecrire(CLE, e)
    return e, evenement


def autorise(e=None, maintenant=None):
    """Nouveaux ordres permis ? -> (bool, raison)."""
    e = e if e is not None else (base.lire(CLE) or {})
    if e.get("coupe"):
        return False, f"COUPE-CIRCUIT ({e.get('raison')}) : /or_risque_reprendre pour repartir"
    if e.get("arret_jour") and e["arret_jour"] == _jour(maintenant or time.time()):
        return False, f"limite du jour atteinte ({e.get('raison')}) : reprise demain"
    return True, ""


def reprendre(maintenant=None):
    """Feu vert : le coupe-circuit et l'arrêt du jour sont levés, le sommet repart de l'équité actuelle."""
    e = base.lire(CLE) or {}
    e.update(coupe=False, raison=None)
    e.pop("arret_jour", None)
    if e.get("equite"):
        e["pic"] = e["equite"]
        e["equite_debut_jour"] = e["equite"]
    base.ecrire(CLE, e)
    return "🟢 Risque : coupe-circuit levé, compteurs repartis de l'équité actuelle. Les ordres reprennent."


def texte(e=None):
    e = e if e is not None else (base.lire(CLE) or {})
    if not e.get("equite"):
        return "Risque : pas encore mesuré (compte MT5 non connecté)"
    ok, raison = autorise(e)
    etat = "OK" if ok else f"⛔ {raison}"
    jour_max, baisse_max = limites()
    return (f"Risque : jour {e['perte_jour_pct']:+.2f} % (limite -{jour_max:g} %) · depuis le sommet "
            f"{e['baisse_pct']:+.2f} % (coupe-circuit -{baisse_max:g} %) · {etat}")
