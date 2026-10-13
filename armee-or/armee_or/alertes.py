"""ALERTES DE PRIX À LA DEMANDE — « préviens-moi quand l'or touche 4 200 ».

  Telegram : /or_alerte 4200 · /or_alerte +1% · /or_alertes · /or_alerte_suppr 2 · /or_alerte_suppr_tout
  Termius  : or alerte 4200 · or alerte -0.5% · or alertes · or alerte suppr 2

Le sens se déduit du cours au moment où l'alerte est posée (au-dessus : alerte à la hausse ; en dessous : à la
baisse). Vérifiée toutes les 2 s sur le meilleur cours disponible ; une alerte déclenchée est retirée.
"""
from __future__ import annotations

import re
import time

from . import base, flux, telegram

MAX_ALERTES = 20
CLE = "alertes:prix"


def _liste():
    return base.lire(CLE) or []


def _cours():
    d = flux.prix_direct()
    return d["prix"] if d else None


def lire_cible(texte, prix):
    """« 4200 », « 4 200,5 », « +1% », « -0.5 % » -> prix visé (None si illisible)."""
    t = texte.replace(" ", "").replace(",", ".").replace("_", "")
    m = re.fullmatch(r"([+-]\d+(?:\.\d+)?)%", t)
    if m:
        return None if prix is None else round(prix * (1 + float(m.group(1)) / 100), 2)
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def ajouter(texte, prix=None, maintenant=None):
    prix = prix if prix is not None else _cours()
    if prix is None:
        return "⏰ Pas de cours frais : alerte non posée, réessaie dans une minute."
    cible = lire_cible(texte, prix)
    if cible is None:
        return "⏰ Montant illisible. Exemples : /or_alerte 4200 · /or_alerte +1% · /or_alerte -0.5%"
    if abs(cible / prix - 1) > 0.5:
        return f"⏰ {cible:.2f} $ est à plus de 50 % du cours ({prix:.2f} $) : vérifie le montant."
    alertes = _liste()
    if len(alertes) >= MAX_ALERTES:
        return f"⏰ Déjà {MAX_ALERTES} alertes : supprime-en une (/or_alertes)."
    sens = 1 if cible > prix else -1
    alertes.append({"prix": cible, "sens": sens, "cree": maintenant or time.time(), "cours_pose": prix})
    base.ecrire(CLE, alertes)
    return (f"⏰ Alerte posée : or {'≥' if sens > 0 else '≤'} {cible:.2f} $ (cours {prix:.2f} $, "
            f"{(cible / prix - 1) * 100:+.2f} %). /or_alertes pour la liste.")


def texte_liste(prix=None):
    alertes = _liste()
    prix = prix if prix is not None else _cours()
    if not alertes:
        return "⏰ Aucune alerte de prix. Pose-en une : /or_alerte 4200 ou /or_alerte +1%"
    lignes = ["⏰ Alertes de prix actives :"]
    for i, a in enumerate(alertes, 1):
        dist = f" ({(a['prix'] / prix - 1) * 100:+.2f} % du cours)" if prix else ""
        lignes.append(f"{i}. or {'≥' if a['sens'] > 0 else '≤'} {a['prix']:.2f} ${dist}")
    lignes.append("Supprimer : /or_alerte_suppr 1 · tout : /or_alerte_suppr_tout")
    return "\n".join(lignes)


def supprimer(qui):
    alertes = _liste()
    if str(qui).strip() in ("tout", "toutes", "all"):
        base.ecrire(CLE, [])
        return f"⏰ {len(alertes)} alerte(s) supprimée(s)."
    try:
        a = alertes.pop(int(str(qui).strip()) - 1)
    except (ValueError, IndexError):
        return "⏰ Numéro inconnu : /or_alertes pour la liste."
    base.ecrire(CLE, alertes)
    return f"⏰ Alerte supprimée : or {'≥' if a['sens'] > 0 else '≤'} {a['prix']:.2f} $."


def verifier(prix=None, maintenant=None):
    """Déclenche (et retire) les alertes franchies. -> nombre d'alertes envoyées."""
    prix = prix if prix is not None else _cours()
    alertes = _liste()
    if prix is None or not alertes:
        return 0
    gardees, envoyees = [], 0
    for a in alertes:
        if (a["sens"] > 0 and prix >= a["prix"]) or (a["sens"] < 0 and prix <= a["prix"]):
            duree = ((maintenant or time.time()) - a["cree"]) / 3600
            telegram.envoyer(f"🔔 ALERTE : l'or {'a atteint' if a['sens'] > 0 else 'est descendu à'} {a['prix']:.2f} $ "
                             f"(cours {prix:.2f} $, alerte posée il y a {duree:.1f} h à {a['cours_pose']:.2f} $).",
                             important=True)
            envoyees += 1
        else:
            gardees.append(a)
    if envoyees:
        base.ecrire(CLE, gardees)
    return envoyees


def commande(c):
    """Commande Telegram ou terminal -> réponse (None si ce n'est pas une commande d'alerte)."""
    c = c.strip().lower()
    for prefixe in ("/or_alerte_suppr", "alerte suppr", "alerte_suppr"):
        if c.startswith(prefixe):
            reste = c[len(prefixe):].strip(" _")
            return supprimer(reste) if reste else texte_liste()
    if c in ("/or_alertes", "alertes"):
        return texte_liste()
    for prefixe in ("/or_alerte", "alerte"):
        if c.startswith(prefixe):
            reste = c[len(prefixe):].strip(" _")
            return ajouter(reste) if reste else texte_liste()
    return None
