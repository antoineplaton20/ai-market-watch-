"""Armée de l'or : données, vigies, analystes, pronostiqueurs (sans triche), levier, papier, chef, indépendance."""
import hashlib
import io
import json
import os
import re
import subprocess
import time
import zipfile

import numpy as np
import pytest

from armee_or import base, chandeliers as C, chef, config, donnees as D, flux, levier as L, marches_lies as M, \
    papier as PA, pronostiqueurs as P, rythme, strategie as S, telegram

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _barres(c, h=None, l=None, o=None, pas=3_600_000, t0=1_700_000_400_000):
    c = np.asarray(c, float)
    o = np.r_[c[0], c[:-1]] if o is None else np.asarray(o, float)
    h = np.maximum(o, c) + 0.5 if h is None else np.asarray(h, float)
    l = np.minimum(o, c) - 0.5 if l is None else np.asarray(l, float)
    t0 -= t0 % pas
    return {"ts": t0 + np.arange(len(c), dtype=np.int64) * pas, "o": o, "h": h, "l": l, "c": c, "v": np.ones(len(c))}


# ------------------------------------------------------------------ données
def _zip(lignes, entete=False):
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("x.csv", ("open_time,open,high,low,close,volume\n" if entete else "")
                   + "\n".join(",".join(map(str, r)) for r in lignes))
    return z.getvalue()


def test_lecture_archive_binance():
    t = 1_735_689_600_000_000                                            # microsecondes (format 2025+)
    brut = _zip([[t, 1, 2, 0.5, 1.5, 10], [t + 900_000_000, 1.5, 2, 1, 1.8, 5]], entete=True)
    lignes = D.lire_archive(brut)
    assert lignes[0][0] == 1_735_689_600_000 and lignes[1][4] == 1.8
    with pytest.raises(D.DonneesInvalides):
        D.lire_archive(_zip([[1, 1, 0.5, 0.8, 1, 1]]))                   # haut < ouverture


def test_regroupement_seulement_bougies_completes():
    lignes = [[i * 900_000, 1 + i, 2 + i, 0.5, 1.5 + i, 1] for i in range(4 * 3 + 2)]   # 3 heures pleines + 2 quarts
    heures = D.regrouper(lignes, 60, 900_000)
    assert len(heures) == 3 and heures[0] == [0, 1, 5, 0.5, 4.5, 4]


def test_empreinte_fausse_refusee(tmp_path):
    d = tmp_path / "b"
    d.mkdir()
    brut = _zip([[1_735_689_600_000, 1, 2, 0.5, 1.5, 10]])
    (d / "PAXGUSDT-15m-2025-01.zip").write_bytes(brut)
    (d / "SHA256SUMS").write_text(f"{hashlib.sha256(b'autre').hexdigest()}  PAXGUSDT-15m-2025-01.zip\n")
    with pytest.raises(D.DonneesInvalides, match="empreinte"):
        D.importer_binance(d)


def test_historique_livre_complet(historique):
    inv = {(r["source"], r["tf"]): r for r in D.inventaire()}
    assert inv[("OR", "1M")]["n"] > 2300 and inv[("GC", "1d")]["n"] > 6000
    assert inv[("PAXGUSDT", "1h")]["n"] > 50000 and inv[("XAUUSDT", "15m")]["n"] > 20000
    b = D.charger("PAXGUSDT", "1h")
    assert np.all(np.diff(b["ts"]) >= 3_600_000)


# ------------------------------------------------------------------ vigie du cours
def test_message_websocket_et_retard():
    msg = json.dumps({"E": 1_000_500, "k": {"t": 960_000, "o": "4400.1", "h": "4401", "l": "4399", "c": "4400.5",
                                            "v": "12", "x": True}})
    bougie, fermee, prix, retard = flux.lire_message(msg, recu_ms=1_000_620)
    assert fermee and prix == 4400.5 and retard == 120 and bougie[0] == 960_000
    assert flux.lire_message("pas du json") is None and flux.lire_message('{"e": "autre"}') is None


class _Session:
    def __init__(self, reponses):
        self.reponses, self.appels = list(reponses), []

    def get(self, url, params=None, **kw):
        self.appels.append(params)
        rep = self.reponses.pop(0) if self.reponses else []
        return type("R", (), {"json": lambda s: rep, "raise_for_status": lambda s: None})()


