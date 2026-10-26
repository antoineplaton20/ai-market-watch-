"""R8.4 : changer le compte DÉMO de l'armée (« or mt5 compte » dans Termius).

Le verrou R2 bloque tout ordre dès que le pont se connecte à un compte différent de celui suivi : c'est voulu, un
changement de compte ne doit jamais passer inaperçu. Après la saisie des nouveaux identifiants (dans Termius, par le
propriétaire) et sa confirmation explicite, l'armée se relie au nouveau compte : identité notée, verrou levé, suivis
de l'ancien compte effacés. Tout reste en pause : les équipes ne reprennent que sur /or_marches_on.
"""
from __future__ import annotations

from . import base, mt5


def etat():
    """-> texte d'une ligne : compte vu par le pont (ou la raison de l'absence de connexion)."""
    try:
        e = mt5.appel("etat", delai=60)
    except mt5.ErreurMT5 as ex:
        return f"pont injoignable : {ex}"
    c = e.get("compte") or {}
    if not e.get("connecte") or not c:
        return f"non connecté : {e.get('erreur') or 'connexion en cours'}"
    return (f"connecté · compte …{str(c.get('login'))[-3:]} · serveur {c.get('server')} · "
            f"{'DÉMO' if c.get('demo') else 'RÉEL (refusé)'} · solde {c.get('balance')} {c.get('currency', '')}")


def relier(compte):
    """Relie l'armée au compte démo confirmé par le propriétaire. -> message. Refuse tout compte réel."""
    if not compte or not compte.get("demo"):
        raise mt5.ErreurMT5("compte démo non confirmé : rien n'est relié (jamais de compte réel)")
    identite = {"login": compte.get("login"), "server": compte.get("server")}
    if not identite["login"] or not identite["server"]:
        raise mt5.ErreurMT5("identité du compte indisponible : rien n'est relié")
    ancien = base.lire("r2:compte_lie")
    base.ecrire("r2:compte_lie", identite)
    base.ecrire("r2:compte_change", False)
    base.ecrire("r2:ordre_incertain", None)            # une intention de l'ancien compte n'a plus de sens ici
    base.ecrire("mt5:suivi", {})
    base.ecrire("mt5:pause", True)
    base.ecrire("pause", True)
    base.ecrire("marches:actif", False)
    from . import marches
    e = marches.lire()
    for cle in ("positions", "vu", "bloque", "reessai", "refus"):
        e[cle] = {}
    marches.ecrire(e)
    return (f"🔗 Armée reliée au compte démo …{str(identite['login'])[-3:]} ({identite['server']})"
            + (f", à la place de …{str(ancien.get('login'))[-3:]}" if isinstance(ancien, dict) and ancien.get('login')
               else "")
            + ". Tout est en pause ; les positions de l'ancien compte ne sont plus suivies. Pour reprendre : "
            "/or_marches_1000 si tu veux imiter 1 000 €, puis /or_marches_on.")


def relier_compte_actuel():
    e = mt5.appel("etat", delai=60)
    if not e.get("connecte"):
        raise mt5.ErreurMT5("MT5 non connecté : rien n'est relié")
    return relier(e.get("compte"))
