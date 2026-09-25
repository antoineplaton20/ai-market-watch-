"""SÉCURITÉ DE FONCTIONNEMENT : une seule instance, signe de vie, message « je suis vivant », sauvegardes."""
import datetime as dt
import json
import os
import shutil
import time
import zipfile
import config
from alertes import alerte, log

FICHIER_BATTEMENT = "battement.json"
FICHIER_VERROU = "bot.lock"
DOSSIER_SAUVEGARDES = "sauvegardes"
A_SAUVEGARDER = ["champion.json", "challenger.json", "population.json", "etat.json", "journal.db",
                 "evolution_etat.json", "evolution_journal.csv", "champions_archive.json", ".env",
                 "notes_backtest_15m.json", "notes_backtest_1h.json", "notes_backtest_4h.json",
                 "approbations.json", "registre_recherche.jsonl", "recherche_hebdo.json", "deblocages.csv",
                 "marches_etat.json"]
BASE_V17 = os.path.join("runtime", "v17_ops.db")      # portefeuille et journal du moteur v17
_verrou = None


def prendre_verrou():
    """Empêche deux bots de trader en même temps (le verrou est libéré tout seul si le bot s'arrête)."""
    global _verrou
    f = open(FICHIER_VERROU, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _verrou = f
    return True


def battement(etat_resume=""):
    """Signe de vie écrit à chaque tour de boucle : le chien de garde le surveille."""
    tmp = FICHIER_BATTEMENT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "pid": os.getpid(), "resume": etat_resume}, f)
    os.replace(tmp, FICHIER_BATTEMENT)


def age_battement():
    try:
        with open(FICHIER_BATTEMENT, encoding="utf-8") as f:
            return time.time() - json.load(f)["ts"]
    except Exception:
        return None


def message_vivant(etat, capital, demarrage):
    if time.time() - etat.get("dernier_vivant", 0) < config.VIVANT_H * 3600:
        return
    etat["dernier_vivant"] = time.time()
    dj = etat.get("disjoncteur")
    explo = sum(1 for p in etat["positions"].values() if p.get("mode") == "exploration")
    import langage as L
    alerte(f"💓 Tout fonctionne depuis {(time.time() - demarrage) / 3600:.0f} h · "
           f"{L.pluriel(len(etat['positions']), 'achat')} en cours"
           + (f" dont {L.pluriel(explo, 'essai')} 🧪" if explo else "")
           + f" · capital suivi {L.dollars(capital)} · "
           + ("⛔ sécurité générale déclenchée (/sante)" if dj else "protections actives"), important=False)


def _copie_sqlite(chemin):
    """Copie d'une base SQLite en cours d'utilisation (API de sauvegarde SQLite, jamais une copie de fichier)."""
    if not os.path.exists(chemin):
        return None
    copie = chemin + ".sauvegarde"
    try:
        import sqlite3
        src, dst = sqlite3.connect(chemin), sqlite3.connect(copie)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        return copie
    except Exception as e:
        log(f"Sauvegarde de {chemin} impossible ({e})")
        return None


def sauvegarde_quotidienne(etat):
    """Une archive par jour de tout ce que le système a appris. Les 30 dernières sont gardées."""
    aujourdhui = dt.date.today().isoformat()
    if etat.get("derniere_sauvegarde") == aujourdhui:
        return None
    os.makedirs(DOSSIER_SAUVEGARDES, exist_ok=True)
    chemin = os.path.join(DOSSIER_SAUVEGARDES, f"sauvegarde_{aujourdhui}.zip")
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        for f in A_SAUVEGARDER:
            if os.path.exists(f):
                z.write(f)
        copie = _copie_sqlite(BASE_V17)                    # v17 : copie cohérente même si le moteur écrit
        if copie:
            z.write(copie, BASE_V17)
            os.remove(copie)
    archives = sorted(x for x in os.listdir(DOSSIER_SAUVEGARDES) if x.startswith("sauvegarde_"))
    for vieille in archives[:-config.SAUVEGARDES_GARDEES]:
        os.remove(os.path.join(DOSSIER_SAUVEGARDES, vieille))
    if config.SAUVEGARDE_COPIE:
        try:
            os.makedirs(config.SAUVEGARDE_COPIE, exist_ok=True)
            shutil.copy2(chemin, config.SAUVEGARDE_COPIE)
        except Exception as e:
            log(f"Copie de sauvegarde impossible ({e})")
    etat["derniere_sauvegarde"] = aujourdhui
    log(f"💾 Sauvegarde du jour : {chemin}")
    return chemin
