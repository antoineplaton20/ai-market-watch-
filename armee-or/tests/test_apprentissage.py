"""Apprentissage : observations sans regard vers le futur, examen d'entrée, frais réels, journal. Aucun réseau."""
import time

import numpy as np

from armee_or import apprentissage as A, base, chef, pronostiqueurs as P, strategie as S


def _barres(n=3000, pas=3_600_000, graine=5, t0=1_700_000_000_000):
    c = 4000 + np.cumsum(np.random.default_rng(graine).normal(0, 3, n))
    return {"ts": t0 + np.arange(n, dtype=np.int64) * pas, "o": c, "h": c + 2, "l": c - 2, "c": c, "v": np.ones(n)}


def test_valeur_connue_seulement_apres_son_instant():
    t = np.array([100, 200, 300])
    v = np.array([1.0, 2.0, 3.0])
    assert np.isnan(A._asof(t, v, np.array([99]))[0])
    assert list(A._asof(t, v, np.array([100, 250, 1000]))) == [1.0, 2.0, 3.0]


def test_scores_candidats_alignes_sur_la_cloture():
    b = _barres(100)
    clotures = b["ts"] // 1000 + 3600
    A.enregistrer("veille:acheteurs_pct", [(int(t), float(i)) for i, t in enumerate(clotures)])
    sc = A.scores(b, "1h")["acheteurs_pct"]
    assert list(sc[:5]) == [0.0, 1.0, 2.0, 3.0, 4.0]                   # valeur publiée à la clôture, pas avant


def test_examen_admet_un_vrai_signal_et_rejette_le_bruit():
    b = _barres(3000)
    h = S.UNITES["1h"][0]
    fut = np.r_[b["c"][h:] - b["c"][:-h], np.zeros(h)]
    clotures = b["ts"] // 1000 + 3600
    bruit = np.random.default_rng(9).normal(0, 1, len(fut))
    A.enregistrer("veille:acheteurs_pct", list(zip(clotures, np.sign(fut) + 0.3 * bruit)))   # sait l'avenir
    A.enregistrer("veille:desequilibre_pct", list(zip(clotures, bruit)))                      # pur hasard
    resultats, seuil = A.examiner({"1h": b})
    assert resultats["1h"]["acheteurs_pct"]["admis"] and resultats["1h"]["acheteurs_pct"]["z"] > seuil
    assert not resultats["1h"]["desequilibre_pct"]["admis"]
    assert A.admis("1h") == ["acheteurs_pct"]
    y = P._cible(b["c"], h)
    probas = A.probas_admis(b, "1h", h, y)
    assert list(probas) == ["candidat:acheteurs_pct"] and np.nanmax(probas["candidat:acheteurs_pct"]) > 0.7


