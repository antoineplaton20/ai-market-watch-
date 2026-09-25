"""REGISTRE DE RECHERCHE IMMUABLE : chaque événement de recherche est ajouté, jamais modifié ni effacé.
Chaque ligne contient l'empreinte de la précédente (chaîne d'empreintes) : toute retouche après coup
casse la chaîne et se voit immédiatement (python -c "import registre; print(registre.verifier())")."""
import hashlib
import json
import os
import time

FICHIER = "registre_recherche.jsonl"


def _empreinte(entree):
    return hashlib.sha256(json.dumps(entree, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _derniere():
    if not os.path.exists(FICHIER):
        return None
    derniere = None
    with open(FICHIER, encoding="utf-8") as f:
        for ligne in f:
            if ligne.strip():
                derniere = json.loads(ligne)
    return derniere


def ajouter(genre, contenu):
    precedente = _derniere()
    entree = {"n": (precedente["n"] + 1) if precedente else 1, "date": time.strftime("%Y-%m-%d %H:%M:%S"),
              "type": genre, "contenu": contenu, "precedent": precedente["empreinte"] if precedente else None}
    entree["empreinte"] = _empreinte(entree)
    with open(FICHIER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False, default=str) + "\n")
    return entree["empreinte"]


def verifier():
    """Renvoie (intègre, nombre d'entrées, message)."""
    if not os.path.exists(FICHIER):
        return True, 0, "registre vide"
    precedente, n = None, 0
    with open(FICHIER, encoding="utf-8") as f:
        for ligne in f:
            if not ligne.strip():
                continue
            e = json.loads(ligne)
            n += 1
            attendu = e.pop("empreinte")
            if _empreinte(e) != attendu or e["precedent"] != precedente:
                return False, n, f"entrée {e.get('n')} modifiée ou supprimée après coup"
            precedente = attendu
    return True, n, f"{n} entrées, chaîne intacte"
