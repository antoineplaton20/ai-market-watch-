"""LECTURE DES BOUGIES JAPONAISES — 14 figures classiques (Steve Nison), sur bougies FERMÉES uniquement.

Chaque figure n'a de sens que dans son CONTEXTE :
  figures de REBOND (haussières) : seulement APRÈS UNE BAISSE
  figures de CHUTE  (baissières) : seulement APRÈS UNE HAUSSE

Les failles de lecture connues, et comment on s'en protège :
  1. Lire une bougie pas encore fermée : elle peut changer du tout au tout -> on ne lit que des bougies fermées.
  2. Oublier le contexte : un « marteau » en pleine hausse ne veut rien dire -> tendance préalable exigée.
  3. Trader la figure seule : sans confirmation, la plupart échouent -> option « confirmation » (la bougie
     suivante doit clôturer au-dessus du plus haut de la figure).
  4. Ignorer le volume : une figure sans volume est souvent du bruit -> option « volume ».
  5. Les trous (gaps) des actions n'existent presque pas en crypto (marché 24 h/24) -> définitions adaptées :
     on compare les corps des bougies, pas des trous d'ouverture.
  6. Petite unité de temps = beaucoup de fausses figures -> c'est l'évolution qui juge, unité par unité, avec le
     coffre-fort, la barre anti-chance, le walk-forward et le Sharpe dégonflé. Une figure qui ne passe pas les
     portes ne trade jamais.

Mécanisme économique (pourquoi ça PEUT marcher) : une longue mèche basse après une baisse montre que les vendeurs
ont poussé le prix puis ont été absorbés par des acheteurs dans la même bougie (rejet du prix bas) ; un avalement
montre que les acheteurs ont repris tout le terrain perdu la veille. Ce sont des hypothèses, pas des certitudes.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

REBOND = {
    "MARTEAU": "marteau : longue mèche basse, les vendeurs ont été repoussés",
    "AVALEMENT_HAUSSIER": "avalement haussier : les acheteurs reprennent toute la bougie précédente",
    "ETOILE_DU_MATIN": "étoile du matin : grande baisse, hésitation, puis forte reprise",
    "PENETRANTE": "ligne pénétrante : reprise de plus de la moitié de la baisse précédente",
    "TROIS_SOLDATS": "trois soldats blancs : trois hausses fermes d'affilée",
    "HARAMI_HAUSSIER": "harami haussier : la baisse s'essouffle à l'intérieur de la bougie précédente",
    "DOJI_LIBELLULE": "doji libellule : prix bas rejeté, clôture au plus haut",
}
CHUTE = {
    "ETOILE_FILANTE": "étoile filante : longue mèche haute, les acheteurs ont été repoussés",
    "AVALEMENT_BAISSIER": "avalement baissier : les vendeurs reprennent toute la bougie précédente",
    "ETOILE_DU_SOIR": "étoile du soir : grande hausse, hésitation, puis forte baisse",
    "NUAGE_NOIR": "couverture en nuage noir : la baisse efface plus de la moitié de la hausse précédente",
    "TROIS_CORBEAUX": "trois corbeaux noirs : trois baisses fermes d'affilée",
    "HARAMI_BAISSIER": "harami baissier : la hausse s'essouffle à l'intérieur de la bougie précédente",
    "PENDU": "pendu : forme de marteau en haut d'une hausse, les vendeurs se réveillent",
}
FIGURES = {**REBOND, **CHUTE}
TENDANCE_N = 5                           # contexte : clôture d'il y a 1 bougie comparée à celle d'il y a 6


def _dec(x, k):
    """x décalé de k bougies vers le passé (NaN au début) : x[i-k] à la position i."""
    x = np.asarray(x, dtype=float)
    if k == 0:
        return x
    return np.r_[np.full(k, np.nan), x[:-k]] if len(x) > k else np.full(len(x), np.nan)


def figures(o, h, l, c) -> Dict[str, np.ndarray]:
    """Tableaux booléens : figure présente sur la bougie i (qui vient de fermer), avec son contexte.
    N'utilise JAMAIS une bougie après i."""
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    with np.errstate(invalid="ignore", divide="ignore"):
        corps = np.abs(c - o)
        amp = np.where(h - l > 0, h - l, np.nan)
        haut_corps, bas_corps = np.maximum(o, c), np.minimum(o, c)
        meche_h, meche_b = h - haut_corps, bas_corps - l
        vert, rouge = c > o, c < o
        o1, c1 = _dec(o, 1), _dec(c, 1)
        o2, c2 = _dec(o, 2), _dec(c, 2)
        corps1, corps2 = np.abs(c1 - o1), np.abs(c2 - o2)
        amp1 = _dec(amp, 1)
        amp2 = _dec(amp, 2)
        vert1, rouge1 = c1 > o1, c1 < o1
        vert2, rouge2 = c2 > o2, c2 < o2
        baisse = _dec(c, 1) < _dec(c, 1 + TENDANCE_N)          # contexte connu AVANT la figure
        hausse = _dec(c, 1) > _dec(c, 1 + TENDANCE_N)
        baisse2 = _dec(c, 2) < _dec(c, 2 + TENDANCE_N)
        hausse2 = _dec(c, 2) > _dec(c, 2 + TENDANCE_N)
        petit = corps <= 0.35 * amp
        f = {
            "MARTEAU": baisse & petit & (meche_b >= 2 * corps) & (meche_h <= 0.25 * amp),
            "AVALEMENT_HAUSSIER": baisse & rouge1 & vert & (o <= c1) & (c >= o1) & (corps > corps1),
            "ETOILE_DU_MATIN": baisse2 & rouge2 & (corps2 >= 0.6 * amp2) & (corps1 <= 0.3 * amp1)
                               & vert & (c >= (o2 + c2) / 2),
            "PENETRANTE": baisse & rouge1 & (corps1 >= 0.6 * amp1) & vert & (o <= c1)
                          & (c > (o1 + c1) / 2) & (c < o1),
            "TROIS_SOLDATS": vert & vert1 & vert2 & (c > c1) & (c1 > c2) & (meche_h <= 0.3 * corps)
                             & (corps >= 0.5 * amp) & (corps1 >= 0.5 * amp1) & baisse2,
            "HARAMI_HAUSSIER": baisse & rouge1 & (corps1 >= 0.6 * amp1) & vert & (o >= c1) & (c <= o1)
                               & (corps <= 0.5 * corps1),
            "DOJI_LIBELLULE": baisse & (corps <= 0.1 * amp) & (meche_b >= 0.6 * amp) & (meche_h <= 0.1 * amp),
            "ETOILE_FILANTE": hausse & petit & (meche_h >= 2 * corps) & (meche_b <= 0.25 * amp),
            "AVALEMENT_BAISSIER": hausse & vert1 & rouge & (o >= c1) & (c <= o1) & (corps > corps1),
            "ETOILE_DU_SOIR": hausse2 & vert2 & (corps2 >= 0.6 * amp2) & (corps1 <= 0.3 * amp1)
                              & rouge & (c <= (o2 + c2) / 2),
            "NUAGE_NOIR": hausse & vert1 & (corps1 >= 0.6 * amp1) & rouge & (o >= c1)
                          & (c < (o1 + c1) / 2) & (c > o1),
            "TROIS_CORBEAUX": rouge & rouge1 & rouge2 & (c < c1) & (c1 < c2) & (meche_b <= 0.3 * corps)
                              & (corps >= 0.5 * amp) & (corps1 >= 0.5 * amp1) & hausse2,
            "HARAMI_BAISSIER": hausse & vert1 & (corps1 >= 0.6 * amp1) & rouge & (o <= c1) & (c >= o1)
                               & (corps <= 0.5 * corps1),
            "PENDU": hausse & petit & (meche_b >= 2 * corps) & (meche_h <= 0.25 * amp),
        }
    f = {k: np.nan_to_num(v.astype(float), nan=0.0).astype(bool) for k, v in f.items()}
    f["REBOND"] = np.logical_or.reduce([f[k] for k in REBOND])
    f["CHUTE"] = np.logical_or.reduce([f[k] for k in CHUTE])
    return f


def caracteristiques(o, h, l, c) -> Dict[str, np.ndarray]:
    """Colonnes pour les génomes : bougie_X (sur la dernière bougie fermée) et bougie_X_prec (celle d'avant,
    pour exiger une confirmation), plus le plus haut de la bougie précédente."""
    f = figures(o, h, l, c)
    res = {}
    for k, v in f.items():
        res[f"bougie_{k}"] = v
        res[f"bougie_{k}_prec"] = np.r_[False, v[:-1]] if len(v) else v
    res["h_prec"] = _dec(h, 1)
    return res


def lire(o, h, l, c, i: int = -1) -> List[str]:
    """Lecture en français de la bougie i (déjà fermée) : [« marteau : ... (rebond possible) », ...]."""
    if len(c) < TENDANCE_N + 3:
        return []
    f = figures(o, h, l, c)
    res = [f"{FIGURES[k]} (signal de rebond, à confirmer)" for k in REBOND if f[k][i]]
    res += [f"{FIGURES[k]} (signal de chute, prudence)" for k in CHUTE if f[k][i]]
    return res
