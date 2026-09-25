"""Bougies japonaises : chaque figure reconnue dans son contexte, et seulement dans son contexte."""
import numpy as np

import strategie as S
from moteurs import chandeliers as CH


def serie(tendance, fin):
    """6 bougies de tendance (baisse ou hausse) puis les bougies `fin` (o, h, l, c)."""
    pas = -1.0 if tendance == "baisse" else 1.0
    b = []
    p = 100.0
    for _ in range(7):
        b.append((p, p + 0.3 if pas > 0 else p + 0.1, p - 0.1 if pas > 0 else p - 0.3, p + pas * 0.2))
        p += pas * 0.2
    b += fin
    o, h, l, c = (np.array(x, dtype=float) for x in zip(*b))
    return o, h, l, c


def dernier(tendance, fin):
    f = CH.figures(*serie(tendance, fin))
    return {k for k, v in f.items() if v[-1] and k not in ("REBOND", "CHUTE")}


def test_marteau_seulement_apres_une_baisse():
    marteau = [(98.5, 98.7, 96.5, 98.65)]                          # petit corps en haut, longue mèche basse
    assert "MARTEAU" in dernier("baisse", marteau)
    assert "MARTEAU" not in dernier("hausse", [(101.5, 101.7, 99.5, 101.65)])
    assert "PENDU" in dernier("hausse", [(101.5, 101.7, 99.5, 101.65)])    # même forme en haut : pendu


def test_avalements():
    assert "AVALEMENT_HAUSSIER" in dernier("baisse", [(98.6, 98.7, 97.9, 98.0), (97.9, 99.0, 97.8, 98.9)])
    assert "AVALEMENT_BAISSIER" in dernier("hausse", [(101.4, 102.1, 101.3, 102.0), (102.1, 102.2, 101.0, 101.1)])


def test_etoiles_du_matin_et_du_soir():
    matin = [(98.6, 98.7, 96.9, 97.0), (96.9, 97.1, 96.6, 96.8), (96.9, 98.4, 96.8, 98.3)]
    assert "ETOILE_DU_MATIN" in dernier("baisse", matin)
    soir = [(101.4, 103.1, 101.3, 103.0), (103.1, 103.4, 102.9, 103.2), (103.1, 103.2, 101.5, 101.6)]
    assert "ETOILE_DU_SOIR" in dernier("hausse", soir)


def test_trois_soldats_et_trois_corbeaux():
    soldats = [(98.6, 99.25, 98.55, 99.2), (99.2, 99.85, 99.15, 99.8), (99.8, 100.45, 99.75, 100.4)]
    assert "TROIS_SOLDATS" in dernier("baisse", soldats)
    corbeaux = [(101.4, 101.45, 100.75, 100.8), (100.8, 100.85, 100.15, 100.2), (100.2, 100.25, 99.55, 99.6)]
    assert "TROIS_CORBEAUX" in dernier("hausse", corbeaux)


def test_lecture_en_francais():
    o, h, l, c = serie("baisse", [(98.5, 98.7, 96.5, 98.65)])
    texte = CH.lire(o, h, l, c)
    assert any(t.startswith("marteau") and "rebond" in t for t in texte)


def test_espece_chandeliers_confirmation_et_jamais_sur_une_chute():
    g = S.genome_defaut()
    g.update({"espece": "CHANDELIERS", "motif": "MARTEAU", "confirmation": True, "bougie_volume": False})
    F = {"c": 99.0, "h_prec": 98.7, "bougie_MARTEAU_prec": True, "bougie_MARTEAU": False, "bougie_CHUTE": False,
         "v": 1.0, "vol_moy": 1.0, "ema20": 99.0, f"hh_{g['lookback']}": 100.0, f"ll_{g['lookback']}": 97.0}
    assert bool(S.condition_espece(g, F, "1h"))                      # marteau hier, clôture au-dessus de son haut
    assert not bool(S.condition_espece(g, {**F, "c": 98.5}, "1h"))    # pas de confirmation
    assert not bool(S.condition_espece(g, {**F, "bougie_CHUTE": True}, "1h"))
    g["confirmation"] = False
    assert bool(S.condition_espece(g, {**F, "bougie_MARTEAU": True}, "1h"))
    assert "CHANDELIERS" in S.ESPECES and "bougies japonaises" in S.decrire(g)
