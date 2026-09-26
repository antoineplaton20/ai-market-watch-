"""Labo de stratégies : indicateurs, règles du moteur, données vérifiées, portes, IA (simulée), Pine, direct papier."""
import json
import os
import time

import numpy as np
import pytest

from labo import donnees as D, ia, moteur as M, pine, registre as R, service as S, strategie as ST
from labo import indicateurs as I


# ------------------------------------------------------------------ indicateurs
def test_indicateurs_de_base():
    x = np.arange(1, 31, dtype=float)
    assert np.isnan(I.sma(x, 5)[3]) and I.sma(x, 5)[4] == 3.0
    assert I.ema(x, 5)[4] == 3.0 and I.ema(x, 5)[5] == pytest.approx(3 + 2 / 6 * 3)
    assert I.rsi(x, 14)[-1] == 100.0                                  # que des hausses
    h, l, c = x + 1, x - 1, x
    assert I.atr(h, l, c, 14)[-1] == pytest.approx(2.0, rel=0.05)
    assert I.plus_haut_precedent(h, 3)[5] == h[2:5].max()
    assert np.isnan(I.plus_haut_precedent(h, 3)[2])


# ------------------------------------------------------------------ moteur : règles d'exécution
SPEC = {"stop_atr": 1.0, "rr": 2.0, "sortie_tendance": False}


def _barres(o, h, l, c):
    n = len(o)
    return {"ts": np.arange(n, dtype=np.int64) * 3_600_000, "o": np.array(o, float), "h": np.array(h, float),
            "l": np.array(l, float), "c": np.array(c, float), "v": np.ones(n)}


def _sig(n, signal_a, atr=1.0):
    e = np.zeros(n, dtype=bool)
    e[signal_a] = True
    return e, np.ones(n, dtype=bool), np.full(n, atr)


def test_achat_a_l_ouverture_suivante_puis_objectif():
    # signal à la clôture de la bougie 0 (100) : stop 99, objectif 102 ; achat à l'ouverture de la bougie 1
    b = _barres([100, 100.2, 101], [100, 100.5, 102.5], [100, 99.8, 100.8], [100, 100.4, 102])
    trades, ev, etat = M.simuler(b, SPEC, frais=0, glissement=0, signaux=_sig(3, 0))
    assert [e["type"] for e in ev] == ["entree", "sortie"] and trades[0]["entree_ts"] == 3_600_000
    assert trades[0]["prix_entree"] == 100.2 and trades[0]["prix_sortie"] == 102.0 and trades[0]["motif"] == "objectif"
    assert etat["position"] is None and etat["dernier_ts"] == 2 * 3_600_000


def test_stop_compte_en_premier_si_doute():
    b = _barres([100, 100, 100], [100, 103, 100], [100, 98, 100], [100, 100, 100])   # stop ET objectif dans la bougie 1
    trades, _, _ = M.simuler(b, SPEC, frais=0, glissement=0, signaux=_sig(3, 0))
    assert trades[0]["motif"] == "stop" and trades[0]["prix_sortie"] == 99.0 and trades[0]["R"] == pytest.approx(-1.0)


def test_trou_de_cotation_sous_le_stop_sortie_a_l_ouverture():
    b = _barres([100, 100, 97, 97], [100, 100.5, 97.5, 97], [100, 99.5, 96, 97], [100, 100, 97, 97])
    trades, _, _ = M.simuler(b, SPEC, frais=0, glissement=0, signaux=_sig(4, 0))
    assert trades[0]["motif"] == "stop (trou)" and trades[0]["prix_sortie"] == 97.0 and trades[0]["R"] < -1


def test_pas_d_achat_si_l_ouverture_est_deja_sous_le_stop():
    b = _barres([100, 98, 98], [100, 98.5, 98], [100, 97.5, 98], [100, 98, 98])
    trades, ev, _ = M.simuler(b, SPEC, frais=0, glissement=0, signaux=_sig(3, 0))
    assert trades == [] and ev == []


