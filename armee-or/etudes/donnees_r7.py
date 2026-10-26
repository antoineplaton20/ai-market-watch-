"""R7 : chargement des données de test (archives mensuelles Binance et historiques Yahoo), contrôlées par qualite.py.

Binance (data.binance.vision, sommes SHA-256 vérifiées au téléchargement par etudes/telecharger_r7.py) :
  colonnes : ouverture (ms, ou µs depuis 2025), o, h, l, c, volume, clôture, volume en devise, nombre de trades,
  volume ACHETEUR (preneur), …
Dukascopy (R8, datafeed.dukascopy.com, fichiers mensuels BID_candles_hour_1.bi5 compressés LZMA, téléchargés par
etudes/corpus_r8/dukascopy.py) : enregistrements de 24 octets (secondes depuis le début du mois, o, c, l, h en
entiers, volume) ; l'échelle des prix est trouvée en comparant au niveau d'une référence (Yahoo).
"""
import calendar
import glob
import io
import lzma
import os
import struct
import zipfile

import numpy as np


def charger_binance(dossier, symbole, intervalle):
    lignes = []
    for z in sorted(glob.glob(os.path.join(dossier, f"{symbole}-{intervalle}-*.zip"))):
        zz = zipfile.ZipFile(z)
        brut = zz.read(zz.namelist()[0]).decode()
        for ligne in brut.splitlines():
            p = ligne.split(",")
            if not p[0].isdigit():
                continue
            t = int(p[0])
            t = t // 1000 if t > 10**14 else t
            lignes.append((t, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[9])))
    a = np.array(sorted(set(lignes)), dtype=float)
    return {"ts": a[:, 0].astype(np.int64), "o": a[:, 1], "h": a[:, 2], "l": a[:, 3], "c": a[:, 4], "v": a[:, 5],
            "vb": a[:, 6]}


def charger_dukascopy(dossier, symbole, reference=None):
    """Bougies d'une heure, heures de cotation seulement (volume ou amplitude non nuls). reference : dict avec ts (ms)
    et c d'un même marché, pour l'échelle (puissance de 10) ; sans référence, les prix restent en entiers."""
    rep = os.path.join(dossier, symbole)
    lignes = []
    for f in sorted(os.listdir(rep)) if os.path.isdir(rep) else []:
        brut = open(os.path.join(rep, f), "rb").read()
        if not brut:                                              # mois absent chez Dukascopy (404 noté vide)
            continue
        t0 = calendar.timegm((int(f[:4]), int(f[5:7]), 1, 0, 0, 0))
        x = lzma.decompress(brut)
        for k in range(len(x) // 24):
            t, o, c, l, h, v = struct.unpack(">5if", x[24 * k:24 * k + 24])
            if v > 0 or h > l:
                lignes.append((t0 + t, o, h, l, c, v))
    if not lignes:
        return None
    a = np.array(sorted(set(lignes)), dtype=float)
    echelle = 1.0
    if reference is not None:
        sel = (reference["ts"] >= a[0, 0] * 1000) & (reference["ts"] <= a[-1, 0] * 1000)
        echelle = 10.0 ** round(float(np.log10(np.median(a[:, 4]) / np.median(reference["c"][sel]))))
    return {"ts": (a[:, 0] * 1000).astype(np.int64), "o": a[:, 1] / echelle, "h": a[:, 2] / echelle,
            "l": a[:, 3] / echelle, "c": a[:, 4] / echelle, "v": a[:, 5], "vb": a[:, 5] / 2}


def regrouper(d, minutes):
    """Bougies de `minutes` à partir de bougies plus courtes (alignées sur l'heure UTC)."""
    pas = minutes * 60_000
    cle = d["ts"] // pas
    debut = np.flatnonzero(np.r_[True, cle[1:] != cle[:-1]])
    fin = np.r_[debut[1:], len(cle)]
    out = {"ts": cle[debut] * pas, "o": d["o"][debut], "c": d["c"][fin - 1],
           "h": np.maximum.reduceat(d["h"], debut), "l": np.minimum.reduceat(d["l"], debut),
           "v": np.add.reduceat(d["v"], debut), "vb": np.add.reduceat(d["vb"], debut)}
    return out


def tableau(d):
    return d["o"], d["h"], d["l"], d["c"]


def lignes_controle(d):
    return list(zip(d["ts"].tolist(), d["o"].tolist(), d["h"].tolist(), d["l"].tolist(), d["c"].tolist()))


def heure_utc(ts_ms):
    return (np.asarray(ts_ms) // 3_600_000) % 24


def minute_du_jour(ts_ms):
    return (np.asarray(ts_ms) // 60_000) % 1440


def jour(ts_ms):
    return np.asarray(ts_ms) // 86_400_000


def jour_semaine(ts_ms):
    return (jour(ts_ms) + 3) % 7                                  # 0 = lundi (le 01/01/1970 était un jeudi)
