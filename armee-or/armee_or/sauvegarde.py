"""SAUVEGARDES ET ENTRETIEN DE NUIT — rien de ce que l'armée a appris ne doit disparaître avec le serveur.

Chaque nuit (vers 3 h, heure de Paris) :
1. ENTRETIEN : le journal des bots (table « rapports », ~80 000 lignes par jour) est limité à 7 jours ;
2. COPIE COMPLÈTE locale de la base (runtime/sauvegardes/or-complete-AAAAMMJJ.db.gz, 3 gardées) : protège
   contre une base abîmée ;
3. SAUVEGARDE ESSENTIELLE envoyée sur Telegram : tout ce qui ne se retélécharge pas (observations de veille,
   pronostics notés, décisions, ordres, frais mesurés, réglages, alertes…), sans les bougies (re-téléchargeables)
   ni le journal des bots. Protège contre la perte du serveur.

Restauration (dans Termius) : « or restaurer » (dernière copie locale) ou « or restaurer <code> » (code indiqué
sous la sauvegarde Telegram, pour un serveur neuf). L'armée est arrêtée pendant l'opération, puis relancée.
"""
from __future__ import annotations

import gzip
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from . import base, config, telegram

GARDER_RAPPORTS_JOURS = 7
GARDER_COPIES = 3
HEURE = 3
EXCLUES_ESSENTIELLE = {"bougies", "rapports", "sqlite_sequence"}
LIMITE_TELEGRAM_OCTETS = 19 * 1024 * 1024        # au-delà, Telegram ne laisse pas le bot retélécharger le fichier


def dossier():
    d = config.RACINE / "runtime" / "sauvegardes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _gzip(source, cible):
    with open(source, "rb") as f, gzip.open(cible, "wb", compresslevel=6) as g:
        shutil.copyfileobj(f, g)
    return cible


def entretien(maintenant=None):
    limite = (maintenant or time.time()) - GARDER_RAPPORTS_JOURS * 86400
    with base.connexion() as c:
        n = c.execute("DELETE FROM rapports WHERE ts < ?", (limite,)).rowcount
    return n


def complete(maintenant=None):
    """Copie cohérente de toute la base (API de sauvegarde SQLite : sûre pendant que l'armée écrit)."""
    jour = time.strftime("%Y%m%d", time.gmtime(maintenant or time.time()))
    cible = dossier() / f"or-complete-{jour}.db.gz"
    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "or.db"
        src, dst = sqlite3.connect(config.BASE), sqlite3.connect(copie)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        _gzip(copie, cible)
    for vieux in sorted(dossier().glob("or-complete-*.db.gz"))[:-GARDER_COPIES]:
        vieux.unlink()
    return cible


def essentielle(maintenant=None):
    jour = time.strftime("%Y%m%d-%H%M", time.gmtime(maintenant or time.time()))
    cible = dossier() / f"or-essentielle-{jour}.db.gz"
    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "or.db"
        src, dst = sqlite3.connect(config.BASE), sqlite3.connect(copie)
        try:
            tables = src.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
            for nom, sql in tables:
                if nom in EXCLUES_ESSENTIELLE or not sql:
                    continue
                dst.execute(sql)
                curseur = src.execute(f'SELECT * FROM "{nom}"')
                while True:
                    lot = curseur.fetchmany(5000)
                    if not lot:
                        break
                    dst.executemany(f'INSERT INTO "{nom}" VALUES ({",".join("?" * len(lot[0]))})', lot)
            dst.commit()
        finally:
            dst.close()
            src.close()
        _gzip(copie, cible)
    for vieux in sorted(dossier().glob("or-essentielle-*.db.gz"))[:-GARDER_COPIES]:
        vieux.unlink()
    return cible


def sauvegarder(maintenant=None, envoyer=True):
    m = maintenant or time.time()
    purges = entretien(m)
    comp, ess = complete(m), essentielle(m)
    info = {"ts": m, "complete": str(comp), "complete_octets": comp.stat().st_size, "essentielle": str(ess),
            "essentielle_octets": ess.stat().st_size, "rapports_purges": purges}
    if envoyer:
        taille = ess.stat().st_size / 1e6
        info["file_id"] = telegram.envoyer_document(
            ess, f"💾 Sauvegarde essentielle de l'armée ({taille:.1f} Mo). Serveur perdu ? Dans Termius sur le "
                 "nouveau serveur, après l'installation : or restaurer CODE (le code arrive dans le message suivant).")
        if info["file_id"]:
            telegram.envoyer(f"Code de restauration : {info['file_id']}")
        if ess.stat().st_size > LIMITE_TELEGRAM_OCTETS:
            telegram.envoyer("⚠️ Sauvegarde essentielle trop lourde pour être retéléchargée par le bot (> 19 Mo) : "
                             "garde le fichier, la restauration se fera à partir de lui.", True)
    base.ecrire("sauvegarde:derniere", info)
    return info


