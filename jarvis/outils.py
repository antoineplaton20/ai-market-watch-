# -*- coding: utf-8 -*-
"""Outils (« pouvoirs ») de Jarvis exécutés sur le serveur.

Les outils web (recherche, lecture de pages) tournent chez Anthropic : voir OUTILS_SERVEUR.
Ceux-ci tournent en local : marchés, état des bots, lecture du projet, pilotage des bots.
"""
import fnmatch
import json
import re
import subprocess
from pathlib import Path

from .config import RACINE_PROJET

V17 = RACINE_PROJET / "equipe-bots-v17"
TAILLE_MAX_RESULTAT = 30_000       # caractères renvoyés à Claude par appel
FICHIERS_INTERDITS = (".env", ".env.*", "*.pem", "*.key", "id_rsa*", "*secret*", "*credential*", "*.pkl")
DOSSIERS_IGNORES = {".git", ".venv", "venv", "__pycache__", "node_modules", "data_lake", "data"}

OUTILS_SERVEUR = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
]


def _outil(nom, description, proprietes, requis):
    return {
        "name": nom,
        "description": description,
        "input_schema": {"type": "object", "properties": proprietes, "required": requis,
                         "additionalProperties": False},
        "eager_input_streaming": True,
    }


OUTILS_LOCAUX = [
    _outil(
        "cours_marche",
        "Cours et indicateurs techniques d'un actif via Yahoo Finance : action (NVDA, AIR.PA), ETF, "
        "crypto (BTC-EUR), matière première (GC=F), indice (^GSPC), devise (EURUSD=X). Renvoie dernier "
        "prix, variations, plus haut/bas, volatilité (ATR), RSI 14, moyennes mobiles 20/50/200 et les "
        "derniers cours. À utiliser pour toute question sur un prix ou une tendance, plutôt que de deviner.",
        {
            "symbole": {"type": "string", "description": "Ticker Yahoo Finance, ex. NVDA, BTC-EUR, GC=F"},
            "periode": {"type": "string", "enum": ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"],
                        "description": "Profondeur d'historique (défaut 6mo)"},
            "intervalle": {"type": "string", "enum": ["15m", "1h", "1d", "1wk"],
                           "description": "Taille des bougies (défaut 1d ; 15m/1h seulement sur 5d/1mo)"},
        },
        ["symbole"],
    ),
    _outil(
        "etat_bots",
        "État en direct des bots de trading de l'utilisateur : moteur V17 (superviseur, PID, dernières "
        "lignes du journal), bot de veille Trade Republic (positions, portefeuille virtuel, derniers "
        "signaux) et dernier bilan hebdomadaire.",
        {},
        [],
    ),
    _outil(
        "lister_projet",
        "Liste les fichiers du projet de l'utilisateur (dépôt ai-market-watch : bot.py, univers.py, "
        "equipe-bots-v17/, bilans/...). Les fichiers secrets (.env, clés) sont masqués.",
        {
            "dossier": {"type": "string", "description": "Dossier relatif à la racine du projet (défaut « . »)"},
            "motif": {"type": "string", "description": "Filtre glob sur le nom, ex. *.py ou *.md"},
        },
        [],
    ),
    _outil(
        "lire_fichier_projet",
        "Lit un fichier texte du projet (code, documentation, bilans, journaux). Lecture seule.",
        {
            "chemin": {"type": "string", "description": "Chemin relatif à la racine du projet"},
            "ligne_debut": {"type": "integer", "description": "Première ligne (1 par défaut)"},
            "nb_lignes": {"type": "integer", "description": "Nombre de lignes (400 par défaut)"},
        },
        ["chemin"],
    ),
    _outil(
        "chercher_projet",
        "Recherche une expression régulière dans les fichiers texte du projet (comme grep). "
        "Renvoie fichier:ligne: contenu.",
        {
            "motif": {"type": "string", "description": "Expression régulière Python"},
            "dossier": {"type": "string", "description": "Dossier relatif où chercher (défaut « . »)"},
        },
        ["motif"],
    ),
    _outil(
        "piloter_bots",
        "Démarre ou arrête le moteur de trading V17 (mode démo). Action à effet réel : l'utilisateur "
        "doit la confirmer, l'outil le lui demande lui-même. N'appelle cet outil que si l'utilisateur "
        "l'a explicitement demandé.",
        {"action": {"type": "string", "enum": ["demarrer", "arreter"]}},
        ["action"],
    ),
]

