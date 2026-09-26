"""APPLICATION iPHONE : tableau de bord de TOUS les bots + quelques commandes, servi par l'API v17.

- /app                    l'application (à ajouter sur l'écran d'accueil depuis Safari)
- /app/api/tableau        état complet (bot principal, v17, veilles, services)
- /app/api/journal        dernières lignes d'un journal (secrets masqués)
- /app/api/action         pause / reprise des achats, tout vendre (bot principal), pause / reprise v17

Tout /app/api/* exige le code secret V17_APP_TOKEN (créé par « bots app »). Sans code : 503, rien n'est lisible.
L'API écoute toujours sur 127.0.0.1 : l'iPhone passe par Tailscale (HTTPS privé) ou par Termius.
Les commandes du bot principal sont déposées dans commandes_app.txt : c'est main.py qui les applique
(comme si elles venaient de Telegram), jamais l'API elle-même.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, Response

from .. import commandes_app, rapport
from ..core import config as C
from ..core.store import OpsStore

DOSSIER_APP = Path(__file__).with_name("mobile_app")
SERVICES = {
    "principal": "equipe-bots", "v17": "equipe-bots-v17", "tr": "equipe-bots-tr",
    "marches": "equipe-bots-marches", "renseignement": "equipe-bots-renseignement", "api": "equipe-bots-v17-api",
}
JOURNAUX = {"principal": "bot.log", "tr": "tr.log", "marches": "marches.log", "renseignement": "renseignement.log"}
ACTIONS = commandes_app.ACTIONS
SECRETS = [
    (re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{20,}"), "bot***"),                       # jeton Telegram dans une URL
    (re.compile(r"(signature|apiKey|api_key|secret|X-MBX-APIKEY)([=:\"' ]+)[A-Za-z0-9+/_-]{8,}", re.I), r"\1\2***"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"), "sk-ant-***"),
]
ESSAIS_MAX = 10                  # 10 codes faux en 10 min : l'application est verrouillée 10 min
_echecs: list[float] = []

# Les modules de la plateforme (alertes.py) configurent sinon le journal bot.log du bot principal dans ce
# processus : un gestionnaire neutre l'en empêche (logging.basicConfig ne fait rien s'il y en a déjà un).
if not logging.getLogger().handlers:
    logging.getLogger().addHandler(logging.NullHandler())

router = APIRouter()


# ------------------------------------------------------------------ outils
def masquer(texte: str) -> str:
    for motif, remplacement in SECRETS:
        texte = motif.sub(remplacement, texte)
    return texte


def _json(chemin, defaut=None):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defaut


def _num(x, defaut=0.0):
    try:
        v = float(x)
        return v if v == v and abs(v) != float("inf") else defaut
    except (TypeError, ValueError):
        return defaut


def fin_de_fichier(chemin, lignes=80, octets=64_000):
    """Dernières lignes d'un journal, sans lire tout le fichier."""
    try:
        with open(chemin, "rb") as f:
            f.seek(0, os.SEEK_END)
            taille = f.tell()
            f.seek(max(0, taille - octets))
            brut = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return [masquer(x) for x in brut.splitlines()[-lignes:]]


def etat_services():
    """systemctl is-active pour chaque service (None hors systemd)."""
    try:
        r = subprocess.run(["systemctl", "is-active", *SERVICES.values()], capture_output=True, text=True, timeout=4)
    except Exception:
        return {nom: None for nom in SERVICES}
    etats = r.stdout.split()
    if len(etats) != len(SERVICES):
        return {nom: None for nom in SERVICES}
    return dict(zip(SERVICES, etats))


# ------------------------------------------------------------------ sécurité
def verifier_code(authorization: str | None):
    attendu = os.getenv("V17_APP_TOKEN", "").strip()
    if len(attendu) < 16:
        raise HTTPException(503, "Application non configurée : tape « bots app » dans Termius.")
    maintenant = time.time()
    _echecs[:] = [t for t in _echecs if maintenant - t < 600]
    if len(_echecs) >= ESSAIS_MAX:
        raise HTTPException(429, "Trop de codes faux : réessaie dans 10 minutes.")
    fourni = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(fourni.encode(), attendu.encode()):
        _echecs.append(maintenant)
        raise HTTPException(401, "Code d'accès incorrect.")


