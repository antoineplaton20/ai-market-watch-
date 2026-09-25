"""APPROBATION HUMAINE : aucun nouveau champion et aucune hausse de capital sans ton accord.
Le bot t'envoie un message avec deux boutons ; il attend, sans limite de temps. Sans réponse, rien ne change."""
import json
import os
import time
import registre
from alertes import boutons

FICHIER = "approbations.json"


def _lire():
    if not os.path.exists(FICHIER):
        return {}
    try:
        with open(FICHIER, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _ecrire(d):
    with open(FICHIER + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(FICHIER + ".tmp", FICHIER)


def demander(genre, ident, texte, donnees=None):
    """Crée une demande (une seule fois par identifiant) et envoie les boutons."""
    d = _lire()
    if ident in d:
        return False
    d[ident] = {"genre": genre, "texte": texte, "donnees": donnees or {}, "date": time.time()}
    _ecrire(d)
    boutons(f"🙋 TA DÉCISION EST DEMANDÉE\n{texte}", [("✅ Accepter", f"/approuver {ident}"), ("❌ Refuser", f"/refuser {ident}")])
    return True


def en_attente():
    return _lire()


def resoudre(ident, accepte):
    """Retire la demande et la renvoie (ou None si elle n'existe pas / plus)."""
    d = _lire()
    demande = d.pop(ident, None)
    if demande is None:
        return None
    _ecrire(d)
    registre.ajouter("approbation", {"demande": ident, "genre": demande["genre"], "accepte": accepte})
    return demande