def test_frais_et_glissement_diminuent_le_resultat():
    b = _barres([100, 100, 101], [100, 100.5, 102.5], [100, 99.8, 100.8], [100, 100.4, 102])
    sans, _, _ = M.simuler(b, SPEC, frais=0, glissement=0, signaux=_sig(3, 0))
    avec, _, _ = M.simuler(b, SPEC, signaux=_sig(3, 0))
    assert avec[0]["rendement"] < sans[0]["rendement"] and avec[0]["R"] < sans[0]["R"]


def test_reprise_exacte_apres_etat_sauvegarde():
    """Le direct reprend à la dernière bougie traitée : aucun signal rejoué, aucun oublié."""
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    b = _barres(np.r_[c[0], c[:-1]], c + 1.5, c - 1.5, c)
    sig = (rng.random(300) < 0.05, np.ones(300, bool), np.full(300, 1.5))
    tous, _, _ = M.simuler(b, SPEC, signaux=sig)
    partie = {k: v[:150] for k, v in b.items()}
    t1, _, etat = M.simuler(partie, SPEC, signaux=tuple(x[:150] for x in sig))
    t2, _, _ = M.simuler(b, SPEC, signaux=sig, etat=json.loads(json.dumps(etat)))
    assert [t["entree_ts"] for t in t1 + t2] == [t["entree_ts"] for t in tous]


def test_statistiques():
    t = [{"sortie_ts": 1, "r_capital": 0.02, "R": 2}, {"sortie_ts": 2, "r_capital": -0.01, "R": -1}]
    s = M.statistiques(t)
    assert s["trades"] == 2 and s["facteur_profit"] == pytest.approx(2.0) and s["taux_gain"] == 50.0
    assert s["baisse_max_pct"] == pytest.approx(1.0, rel=0.01)
    assert M.statistiques([])["trades"] == 0


# ------------------------------------------------------------------ spécification
def test_specification_bornee_et_controlee():
    spec = ST.normaliser({"nom": "x" * 200, "unite": "3d", "tendance": {"type": "prix_au_dessus_ema", "periode": 5000},
                          "confirmations": [{"type": "rsi_au_dessus", "seuil": -3}, {"type": "adx_fort", "seuil": 99}],
                          "stop_atr": 50, "rr": "abc"})
    assert len(spec["nom"]) == 60 and spec["unite"] == "1h" and spec["tendance"]["periode"] == 300
    assert spec["confirmations"][0]["seuil"] == 40 and spec["confirmations"][1]["seuil"] == 40
    assert spec["stop_atr"] == 6.0 and spec["rr"] == 2.0 and spec["filtre"]["type"] == "aucun"
    for mauvais in ({"confirmations": [{"type": "rsi_sous"}]},                                      # 1 seule
                    {"tendance": {"type": "prix_au_dessus_ema"},
                     "confirmations": [{"type": "rsi_sous"}, {"type": "rsi_sous"}]},                # même type
                    {"tendance": {"type": "__import__('os')"},
                     "confirmations": [{"type": "rsi_sous"}, {"type": "adx_fort"}]}):              # inconnu
        with pytest.raises(ST.SpecInvalide):
            ST.normaliser(mauvais)
    for nom in ST.EXEMPLES:
        assert ST.exemple(nom)["nom"]


# ------------------------------------------------------------------ données vérifiées
def test_donnees_verifiees_et_continues():
    b = D.charger("BTCUSDT", "4h")
    assert len(b["ts"]) > 5000 and np.all(np.diff(b["ts"]) == 4 * 3_600_000)
    assert np.all(b["h"] >= b["l"]) and D.periode()[0] == "2024-01"