# ------------------------------------------------------------------ données
def bot_principal(dossier="."):
    d = Path(dossier)
    etat = _json(d / "etat.json", {}) or {}
    battement = _json(d / "battement.json", {}) or {}
    age = time.time() - _num(battement.get("ts")) if battement.get("ts") else None
    positions = []
    for sym, p in (etat.get("positions") or {}).items():
        entree, qte = _num(p.get("entree")), _num(p.get("quantite"))
        positions.append({
            "symbole": sym, "entree": entree, "quantite": qte, "valeur_entree": entree * qte,
            "stop": _num(p.get("stop")), "objectif": _num(p.get("objectif")),
            "plus_haut": _num(p.get("plus_haut")), "securise": bool(p.get("securise")),
            "essai": p.get("mode") == "exploration", "ouvert": _num(p.get("ouvert")) or None,
            "protege": p.get("id_stop") not in (None, "aucun"),
        })
    dj = etat.get("disjoncteur")
    return {
        "compte": (os.getenv("MODE") or "demo").lower(),
        "vivant": age is not None and age < 15 * 60, "age_battement_s": age,
        "resume": battement.get("resume"),
        "arret_manuel": bool(etat.get("arret_manuel")), "arret_jour": bool(etat.get("arret_jour")),
        "disjoncteur": (dj.get("raison") if isinstance(dj, dict) else str(dj)) if dj else None,
        "niveau_risque": etat.get("niveau_risque"), "reseau_ko": bool(etat.get("reseau_ko")),
        "donnees_ko": etat.get("donnees_ko") or None,
        "latent": _num(etat.get("latent")), "palier": int(_num(etat.get("palier"))) + 1,
        "positions": sorted(positions, key=lambda x: -(x["ouvert"] or 0)),
    }


def v17(store: OpsStore, settings):
    e = rapport.etat(store, settings)
    ordres = [{"ts": o["ts"], "symbole": o["symbol"], "cote": o["side"], "qte": o["qty"], "prix": o["price"],
               "statut": o["status"]} for o in store.recent("orders", 15)]
    courbe = []
    for s in reversed(store.recent("snapshots", 400)):
        try:
            eq = _num(json.loads(s["payload"]).get("equity"), None)
        except ValueError:
            eq = None
        if eq is not None:
            courbe.append([s["ts"], round(eq, 2)])
    return {**e, "ordres": ordres, "courbe": courbe[-200:]}


def renseignement():
    try:
        import lecture_renseignement as LR
        r = LR.resume()
    except Exception:
        return None
    if not r.get("bots"):
        return None
    try:                                              # Polymarket, LECTURE SEULE (aucun pari : bloqué en France)
        predictions = [{"titre": x["titre"][:220], "ts": x["ts"], "importance": x["importance"]}
                       for x in LR.par_source("Polymarket")]
    except Exception:
        predictions = []
    g = (r.get("signaux") or {}).get("global") or {}
    return {"bots": r["bots"], "actifs": r["actifs"], "faits_24h": r["faits_24h"], "sources_24h": r["sources_24h"],
            "climat": g.get("valeur"), "confiance": g.get("confiance"), "en_erreur": r["en_erreur"][:5],
            "alertes": [{"titre": a.get("titre", "")[:200], "niveau": a.get("niveau", 0), "ts": a.get("ts")}
                        for a in r["alertes"]],
            "predictions": predictions}


def symbole_tradingview(symbole):
    """« BTC/USDT » -> « BINANCE:BTCUSDT » (même marché que les bots : Binance spot)."""
    s = str(symbole or "").upper().strip()
    if not re.fullmatch(r"[A-Z0-9]{1,15}/[A-Z0-9]{2,10}", s):
        return None
    return "BINANCE:" + s.replace("/", "")


def symboles_tradingview(principal, w):
    """Tous les marchés suivis ou détenus par les bots, sans doublon, positions d'abord."""
    brut = ([x.get("symbole") for x in principal.get("positions", [])]
            + [x.get("symbol") for x in (w.get("positions") or [])] + list(w.get("symbols") or []))
    return [t for t in dict.fromkeys(symbole_tradingview(x) for x in brut) if t]


