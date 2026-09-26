"""Spécification d'une stratégie du labo : uniquement des BLOCS connus, jamais de code arbitraire.

Modèle (méthode « 1 tendance + 2 confirmations non corrélées + 1 filtre ») :
    {"nom", "explication", "unite": "15m"|"1h"|"4h",
     "tendance": bloc, "confirmations": [bloc, bloc], "filtre": bloc,
     "stop_atr": multiple d'ATR sous le prix, "rr": objectif en multiple du risque,
     "sortie_tendance": vendre si la tendance se retourne}
Un bloc = {"type", "periode", "periode2", "seuil", "seuil2"} ; les champs inutiles d'un type sont ignorés.
Achat seulement (spot, sans levier ni vente à découvert), comme les bots de la plateforme.
"""
from __future__ import annotations

import copy

import numpy as np

from . import indicateurs as I

UNITES = ("15m", "1h", "4h")

# type -> (famille, description, {champ: (min, max, défaut)})
BLOCS = {
    # ---- tendance
    "prix_au_dessus_ema": ("tendance", "prix au-dessus de la moyenne exponentielle",
                           {"periode": (20, 300, 200)}),
    "ema_croisee": ("tendance", "moyenne rapide au-dessus de la moyenne lente",
                    {"periode": (5, 60, 20), "periode2": (20, 250, 50)}),
    "supertrend": ("tendance", "Supertrend haussier", {"periode": (5, 30, 10), "seuil": (1.0, 6.0, 3.0)}),
    "donchian_cassure": ("tendance", "clôture au-dessus du plus haut des N bougies précédentes",
                         {"periode": (10, 120, 20)}),
    # ---- confirmations
    "rsi_au_dessus": ("confirmation", "RSI au-dessus du seuil (élan)", {"periode": (5, 30, 14), "seuil": (40, 75, 50)}),
    "rsi_sous": ("confirmation", "RSI sous le seuil (repli dans la tendance)",
                 {"periode": (2, 30, 14), "seuil": (10, 55, 40)}),
    "macd_positif": ("confirmation", "histogramme MACD positif", {"periode": (5, 20, 12), "periode2": (15, 50, 26)}),
    "adx_fort": ("confirmation", "ADX au-dessus du seuil (tendance forte)",
                 {"periode": (7, 30, 14), "seuil": (10, 40, 20)}),
    "momentum_positif": ("confirmation", "clôture au-dessus de celle d'il y a N bougies", {"periode": (3, 100, 10)}),
    "bollinger_bas": ("confirmation", "clôture sous la bande basse de Bollinger (excès de baisse)",
                      {"periode": (10, 50, 20), "seuil": (1.0, 3.5, 2.0)}),
    # ---- filtres
    "volume_superieur": ("filtre", "volume au-dessus de sa moyenne × seuil",
                         {"periode": (5, 100, 20), "seuil": (0.5, 3.0, 1.0)}),
    "atr_pct_entre": ("filtre", "volatilité (ATR en % du prix) entre deux bornes",
                      {"periode": (5, 50, 14), "seuil": (0.05, 5.0, 0.2), "seuil2": (0.2, 15.0, 5.0)}),
    "aucun": ("filtre", "aucun filtre", {}),
}
TYPES = {f: [t for t, (fam, _, _) in BLOCS.items() if fam == f] for f in ("tendance", "confirmation", "filtre")}
LIMITES = {"stop_atr": (0.5, 6.0, 2.0), "rr": (0.5, 6.0, 2.0)}


class SpecInvalide(ValueError):
    pass


def _borne(valeur, mini, maxi, defaut, entier):
    try:
        v = float(valeur)
    except (TypeError, ValueError):
        v = defaut
    if not np.isfinite(v) or v == 0:
        v = defaut
    v = min(max(v, mini), maxi)
    return int(round(v)) if entier else round(v, 4)


def _bloc(b, famille):
    if not isinstance(b, dict) or b.get("type") not in TYPES[famille]:
        raise SpecInvalide(f"{famille} inconnue : {b.get('type') if isinstance(b, dict) else b!r}")
    out = {"type": b["type"]}
    for champ, (mini, maxi, defaut) in BLOCS[b["type"]][2].items():
        out[champ] = _borne(b.get(champ), mini, maxi, defaut, champ.startswith("periode"))
    if b["type"] == "ema_croisee" and out["periode"] >= out["periode2"]:
        out["periode2"] = min(250, out["periode"] * 2 + 1)
    if b["type"] == "macd_positif" and out["periode"] >= out["periode2"]:
        out["periode2"] = min(50, out["periode"] * 2 + 1)
    if b["type"] == "atr_pct_entre" and out["seuil"] >= out["seuil2"]:
        out["seuil2"] = min(15.0, out["seuil"] * 3)
    return out


def normaliser(spec):
    """Vérifie et borne une spécification (venant de l'IA ou d'un exemple). Lève SpecInvalide si inutilisable."""
    if not isinstance(spec, dict):
        raise SpecInvalide("spécification absente")
    confs = spec.get("confirmations")
    if not isinstance(confs, list) or len(confs) != 2:
        raise SpecInvalide("il faut exactement 2 confirmations")
    out = {
        "nom": str(spec.get("nom") or "Stratégie sans nom").strip()[:60],
        "explication": str(spec.get("explication") or "").strip()[:500],
        "unite": spec.get("unite") if spec.get("unite") in UNITES else "1h",
        "tendance": _bloc(spec.get("tendance"), "tendance"),
        "confirmations": [_bloc(c, "confirmation") for c in confs],
        "filtre": _bloc(spec.get("filtre") or {"type": "aucun"}, "filtre"),
        "sortie_tendance": bool(spec.get("sortie_tendance", True)),
    }
    if out["confirmations"][0]["type"] == out["confirmations"][1]["type"]:
        raise SpecInvalide("les 2 confirmations doivent être de types différents (non corrélées)")
    for champ, (mini, maxi, defaut) in LIMITES.items():
        out[champ] = _borne(spec.get(champ), mini, maxi, defaut, False)
    return out