def test_archive_alteree_refusee(tmp_path, monkeypatch):
    import shutil
    (tmp_path / "archives").mkdir()
    prov = json.loads((D.RACINE / "provenance.json").read_text())
    prov["files"] = [f for f in prov["files"] if f["symbol"] == "BTCUSDT"][:2]
    (tmp_path / "provenance.json").write_text(json.dumps(prov))
    for f in prov["files"]:
        shutil.copy(D.RACINE / "archives" / f"BTCUSDT-15m-{f['month']}.zip", tmp_path / "archives")
    abime = tmp_path / "archives" / f"BTCUSDT-15m-{prov['files'][1]['month']}.zip"
    abime.write_bytes(abime.read_bytes()[:-10] + b"0123456789")
    monkeypatch.setattr(D, "RACINE", tmp_path)
    D._quinze_minutes.cache_clear()
    D.charger.cache_clear()
    try:
        with pytest.raises(D.DonneesInvalides, match="empreinte"):
            D.charger("BTCUSDT", "1h")
    finally:
        D._quinze_minutes.cache_clear()
        D.charger.cache_clear()


# ------------------------------------------------------------------ portes de validation
def test_evaluation_complete_et_reproductible():
    from labo.validation import evaluer
    spec = ST.exemple("cassure")
    r1, r2 = evaluer(spec), evaluer(spec)
    assert len(r1["portes"]) == 7 and r1["valide"] == all(p["ok"] for p in r1["portes"])
    assert r1["monte_carlo"] == r2["monte_carlo"] and r1["global"] == r2["global"]           # déterministe
    assert set(r1["par_actif"]) == set(D.SYMBOLES) and len(r1["periodes"]) == 5
    json.dumps(r1)                                                                           # envoyable à l'app
    assert r1["stress"]["gain_pct"] < r1["global"]["gain_pct"]                                 # coûts × 2 : pire


def test_une_strategie_perdante_est_rejetee():
    from labo.validation import evaluer
    r = evaluer(ST.exemple("tendance_classique"))
    assert not r["valide"] and not next(p for p in r["portes"] if p["nom"] == "Rentable après frais")["ok"]


# ------------------------------------------------------------------ Pine Script
def test_pine_script_pour_chaque_bloc():
    for t in ST.TYPES["tendance"]:
        conf = [{"type": "rsi_au_dessus"}, {"type": "macd_positif"}]
        for f in ST.TYPES["filtre"]:
            spec = ST.normaliser({"nom": 'Nom "piégé" \\', "tendance": {"type": t}, "confirmations": conf,
                                  "filtre": {"type": f}})
            code = pine.generer(spec)
            assert code.startswith("//@version=6") and "strategy.entry(\"Achat\", strategy.long)" in code
            assert 'strategy("Labo · Nom \\"piégé\\" \\\\"' in code                         # titre échappé
    for c in ST.TYPES["confirmation"]:
        autre = "adx_fort" if c != "adx_fort" else "rsi_sous"
        code = pine.generer(ST.normaliser({"tendance": {"type": "supertrend"},
                                           "confirmations": [{"type": c}, {"type": autre}]}))
        assert "conf1 =" in code and "conf2 =" in code and "commission_value = 0.1" in code


# ------------------------------------------------------------------ IA (Claude simulé)
class _Bloc:
    type = "text"

    def __init__(self, texte):
        self.text = texte


class _FauxClaude:
    def __init__(self, reponse, stop="end_turn", erreurs=()):
        self.appels, self._reponse, self._stop, self._erreurs = [], reponse, stop, list(erreurs)
        self.messages = self

    def create(self, **kw):
        self.appels.append(kw)
        if self._erreurs:
            raise self._erreurs.pop(0)
        return type("R", (), {"stop_reason": self._stop, "content": [_Bloc(self._reponse)]})()


def _reponse_ia(**modif):
    b = lambda t, **k: {"type": t, "periode": 14, "periode2": 0, "seuil": 50, "seuil2": 0, **k}
    r = {"nom": "Idée", "explication": "x", "remarques": "", "unite": "4h", "tendance": b("prix_au_dessus_ema", periode=200),
         "confirmations": [b("rsi_au_dessus"), b("adx_fort", seuil=25)], "filtre": b("aucun"), "stop_atr": 2,
         "rr": 2, "sortie_tendance": True}
    r.update(modif)
    return json.dumps(r)


