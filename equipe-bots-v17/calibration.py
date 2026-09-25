"""CALIBRATION DE L'IA : quand le CONTRADICTEUR se dit sûr à 80 %, a-t-il raison 80 % du temps ?
Chaque verdict (ACHAT ou PASSE) est suivi sur le papier avec les règles de sortie du champion,
qu'il ait été tradé ou non : le résultat ne dépend donc pas de ce que le bot a fait."""
import json
import sqlite3
import time
import config
from simulation import simuler_sortie

BDD = "journal.db"


def _cnx():
    c = sqlite3.connect(BDD)
    c.execute("""CREATE TABLE IF NOT EXISTS ia(
        id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT, ts REAL, symbole TEXT, verdict TEXT,
        confiance REAL, entree REAL, atr REAL, params TEXT, r REAL, resolu INTEGER DEFAULT 0)""")
    return c


def enregistrer(decision_id, symbole, verdict, confiance, entree, atr, params):
    c = _cnx()
    with c:
        c.execute("INSERT INTO ia(decision_id,ts,symbole,verdict,confiance,entree,atr,params) VALUES (?,?,?,?,?,?,?,?)",
                  (decision_id, time.time(), symbole, verdict, float(confiance), entree, atr, json.dumps(params)))
    c.close()


def resoudre(ex):
    c = _cnx()
    minutes = config.MINUTES[config.UNITE_BOUGIE]
    for iid, sym, ts, entree, atr, params in c.execute(
            "SELECT id, symbole, ts, entree, atr, params FROM ia WHERE resolu=0 LIMIT 20").fetchall():
        p = json.loads(params)
        if time.time() - ts < (p["horizon_bougies"] * minutes + 30) * 60:
            continue
        try:
            ohlcv = ex.fetch_ohlcv(sym, config.UNITE_BOUGIE, since=int(ts * 1000), limit=p["horizon_bougies"] + 5)
            b = [(o, h, l, cl) for _, o, h, l, cl, _ in ohlcv]
            r = simuler_sortie(b, entree, atr, p["horizon_bougies"], p)[0] if b else None
        except Exception:
            r = None
        with c:
            c.execute("UPDATE ia SET r=?, resolu=1 WHERE id=?", (r, iid))
    c.close()


def probabilites_issues(lignes):
    """(probabilité de succès annoncée, succès réel 0/1) : ACHAT à 80 % -> 0,8 ; PASSE à 80 % -> 0,2."""
    res = []
    for verdict, confiance, r in lignes:
        p = confiance / 100 if verdict == "ACHAT" else 1 - confiance / 100
        res.append((min(max(p, 0.0), 1.0), 1.0 if r > 0 else 0.0))
    return res


def diagnostic(paires):
    """Score de Brier comparé à celui d'un devin qui annoncerait toujours le taux de réussite moyen."""
    n = len(paires)
    if n < config.CALIBRATION_ECHANTILLON_MIN:
        return {"statut": "EN RODAGE", "n": n}
    brier = sum((p - y) ** 2 for p, y in paires) / n
    base = sum(y for _, y in paires) / n
    reference = base * (1 - base)
    ecart = sum(p for p, _ in paires) / n - base
    if brier >= reference:
        statut = "NON FIABLE"
    elif ecart > 0.10:
        statut = "SURCONFIANT"
    elif ecart < -0.10:
        statut = "SOUS-CONFIANT"
    else:
        statut = "CALIBRÉ"
    tranches = []
    for bas in (0.0, 0.2, 0.4, 0.6, 0.8):
        dedans = [(p, y) for p, y in paires if bas <= p < bas + 0.2 or (bas == 0.8 and p == 1.0)]
        if dedans:
            tranches.append((bas, sum(p for p, _ in dedans) / len(dedans), sum(y for _, y in dedans) / len(dedans),
                             len(dedans)))
    return {"statut": statut, "n": n, "brier": brier, "reference": reference, "ecart": ecart, "tranches": tranches}


def mesure():
    c = _cnx()
    lignes = c.execute("SELECT verdict, confiance, r FROM ia WHERE resolu=1 AND r IS NOT NULL").fetchall()
    c.close()
    return diagnostic(probabilites_issues(lignes))


def texte():
    d = mesure()
    if d["statut"] == "EN RODAGE":
        return f"🎯 Calibration de l'IA : en rodage ({d['n']}/{config.CALIBRATION_ECHANTILLON_MIN} verdicts vérifiés)"
    lignes = [f"🎯 Calibration de l'IA : {d['statut']} (Brier {d['brier']:.3f} contre {d['reference']:.3f} "
              f"pour un devin naïf, {d['n']} verdicts)"]
    for bas, annonce, reel, n in d["tranches"]:
        lignes.append(f"  annoncé {annonce:.0%} → réalisé {reel:.0%} ({n} cas)")
    return "\n".join(lignes)
