"""Exécution du labo dans l'API de l'application : essais en arrière-plan et test en direct sur PAPIER.

- Un seul essai à la fois ; au plus LABO_IA_PAR_JOUR appels à Claude par 24 h (défaut 30), pour borner le coût.
- Test en direct : toutes les 60 s, bougies publiques Binance (sans clé) de BTC, ETH et SOL ; la même fonction de
  simulation que le backtest décide des entrées et sorties FICTIVES ; chaque signal part sur Telegram, préfixé
  [labo]. Aucun ordre n'est jamais passé, aucun bot qui trade n'est modifié.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import numpy as np

from . import ia, pine, registre as R
from .moteur import simuler, statistiques
from .strategie import EXEMPLES, SpecInvalide, conditions, exemple as exemple_spec

_log = logging.getLogger("labo")
IA_PAR_JOUR = int(os.getenv("LABO_IA_PAR_JOUR", "30") or 30)
SUIVIS_MAX = 5
SYMBOLES_DIRECT = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
INTERVALLE_SUIVI_S = 60
_occupe = threading.Lock()
_suivi_lance = threading.Lock()
_suivi_actif = False


class LaboRefus(RuntimeError):
    """Demande refusée avec un message pour l'utilisateur (déjà un essai en cours, limite du jour...)."""


def lancer(idee=None, exemple=None, *, generer=None, synchrone=False):
    """Démarre un essai -> identifiant. idee : texte libre (Claude) ; exemple : clé de strategie.EXEMPLES."""
    spec = None
    if exemple:
        if exemple not in EXEMPLES:
            raise LaboRefus("Exemple inconnu.")
        spec = exemple_spec(exemple)
    elif not (idee or "").strip():
        raise LaboRefus("Décris une idée ou choisis un exemple.")
    elif R.appels_ia_depuis(time.time() - 86400) >= IA_PAR_JOUR:
        raise LaboRefus(f"Limite de {IA_PAR_JOUR} idées analysées par l'IA sur 24 h atteinte (coût maîtrisé). "
                        "Les exemples restent disponibles.")
    if not _occupe.acquire(blocking=False):
        raise LaboRefus("Un test est déjà en cours : attends son résultat.")
    try:
        eid = R.nouvel_essai(idee.strip() if idee else EXEMPLES[exemple]["nom"], "exemple" if exemple else "ia")
    except Exception:
        _occupe.release()
        raise
    if synchrone:
        _travail(eid, idee, spec, generer)
    else:
        threading.Thread(target=_travail, args=(eid, idee, spec, generer), daemon=True, name=f"labo-{eid}").start()
    return eid


def _travail(eid, idee, spec, generer):
    from .validation import evaluer
    try:
        remarques = ""
        if spec is None:
            spec, remarques = (generer or ia.generer)(idee)
        resultat = evaluer(spec)
        resultat["pine"] = pine.generer(spec)
        R.terminer(eid, spec, resultat, remarques)
    except (ia.IAIndisponible, SpecInvalide) as ex:
        R.echec(eid, str(ex), spec)
    except Exception as ex:                                  # jamais d'exception perdue dans un fil
        _log.exception("Essai %s en échec", eid)
        R.echec(eid, f"Erreur pendant le test : {type(ex).__name__} {str(ex)[:200]}", spec)
    finally:
        _occupe.release()


# ------------------------------------------------------------------ test en direct (papier)
def activer(essai_id, actif=True, forcer=False):
    e = R.essai(essai_id)
    if not e or e["statut"] != "fini":
        raise LaboRefus("Essai introuvable ou pas encore terminé.")
    if actif:
        if not e["valide"] and not forcer:
            raise LaboRefus("Cette stratégie a échoué aux portes du backtest.")
        if len(R.suivis(actifs_seulement=True)) >= SUIVIS_MAX:
            raise LaboRefus(f"{SUIVIS_MAX} stratégies suivies au maximum : arrête-en une d'abord.")
    R.activer_suivi(e["id"], actif)
    return {"ok": True, "message": ("Test en direct lancé : signaux fictifs sur Telegram, préfixés [labo]. Aucun ordre."
                                    if actif else "Test en direct arrêté.")}