def test_ia_sortie_structuree_et_validee():
    claude = _FauxClaude(_reponse_ia())
    spec, remarques = ia.generer("suivre la tendance avec un RSI", client=claude)
    assert spec["tendance"]["periode"] == 200 and spec["confirmations"][1]["seuil"] == 25
    kw = claude.appels[0]
    assert kw["model"] == ia.MODELE and kw["extra_body"]["output_config"]["format"]["schema"] == ia.SCHEMA
    assert kw["extra_body"]["fallbacks"] == "default"
    assert ia.SCHEMA["properties"]["tendance"]["properties"]["type"]["enum"] == ST.TYPES["tendance"]


def test_ia_erreurs_claires():
    with pytest.raises(ia.IAIndisponible, match="refusé"):
        ia.generer("une idée de stratégie", client=_FauxClaude(_reponse_ia(), stop="refusal"))
    with pytest.raises(ia.IAIndisponible, match="inutilisable"):
        ia.generer("une idée de stratégie", client=_FauxClaude(_reponse_ia(confirmations=[])))
    with pytest.raises(ia.IAIndisponible, match="10 caractères"):
        ia.generer("court", client=_FauxClaude(_reponse_ia()))


def test_ia_sans_cle(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ia.IAIndisponible, match="ANTHROPIC_API_KEY"):
        ia.generer("une idée de stratégie assez longue")


def test_ia_repli_si_option_refusee():
    BadRequestError = type("BadRequestError", (Exception,), {})
    claude = _FauxClaude(_reponse_ia(), erreurs=[BadRequestError("fallbacks non pris en charge")])
    spec, _ = ia.generer("suivre la tendance avec un RSI", client=claude)
    assert len(claude.appels) == 2 and "fallbacks" not in claude.appels[1]["extra_body"]


# ------------------------------------------------------------------ service
def test_essai_exemple_puis_registre():
    eid = S.lancer(exemple="cassure", synchrone=True)
    e = R.essai(eid)
    assert e["statut"] == "fini" and e["resultat"]["pine"].startswith("//@version=6")
    assert R.compte()["testes"] == 1 and R.essais()[0]["id"] == eid


def test_essai_ia_en_echec_garde_le_message():
    def panne(idee):
        raise ia.IAIndisponible("Claude injoignable (APIConnectionError). Réessaie dans un instant.")
    eid = S.lancer(idee="une idée de stratégie", generer=panne, synchrone=True)
    assert R.essai(eid)["statut"] == "erreur" and "injoignable" in R.essai(eid)["erreur"]


def test_limites_du_service(monkeypatch):
    with pytest.raises(S.LaboRefus):
        S.lancer()
    with pytest.raises(S.LaboRefus):
        S.lancer(exemple="inconnu")
    monkeypatch.setattr(S, "IA_PAR_JOUR", 0)
    with pytest.raises(S.LaboRefus, match="Limite"):
        S.lancer(idee="une idée de stratégie")
    assert S._occupe.acquire(blocking=False)
    try:
        with pytest.raises(S.LaboRefus, match="déjà en cours"):
            S.lancer(exemple="cassure")
    finally:
        S._occupe.release()


def test_suivi_reserve_aux_candidates_sauf_confirmation():
    eid = S.lancer(exemple="tendance_classique", synchrone=True)
    with pytest.raises(S.LaboRefus, match="échoué"):
        S.activer(eid, True)
    assert "lancé" in S.activer(eid, True, forcer=True)["message"]
    assert R.suivis(actifs_seulement=True)[0]["essai_id"] == eid
    S.activer(eid, False)
    assert R.suivis(actifs_seulement=True) == []