def marches(dossier="."):
    chemin = Path(dossier) / "marches_etat.json"
    if not chemin.exists():                           # veille marchés pas déployée
        return None
    try:
        import veille_marches as VM
        return {"texte": VM.texte_statut(VM.charger_etat(str(chemin)))}
    except Exception:
        return None


def tableau(store: OpsStore, settings, dossier="."):
    alertes = []
    p = bot_principal(dossier)
    try:
        w = v17(store, settings)
    except Exception as ex:                          # base v17 absente ou illisible : le reste s'affiche
        w = {"erreur": str(ex)[:200]}
    if p["disjoncteur"]:
        alertes.append(f"Bot principal : sécurité générale déclenchée ({p['disjoncteur']})")
    if p["reseau_ko"]:
        alertes.append("Bot principal : connexion Binance instable")
    if w.get("pending"):
        alertes.append("v17 : rapprochement en cours avec Binance")
    if w.get("entries_blocked"):
        alertes.append("v17 : achats bloqués par un réglage invalide")
    if w.get("governor", {}).get("halted"):
        alertes.append("v17 : limite de perte cumulée atteinte, achats bloqués")
    if w.get("kill_switch"):
        alertes.append("v17 : KILL_SWITCH actif")
    return {"ts": time.time(), "services": etat_services(), "principal": p, "v17": w,
            "renseignement": renseignement(), "marches": marches(dossier), "alertes": alertes,
            "tradingview": symboles_tradingview(p, w)}


def executer_action(action, store: OpsStore, settings, dossier="."):
    if action in ACTIONS:
        commandes_app.deposer(ACTIONS[action], dossier)
        return {"ok": True, "message": "Commande transmise au bot principal : appliquée dans ~20 s, "
                                       "confirmation sur Telegram."}
    if action in ("v17_stop", "v17_reprise"):
        return {"ok": True, "message": rapport.regler_pause(action == "v17_stop", store, settings)}
    raise HTTPException(400, "Action inconnue.")


# ------------------------------------------------------------------ routes
def _contexte():
    s = C.settings
    return OpsStore(s.ops_db), s


def _fichier(nom, media):
    chemin = DOSSIER_APP / nom
    if not chemin.is_file():
        raise HTTPException(404)
    return FileResponse(chemin, media_type=media, headers={"Cache-Control": "no-cache"})


@router.get("/app", include_in_schema=False)
@router.get("/app/", include_in_schema=False)
def page():
    return _fichier("index.html", "text/html; charset=utf-8")


@router.get("/app/manifest.webmanifest", include_in_schema=False)
def manifeste():
    return _fichier("manifest.webmanifest", "application/manifest+json")


@router.get("/app/sw.js", include_in_schema=False)
def service_worker():
    r = _fichier("sw.js", "text/javascript")
    r.headers["Service-Worker-Allowed"] = "/app/"
    return r


@router.get("/app/{nom}.png", include_in_schema=False)
def icone(nom: str):
    if nom not in ("icon-180", "icon-192", "icon-512"):
        raise HTTPException(404)
    return _fichier(f"{nom}.png", "image/png")


@router.get("/app/api/tableau")
def api_tableau(authorization: str | None = Header(default=None)):
    verifier_code(authorization)
    store, s = _contexte()
    return tableau(store, s)


@router.get("/app/api/journal")
def api_journal(source: str = "principal", lignes: int = 80, authorization: str | None = Header(default=None)):
    verifier_code(authorization)
    _, s = _contexte()
    fichier = s.log_file if source == "v17" else JOURNAUX.get(source)
    if not fichier:
        raise HTTPException(400, "Journal inconnu.")
    return {"source": source, "lignes": fin_de_fichier(fichier, min(max(int(lignes), 10), 300))}


@router.post("/app/api/action")
def api_action(corps: dict, authorization: str | None = Header(default=None)):
    verifier_code(authorization)
    store, s = _contexte()
    return executer_action(str(corps.get("action", "")), store, s)


@router.get("/app/api/verifier")
def api_verifier(authorization: str | None = Header(default=None)):
    verifier_code(authorization)
    return Response(status_code=204)