def test_rattrapage_des_minutes_manquantes():
    maintenant = 1_700_000_000_000 - 1_700_000_000_000 % 60_000
    D.inserer("XAUUSDT", "1m", [[maintenant - 10 * 60_000, 1, 2, 0.5, 1, 1]])
    rep = [[maintenant - k * 60_000, "1", "2", "0.5", "1.5", "3", 0, 0, 0, 0, 0, 0] for k in range(9, -1, -1)]
    s = _Session([rep])
    assert flux.rattraper("XAUUSDT", session=s, maintenant_ms=maintenant) == 9     # la minute en cours (k=0) est exclue
    assert s.appels[0]["startTime"] == maintenant - 9 * 60_000


def test_prix_direct_priorites_et_fraicheur():
    assert flux.prix_direct() is None
    base.ecrire("direct:PAXGUSDT", {"prix": 4400, "ts": time.time(), "retard_ms": 50, "source": "p"})
    assert flux.prix_direct()["cle"] == "PAXGUSDT"
    base.ecrire("direct:XAUUSDT", {"prix": 4401, "ts": time.time(), "retard_ms": 30, "source": "x"})
    assert flux.prix_direct()["cle"] == "XAUUSDT"
    base.ecrire("direct:XAUUSDT", {"prix": 4401, "ts": time.time() - 600, "retard_ms": 30, "source": "x"})
    assert flux.prix_direct()["cle"] == "PAXGUSDT"                                   # périmé : on passe au suivant


# ------------------------------------------------------------------ analystes
def test_avalement_haussier_detecte():
    b = _barres([100, 101, 102, 101, 99.5, 101.5], o=[100, 100, 101, 102, 101, 99])
    m = C.detecter(b)
    assert m["avalement_haussier"][1][-1] and not m["avalement_baissier"][1][-1]


def test_statistiques_motifs_sur_l_or(historique):
    st = C.statistiques(D.charger("PAXGUSDT", "4h"), 6)
    assert set(st) == set(C.detecter(_barres(np.arange(50.0) + 100)))
    assert all(v["n"] >= 0 for v in st.values()) and any(abs(v["z"]) > 2 for v in st.values())


def test_rythme():
    b = _barres(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 1200)))
    e = rythme.etat(b)
    assert e["regime"] in ("calme", "normal", "volatilité forte", "volatilité extrême") and e["seance"]
    assert rythme.seance(0) == "Asie (Tokyo, Shanghai)" and len(rythme.profil_horaire(b)) == 24


def test_marches_lies_contexte():
    ts = np.arange(80) * 86400
    montee, baisse = np.linspace(100, 130, 80), np.linspace(130, 100, 80)
    r = M.analyser({"GC=F": (ts, montee), "DX-Y.NYB": (ts, baisse), "^TNX": (ts, baisse), "SI=F": (ts, montee)})
    assert r["contexte"] > 0.3                                     # dollar et taux en baisse, argent en hausse
    assert next(x for x in r["marches"] if x["ticker"] == "GC=F")["correlation_60j"] is None


# ------------------------------------------------------------------ pronostiqueurs : aucune triche avec le futur
def test_calibration_ne_voit_pas_le_futur():
    rng = np.random.default_rng(7)
    c = 100 + np.cumsum(rng.normal(0, 1, 4000))
    b = _barres(c)
    y = P._cible(b["c"], 4)
    s = P.score_retour_moyenne(b)
    p1 = P.calibrer(s, y)
    t = 3000
    c2 = c.copy()
    c2[t + 1:] = c2[t + 1:] + np.cumsum(rng.normal(5, 3, len(c) - t - 1))      # futur complètement changé
    b2 = _barres(c2)
    p2 = P.calibrer(P.score_retour_moyenne(b2), P._cible(b2["c"], 4))
    np.testing.assert_array_equal(np.nan_to_num(p1[:t + 1], nan=-1), np.nan_to_num(p2[:t + 1], nan=-1))


def test_scores_ne_voient_pas_le_futur():
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 1, 1500))
    b = _barres(c)
    for nom, (_, fn) in P.PRONOSTIQUEURS.items():
        complet = fn(b)
        tronque = fn({k: v[:1200] for k, v in b.items()})
        np.testing.assert_allclose(np.nan_to_num(complet[:1200], nan=-9), np.nan_to_num(tronque, nan=-9),
                                   err_msg=nom)


