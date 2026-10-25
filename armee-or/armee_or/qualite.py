"""CONTRÔLEUR DES DONNÉES (R6.2) : aucune preuve sur un historique douteux.

Contrôles d'une série journalière [(ts en ms, ouverture, haut, bas, clôture)], seuils fixés à l'avance :
- lignes rejetées : valeur absente, prix nul ou négatif, bas au-dessus de l'ouverture ou de la clôture… ;
- trous : plus de 7 jours calendaires sans bougie (jours fériés et week-ends tolérés) ;
- prix figés : 5 clôtures identiques ou plus d'affilée (marché fermé ou flux mort) ;
- sauts aberrants : variation de plus de 15 écarts robustes ET de plus de 20 % (35 % en crypto) ; un saut aussitôt
  annulé le lendemain est une erreur de cotation probable ;
- ouvertures recopiées : ouverture égale à la clôture de la veille (source qui n'a pas la vraie ouverture : le banc
  exécute alors au cours de décision, un peu optimiste).

Verdict : « écarté » (exclu du banc), « réserve » (gardé, signalé), « bon ».
"""
from __future__ import annotations

import math

import numpy as np

TROU_JOURS = 7
FIGE_MIN = 5
SAUT_SIGMAS = 15.0
SAUT_MIN = {"crypto": 0.35}
SAUT_MIN_DEFAUT = 0.20
REJET_MAX = 0.05
FIGE_MAX = 0.05
ERREURS_MAX = 2
RECOPIE_MAX = 0.5


def _valide(o, h, l, c):
    try:
        v = [float(x) for x in (o, h, l, c)]
    except (TypeError, ValueError):
        return False
    return all(math.isfinite(x) and x > 0 for x in v) and v[2] <= min(v[0], v[3]) and v[1] >= max(v[0], v[3])


def controler(lignes, famille=""):
    """lignes : [(ts_ms, o, h, l, c)] dans l'ordre reçu -> rapport (dict) ; les lignes invalides sont comptées."""
    total = len(lignes)
    bonnes = [(int(t), float(o), float(h), float(l), float(c)) for t, o, h, l, c in lignes if _valide(o, h, l, c)]
    rapport = {"lignes": total, "rejetees": total - len(bonnes), "trous": 0, "figes": 0, "sauts": 0, "erreurs": 0,
               "ouvertures_recopiees": 0.0, "doublons": 0, "desordre": 0, "raisons": [], "verdict": "bon"}
    if len(bonnes) < 2:
        rapport.update(verdict="écarté", raisons=["moins de 2 bougies valides"])
        return rapport
    ts = np.array([b[0] for b in bonnes], dtype=np.int64)
    o, c = np.array([b[1] for b in bonnes]), np.array([b[4] for b in bonnes])
    pas = np.diff(ts)
    rapport["doublons"] = int((pas == 0).sum())
    rapport["desordre"] = int((pas < 0).sum())
    rapport["trous"] = int((pas > TROU_JOURS * 86_400_000).sum())
    meme = np.concatenate(([False], c[1:] == c[:-1]))
    serie, figes = 0, 0
    for m in meme:
        serie = serie + 1 if m else 0
        if serie == FIGE_MIN - 1:
            figes += FIGE_MIN
        elif serie >= FIGE_MIN:
            figes += 1
    rapport["figes"] = figes
    r = np.diff(np.log(c))
    sigma = 1.4826 * np.median(np.abs(r - np.median(r))) or float(np.std(r)) or 1e-9
    seuil = max(SAUT_SIGMAS * sigma, SAUT_MIN.get(famille, SAUT_MIN_DEFAUT))
    gros = np.abs(r) > seuil
    rapport["sauts"] = int(gros.sum())
    rapport["erreurs"] = int(sum(1 for i in range(len(r) - 1) if gros[i] and gros[i + 1] and r[i] * r[i + 1] < 0
                                 and abs(r[i] + r[i + 1]) < 0.25 * abs(r[i])))
    rapport["ouvertures_recopiees"] = float(np.mean(np.isclose(o[1:], c[:-1], rtol=1e-9, atol=0.0)))
    n = len(bonnes)
    ecarte = [m for m, faux in (
        (f"{rapport['rejetees']} lignes invalides ({rapport['rejetees'] / max(total, 1) * 100:.0f} %)",
         rapport["rejetees"] > REJET_MAX * total),
        (f"{figes} clôtures figées ({figes / n * 100:.0f} %)", figes > FIGE_MAX * n),
        (f"{rapport['erreurs']} erreurs de cotation (sauts aussitôt annulés)", rapport["erreurs"] > ERREURS_MAX),
        (f"{rapport['desordre']} dates en désordre", rapport["desordre"] > 0)) if faux]
    reserve = [m for m, faux in (
        (f"{rapport['doublons']} doublons", rapport["doublons"] > 0),
        (f"{rapport['trous']} trous de plus de {TROU_JOURS} jours", rapport["trous"] > 3),
        (f"{rapport['sauts']} sauts de plus de {seuil * 100:.0f} %", rapport["sauts"] > 0),
        (f"ouvertures recopiées {rapport['ouvertures_recopiees'] * 100:.0f} %",
         rapport["ouvertures_recopiees"] > RECOPIE_MAX)) if faux]
    rapport["raisons"] = ecarte + reserve
    rapport["verdict"] = "écarté" if ecarte else "réserve" if reserve else "bon"
    return rapport
