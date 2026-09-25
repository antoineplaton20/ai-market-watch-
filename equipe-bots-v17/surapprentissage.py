"""SUR-APPRENTISSAGE : mesurer le risque que la meilleure stratégie ne soit bonne que par chance.

Deux outils de la recherche en finance quantitative :

1. PBO — Probabilité de Sur-Apprentissage du Backtest (Bailey, Borwein, López de Prado, Zhu).
   Méthode CSCV : l'historique d'entraînement est coupé en 12 tranches. Pour chacune des 924 façons d'en
   prendre 6 comme « passé » et 6 comme « futur », on choisit la meilleure stratégie sur le passé et on
   regarde son classement sur le futur. PBO = part des cas où elle finit dans la moitié la moins bonne.
   0 % = la sélection est fiable | 50 % = pas mieux que tirer au sort | plus = elle choisit la chance.

2. Sharpe dégonflé — Deflated Sharpe Ratio (Bailey, López de Prado).
   Probabilité que le vrai rendement ajusté du risque d'une stratégie soit positif, une fois retiré
   l'effet « on a essayé beaucoup de stratégies et gardé la meilleure » et l'effet des gros écarts
   (asymétrie, queues épaisses). 95 % = très probablement réel | 50 % = pile ou face."""
import itertools
import math
from statistics import NormalDist
import numpy as np

EULER = 0.5772156649015329
NORMALE = NormalDist()


def matrice_tranches(trades, t_debut, t_fin, nb_tranches):
    """trades : liste de (heures d'entrée, R) par stratégie -> matrice [tranches x stratégies] de R cumulés."""
    bornes = np.linspace(t_debut, t_fin, nb_tranches + 1)
    M = np.zeros((nb_tranches, len(trades)))
    for j, (te, rs) in enumerate(trades):
        if len(te):
            idx = np.clip(np.searchsorted(bornes, te, side="right") - 1, 0, nb_tranches - 1)
            np.add.at(M[:, j], idx, rs)
    return M


def pbo_cscv(M):
    """PBO par validation croisée combinatoire symétrique. M : [tranches x stratégies].
    Renvoie (pbo, dégradation) ; dégradation = rang moyen hors échantillon du meilleur (1 = premier)."""
    S, N = M.shape
    if N < 10 or S < 4 or S % 2:
        return None, None
    combos = np.array([[i in c for i in range(S)] for c in itertools.combinations(range(S), S // 2)])
    IS = combos.astype(float) @ M
    OOS = (~combos).astype(float) @ M
    meilleur = IS.argmax(axis=1)
    perf = OOS[np.arange(len(combos)), meilleur]
    # rang relatif hors échantillon (égalités comptées à moitié), puis logit
    rang = (OOS < perf[:, None]).sum(axis=1) + 0.5 * ((OOS == perf[:, None]).sum(axis=1) - 1) + 1
    omega = rang / (N + 1)
    lam = np.log(omega / (1 - omega))
    return float(np.mean(lam <= 0)), float(np.mean(1 - omega))


def n_effectif(M):
    """Nombre de stratégies VRAIMENT différentes (les mutations d'une même idée comptent pour une seule).
    Ratio de participation des valeurs propres de la matrice de corrélation."""
    X = M[:, M.std(axis=0) > 0]
    if X.shape[1] < 2:
        return 1.0
    C = np.nan_to_num(np.corrcoef(X, rowvar=False))
    vp = np.clip(np.linalg.eigvalsh(C), 0, None)
    return float(max(1.0, vp.sum() ** 2 / (vp ** 2).sum()))


def sharpe_degonfle(rs, variance_sharpes, nb_essais):
    """Probabilité que le Sharpe réel soit positif après correction du nombre d'essais et des queues épaisses."""
    rs = np.asarray(rs, dtype=float)
    T = len(rs)
    if T < 10 or rs.std() == 0:
        return 0.0
    sr = rs.mean() / rs.std(ddof=1)
    z = (rs - rs.mean()) / rs.std()
    asym, kurt = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    n = max(nb_essais, 1.0001)
    sr0 = math.sqrt(max(variance_sharpes, 0.0)) * ((1 - EULER) * NORMALE.inv_cdf(1 - 1 / n)
                                                   + EULER * NORMALE.inv_cdf(1 - 1 / (n * math.e)))
    denom = math.sqrt(max(1 - asym * sr + (kurt - 1) / 4 * sr ** 2, 1e-6))
    return float(NORMALE.cdf((sr - sr0) * math.sqrt(T - 1) / denom))


def variance_robuste(valeurs):
    """Variance insensible aux valeurs extrêmes (écart absolu médian) : une stratégie dégénérée
    (par exemple 20 trades tous perdus exactement au stop) ne doit pas fausser la mesure."""
    v = np.asarray([x for x in valeurs if x is not None and np.isfinite(x)], dtype=float)
    if len(v) < 2:
        return 0.0
    mad = np.median(np.abs(v - np.median(v)))
    return float((1.4826 * mad) ** 2)


def sharpe(rs):
    rs = np.asarray(rs, dtype=float)
    return float(rs.mean() / rs.std(ddof=1)) if len(rs) >= 10 and rs.std() > 0 else None