def test_consensus_sans_competence_egale_le_naif():
    rng = np.random.default_rng(5)
    y = (rng.random(3000) > 0.5).astype(float)
    base_ = np.full(3000, 0.5)
    hasard = {"a": rng.random(3000), "b": rng.random(3000)}                 # pronostics inutiles
    pc, poids = P.consensus(hasard, base_, y)
    assert np.allclose(pc, base_) and all(w == 0 for _, d in poids for w in d.values())


# ------------------------------------------------------------------ levier
def test_prix_de_liquidation():
    assert L.prix_liquidation(100, 1, 1000, 20000) == pytest.approx(100 * (1 - (0.05 - 0.005)))
    assert L.prix_liquidation(100, -1, 1000, 20000) == pytest.approx(100 * (1 + 0.045))
    assert L.taille("x20 (max. UE)", 1000, 100, 99)[0] == 20000
    notionnel, lev = L.taille("pro 1 % risqué", 1000, 100, 99)                 # 1 % de risque, stop à 1 %
    assert notionnel == pytest.approx(1000) and lev == pytest.approx(1)
    assert L.taille("pro 1 % risqué", 1000, 100, 99.99)[1] == L.LEVIER_MAX_UE    # plafonné à 20


def test_kelly_et_fiche():
    assert L.kelly(0.5, 1) == 0 and L.kelly(0.6, 1) == pytest.approx(0.2)
    f = L.fiche(1000, 4400, 30, 1, 0.55, "x50 (max. Binance)", stop_atr=3)
    assert f["liquidation_avant_stop"] and f["distance_liquidation_pct"] < f["distance_stop_pct"]
    f1 = L.fiche(1000, 4400, 30, 1, 0.55, "x1", stop_atr=3)
    assert not f1["liquidation_avant_stop"] and f1["perte_si_stop_pct_capital"] < 3


# ------------------------------------------------------------------ comptes papier
def _pas_simple(c, o=None, h=None, l=None, profil="x1", sens=1, regles=None, capital=1000):
    b = _barres(c, h=h, l=l, o=o)
    atr = np.full(len(c), 1.0)
    compte, trades = PA.compte_neuf(capital), []
    for i in range(1, len(c)):
        PA.pas(compte, profil, i, b, atr, sens if i == 1 else 0, trades, regles or {"stop_atr": 2, "rr": None, "duree": 4})
    return compte, trades


def test_papier_sortie_a_l_horizon_avec_frais():
    compte, trades = _pas_simple([100, 100, 101, 102, 103, 104, 104])
    assert trades[0]["motif"] == "durée" and trades[0]["pnl"] > 0 and compte["frais"] > 0 and compte["financement"] > 0


def test_papier_liquidation_x50_sur_petit_trou():
    # achat à 100 ; trou d'ouverture à 97 : sous la liquidation x50 (≈ 98,5) -> compte vidé, jamais négatif
    compte, trades = _pas_simple([100, 100, 97, 97], o=[100, 100, 97, 97], h=[100, 100.2, 97.5, 97],
                                 l=[100, 99.8, 96.5, 97], profil="x50 (max. Binance)")
    assert trades[0]["motif"] == "liquidation" and compte["capital"] == 0 and compte["ruine"] and compte["liquidations"] == 1
    compte1, trades1 = _pas_simple([100, 100, 97, 97], o=[100, 100, 97, 97], h=[100, 100.2, 97.5, 97],
                                   l=[100, 99.8, 96.5, 97], profil="x1")
    assert trades1[0]["motif"] == "stop" and 960 < compte1["capital"] < 980           # même trou à x1 : -3 %


def test_papier_vente_a_decouvert_et_stop():
    compte, trades = _pas_simple([100, 100, 103, 103], o=[100, 100, 101, 103], h=[100, 100.5, 103.5, 103],
                                 l=[100, 99.5, 100.8, 103], sens=-1)
    assert trades[0]["sens"] == -1 and trades[0]["motif"] == "stop" and compte["capital"] < 1000


# ------------------------------------------------------------------ règle de décision du chef
def test_pas_d_action_si_avantage_inferieur_aux_couts():
    b = _barres(100 + np.cumsum(np.random.default_rng(2).normal(0, 0.1, 1500)))
    assert not S.decisions(np.full(1500, 0.52), b, "1h").any()           # petit avantage, gros coûts relatifs
    b = _barres(1000 + np.cumsum(np.random.default_rng(2).normal(0, 5, 1500)))    # marché qui bouge assez
    dec = S.decisions(np.full(1500, 0.99), b, "1d")
    assert (dec[600:] == 1).any()                                         # avantage énorme : on agit
    assert (S.decisions(np.full(1500, 0.01), b, "1d")[600:] <= 0).all()