TYPES_JSON = {"string": str, "integer": int, "number": (int, float), "boolean": bool}


def valider(nom: str, entree) -> str | None:
    """Vérifie l'entrée d'un outil contre son schéma (le streaming précoce ne la valide pas)."""
    schema = next((o["input_schema"] for o in OUTILS_LOCAUX if o["name"] == nom), None)
    if schema is None:
        return f"Outil inconnu : {nom}"
    if not isinstance(entree, dict):
        return "Entrée invalide : un objet JSON est attendu."
    for cle in schema["required"]:
        if cle not in entree:
            return f"Paramètre manquant : {cle}"
    for cle, val in entree.items():
        prop = schema["properties"].get(cle)
        if prop is None:
            return f"Paramètre inconnu : {cle}"
        attendu = TYPES_JSON[prop["type"]]
        if not isinstance(val, attendu) or (prop["type"] == "integer" and isinstance(val, bool)):
            return f"Paramètre {cle} : type {prop['type']} attendu"
        if "enum" in prop and val not in prop["enum"]:
            return f"Paramètre {cle} : valeur parmi {prop['enum']} attendue"
    return None


# ── Sécurité des chemins ─────────────────────────────────────────────────────

def _interdit(p: Path) -> bool:
    return any(fnmatch.fnmatch(p.name.lower(), m) for m in FICHIERS_INTERDITS)


def _chemin_projet(relatif: str) -> Path:
    p = (RACINE_PROJET / (relatif or ".")).resolve()
    racine = RACINE_PROJET.resolve()
    if p != racine and racine not in p.parents:
        raise ValueError("Chemin hors du projet refusé.")
    if _interdit(p):
        raise ValueError("Fichier sensible (secrets) : lecture refusée.")
    return p


def _fichiers(base: Path):
    for f in sorted(base.rglob("*")):
        rel = f.relative_to(RACINE_PROJET)
        if any(part in DOSSIERS_IGNORES for part in rel.parts[:-1]) or f.name in DOSSIERS_IGNORES:
            continue
        if f.is_file() and not _interdit(f):
            yield f, rel


def _couper(texte: str) -> str:
    if len(texte) <= TAILLE_MAX_RESULTAT:
        return texte
    return texte[:TAILLE_MAX_RESULTAT] + f"\n… [tronqué : {len(texte) - TAILLE_MAX_RESULTAT} caractères de plus]"


# ── Outils ───────────────────────────────────────────────────────────────────

def cours_marche(symbole: str, periode: str = "6mo", intervalle: str = "1d") -> str:
    import numpy as np
    import yfinance as yf

    df = yf.Ticker(symbole).history(period=periode, interval=intervalle, auto_adjust=False)
    if df is None or df.empty:
        return f"Aucune donnée pour {symbole!r} (ticker Yahoo Finance invalide ou marché sans cotation)."
    c, h, b = df["Close"], df["High"], df["Low"]
    dernier = float(c.iloc[-1])

    def var(n):
        return f"{(dernier / float(c.iloc[-n - 1]) - 1) * 100:+.2f}%" if len(c) > n else "n/d"

    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    perte = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / perte.replace(0, np.nan))
    tr = np.maximum(h - b, np.maximum((h - c.shift()).abs(), (b - c.shift()).abs()))
    atr = tr.rolling(14).mean()
    mm = {n: (float(c.rolling(n).mean().iloc[-1]) if len(c) >= n else None) for n in (20, 50, 200)}
    rendements = c.pct_change().dropna()
    info = {
        "symbole": symbole, "periode": periode, "intervalle": intervalle,
        "derniere_date": str(df.index[-1]), "dernier_prix": round(dernier, 6),
        "variation": {"1 bougie": var(1), "5 bougies": var(5), "20 bougies": var(20), "periode": var(len(c) - 1)},
        "plus_haut_periode": round(float(h.max()), 6), "plus_bas_periode": round(float(b.min()), 6),
        "rsi14": round(float(rsi.iloc[-1]), 1) if not np.isnan(rsi.iloc[-1]) else None,
        "atr14": round(float(atr.iloc[-1]), 6) if not np.isnan(atr.iloc[-1]) else None,
        "volatilite_par_bougie_%": round(float(rendements.std() * 100), 3) if len(rendements) > 2 else None,
        "moyennes_mobiles": {f"mm{n}": (round(v, 6) if v else None) for n, v in mm.items()},
        "volume_dernier": float(df["Volume"].iloc[-1]) if "Volume" in df else None,
        "derniers_cours": [[str(i)[:16], round(float(v), 6)] for i, v in c.tail(15).items()],
    }
    return json.dumps(info, ensure_ascii=False)


