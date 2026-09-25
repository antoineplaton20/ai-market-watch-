"""JOURNAL D'AUDIT : chaque décision et chaque ordre sont enregistrés avec tout ce qu'il faut pour
les expliquer et les rejouer après coup (empreinte de l'état du marché, versions, prix voulu / obtenu)."""
import hashlib
import json
import math
import sqlite3
import time
import uuid
import config

BDD = "journal.db"


def _cnx():
    c = sqlite3.connect(BDD)
    c.execute("""CREATE TABLE IF NOT EXISTS decisions(
        decision_id TEXT PRIMARY KEY, ts REAL, symbole TEXT, role TEXT, genome_id TEXT, genome_hash TEXT,
        politique TEXT, etat_hash TEXT, etat_json TEXT, score REAL, signal INTEGER, vetos TEXT,
        niveau_risque TEXT, issue TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ordres(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, decision_id TEXT, symbole TEXT, cote TEXT, type TEXT,
        qte_voulue REAL, prix_voulu REAL, qte_obtenue REAL, prix_obtenu REAL, glissement_bps REAL,
        frais_estimes REAL, ordre_id TEXT, politique TEXT, raison TEXT)""")
    return c


def _propre(x):
    """Valeurs JSON stables : NaN et infinis deviennent null, les nombres numpy deviennent des nombres."""
    if isinstance(x, dict):
        return {str(k): _propre(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_propre(v) for v in x]
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def empreinte(objet):
    """Empreinte SHA-256 déterministe : mêmes entrées = même empreinte, un chiffre change = tout change."""
    return hashlib.sha256(json.dumps(_propre(objet), sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def decision(symbole, role, genome, etat_marche, score, signal, vetos, niveau_risque):
    """Enregistre une décision AVANT toute action. Renvoie son identifiant (uuid)."""
    did = uuid.uuid4().hex[:16]
    etat = _propre(etat_marche)
    c = _cnx()
    with c:
        c.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (did, time.time(), symbole, role, genome.get("id"), empreinte(genome), config.POLITIQUE_VERSION,
                   empreinte(etat), json.dumps(etat, ensure_ascii=False), float(score), int(bool(signal)),
                   json.dumps(list(vetos)), niveau_risque, None))
    c.close()
    return did


def issue(decision_id, texte):
    c = _cnx()
    with c:
        c.execute("UPDATE decisions SET issue=? WHERE decision_id=?", (texte, decision_id))
    c.close()


def ordre(decision_id, symbole, cote, genre, qte_voulue, prix_voulu, reponse=None, raison=""):
    """Enregistre un ordre envoyé et, s'il est connu, son exécution réelle (glissement mesuré)."""
    reponse = reponse or {}
    qte = reponse.get("filled")
    prix = reponse.get("average")
    gliss = None
    if prix and prix_voulu:
        ecart = (float(prix) - prix_voulu) / prix_voulu * 1e4
        gliss = ecart if cote == "buy" else -ecart                  # positif = défavorable
    frais = float(qte) * float(prix) * config.FRAIS_ALLER_RETOUR_PCT / 200 if qte and prix else None
    c = _cnx()
    with c:
        c.execute("INSERT INTO ordres(ts,decision_id,symbole,cote,type,qte_voulue,prix_voulu,qte_obtenue,prix_obtenu,"
                  "glissement_bps,frais_estimes,ordre_id,politique,raison) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (time.time(), decision_id, symbole, cote, genre, qte_voulue, prix_voulu,
                   float(qte) if qte is not None else None, float(prix) if prix else None, gliss, frais,
                   str(reponse.get("id") or ""), config.POLITIQUE_VERSION, raison))
    c.close()


def glissement_moyen(n=100):
    """Glissement réel moyen des derniers ordres au marché (en points de base, positif = défavorable)."""
    c = _cnx()
    lignes = c.execute("SELECT glissement_bps FROM ordres WHERE type='market' AND glissement_bps IS NOT NULL "
                       "ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    c.close()
    return (sum(x for (x,) in lignes) / len(lignes), len(lignes)) if lignes else (None, 0)


def dernieres_decisions(n=10):
    c = _cnx()
    lignes = c.execute("SELECT ts, symbole, role, score, signal, vetos, issue FROM decisions ORDER BY ts DESC LIMIT ?",
                       (n,)).fetchall()
    c.close()
    return lignes


def decisions_depuis(ts):
    c = _cnx()
    r = c.execute("SELECT COUNT(*), COALESCE(SUM(signal),0) FROM decisions WHERE ts >= ? AND role='champion'",
                  (ts,)).fetchone()
    c.close()
    return int(r[0]), int(r[1])
