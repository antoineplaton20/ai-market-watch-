"""LECTURE DU RENSEIGNEMENT — ce que les bots d'achat / vente peuvent demander à l'armée de renseignement.

Règle d'or : ne JAMAIS ralentir ni faire planter un bot qui trade.
- base ouverte en LECTURE SEULE, attente maximale 0,3 s ;
- toute erreur (base absente, occupée, abîmée) renvoie « pas d'information » (None / liste vide) ;
- aucune dépendance lourde (ni pandas, ni réseau).

La base est écrite par un seul processus : renseignement.py (service equipe-bots-renseignement).
"""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Dict, Iterable, List, Optional

BASE = os.path.join("runtime", "renseignement.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS faits(id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT UNIQUE, ts REAL, vu REAL,
    bot TEXT, source TEXT, sources TEXT, n_sources INTEGER DEFAULT 1, titre TEXT, lien TEXT,
    themes TEXT DEFAULT ',', actifs TEXT DEFAULT ',', ton REAL, importance INTEGER DEFAULT 0,
    ia INTEGER DEFAULT 0, analyse INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_faits_ts ON faits(ts);
CREATE INDEX IF NOT EXISTS idx_faits_analyse ON faits(analyse);
CREATE TABLE IF NOT EXISTS signaux(cle TEXT PRIMARY KEY, valeur REAL, confiance REAL, n INTEGER, resume TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS alertes(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, cle TEXT, niveau INTEGER, ton REAL,
    titre TEXT, sources INTEGER, envoyee INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_alertes_ts ON alertes(ts);
CREATE TABLE IF NOT EXISTS bots(nom TEXT PRIMARY KEY, famille TEXT, derniere REAL, prochaine REAL, ok INTEGER DEFAULT 0,
    ko INTEGER DEFAULT 0, faits INTEGER DEFAULT 0, erreur TEXT);
"""


def _lire(requete: str, params: Iterable = (), base: Optional[str] = None) -> List[sqlite3.Row]:
    chemin = base or BASE
    if not os.path.exists(chemin):
        return []
    try:
        c = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, timeout=0.3)
        try:
            c.row_factory = sqlite3.Row
            return c.execute(requete, tuple(params)).fetchall()
        finally:
            c.close()
    except sqlite3.Error:
        return []


def cle_actif(symbole: str) -> str:
    """« BTC/USDT », « BTC-EUR », « btc » -> « actif:BTC » ; « MC.PA » -> « actif:MC.PA »."""
    s = (symbole or "").upper().strip()
    for sep in ("/", "-"):
        if sep in s and s.split(sep)[1] in ("USDT", "USD", "EUR", "USDC"):
            s = s.split(sep)[0]
    return f"actif:{s}"


def signal(cle: str, age_max_min: float = 240, base: Optional[str] = None) -> Optional[Dict]:
    """Signal agrégé : valeur de -2 (très négatif) à +2 (très positif), confiance de 0 à 1."""
    lignes = _lire("SELECT * FROM signaux WHERE cle = ? AND ts >= ?", (cle, time.time() - age_max_min * 60), base)
    return dict(lignes[0]) if lignes else None


def alerte_grave(cles: Iterable[str], age_max_h: float = 6, base: Optional[str] = None) -> Optional[Dict]:
    """Nouvelle GRAVE et récente sur l'un de ces actifs (importance 3, ton très négatif). None sinon."""
    cles = [c for c in cles if c]
    if not cles:
        return None
    limite = time.time() - age_max_h * 3600
    marques = " OR ".join("actifs LIKE ?" for _ in cles)
    motifs = [f"%,{c.split(':', 1)[-1]},%" for c in cles]
    lignes = _lire(f"SELECT titre, source, n_sources, ts, ton FROM faits WHERE ts >= ? AND importance >= 3 "
                   f"AND ton <= -2 AND ({marques}) ORDER BY ts DESC LIMIT 1", [limite, *motifs], base)
    if lignes:
        return dict(lignes[0])
    marques = ",".join("?" for _ in cles)
    lignes = _lire(f"SELECT titre, cle, sources AS n_sources, ts, ton FROM alertes WHERE ts >= ? AND niveau >= 3 "
                   f"AND ton <= -2 AND cle IN ({marques}) ORDER BY ts DESC LIMIT 1", [limite, *cles], base)
    return dict(lignes[0]) if lignes else None


def risque_global(seuil: float = -1.5, confiance_min: float = 0.5, base: Optional[str] = None) -> Optional[Dict]:
    """Climat mondial nettement négatif et solide (beaucoup de sources) : None si ce n'est pas le cas."""
    s = signal("global", 120, base)
    if s and s["valeur"] <= seuil and s["confiance"] >= confiance_min:
        return s
    return None


def articles(age_h: float = 48, limite: int = 1500, base: Optional[str] = None) -> List[Dict]:
    """Titres récents collectés par l'armée (pour la veille marchés)."""
    lignes = _lire("SELECT titre, source, ts, themes FROM faits WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
                   (time.time() - age_h * 3600, limite), base)
    return [{"titre": r["titre"], "source": r["source"], "ts": r["ts"],
             "themes": [t for t in (r["themes"] or "").split(",") if t]} for r in lignes]


def frais(age_max_min: float = 30, base: Optional[str] = None) -> bool:
    """La synthèse a-t-elle tourné récemment ? (sinon : l'armée est arrêtée ou en panne)"""
    return signal("global", age_max_min, base) is not None


def resume(base: Optional[str] = None) -> Dict:
    maintenant = time.time()
    bots = [dict(r) for r in _lire("SELECT * FROM bots", (), base)]
    n24 = _lire("SELECT COUNT(*) AS n, COUNT(DISTINCT source) AS s FROM faits WHERE ts >= ?",
                (maintenant - 86400,), base)
    n1 = _lire("SELECT COUNT(*) AS n FROM faits WHERE vu >= ?", (maintenant - 3600,), base)
    return {
        "bots": len(bots),
        "actifs": sum(1 for b in bots if b["derniere"] and maintenant - b["derniere"] < 3 * 3600 and not b["erreur"]),
        "en_erreur": [b["nom"] for b in bots if b["erreur"]],
        "faits_24h": n24[0]["n"] if n24 else 0, "sources_24h": n24[0]["s"] if n24 else 0,
        "faits_1h": n1[0]["n"] if n1 else 0,
        "signaux": {r["cle"]: dict(r) for r in _lire("SELECT * FROM signaux WHERE ts >= ?", (maintenant - 3600,), base)},
        "alertes": [dict(r) for r in _lire("SELECT * FROM alertes WHERE ts >= ? ORDER BY ts DESC LIMIT 5",
                                           (maintenant - 86400,), base)],
    }


def _fr(x: float, signe: bool = True) -> str:
    return (f"{x:+.1f}" if signe else f"{x:.1f}").replace(".", ",")


def texte_statut(base: Optional[str] = None) -> str:
    """Résumé pour Telegram (/renseignement) et pour « bots renseignement-etat »."""
    from moteurs.sources_marches import THEMES
    r = resume(base)
    if not r["bots"]:
        return "🛰 Armée de renseignement : pas encore déployée. Dans Termius : bots renseignement-demarrer"
    lignes = [f"🛰 Armée de renseignement : {r['actifs']}/{r['bots']} bots actifs · {r['faits_24h']} infos en 24 h "
              f"({r['sources_24h']} sources) · {r['faits_1h']} dans la dernière heure"]
    s = r["signaux"]
    g = s.get("global")
    if g:
        lignes.append(f"Climat mondial par rapport aux 3 derniers jours : {_fr(g['valeur'])} (échelle -2 à +2, "
                      f"confiance {g['confiance'] * 100:.0f} %)")
    themes = sorted(((k.split(":", 1)[1], v) for k, v in s.items() if k.startswith("theme:") and v["n"] >= 3),
                    key=lambda x: x[1]["valeur"])
    if themes:
        bas = [f"{THEMES.get(k, k)} {_fr(v['valeur'])}" for k, v in themes[:3] if v["valeur"] < -0.2]
        hauts = [f"{THEMES.get(k, k)} {_fr(v['valeur'])}" for k, v in reversed(themes[-3:]) if v["valeur"] > 0.2]
        lignes.append("⬇️ Se dégrade : " + (" · ".join(bas) or "rien de net"))
        lignes.append("⬆️ S'améliore : " + (" · ".join(hauts) or "rien de net"))
    actifs = sorted(((k.split(":", 1)[1], v) for k, v in s.items() if k.startswith("actif:") and v["n"] >= 3),
                    key=lambda x: -abs(x[1]["valeur"]))
    if actifs:
        lignes.append("🎯 Actifs dans l'actualité : " + " · ".join(f"{a} {_fr(v['valeur'])} ({v['n']} infos)"
                                                                   for a, v in actifs[:6]))
    for a in r["alertes"]:
        lignes.append(f"{'🚨' if a['niveau'] >= 3 else '📡'} {a['titre'][:160]}")
    if r["en_erreur"]:
        lignes.append("⚠️ Bots en difficulté (ils réessaient seuls) : " + ", ".join(r["en_erreur"][:5]))
    return "\n".join(lignes)