def etat_bots() -> str:
    parties = []
    statut = V17 / "termius_demo_status.sh"
    if statut.exists():
        try:
            r = subprocess.run(["bash", str(statut)], cwd=V17, capture_output=True, text=True, timeout=30)
            parties.append("## Moteur V17\n" + (r.stdout + r.stderr).strip())
        except Exception as e:
            parties.append(f"## Moteur V17\nStatut illisible : {e}")
    etat = RACINE_PROJET / "state.json"
    if etat.exists():
        try:
            s = json.loads(etat.read_text(encoding="utf-8"))
            resume = {
                "capital": s.get("capital"), "positions": s.get("positions"),
                "portefeuille_virtuel": {k: v for k, v in s.get("virtuel", {}).items() if k != "trades"},
                "derniers_trades_virtuels": s.get("virtuel", {}).get("trades", [])[-5:],
                "derniers_signaux": s.get("journal", [])[-10:], "pause": s.get("pause"),
            }
            parties.append("## Bot de veille Trade Republic (state.json)\n" + json.dumps(resume, ensure_ascii=False, default=str))
        except Exception as e:
            parties.append(f"## Bot de veille\nstate.json illisible : {e}")
    else:
        parties.append("## Bot de veille Trade Republic\nPas de state.json local (le bot tourne sur GitHub Actions).")
    bilans = sorted((RACINE_PROJET / "bilans").glob("*.md"))
    if bilans:
        parties.append(f"## Dernier bilan ({bilans[-1].name})\n" + bilans[-1].read_text(encoding="utf-8"))
    return _couper("\n\n".join(parties))


def lister_projet(dossier: str = ".", motif: str = "*") -> str:
    base = _chemin_projet(dossier)
    if not base.is_dir():
        return f"Pas un dossier : {dossier}"
    lignes = [f"{rel}  ({f.stat().st_size} o)" for f, rel in _fichiers(base) if fnmatch.fnmatch(f.name, motif or "*")]
    return _couper("\n".join(lignes) or "Aucun fichier.")


def lire_fichier_projet(chemin: str, ligne_debut: int = 1, nb_lignes: int = 400) -> str:
    p = _chemin_projet(chemin)
    if not p.is_file():
        return f"Fichier introuvable : {chemin}"
    lignes = p.read_text(encoding="utf-8", errors="replace").splitlines()
    debut = max(1, ligne_debut)
    fin = min(len(lignes), debut + max(1, nb_lignes) - 1)
    corps = "\n".join(f"{i:>6}\t{lignes[i - 1]}" for i in range(debut, fin + 1))
    return _couper(f"{chemin} — lignes {debut}-{fin} sur {len(lignes)}\n{corps}")


def chercher_projet(motif: str, dossier: str = ".") -> str:
    rx = re.compile(motif)
    resultats = []
    for f, rel in _fichiers(_chemin_projet(dossier)):
        if f.stat().st_size > 2_000_000:
            continue
        try:
            for n, ligne in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(ligne):
                    resultats.append(f"{rel}:{n}: {ligne.strip()[:200]}")
        except UnicodeDecodeError:
            continue
        if len(resultats) >= 200:
            resultats.append("… (limite de 200 résultats)")
            break
    return _couper("\n".join(resultats) or "Aucun résultat.")


def piloter_bots(action: str) -> str:
    script = V17 / ("termius_demo_start.sh" if action == "demarrer" else "termius_demo_stop.sh")
    if not script.exists():
        return f"Script introuvable : {script.name}"
    r = subprocess.run(["bash", str(script)], cwd=V17, capture_output=True, text=True, timeout=180)
    return _couper(f"Code retour {r.returncode}\n{(r.stdout + r.stderr).strip()}")


FONCTIONS = {
    "cours_marche": cours_marche,
    "etat_bots": etat_bots,
    "lister_projet": lister_projet,
    "lire_fichier_projet": lire_fichier_projet,
    "chercher_projet": chercher_projet,
    "piloter_bots": piloter_bots,
}
ACTIONS_A_CONFIRMER = {"piloter_bots"}