def _barres(lignes):
    t = np.array(lignes, dtype=float)
    return {"ts": t[:, 0].astype(np.int64), "o": t[:, 1], "h": t[:, 2], "l": t[:, 3], "c": t[:, 4], "v": t[:, 5]}


def _message(ev, spec, sym):
    base, nom = sym.split("/")[0], spec["nom"]
    if ev["type"] == "entree":
        return (f"📡 [labo] Signal d'ACHAT {base} · « {nom} » · prix {ev['prix_entree']:.6g} $, stop "
                f"{ev['stop']:.6g} $, objectif {ev['objectif']:.6g} $. Test papier : aucun ordre passé.")
    return (f"📡 [labo] Sortie {base} ({ev['motif']}) · « {nom} » · {ev['R']:+.2f} R "
            f"({ev['rendement'] * 100:+.2f} %). Test papier.")


def tour_de_suivi(marche, prevenir, maintenant_ms=None):
    """Un passage du test en direct sur toutes les stratégies suivies. Toute erreur reste locale à une stratégie."""
    from v17_ops.adapters.market import closed_candles
    for s in R.suivis(actifs_seulement=True):
        spec, etat, trades = s["spec"], dict(s["etat"] or {}), list(s["trades"] or [])
        erreur = None
        for sym in SYMBOLES_DIRECT:
            try:
                lignes = closed_candles(marche.fetch_ohlcv(sym, timeframe=spec["unite"], limit=500), spec["unite"],
                                        maintenant_ms)
                if len(lignes) < 50:
                    continue
                barres = _barres(lignes)
                e = etat.get(sym) or {"position": None, "dernier_ts": int(barres["ts"][-1])}   # départ : maintenant
                nouveaux, evenements, etat[sym] = simuler(barres, spec, etat=e, signaux=conditions(barres, spec))
                for t in nouveaux:
                    t["symbole"] = sym
                trades += nouveaux
                for ev in evenements:
                    prevenir(_message(ev, spec, sym))
            except Exception as ex:
                erreur = f"{sym} : {type(ex).__name__} {str(ex)[:120]}"
        R.maj_suivi(s["essai_id"], etat, trades, erreur)


def bilan_suivi(s):
    positions = [{"symbole": sym, **e["position"]} for sym, e in (s.get("etat") or {}).items()
                 if isinstance(e, dict) and e.get("position")]
    return {"essai_id": s["essai_id"], "nom": (s.get("spec") or {}).get("nom"), "actif": s["actif"],
            "depuis": s["depuis"], "maj": s["maj"], "erreur": s.get("erreur"), "positions": positions,
            "stats": statistiques(s.get("trades") or []), "derniers": (s.get("trades") or [])[-5:][::-1]}


def _boucle_suivi():
    from v17_ops.adapters.market import BinancePublic
    marche = None

    def prevenir(msg):
        try:
            from alertes import alerte
            alerte(msg, important=False)
        except Exception as ex:
            _log.warning("Telegram indisponible pour le labo : %s", ex)

    while True:
        time.sleep(INTERVALLE_SUIVI_S)
        try:
            if R.suivis(actifs_seulement=True):
                marche = marche or BinancePublic()
                tour_de_suivi(marche, prevenir)
        except Exception:
            _log.exception("Test en direct du labo : tour en erreur (il continue)")


def demarrer_suivi():
    """Lance le fil du test en direct (une seule fois par processus). Appelé au démarrage de l'API."""
    global _suivi_actif
    with _suivi_lance:
        if _suivi_actif:
            return
        _suivi_actif = True
    try:
        R.orphelins()
    except Exception:
        pass
    threading.Thread(target=_boucle_suivi, daemon=True, name="labo-suivi").start()