def decrire(spec):
    """Résumé lisible (français) d'une spécification normalisée."""
    def txt(b):
        params = ", ".join(f"{k} {v}" for k, v in b.items() if k != "type")
        return BLOCS[b["type"]][1] + (f" ({params})" if params else "")
    return (f"Tendance : {txt(spec['tendance'])} · Confirmations : {txt(spec['confirmations'][0])} ; "
            f"{txt(spec['confirmations'][1])} · Filtre : {txt(spec['filtre'])} · Stop {spec['stop_atr']} × ATR, "
            f"objectif {spec['rr']} R · bougies {spec['unite']}"
            + (" · sortie si la tendance se retourne" if spec["sortie_tendance"] else ""))


# ----------------------------------------------------------------------------- calcul des conditions
def _condition(b, o, h, l, c, v):
    t, p = b["type"], b.get("periode")
    with np.errstate(invalid="ignore"):
        if t == "prix_au_dessus_ema":
            return c > I.ema(c, p)
        if t == "ema_croisee":
            return I.ema(c, p) > I.ema(c, b["periode2"])
        if t == "supertrend":
            return I.supertrend_haussier(h, l, c, p, b["seuil"])
        if t == "donchian_cassure":
            return c > I.plus_haut_precedent(h, p)
        if t == "rsi_au_dessus":
            return I.rsi(c, p) > b["seuil"]
        if t == "rsi_sous":
            return I.rsi(c, p) < b["seuil"]
        if t == "macd_positif":
            return I.macd_hist(c, p, b["periode2"], 9) > 0
        if t == "adx_fort":
            return I.adx(h, l, c, p) > b["seuil"]
        if t == "momentum_positif":
            prec = np.concatenate((np.full(p, np.nan), c[:-p])) if len(c) > p else np.full(len(c), np.nan)
            return c > prec
        if t == "bollinger_bas":
            return c < I.bollinger_bas(c, p, b["seuil"])
        if t == "volume_superieur":
            return v > b["seuil"] * I.sma(v, p)
        if t == "atr_pct_entre":
            pct = I.atr(h, l, c, p) / c * 100
            return (pct >= b["seuil"]) & (pct <= b["seuil2"])
        if t == "aucun":
            return np.ones(len(c), dtype=bool)
    raise SpecInvalide(t)


def conditions(barres, spec):
    """-> (entree, tendance, atr) : tableaux alignés sur les bougies (valeurs à la CLÔTURE de chaque bougie)."""
    o, h, l, c, v = (barres[k] for k in ("o", "h", "l", "c", "v"))
    tendance = _condition(spec["tendance"], o, h, l, c, v)
    entree = tendance.copy()
    for b in spec["confirmations"] + [spec["filtre"]]:
        entree &= _condition(b, o, h, l, c, v)
    return entree, tendance, I.atr(h, l, c, 14)


# ----------------------------------------------------------------------------- exemples prêts à tester
EXEMPLES = {
    "tendance_classique": {
        "nom": "Tendance classique EMA 200", "unite": "1h",
        "explication": "Suivre la tendance longue (prix au-dessus de l'EMA 200), confirmée par l'élan (RSI > 50) et une "
                       "tendance forte (ADX > 20), seulement quand le volume est au-dessus de la normale.",
        "tendance": {"type": "prix_au_dessus_ema", "periode": 200},
        "confirmations": [{"type": "rsi_au_dessus", "periode": 14, "seuil": 50},
                          {"type": "adx_fort", "periode": 14, "seuil": 20}],
        "filtre": {"type": "volume_superieur", "periode": 20, "seuil": 1.0},
        "stop_atr": 2.0, "rr": 2.0, "sortie_tendance": True},
    "repli_dans_tendance": {
        "nom": "Repli dans la tendance", "unite": "1h",
        "explication": "Acheter un repli (RSI 2 très bas) quand la tendance de fond est haussière (EMA 50 > EMA 200) "
                       "et que l'élan sur 50 bougies reste positif, hors marchés trop calmes ou trop agités.",
        "tendance": {"type": "ema_croisee", "periode": 50, "periode2": 200},
        "confirmations": [{"type": "rsi_sous", "periode": 2, "seuil": 15},
                          {"type": "momentum_positif", "periode": 50}],
        "filtre": {"type": "atr_pct_entre", "periode": 14, "seuil": 0.3, "seuil2": 4.0},
        "stop_atr": 2.5, "rr": 1.5, "sortie_tendance": True},
    "cassure": {
        "nom": "Cassure de 20 bougies", "unite": "4h",
        "explication": "Acheter la cassure du plus haut de 20 bougies, confirmée par un MACD positif et une tendance "
                       "forte (ADX > 25), avec un volume supérieur à 1,2 fois la moyenne.",
        "tendance": {"type": "donchian_cassure", "periode": 20},
        "confirmations": [{"type": "macd_positif", "periode": 12, "periode2": 26},
                          {"type": "adx_fort", "periode": 14, "seuil": 25}],
        "filtre": {"type": "volume_superieur", "periode": 20, "seuil": 1.2},
        "stop_atr": 2.0, "rr": 3.0, "sortie_tendance": False},
}


def exemple(nom):
    return normaliser(copy.deepcopy(EXEMPLES[nom]))