def test_candidat_sans_historique_en_attente():
    b = _barres(1500)
    A.enregistrer("veille:prime_pct", [(int(b["ts"][-1] // 1000), 1.0)] * 40)
    A.enregistrer("veille:prime_pct", [(int(b["ts"][-1] // 1000) + i, 1.0) for i in range(40)])
    resultats, _ = A.examiner({"1h": b})
    assert resultats["1h"]["prime_pct"]["admis"] is False and "historique" in resultats["1h"]["prime_pct"]["raison"]


def test_frais_reels_mesures_puis_utilises_progressivement():
    assert A.couts_reels() is None and S.couts(4, 1) > 0.0014               # estimation fixe au départ
    base.ecrire("direct:MT5", {"prix": 4000.0, "bid": 3999.8, "ask": 4000.2, "ts": time.time()})
    base.ecrire("eclair:ecarts", [0.4] * 100)
    for _ in range(30):
        A.enregistrer_execution("entrainement", 1, 4000.2, 4000.3, 0.01)     # 0,1 $ de glissement défavorable
    deals = [{"position_id": 1, "entry": 0, "volume": 0.01, "price": 4000.0, "commission": -0.07, "fee": 0, "swap": 0,
              "time": 0},
             {"position_id": 1, "entry": 1, "volume": 0.01, "price": 4001.0, "commission": -0.07, "fee": 0,
              "swap": -0.4, "time": 4 * 3600}]
    m = A.mesurer_couts(deals)
    assert abs(m["ecart"] - 0.0001) < 1e-9 and m["glissement"] > 0 and m["commission"] > 0 and m["financement_heure"] > 0
    c = A.appliquer_couts()
    assert 0.4 < c["poids_mesure"] < 0.6
    assert c["aller_retour"] < 2 * (0.0005 + 0.0002)                        # plus bas que l'estimation Binance
    assert S.couts(4, 1) == c["aller_retour"] + c["financement_heure"] * 4


def test_archive_de_la_veille(monkeypatch):
    t = time.time()
    base.ecrire("microstructure", {"ts": t, "financement_pct": 0.01, "acheteurs_pct": 70.0, "desequilibre_pct": -12.0})
    base.ecrire("marches", {"ts": t, "contexte": -0.4, "ratio_or_argent": 66.0})
    base.ecrire("tendances", {"ts": t, "alignement": -3})
    assert A.archiver_veille(t) == 6
    assert A.archiver_veille(t + 10) == 6                                   # même quart d'heure : remplacé
    assert A.cles()["veille:acheteurs_pct"] == 1


class _Rep:
    def __init__(self, d):
        self.d = d

    def json(self):
        return self.d

    def raise_for_status(self):
        pass


class _Session:
    def get(self, url, params=None, headers=None, timeout=None):
        if "finance.yahoo" in url:
            n = 400 if params["interval"] == "1d" else 800
            pas = 86400 if params["interval"] == "1d" else 3600
            ts = [1_600_000_000 + i * pas for i in range(n)]
            return _Rep({"chart": {"result": [{"timestamp": ts, "indicators": {"quote": [{"close": [100.0 + i % 7
                                                                                                    for i in range(n)]}]}}]}})
        if "cftc" in url:
            return _Rep([{"report_date_as_yyyy_mm_dd": f"2025-{m:02d}-07T00:00:00.000", "m_money_positions_long_all": "150000",
                          "m_money_positions_short_all": str(10000 * m), "open_interest_all": "400000"} for m in range(1, 13)])
        if "fundingRate" in url:                                             # 10 relevés, puis plus rien
            servi, self.servi = getattr(self, "servi", False), True
            return _Rep([] if servi else [{"fundingTime": params["startTime"] + i * 28_800_000, "fundingRate": "0.0001"}
                                          for i in range(10)])
        raise ConnectionError(url)


def test_rattrapage_de_l_historique_sans_regard_vers_le_futur():
    bilan, erreurs = A.rattraper_historique(_Session(), maintenant=2_000_000_000)
    assert not erreurs and bilan["jour:dollar"] == 400 and bilan["heure:dollar"] == 800 and bilan["financement"] == 10
    t, v = A.serie("yahoo:dollar:1d")
    assert t[0] == 1_600_000_000 + 86400                                    # connue le lendemain de la bougie
    t, _ = A.serie("cot:net_pct")
    assert len(t) == 12 and t[0] % 86400 == 0                               # rapport daté du vendredi suivant
    assert len(A.serie("cot:variation_pct")[0]) == 11


def test_journal_et_bots_d_apprentissage():
    base.ecrire("prono:1h", {"poids": {"retour_moyenne": 0.004, "tendance": 0.0}})
    texte = A.journal()
    assert "Journal d'apprentissage" in texte and "retour_moyenne" in texte and "estimation" in texte
    fake = type("Chef", (), {"pause": False})()
    assert "en attente" in chef.bot_examen(fake)
    assert "24 h" in chef.bot_journal(fake) and "prochain journal" in chef.bot_journal(fake)


def test_croissance_de_la_memoire_relevee_chaque_heure():
    t = 1_900_000_000
    A.releve_memoire(t - 8 * 86400)
    A.releve_memoire(t - 86400)
    A.enregistrer("veille:acheteurs_pct", [(t + i, 1.0) for i in range(25)])
    assert len(A.releve_memoire(t - 86400 + 60)) == 2                     # moins d'une heure : pas de nouveau relevé
    texte = A.texte_memoire(t)
    assert "observations de veille : 25 · +25 · +25" in texte and "pronostics jugés" in texte
    base.ecrire("memoire:releves", [])
    assert "pas encore de relevé" in A.texte_memoire(t)