# ------------------------------------------------------------------ chef d'orchestre
def test_un_bot_en_panne_n_arrete_pas_les_autres():
    passes = []

    def panne(chef_):
        raise RuntimeError("source HS")
    b1, b2 = chef.Bot("A", "x", 10, panne), chef.Bot("B", "x", 10, lambda c: passes.append(1) or "ok")
    fake = type("Chef", (), {"bots": [b1, b2], "pause": False, "tour": chef.Chef.tour})()
    fake.tour()
    assert b1.echecs == 1 and b1.ko == 1 and passes == [1] and b1.prochaine > time.time() + 10     # attente allongée
    with base.connexion() as c:
        assert c.execute("SELECT COUNT(*) FROM rapports WHERE bot='A' AND ok=0").fetchone()[0] == 1   # compte rendu
    assert base.lire("chef")["bots"][0]["nom"] == "A"


def test_tour_complet_sur_l_historique(historique, monkeypatch):
    monkeypatch.setattr(chef, "bot_marches", lambda c: "réseau désactivé en test")
    monkeypatch.setattr(chef.Bot, "__init__", chef.Bot.__init__)
    ch = chef.Chef()
    ch.bots = [b for b in ch.bots if b.nom not in ("Vigie des marchés liés",)]
    ch.bots[1].fonction = lambda c: "archiviste sans réseau"
    ch.tour()
    assert all(b.echecs == 0 for b in ch.bots), [b.etat() for b in ch.bots if b.echecs]
    for tf in ("1h", "4h", "1d"):
        assert base.lire(f"prono:{tf}")["p"] > 0 and base.lire(f"papier:{tf}")["comptes"]
    assert "Rapport de l'armée de l'or" in chef.rapport(ch) and "aucun ordre" in chef.rapport(ch)


def test_papier_n_utilise_que_les_decisions_enregistrees(historique):
    b = D.charger("PAXGUSDT", "1h", limite=2000)
    dec = np.ones(len(b["ts"]), dtype=int)                               # « acheter » partout...
    partie = {k: v[:-10] for k, v in b.items()}
    chef._papier("1h", partie, dec[:-10])                                 # départ
    chef._papier("1h", b, dec)                                            # ... mais aucune décision enregistrée
    etat = base.lire("papier:1h")
    assert etat["dernier_ts"] == int(b["ts"][-1])
    assert all(c["trades"] == 0 and c["position"] is None for c in etat["comptes"].values())


def test_commandes_pause_reprise_par_fichier():
    ch = type("Chef", (), {"pause": False})()
    (config.RACINE / "runtime" / "commandes.txt").write_text("pause\n")
    chef.bot_commandes(ch)
    assert ch.pause and base.lire("pause") is True
    (config.RACINE / "runtime" / "commandes.txt").write_text("reprise\n")
    chef.bot_commandes(ch)
    assert not ch.pause


def test_bilan_historique(historique):
    bh = chef.bilan_historique()
    for tf in ("1h", "4h", "1d"):
        u = bh["unites"][tf]
        assert u["garder_or_x"] > 1.5 and set(u["comptes"]) == set(L.PROFILS)
        assert all(c["capital"] >= 0 for c in u["comptes"].values())
    assert "ruiné" in chef.rapport_bilan()


# ------------------------------------------------------------------ Telegram et indépendance
def test_telegram_sans_jeton_ne_plante_pas():
    assert telegram.envoyer("test") is False and telegram.commandes() == []
    assert telegram.alerte_rare("x", "y") is False and telegram.alerte_rare("x", "y") is False


def test_independance_des_autres_bots():
    for fichier in os.listdir(os.path.join(RACINE, "armee_or")):
        if fichier.endswith(".py"):
            texte = open(os.path.join(RACINE, "armee_or", fichier), encoding="utf-8").read()
            assert "equipe-bots" not in texte and "v17_ops" not in texte and not re.search(r"(?m)^import config", texte), fichier
    inst = open(os.path.join(RACINE, "installer_or.sh"), encoding="utf-8").read()
    assert "/home/bots/armee-or" in inst and "armee-or-flux" in inst and "armee-or-chef" in inst
    assert "rm -rf /home/bots/equipe-bots" not in inst and "systemctl stop equipe" not in inst
    for script in ("installer_or.sh", "or"):
        assert subprocess.run(["bash", "-n", os.path.join(RACINE, script)]).returncode == 0