class _FauxMarche:
    """Bougies 1 h : 300 fermées + 1 en cours ; `ajouter` simule le temps qui passe."""

    def __init__(self):
        self.t0 = (int(time.time() * 1000) // 3_600_000 - 400) * 3_600_000
        self.c = list(100 + np.cumsum(np.random.default_rng(3).normal(0.05, 1, 301)))

    def fetch_ohlcv(self, sym, timeframe="1h", limit=500):
        return [[self.t0 + i * 3_600_000, c - 0.2, c + 1.5, c - 1.5, c, 10.0] for i, c in enumerate(self.c)][-limit:]


def test_direct_papier_signaux_sans_doublon(monkeypatch):
    spec = ST.normaliser({"nom": "Toujours", "unite": "1h", "tendance": {"type": "prix_au_dessus_ema", "periode": 20},
                          "confirmations": [{"type": "momentum_positif", "periode": 3},
                                            {"type": "rsi_au_dessus", "periode": 14, "seuil": 40}],
                          "stop_atr": 1.0, "rr": 1.0})
    eid = R.nouvel_essai("test", "exemple")
    R.terminer(eid, spec, {"valide": True})
    S.activer(eid, True)
    marche, messages = _FauxMarche(), []
    fin = marche.t0 + 301 * 3_600_000 + 60_000
    S.tour_de_suivi(marche, messages.append, maintenant_ms=fin)
    assert messages == []                                   # départ : maintenant, pas de signaux rétroactifs
    rng = np.random.default_rng(4)
    for k in range(60):                                     # 60 heures de marché
        marche.c.append(marche.c[-1] + rng.normal(0.1, 1))
        S.tour_de_suivi(marche, messages.append, maintenant_ms=fin + (k + 1) * 3_600_000)
    s = R.suivis()[0]
    assert messages and all(m.startswith("📡 [labo]") and "papier" in m for m in messages)
    assert len(s["trades"]) == sum("Sortie" in m for m in messages)
    avant = len(messages)
    S.tour_de_suivi(marche, messages.append, maintenant_ms=fin + 61 * 3_600_000)      # même bougie : rien de neuf
    assert len(messages) == avant
    bilan = S.bilan_suivi(R.suivis()[0])
    assert bilan["stats"]["trades"] == len(s["trades"])


# ------------------------------------------------------------------ routes HTTP de l'application
def test_routes_du_labo(tmp_path, monkeypatch, reglages):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from v17_ops.core import config as C
    from v17_ops.api.app import app
    monkeypatch.setenv("V17_APP_TOKEN", "b" * 32)
    monkeypatch.setattr(C, "settings", reglages())
    c = TestClient(app)
    ok = {"Authorization": "Bearer " + "b" * 32}
    assert c.get("/app/api/labo").status_code == 401
    d = c.get("/app/api/labo", headers=ok).json()
    assert len(d["exemples"]) == 3 and d["compte"]["testes"] == 0
    eid = c.post("/app/api/labo/essai", json={"exemple": "cassure"}, headers=ok).json()["id"]
    for _ in range(100):
        e = c.get(f"/app/api/labo/essai/{eid}", headers=ok).json()
        if e["statut"] != "en_cours":
            break
        time.sleep(0.2)
    assert e["statut"] == "fini" and len(e["resultat"]["portes"]) == 7
    assert c.post("/app/api/labo/essai", json={}, headers=ok).status_code == 409
    assert c.post("/app/api/labo/suivi", json={"id": eid, "actif": True}, headers=ok).status_code in (200, 409)
    assert c.get("/app/api/labo/essai/999", headers=ok).status_code == 404


def test_application_contient_le_labo():
    from v17_ops.api.mobile import DOSSIER_APP
    html = (DOSSIER_APP / "index.html").read_text(encoding="utf-8")
    assert 'data-onglet="labo"' in html and "Tester avec l'IA" in html and "Copier le Pine Script" in html
    assert "innerHTML" not in html
