# -*- coding: utf-8 -*-
"""Mémoire long terme de Jarvis : backend local de l'outil `memory_20250818` de Claude.

Claude manipule un répertoire virtuel /memories ; on le mappe sur jarvis/data/memoires
en interdisant toute sortie de ce dossier.
"""
import shutil
from pathlib import Path

from .config import MEMOIRES

OUTIL_MEMOIRE = {"type": "memory_20250818", "name": "memory"}


class ErreurMemoire(Exception):
    pass


def _chemin(virtuel: str) -> Path:
    if not virtuel or not virtuel.startswith("/memories"):
        raise ErreurMemoire(f"Le chemin doit commencer par /memories : {virtuel!r}")
    relatif = virtuel[len("/memories"):].lstrip("/")
    reel = (MEMOIRES / relatif).resolve()
    if reel != MEMOIRES.resolve() and MEMOIRES.resolve() not in reel.parents:
        raise ErreurMemoire(f"Chemin hors de /memories refusé : {virtuel!r}")
    return reel


def _vue(cmd: dict) -> str:
    p = _chemin(cmd.get("path", "/memories"))
    if p.is_dir():
        lignes = [f"Contenu de {cmd.get('path', '/memories')} :"]
        for f in sorted(p.rglob("*")):
            if f.is_file():
                lignes.append(f"- /memories/{f.relative_to(MEMOIRES)} ({f.stat().st_size} o)")
        return "\n".join(lignes) if len(lignes) > 1 else "Répertoire vide."
    if not p.exists():
        raise ErreurMemoire(f"Introuvable : {cmd['path']}")
    lignes = p.read_text(encoding="utf-8").splitlines()
    debut, fin = 1, len(lignes)
    if cmd.get("view_range"):
        debut, fin = cmd["view_range"][0], cmd["view_range"][1]
        fin = len(lignes) if fin == -1 else fin
    return "\n".join(f"{i:>5}\t{lignes[i - 1]}" for i in range(max(1, debut), min(fin, len(lignes)) + 1))


def executer(cmd: dict) -> str:
    """Exécute une commande de l'outil memory et renvoie le texte du tool_result."""
    c = cmd.get("command")
    if c == "view":
        return _vue(cmd)
    if c == "create":
        p = _chemin(cmd["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(cmd.get("file_text", ""), encoding="utf-8")
        return f"Fichier créé : {cmd['path']}"
    if c == "str_replace":
        p = _chemin(cmd["path"])
        texte = p.read_text(encoding="utf-8")
        n = texte.count(cmd["old_str"])
        if n != 1:
            raise ErreurMemoire(f"old_str trouvé {n} fois (il faut exactement 1) dans {cmd['path']}")
        p.write_text(texte.replace(cmd["old_str"], cmd.get("new_str", "")), encoding="utf-8")
        return f"Modifié : {cmd['path']}"
    if c == "insert":
        p = _chemin(cmd["path"])
        lignes = p.read_text(encoding="utf-8").splitlines()
        n = int(cmd["insert_line"])
        lignes[n:n] = cmd.get("insert_text", "").splitlines()
        p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        return f"Texte inséré ligne {n} : {cmd['path']}"
    if c == "delete":
        p = _chemin(cmd["path"])
        if p == MEMOIRES.resolve():
            raise ErreurMemoire("Suppression de /memories entier refusée.")
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        return f"Supprimé : {cmd['path']}"
    if c == "rename":
        src, dst = _chemin(cmd["old_path"]), _chemin(cmd["new_path"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return f"Renommé : {cmd['old_path']} -> {cmd['new_path']}"
    raise ErreurMemoire(f"Commande memory inconnue : {c!r}")