def bot_nuit(maintenant=None):
    from .brief import _paris
    m = maintenant or time.time()
    jour = _paris(m).date().isoformat()
    if (base.lire("sauvegarde:derniere") or {}).get("jour") == jour:
        return "sauvegarde de la nuit déjà faite"
    if _paris(m).hour != HEURE:
        return f"prochaine sauvegarde vers {HEURE} h"
    info = sauvegarder(m)
    base.ecrire("sauvegarde:derniere", {**info, "jour": jour})
    return (f"sauvegarde faite : complète {info['complete_octets'] / 1e6:.1f} Mo, essentielle "
            f"{info['essentielle_octets'] / 1e6:.1f} Mo, {info['rapports_purges']} lignes de journal purgées")


def texte():
    s = base.lire("sauvegarde:derniere")
    if not s:
        return "💾 Aucune sauvegarde encore (la première est faite vers 3 h ; « or sauvegarde » pour la faire maintenant)."
    return (f"💾 Dernière sauvegarde : {time.strftime('%d/%m %H:%M', time.localtime(s['ts']))} · complète "
            f"{s['complete_octets'] / 1e6:.1f} Mo (sur le serveur) · essentielle {s['essentielle_octets'] / 1e6:.1f} Mo"
            f"{' (envoyée sur Telegram)' if s.get('file_id') else ''}")


# ============================================================================ restauration
def telecharger(file_id, cible, session=None):
    import requests
    s = session or requests
    r = s.get(f"https://api.telegram.org/bot{config.TELEGRAM_JETON}/getFile", params={"file_id": file_id},
              timeout=30).json()
    if not r.get("ok"):
        raise RuntimeError(f"Telegram refuse ce code ({r.get('description', '?')})")
    contenu = s.get(f"https://api.telegram.org/file/bot{config.TELEGRAM_JETON}/{r['result']['file_path']}",
                    timeout=120).content
    Path(cible).write_bytes(contenu)
    return cible


def _ouvrir(fichier_gz, tmp):
    brut = Path(tmp) / "restauration.db"
    with gzip.open(fichier_gz, "rb") as g, open(brut, "wb") as f:
        shutil.copyfileobj(g, f)
    c = sqlite3.connect(brut)
    try:
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("fichier de sauvegarde abîmé")
        if not c.execute("SELECT name FROM sqlite_master WHERE name='kv'").fetchone():
            raise RuntimeError("ce fichier n'est pas une sauvegarde de l'armée")
    finally:
        c.close()
    return brut


def restaurer(source=None, session=None):
    """source : None (dernière copie complète locale), chemin d'un .db.gz, ou code Telegram d'une sauvegarde."""
    with tempfile.TemporaryDirectory() as tmp:
        if source is None:
            copies = sorted(dossier().glob("or-complete-*.db.gz"))
            if not copies:
                raise RuntimeError("aucune copie locale : donne le code de la sauvegarde Telegram")
            fichier = copies[-1]
        elif Path(source).exists():
            fichier = Path(source)
        else:
            fichier = telecharger(source, Path(tmp) / "sauvegarde.db.gz", session)
        brut = _ouvrir(fichier, tmp)
        src = sqlite3.connect(brut)
        try:
            tables = [n for (n,) in src.execute("SELECT name FROM sqlite_master WHERE type='table'")
                      if n != "sqlite_sequence"]
            complete_ = "bougies" in tables
        finally:
            src.close()
        if complete_:                                           # copie complète : la base entière est remplacée
            avant = Path(str(config.BASE) + ".avant-restauration")
            if Path(config.BASE).exists():
                shutil.copy(config.BASE, avant)
            for suffixe in ("-wal", "-shm"):
                Path(str(config.BASE) + suffixe).unlink(missing_ok=True)
            shutil.copy(brut, config.BASE)
            return f"Base entière restaurée depuis {Path(fichier).name} (ancienne base gardée : {avant.name})."
        n = 0                                                   # essentielle : tables remplacées, bougies gardées
        decalage = base.lire("telegram_decalage")               # jamais rejouer d'anciennes commandes Telegram
        with base.connexion() as c:
            c.execute("ATTACH DATABASE ? AS s", (str(brut),))
            for t in tables:
                cols = [r[1] for r in c.execute(f'PRAGMA s.table_info("{t}")')]
                c.execute(f'CREATE TABLE IF NOT EXISTS main."{t}" AS SELECT * FROM s."{t}" WHERE 0')
                c.execute(f'DELETE FROM main."{t}"')
                liste = ",".join(f'"{x}"' for x in cols)
                n += c.execute(f'INSERT INTO main."{t}" ({liste}) SELECT {liste} FROM s."{t}"').rowcount
            c.commit()
            c.execute("DETACH DATABASE s")
        if decalage is not None:
            base.ecrire("telegram_decalage", decalage)
        return f"Sauvegarde essentielle restaurée : {len(tables)} tables, {n} lignes (bougies du serveur gardées)."
